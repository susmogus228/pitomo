"""Browser storefront contract, payment state machine and additive seed regressions."""
from tests.helpers import with_consent
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
import pytest
from sqlalchemy import select, text

from app.core.config import Settings
from app.db.models import BrowserSessionORM, ProductVariantORM
from app.db.pitomo_seed import seed_pitomo_catalog
from app.db.session import Database
from app.main import create_test_app

ORIGIN = 'http://testserver'
DETAILS = {'contact_name': 'Тестовый покупатель', 'phone': '+7 700 123 45 67',
           'delivery_method': 'pickup', 'payment_method': 'demo'}


@pytest.fixture
def client():
    with TestClient(create_test_app()) as client:
        yield client


def register(client, email='browser@example.com'):
    data = {'email': email, 'password': 'StrongPass123', 'first_name': 'Покупатель'}
    assert client.post('/api/v1/auth/register', json=with_consent(client, data)).status_code == 201
    return {'email': email, 'password': data['password']}


def login(client, credentials=None):
    credentials = credentials or register(client)
    response = client.post('/api/v1/auth/browser/login', json=credentials, headers={'Origin': ORIGIN})
    assert response.status_code == 200, response.text
    return {'Origin': ORIGIN, 'X-CSRF-Token': client.cookies['pitomo_csrf']}


def checkout(client, headers, details=None, key='pitomo-order'):
    response = client.post('/api/v1/cart/items', json={'variant_id': 20, 'quantity': 2}, headers=headers)
    assert response.status_code in {200, 201}, response.text
    result = client.post('/api/v1/orders', json=details or DETAILS,
                         headers={**headers, 'Idempotency-Key': key})
    assert result.status_code == 201, result.text
    return result.json()


def test_session_cookies_and_server_revocation(client):
    credentials = register(client)
    response = client.post('/api/v1/auth/browser/login', json=credentials, headers={'Origin': ORIGIN})
    assert response.status_code == 200
    cookies = response.headers.get_list('set-cookie')
    assert any('pitomo_session=' in cookie and 'HttpOnly' in cookie and 'SameSite=lax' in cookie for cookie in cookies)
    assert not any('pitomo_csrf=' in cookie and 'HttpOnly' in cookie for cookie in cookies)
    assert 'access_token' not in response.json()
    token = client.cookies['pitomo_session']
    assert client.get('/api/v1/auth/session').json()['email'] == credentials['email']
    headers = {'Origin': ORIGIN, 'X-CSRF-Token': client.cookies['pitomo_csrf']}
    assert client.post('/api/v1/auth/logout', headers=headers).status_code == 204
    assert client.get('/api/v1/auth/session').status_code == 401
    client.cookies.set('pitomo_session', token)
    assert client.get('/api/v1/auth/session').status_code == 401


@pytest.mark.parametrize('origin', [None, 'https://evil.example', 'null', ORIGIN + '.evil.example'])
def test_login_rejects_missing_or_foreign_origin(client, origin):
    data = register(client)
    headers = {'Origin': origin} if origin else {}
    assert client.post('/api/v1/auth/browser/login', json=data, headers=headers).status_code == 403
    assert client.get('/api/v1/auth/session').status_code == 401


@pytest.mark.parametrize('kind', ['missing', 'wrong', 'origin', 'forged-cookie'])
def test_cookie_auth_rejects_csrf_before_mutation(client, kind):
    headers = login(client)
    if kind == 'missing':
        headers.pop('X-CSRF-Token')
    if kind == 'wrong':
        headers['X-CSRF-Token'] = '0' * 64
    if kind == 'origin':
        headers['Origin'] = 'https://evil.example'
    if kind == 'forged-cookie':
        original_session = client.cookies['pitomo_session']
        client.cookies.clear()
        client.cookies.set('pitomo_session', original_session)
        client.cookies.set('pitomo_csrf', '0' * 64)
        headers['X-CSRF-Token'] = '0' * 64
    assert client.put('/api/v1/favorites/2', headers=headers).status_code in {401, 403}


