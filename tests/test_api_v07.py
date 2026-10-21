from tests.helpers import with_consent
from pathlib import Path
import os
import subprocess
import sys

from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect, text

from app.main import create_test_app as create_app
from tests.helpers import admin_headers


ROOT = Path(__file__).resolve().parents[1]


def register(client, email='customer-v07@example.com', password='StrongPass123'):
    response = client.post('/api/v1/auth/register', json=with_consent(client, {
        'email': email,
        'password': password,
        'first_name': 'Role',
        'last_name': 'Test',
    }))
    assert response.status_code == 201, response.text
    return response.json()


def login_headers(client, email='customer-v07@example.com', password='StrongPass123'):
    response = client.post('/api/v1/auth/login', json={'email': email, 'password': password})
    assert response.status_code == 200, response.text
    return {'Authorization': f"Bearer {response.json()['access_token']}"}


def test_registration_always_creates_customer_and_cannot_request_admin():
    client = TestClient(create_app())
    user = register(client)
    assert user['role'] == 'customer'

    response = client.post('/api/v1/auth/register', json=with_consent(client, {
        'email': 'try-admin@example.com',
        'password': 'StrongPass123',
        'first_name': 'Try',
        'last_name': 'Admin',
        'role': 'admin',
    }))
    assert response.status_code == 422


def test_admin_routes_require_authentication_and_role():
    client = TestClient(create_app())
    assert client.get('/api/v1/admin/users').status_code == 401

    register(client)
    customer = login_headers(client)
    response = client.get('/api/v1/admin/users', headers=customer)
    assert response.status_code == 403
    assert 'администратор' in response.json()['detail'].casefold()


def test_admin_can_list_get_and_promote_user():
    client = TestClient(create_app())
    customer = register(client, 'promote-me@example.com')
    customer_headers = login_headers(client, 'promote-me@example.com')
    admin = admin_headers(client, 'v07-admin@example.com')

    listing = client.get('/api/v1/admin/users', headers=admin)
    assert listing.status_code == 200
    assert {u['email'] for u in listing.json()} == {'promote-me@example.com', 'v07-admin@example.com'}

    detail = client.get(f"/api/v1/admin/users/{customer['id']}", headers=admin)
    assert detail.status_code == 200
    assert detail.json()['role'] == 'customer'

    promoted = client.patch(
        f"/api/v1/admin/users/{customer['id']}",
        headers=admin,
        json={'role': 'admin'},
    )
    assert promoted.status_code == 200
    assert promoted.json()['role'] == 'admin'

    # JWT contains only user identity. Role is read from the DB for every request,
    # so the already-issued token receives admin privileges immediately.
    assert client.get('/api/v1/admin/users', headers=customer_headers).status_code == 200


def test_admin_can_deactivate_user_and_existing_token_stops_working():
    client = TestClient(create_app())
    customer = register(client, 'disable-me@example.com')
    customer_headers = login_headers(client, 'disable-me@example.com')
    admin = admin_headers(client, 'disable-admin@example.com')

    response = client.patch(
        f"/api/v1/admin/users/{customer['id']}",
        headers=admin,
        json={'is_active': False},
    )
    assert response.status_code == 200
    assert response.json()['is_active'] is False
    assert client.get('/api/v1/users/me', headers=customer_headers).status_code == 401
    assert client.post('/api/v1/auth/login', json={
        'email': 'disable-me@example.com',
        'password': 'StrongPass123',
    }).status_code == 401

    reactivated = client.patch(
        f"/api/v1/admin/users/{customer['id']}",
        headers=admin,
        json={'is_active': True},
    )
    assert reactivated.status_code == 200
    assert reactivated.json()['is_active'] is True
    assert client.post('/api/v1/auth/login', json={
        'email': 'disable-me@example.com',
        'password': 'StrongPass123',
    }).status_code == 200


def test_admin_cannot_remove_own_access():
    client = TestClient(create_app())
    headers = admin_headers(client, 'self-admin@example.com')
    me = client.get('/api/v1/users/me', headers=headers).json()

    demote = client.patch(
        f"/api/v1/admin/users/{me['id']}", headers=headers, json={'role': 'customer'}
    )
    assert demote.status_code == 409

    deactivate = client.patch(
        f"/api/v1/admin/users/{me['id']}", headers=headers, json={'is_active': False}
    )
    assert deactivate.status_code == 409


def test_admin_get_unknown_user_is_404():
    client = TestClient(create_app())
    headers = admin_headers(client)
    assert client.get('/api/v1/admin/users/999999', headers=headers).status_code == 404
    assert client.patch('/api/v1/admin/users/999999', headers=headers, json={'role': 'admin'}).status_code == 404


