from tests.helpers import with_consent
from fastapi.testclient import TestClient
import pytest

from app.core.security import create_access_token, verify_password


@pytest.fixture
def client():
    from app.main import create_test_app as create_app
    return TestClient(create_app())


def register_payload(email='user@example.com'):
    return {
        'email': email,
        'password': 'StrongPass123',
        'first_name': 'Kirill',
        'last_name': 'Ivanov',
    }


def register(client, email='user@example.com'):
    response = client.post('/api/v1/auth/register', json=with_consent(client, register_payload(email)))
    assert response.status_code == 201
    return response.json()


def login(client, email='user@example.com', password='StrongPass123'):
    return client.post('/api/v1/auth/login', json={'email': email, 'password': password})


def bearer(token):
    return {'Authorization': f'Bearer {token}'}


def test_register_user_and_hide_password(client):
    response = client.post('/api/v1/auth/register', json=with_consent(client, register_payload('User@Example.COM')))
    assert response.status_code == 201
    data = response.json()
    assert data == {
        'id': 1,
        'email': 'user@example.com',
        'first_name': 'Kirill',
        'last_name': 'Ivanov',
        'is_active': True,
        'role': 'customer',
    }
    assert 'password' not in data
    assert 'password_hash' not in data


def test_password_is_hashed_in_repository(client):
    from app.users.repository import SQLAlchemyUserRepository

    register(client)
    with client.app.state.database.session_factory() as session:
        user = SQLAlchemyUserRepository(session).get(1)
    assert user is not None
    assert user.password_hash != 'StrongPass123'
    assert user.password_hash.startswith('pbkdf2_sha256$')
    assert verify_password('StrongPass123', user.password_hash)


def test_duplicate_email_is_case_insensitive(client):
    register(client, 'user@example.com')
    response = client.post('/api/v1/auth/register', json=with_consent(client, register_payload('USER@example.com')))
    assert response.status_code == 409
    assert 'email' in response.json()['detail']


@pytest.mark.parametrize(
    'payload',
    [
        {**register_payload(), 'email': 'not-an-email'},
        {**register_payload(), 'password': 'short'},
        {**register_payload(), 'first_name': '   '},
        {**register_payload(), 'unknown': 'field'},
    ],
)
def test_invalid_registration_payload(client, payload):
    assert client.post('/api/v1/auth/register', json=with_consent(client, payload)).status_code == 422


def test_login_returns_jwt(client):
    register(client)
    response = login(client)
    assert response.status_code == 200
    data = response.json()
    assert data['token_type'] == 'bearer'
    assert data['expires_in'] == 1800
    assert len(data['access_token'].split('.')) == 3


@pytest.mark.parametrize(
    ('email', 'password'),
    [
        ('missing@example.com', 'StrongPass123'),
        ('user@example.com', 'WrongPassword123'),
    ],
)
def test_login_rejects_bad_credentials(client, email, password):
    register(client)
    response = login(client, email=email, password=password)
    assert response.status_code == 401
    assert response.headers['www-authenticate'] == 'Bearer'
    assert response.json()['detail'] == 'Неверный email или пароль'


def test_me_requires_bearer_token(client):
    assert client.get('/api/v1/users/me').status_code == 401
    assert client.get('/api/v1/users/me', headers={'Authorization': 'Basic abc'}).status_code == 401


def test_me_returns_current_user(client):
    user = register(client)
    token = login(client).json()['access_token']
    response = client.get('/api/v1/users/me', headers=bearer(token))
    assert response.status_code == 200
    assert response.json() == user


def test_tampered_token_is_rejected(client):
    register(client)
    token = login(client).json()['access_token']
    head, body, signature = token.split('.')
    tampered = f'{head}.{body}.{signature[:-1]}x'
    assert client.get('/api/v1/users/me', headers=bearer(tampered)).status_code == 401


def test_expired_token_is_rejected(client):
    register(client)
    settings = client.app.state.settings
    expired = create_access_token(subject=1, secret=settings.jwt_secret, expires_minutes=-1)
    response = client.get('/api/v1/users/me', headers=bearer(expired))
    assert response.status_code == 401


def test_patch_current_profile(client):
    register(client)
    token = login(client).json()['access_token']
    response = client.patch('/api/v1/users/me', headers=bearer(token), json={
        'email': 'new@example.com',
        'first_name': 'New Name',
        'last_name': 'New Last',
    })
    assert response.status_code == 200
    assert response.json()['email'] == 'new@example.com'
    assert response.json()['first_name'] == 'New Name'
    assert response.json()['last_name'] == 'New Last'

    assert login(client, email='user@example.com').status_code == 401
    assert login(client, email='new@example.com').status_code == 200


def test_patch_can_clear_last_name(client):
    register(client)
    token = login(client).json()['access_token']
    response = client.patch('/api/v1/users/me', headers=bearer(token), json={'last_name': None})
    assert response.status_code == 200
    assert response.json()['last_name'] is None


@pytest.mark.parametrize('payload', [{'email': None}, {'first_name': None}, {'unknown': 'x'}])
def test_patch_rejects_invalid_profile_changes(client, payload):
    register(client)
    token = login(client).json()['access_token']
    assert client.patch('/api/v1/users/me', headers=bearer(token), json=payload).status_code == 422


def test_patch_rejects_email_used_by_other_user(client):
    register(client, 'first@example.com')
    first_token = login(client, email='first@example.com').json()['access_token']
    register(client, 'second@example.com')
    response = client.patch(
        '/api/v1/users/me',
        headers=bearer(first_token),
        json={'email': 'SECOND@example.com'},
    )
    assert response.status_code == 409


def test_each_application_instance_has_its_own_memory_users():
    from app.main import create_test_app as create_app

    first = TestClient(create_app())
    second = TestClient(create_app())
    register(first)
    assert login(first).status_code == 200
    assert login(second).status_code == 401


def test_openapi_reports_v03_and_auth_routes(client):
    schema = client.get('/openapi.json').json()
    assert schema['info']['version'] == '0.14.0'
    assert '/api/v1/auth/register' in schema['paths']
    assert '/api/v1/auth/login' in schema['paths']
    assert '/api/v1/users/me' in schema['paths']
    assert 'HTTPBearer' in schema['components']['securitySchemes']