def test_production_cookies_require_https_and_are_secure():
    settings = Settings.for_testing(environment='production', demo_payments=False,
        privacy_operator_name='Synthetic Operator', privacy_operator_id='123456789012',
        privacy_contact_email='privacy@example.test', privacy_storage_country='KZ', privacy_documents_approved=True)
    with TestClient(create_test_app(settings=settings), base_url='https://testserver') as secure:
        credentials = register(secure)
        assert secure.post('/api/v1/auth/browser/login', json=credentials,
                           headers={'Origin': 'http://testserver'}).status_code == 403
        result = secure.post('/api/v1/auth/browser/login', json=credentials,
                             headers={'Origin': 'https://testserver'})
        assert result.status_code == 200
        assert all('Secure' in cookie for cookie in result.headers.get_list('set-cookie'))
        assert secure.get('/api/v1/auth/session').status_code == 200


def test_browser_login_shares_legacy_auth_rate_limit():
    settings = Settings.for_testing(login_max_attempts=1)
    with TestClient(create_test_app(settings=settings)) as limited:
        credentials = register(limited)
        assert limited.post('/api/v1/auth/browser/login', json=credentials, headers={'Origin': ORIGIN}).status_code == 200
        assert limited.post('/api/v1/auth/login', json=credentials).status_code == 429


def test_csrf_cannot_be_reused_across_sessions_and_expired_session_fails(client):
    credentials = register(client)
    first = login(client, credentials)
    login(client, credentials)
    assert client.put('/api/v1/favorites/2', headers=first).status_code == 403
    with client.app.state.database.session_factory.begin() as session:
        for row in session.scalars(select(BrowserSessionORM)):
            row.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    assert client.get('/api/v1/auth/session').status_code == 401


def test_favorites_idempotent_persistent_and_user_owned(client):
    headers = login(client)
    for _ in range(2):
        assert client.put('/api/v1/favorites/2', headers=headers).status_code == 204
    assert [p['id'] for p in client.get('/api/v1/favorites').json()] == [2]
    assert client.put('/api/v1/favorites/2147483647', headers=headers).status_code == 404
    first_cookies = dict(client.cookies)
    client.cookies.clear()
    other = login(client, register(client, 'second@example.com'))
    assert client.get('/api/v1/favorites').json() == []
    assert client.delete('/api/v1/favorites/2', headers=other).status_code == 204
    client.cookies.clear()
    client.cookies.update(first_cookies)
    assert len(client.get('/api/v1/favorites').json()) == 1
    for _ in range(2):
        assert client.delete('/api/v1/favorites/2', headers=headers).status_code == 204


def test_checkout_demo_failure_retry_success_and_paid_immutability(client):
    headers = login(client)
    order = checkout(client, headers)
    assert (order['status'], order['payment_status'], order['is_demo']) == ('created', 'pending', True)
    path = f"/api/v1/orders/{order['id']}"
    assert client.post(path + '/demo-payment', json={'outcome': 'failure'}, headers=headers).json()['payment_status'] == 'failed'
    paid = client.post(path + '/demo-payment', json={'outcome': 'success'}, headers=headers).json()
    assert paid['payment_status'] == 'demo_paid'
    assert client.post(path + '/demo-payment', json={'outcome': 'failure'}, headers=headers).json() == paid
    assert client.post(path + '/cancel', headers=headers).status_code == 409
    assert client.get(path).json() == paid
    assert client.post(path + '/demo-payment', json={'outcome': 'success', 'card_number': 'not-accepted'}, headers=headers).status_code == 422


@pytest.mark.parametrize('method', ['demo', 'cod'])
def test_cancel_restocks_once_and_prevents_payment(client, method):
    headers = login(client)
    with client.app.state.database.session_factory() as session:
        before = session.get(ProductVariantORM, 20).stock
    order = checkout(client, headers, {**DETAILS, 'payment_method': method})
    path = f"/api/v1/orders/{order['id']}"
    cancelled = client.post(path + '/cancel', headers=headers)
    assert cancelled.status_code == 200
    assert cancelled.json()['status'] == cancelled.json()['payment_status'] == 'cancelled'
    assert client.post(path + '/cancel', headers=headers).json() == cancelled.json()
    assert client.post(path + '/demo-payment', json={'outcome': 'success'}, headers=headers).status_code == 409
    with client.app.state.database.session_factory() as session:
        assert session.get(ProductVariantORM, 20).stock == before


def test_checkout_replay_and_payload_conflict_do_not_duplicate(client):
    headers = login(client)
    order = checkout(client, headers)
    retry_headers = {**headers, 'Idempotency-Key': 'pitomo-order'}
    assert client.post('/api/v1/orders', json=DETAILS, headers=retry_headers).json() == order
    assert client.post('/api/v1/orders', json={**DETAILS, 'payment_method': 'cod'}, headers=retry_headers).status_code == 409
    assert len(client.get('/api/v1/orders').json()) == 1


