from tests.helpers import with_consent
from pathlib import Path

from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine, inspect, select, text
from sqlalchemy.dialects import postgresql

from app.core.config import DEFAULT_POSTGRES_URL
from app.main import create_test_app as create_app
from tests.helpers import admin_headers, promote_user_to_admin


def _migrate(url: str, monkeypatch):
    monkeypatch.setenv('PETSHOP_DATABASE_URL', url)
    config = Config(str(Path(__file__).resolve().parents[1] / 'alembic.ini'))
    command.upgrade(config, 'head')


def test_default_runtime_database_is_postgresql():
    assert DEFAULT_POSTGRES_URL.startswith('postgresql+psycopg://')


def test_alembic_creates_full_schema_and_demo_catalog(tmp_path, monkeypatch):
    db_file = tmp_path / 'migration.db'
    url = f'sqlite+pysqlite:///{db_file}'
    _migrate(url, monkeypatch)

    engine = create_engine(url)
    tables = set(inspect(engine).get_table_names())
    assert {'users', 'products', 'product_variants', 'carts', 'cart_items', 'orders', 'order_items'} <= tables
    with engine.connect() as connection:
        assert connection.execute(text('SELECT COUNT(*) FROM products')).scalar_one() == 20
        assert connection.execute(text('SELECT COUNT(*) FROM product_variants')).scalar_one() == 25


def test_data_persists_across_application_instances(tmp_path, monkeypatch):
    db_file = tmp_path / 'persistent.db'
    url = f'sqlite+pysqlite:///{db_file}'
    _migrate(url, monkeypatch)

    first = TestClient(create_app(url))
    registered = first.post('/api/v1/auth/register', json=with_consent(first, {
        'email': 'persist@example.com',
        'password': 'StrongPass123',
        'first_name': 'Persist',
        'last_name': 'User',
    }))
    assert registered.status_code == 201
    promote_user_to_admin(first, 'persist@example.com')
    login = first.post('/api/v1/auth/login', json={'email': 'persist@example.com', 'password': 'StrongPass123'})
    admin = {'Authorization': f"Bearer {login.json()['access_token']}"}
    assert first.patch('/api/v1/products/2', headers=admin, json={'name': 'Persisted product'}).status_code == 200

    second = TestClient(create_app(url))
    login = second.post('/api/v1/auth/login', json={
        'email': 'persist@example.com',
        'password': 'StrongPass123',
    })
    assert login.status_code == 200
    assert second.get('/api/v1/products/2').json()['name'] == 'Persisted product'


def test_file_database_health_reports_sqlite(tmp_path, monkeypatch):
    db_file = tmp_path / 'health.db'
    url = f'sqlite+pysqlite:///{db_file}'
    _migrate(url, monkeypatch)
    client = TestClient(create_app(url))
    assert client.get('/health').json() == {'status': 'ok', 'storage': 'sqlite'}


def test_openapi_reports_v060():
    client = TestClient(create_app())
    schema = client.get('/openapi.json').json()
    assert schema['info']['version'] == '0.14.0'
    assert '/api/v1/orders' in schema['paths']


def test_sql_repository_allocates_distinct_ids_for_multi_variant_create():
    client = TestClient(create_app())
    response = client.post('/api/v1/products', headers=admin_headers(client, 'v06-admin@example.com'), json={
        'name': 'Multi variant product',
        'pet_type': 'cat',
        'brand': 'DBTest',
        'category': 'food',
        'composition': 'test',
        'variants': [
            {'sku': 'MULTI-DB-S', 'label': 'S', 'price': '100.00', 'stock': 2},
            {'sku': 'MULTI-DB-L', 'label': 'L', 'price': '200.00', 'stock': 3},
        ],
    })
    assert response.status_code == 201, response.text
    ids = [item['id'] for item in response.json()['variants']]
    assert len(ids) == 2
    assert len(set(ids)) == 2


def test_postgresql_checkout_query_uses_for_update():
    from app.db.models import ProductVariantORM

    statement = select(ProductVariantORM).where(ProductVariantORM.id == 20).with_for_update()
    sql = str(statement.compile(dialect=postgresql.dialect()))
    assert 'FOR UPDATE' in sql


def test_request_transaction_rolls_back_partial_checkout(monkeypatch):
    from app.orders.repository import SQLAlchemyOrderRepository

    client = TestClient(create_app())
    payload = {
        'email': 'rollback-v06@example.com',
        'password': 'StrongPass123',
        'first_name': 'Rollback',
        'last_name': 'Test',
    }
    assert client.post('/api/v1/auth/register', json=with_consent(client, payload)).status_code == 201
    token = client.post('/api/v1/auth/login', json={
        'email': payload['email'],
        'password': payload['password'],
    }).json()['access_token']
    headers = {'Authorization': f'Bearer {token}'}
    assert client.post('/api/v1/cart/items', headers=headers, json={
        'variant_id': 20,
        'quantity': 2,
    }).status_code == 200

    original_add = SQLAlchemyOrderRepository.add

    def explode_after_stock_flush(self, order, **kwargs):
        raise RuntimeError('forced database failure')

    monkeypatch.setattr(SQLAlchemyOrderRepository, 'add', explode_after_stock_flush)
    with pytest.raises(RuntimeError, match='forced database failure'):
        client.post('/api/v1/orders', headers=headers)
    monkeypatch.setattr(SQLAlchemyOrderRepository, 'add', original_add)

    product = client.get('/api/v1/products/2').json()
    stock = next(v['stock'] for v in product['variants'] if v['id'] == 20)
    assert stock == 5
    assert client.get('/api/v1/cart', headers=headers).json()['total_items'] == 2
    assert client.get('/api/v1/orders', headers=headers).json() == []
