"""Regression tests for security and request transaction boundaries."""
from tests.helpers import with_consent
from dataclasses import replace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError

from app.main import create_app as create_runtime_app, create_test_app as create_app


def test_password_whitespace_is_significant():
    client = TestClient(create_app())
    payload = {'email': 'space@example.com', 'password': '  long password  ', 'first_name': ' Test '}
    assert client.post('/api/v1/auth/register', json=with_consent(client, payload)).status_code == 201
    assert client.post('/api/v1/auth/login', json={
        'email': payload['email'], 'password': payload['password'].strip(),
    }).status_code == 401
    assert client.post('/api/v1/auth/login', json={
        'email': payload['email'], 'password': payload['password'],
    }).status_code == 200


def test_validation_error_never_echoes_password_or_body():
    client = TestClient(create_app())
    secret = 'private-secret-that-must-not-appear'
    response = client.post('/api/v1/auth/register', json=with_consent(client, {
        'email': 'x', 'password': secret, 'first_name': None, 'unexpected': secret,
    }))
    assert response.status_code == 422
    assert secret not in response.text
    assert all('input' not in issue and 'ctx' not in issue for issue in response.json()['detail'])
    assert isinstance(response.json()['detail'], list)


@pytest.mark.parametrize('message, expected_status', [
    ('UNIQUE constraint failed: users.email', 409),
    ('unexpected internal constraint', 500),
])
def test_commit_failure_is_not_reported_as_success(monkeypatch, message, expected_status):
    client = TestClient(create_app(), raise_server_exceptions=False)
    session_class = client.app.state.database.session_factory.class_

    def fail_commit(self):
        raise IntegrityError('redacted', {}, Exception(message))

    monkeypatch.setattr(session_class, 'commit', fail_commit)
    response = client.post('/api/v1/auth/register', json=with_consent(client, {
        'email': 'commit@example.com', 'password': 'StrongPass123', 'first_name': 'Commit',
    }))
    assert response.status_code == expected_status
    assert message not in response.text


def test_readiness_rejects_empty_database(tmp_path):
    client = TestClient(create_app(f'sqlite+pysqlite:///{tmp_path / "empty.db"}'))
    assert client.get('/ready').status_code == 503


def test_runtime_rejects_missing_secret(monkeypatch):
    monkeypatch.setattr('app.core.config.load_dotenv', lambda: None)
    monkeypatch.delenv('PETSHOP_JWT_SECRET', raising=False)
    monkeypatch.setenv('PETSHOP_DATABASE_URL', 'sqlite+pysqlite:///:memory:')
    with pytest.raises(ValueError, match='JWT'):
        with TestClient(create_runtime_app()):
            pass


def test_login_limits_survive_failed_request_rollback():
    from app.core.config import Settings
    client = TestClient(create_app(settings=Settings.for_testing(login_max_attempts=2)))
    credentials = {'email': 'unknown@example.com', 'password': 'wrong'}
    assert client.post('/api/v1/auth/login', json=credentials).status_code == 401
    assert client.post('/api/v1/auth/login', json=credentials).status_code == 401
    response = client.post('/api/v1/auth/login', json=credentials)
    assert response.status_code == 429
    assert int(response.headers['Retry-After']) > 0


def test_auth_body_is_bounded():
    client = TestClient(create_app())
    assert client.post('/api/v1/auth/login', content=b'x' * 16385).status_code == 413


def test_ready_detects_missing_column():
    from sqlalchemy import text
    client = TestClient(create_app())
    assert client.get('/ready').status_code == 200
    with client.app.state.database.engine.begin() as connection:
        connection.execute(text('ALTER TABLE users DROP COLUMN first_name'))
    assert client.get('/health').status_code == 200
    assert client.get('/ready').status_code == 503


def test_metrics_require_admin_and_logs_do_not_record_input(caplog):
    client = TestClient(create_app())
    with caplog.at_level('INFO', logger='petshop.audit'):
        response = client.post('/api/v1/auth/login', json={
            'email': 'private@example.com', 'password': 'NeverLogThisPassword',
        })
    assert response.status_code == 401
    assert response.headers['X-Request-ID']
    assert 'NeverLogThisPassword' not in caplog.text
    assert 'private@example.com' not in caplog.text
    assert '"status": 401' in caplog.text
    assert client.get('/metrics').status_code == 401


def test_production_docs_are_disabled(monkeypatch):
    from app.core.config import load_settings
    monkeypatch.setattr('app.core.config.load_dotenv', lambda: None)
    monkeypatch.setenv('PETSHOP_ENV', 'production')
    monkeypatch.delenv('PETSHOP_DOCS_ENABLED', raising=False)
    settings = replace(load_settings(), jwt_secret='production-test-key-000000000000000000')
    client = TestClient(create_runtime_app(settings=settings))
    assert client.get('/docs').status_code == 404
    assert client.get('/openapi.json').status_code == 404


@pytest.mark.parametrize('claims', [
    {'sub': '1', 'exp': 4102444800},
    {'sub': '0', 'iat': 1, 'exp': 4102444800},
    {'sub': '2147483648', 'iat': 1, 'exp': 4102444800},
    {'sub': '1', 'iat': True, 'exp': 4102444800},
    {'sub': '1', 'iat': 1, 'exp': '4102444800'},
])
def test_jwt_rejects_invalid_claim_shapes(claims):
    import jwt
    from app.core.security import TokenError, decode_access_token
    secret = 'jwt-test-secret-000000000000000000000000'
    token = jwt.encode(claims, secret, algorithm='HS256')
    with pytest.raises(TokenError):
        decode_access_token(token, secret=secret)


def test_legacy_password_remains_valid_and_is_upgraded():
    from app.core.security import hash_password, verify_password
    from app.users.repository import SQLAlchemyUserRepository
    client = TestClient(create_app())
    payload = {'email': 'legacyhash@example.com', 'password': 'StrongPass123', 'first_name': 'Legacy'}
    assert client.post('/api/v1/auth/register', json=with_consent(client, payload)).status_code == 201
    with client.app.state.database.session_factory() as session:
        repo = SQLAlchemyUserRepository(session)
        user = repo.get_by_email(payload['email'])
        user.change_password_hash(hash_password(payload['password'], iterations=310_000))
        repo.save(user, fields={'password_hash'})
        session.commit()
    assert client.post('/api/v1/auth/login', json={k: payload[k] for k in ('email', 'password')}).status_code == 200
    with client.app.state.database.session_factory() as session:
        user = SQLAlchemyUserRepository(session).get_by_email(payload['email'])
        assert user.password_hash.startswith('pbkdf2_sha256$600000$')
        assert verify_password(payload['password'], user.password_hash)