def test_checkout_validation_and_payment_owner(client):
    headers = login(client)
    assert client.post('/api/v1/orders', json={**DETAILS, 'delivery_method': 'delivery'}, headers=headers).status_code == 422
    assert client.post('/api/v1/orders', json={**DETAILS, 'total': 1}, headers=headers).status_code == 422
    order = checkout(client, headers, {**DETAILS, 'delivery_method': 'delivery', 'address': 'Тестовый адрес, 1'})
    assert order['address'] == 'Тестовый адрес, 1'
    client.cookies.clear()
    other = login(client, register(client, 'other@example.com'))
    path = f"/api/v1/orders/{order['id']}"
    assert client.get(path).status_code == 404
    assert client.post(path + '/cancel', headers=other).status_code == 404
    assert client.post(path + '/demo-payment', json={'outcome': 'success'}, headers=other).status_code == 404


def test_demo_configuration_and_production_fail_closed(client):
    headers = login(client)
    order = checkout(client, headers)
    client.app.state.settings = replace(client.app.state.settings, demo_payments=False)
    assert client.post(f"/api/v1/orders/{order['id']}/demo-payment", json={'outcome': 'success'}, headers=headers).status_code == 409
    assert client.post('/api/v1/orders', json=DETAILS, headers=headers).status_code == 409
    settings = Settings.for_testing(environment='production', demo_payments=False)
    with TestClient(create_test_app(settings=settings)) as production:
        assert production.get('/api/v1/storefront/config').json() == {'demo_payments_enabled': False, 'currency': 'KZT'}
    with pytest.raises(ValueError, match='Demo payments'):
        replace(settings, demo_payments=True).validate()


def test_seed_preserves_stock_and_supports_all_eight_filters(client):
    with client.app.state.database.session_factory.begin() as session:
        assert seed_pitomo_catalog(session) == 48
        row = session.scalar(select(ProductVariantORM).where(ProductVariantORM.sku == 'PITOMO-DEMO-CAT-01'))
        row.stock = 3
    with client.app.state.database.session_factory.begin() as session:
        assert seed_pitomo_catalog(session) == 0
        assert session.scalar(select(ProductVariantORM.stock).where(ProductVariantORM.sku == 'PITOMO-DEMO-CAT-01')) == 3
    from app.catalog.types import PET_TYPES
    for species in PET_TYPES:
        response = client.get('/api/v1/products', params={'pet_type': species})
        assert response.status_code == 200
        assert response.json()['total'] >= 3
        assert all(item['pet_type'] == species for item in response.json()['items'])
    assert client.get('/api/v1/products', params={'pet_type': 'dragon'}).status_code == 422
    seeded = client.get('/api/v1/products', params={'q': 'PITOMO-DEMO-CAT-01'}).json()['items'][0]
    assert seeded['image_url'] == '/media/products/v2/cat-food.webp'


def test_migration_preserves_legacy_sqlite_rows(tmp_path):
    db = Database(f'sqlite+pysqlite:///{tmp_path / "pitomo-migration.db"}')
    config = Config(str(Path(__file__).resolve().parents[1] / 'alembic.ini'))
    config.attributes['database_url'] = db.url
    command.upgrade(config, '0004_v071')
    with db.engine.begin() as connection:
        connection.execute(text("INSERT INTO users(id,email,password_hash,first_name,is_active,role) VALUES(1,'keep@example.com','keep','Keep',1,'customer')"))
        connection.execute(text("INSERT INTO orders(id,user_id,status,created_at) VALUES(1,1,'created',CURRENT_TIMESTAMP)"))
        connection.execute(text("INSERT INTO order_items(order_id,product_id,product_name,variant_id,sku,variant_label,unit_price,currency,quantity) VALUES(1,2,'Historical',20,'OLD','Old',9.99,'KZT',1)"))
    command.upgrade(config, 'head')
    command.check(config)
    with db.engine.connect() as connection:
        assert connection.scalar(text('SELECT password_hash FROM users')) == 'keep'
        assert connection.scalar(text('SELECT product_name FROM order_items')) == 'Historical'
        assert connection.scalar(text('SELECT payment_status FROM orders')) == 'cod_pending'
        assert connection.scalar(text('SELECT COUNT(*) FROM products')) == 20
        assert connection.exec_driver_sql('PRAGMA foreign_key_check').first() is None