def test_catalog_reads_public_but_writes_are_admin_only():
    client = TestClient(create_app())
    assert client.get('/api/v1/products').status_code == 200
    assert client.get('/api/v1/products/1').status_code == 200

    payload = {
        'name': 'Admin-only product',
        'pet_type': 'cat',
        'brand': 'RoleTest',
        'category': 'food',
        'composition': 'test',
        'variants': [{'sku': 'ROLE-ADMIN-1', 'label': 'S', 'price': '100.00', 'stock': 2}],
    }
    assert client.post('/api/v1/products', json=payload).status_code == 401

    register(client, 'plain-customer@example.com')
    customer = login_headers(client, 'plain-customer@example.com')
    assert client.post('/api/v1/products', headers=customer, json=payload).status_code == 403

    admin = admin_headers(client, 'catalog-admin-v07@example.com')
    created = client.post('/api/v1/products', headers=admin, json=payload)
    assert created.status_code == 201
    product_id = created.json()['id']
    variant_id = created.json()['variants'][0]['id']

    assert client.patch(f'/api/v1/products/{product_id}', headers=admin, json={'name': 'Changed'}).status_code == 200
    assert client.patch(
        f'/api/v1/products/{product_id}/variants/{variant_id}',
        headers=admin,
        json={'stock': 3},
    ).status_code == 200
    assert client.delete(
        f'/api/v1/products/{product_id}/variants/{variant_id}', headers=admin
    ).status_code == 422  # the only variant cannot be removed
    assert client.delete(f'/api/v1/products/{product_id}', headers=admin).status_code == 204



def test_admin_update_rejects_empty_null_and_unknown_fields():
    client = TestClient(create_app())
    customer = register(client, 'admin-validation-target@example.com')
    admin = admin_headers(client, 'admin-validation@example.com')
    path = f"/api/v1/admin/users/{customer['id']}"
    assert client.patch(path, headers=admin, json={}).status_code == 422
    assert client.patch(path, headers=admin, json={'role': None}).status_code == 422
    assert client.patch(path, headers=admin, json={'is_active': None}).status_code == 422
    assert client.patch(path, headers=admin, json={'unknown': True}).status_code == 422


def test_openapi_v070_documents_admin_security():
    client = TestClient(create_app())
    schema = client.get('/openapi.json').json()
    assert schema['info']['version'] == '0.14.0'
    assert '/api/v1/admin/users' in schema['paths']
    assert '/api/v1/admin/users/{user_id}' in schema['paths']
    assert schema['paths']['/api/v1/admin/users']['get']['security'] == [{'HTTPBearer': []}]
    assert schema['paths']['/api/v1/products']['get'].get('security') is None
    assert schema['paths']['/api/v1/products']['post']['security'] == [{'HTTPBearer': []}]
    assert '403' in schema['paths']['/api/v1/products']['post']['responses']


def test_v070_migration_defaults_existing_users_to_customer(tmp_path, monkeypatch):
    db_file = tmp_path / 'upgrade-v07.db'
    url = f'sqlite+pysqlite:///{db_file}'
    monkeypatch.setenv('PETSHOP_DATABASE_URL', url)
    config = Config(str(ROOT / 'alembic.ini'))
    command.upgrade(config, '0001_v060')

    engine = create_engine(url)
    with engine.begin() as connection:
        connection.execute(text("""
            INSERT INTO users (email, password_hash, first_name, last_name, is_active)
            VALUES ('legacy@example.com', 'hash', 'Legacy', NULL, 1)
        """))

    command.upgrade(config, 'head')
    columns = {item['name'] for item in inspect(engine).get_columns('users')}
    assert 'role' in columns
    with engine.connect() as connection:
        role = connection.execute(
            text("SELECT role FROM users WHERE email='legacy@example.com'")
        ).scalar_one()
    assert role == 'customer'


def test_bootstrap_cli_creates_first_admin(tmp_path, monkeypatch):
    db_file = tmp_path / 'bootstrap-v07.db'
    url = f'sqlite+pysqlite:///{db_file}'
    monkeypatch.setenv('PETSHOP_DATABASE_URL', url)
    config = Config(str(ROOT / 'alembic.ini'))
    command.upgrade(config, 'head')

    env = os.environ.copy()
    env['PETSHOP_DATABASE_URL'] = url
    env['PETSHOP_JWT_SECRET'] = 'bootstrap-test-key-00000000000000000000000'
    result = subprocess.run(
        [
            sys.executable, '-m', 'app.admin.bootstrap',
            '--email', 'bootstrap-admin@example.com',
            '--password-stdin',
            '--first-name', 'Bootstrap',
            '--last-name', 'Admin',
        ],
        cwd=ROOT,
        env=env,
        input='StrongAdmin123\n',
        capture_output=True,
        text=True,
        check=True,
    )
    assert 'Admin created' in result.stdout

    client = TestClient(create_app(url))
    headers = login_headers(client, 'bootstrap-admin@example.com', 'StrongAdmin123')
    me = client.get('/api/v1/users/me', headers=headers)
    assert me.status_code == 200
    assert me.json()['role'] == 'admin'
    assert client.get('/api/v1/admin/users', headers=headers).status_code == 200
