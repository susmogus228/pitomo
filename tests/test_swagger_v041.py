"""Swagger/OpenAPI regression tests added after the v0.4.0 QA pass."""
from tests.helpers import with_consent
from fastapi.testclient import TestClient
import pytest


@pytest.fixture
def client():
    from app.main import create_test_app as create_app
    return TestClient(create_app())


def test_swagger_ui_and_openapi_are_available(client):
    docs = client.get('/docs')
    assert docs.status_code == 200
    assert 'SwaggerUIBundle' in docs.text
    assert '/openapi.json' in docs.text
    assert 'persistAuthorization' in docs.text

    schema = client.get('/openapi.json')
    assert schema.status_code == 200
    assert schema.json()['info']['version'] == '0.14.0'


def test_openapi_exposes_bearer_auth_for_protected_routes(client):
    schema = client.get('/openapi.json').json()
    assert schema['components']['securitySchemes']['HTTPBearer'] == {
        'type': 'http',
        'scheme': 'bearer',
    }

    protected_operations = [
        ('/api/v1/users/me', 'get'),
        ('/api/v1/users/me', 'patch'),
        ('/api/v1/cart', 'get'),
        ('/api/v1/cart', 'delete'),
        ('/api/v1/cart/items', 'post'),
        ('/api/v1/cart/items/{variant_id}', 'patch'),
        ('/api/v1/cart/items/{variant_id}', 'delete'),
    ]
    for path, method in protected_operations:
        operation = schema['paths'][path][method]
        assert {'HTTPBearer': []} in operation['security']
        assert '401' in operation['responses']


def test_openapi_documents_runtime_error_statuses(client):
    schema = client.get('/openapi.json').json()

    assert {'201', '409', '422'} <= set(schema['paths']['/api/v1/auth/register']['post']['responses'])
    assert {'200', '401', '422'} <= set(schema['paths']['/api/v1/auth/login']['post']['responses'])
    assert {'200', '401', '404', '409', '422'} <= set(
        schema['paths']['/api/v1/cart/items']['post']['responses']
    )
    assert {'200', '404', '422'} <= set(
        schema['paths']['/api/v1/products/{product_id}']['get']['responses']
    )


def test_swagger_equivalent_end_to_end_flow(client):
    register_payload = {
        'email': 'swagger-flow@example.com',
        'password': 'StrongPass123',
        'first_name': 'Swagger',
        'last_name': 'Flow',
    }
    registered = client.post('/api/v1/auth/register', json=with_consent(client, register_payload))
    assert registered.status_code == 201

    login = client.post('/api/v1/auth/login', json={
        'email': register_payload['email'],
        'password': register_payload['password'],
    })
    assert login.status_code == 200
    token = login.json()['access_token']
    headers = {'Authorization': f'Bearer {token}'}

    assert client.get('/api/v1/users/me', headers=headers).status_code == 200
    assert client.get('/api/v1/products').status_code == 200

    added = client.post('/api/v1/cart/items', headers=headers, json={
        'variant_id': 20,
        'quantity': 2,
    })
    assert added.status_code == 200
    assert added.json()['total_items'] == 2

    updated = client.patch('/api/v1/cart/items/20', headers=headers, json={'quantity': 3})
    assert updated.status_code == 200
    assert updated.json()['items'][0]['quantity'] == 3

    assert client.delete('/api/v1/cart/items/20', headers=headers).status_code == 204
    assert client.delete('/api/v1/cart', headers=headers).status_code == 204


def test_swagger_representative_error_flow(client):
    payload = {
        'email': 'swagger-errors@example.com',
        'password': 'StrongPass123',
        'first_name': 'Swagger',
        'last_name': 'Errors',
    }
    assert client.post('/api/v1/auth/register', json=with_consent(client, payload)).status_code == 201
    assert client.post('/api/v1/auth/register', json=with_consent(client, payload)).status_code == 409
    assert client.post('/api/v1/auth/login', json={
        'email': payload['email'],
        'password': 'wrong-password',
    }).status_code == 401
    assert client.get('/api/v1/users/me').status_code == 401
    assert client.get('/api/v1/products/999999').status_code == 404
    assert client.get('/api/v1/products?page=0').status_code == 422

    login = client.post('/api/v1/auth/login', json={
        'email': payload['email'],
        'password': payload['password'],
    })
    headers = {'Authorization': f"Bearer {login.json()['access_token']}"}
    assert client.post('/api/v1/cart/items', headers=headers, json={
        'variant_id': 999999,
        'quantity': 1,
    }).status_code == 404
    assert client.post('/api/v1/cart/items', headers=headers, json={
        'variant_id': 10,
        'quantity': 1,
    }).status_code == 409
    assert client.post('/api/v1/cart/items', headers=headers, json={
        'variant_id': 20,
        'quantity': 0,
    }).status_code == 422


def test_jwt_rejects_noncanonical_signature_alias(client):
    """Changing only unused Base64URL bits must not produce an accepted token."""
    payload = {
        'email': 'canonical-jwt@example.com',
        'password': 'StrongPass123',
        'first_name': 'Canonical',
        'last_name': 'JWT',
    }
    assert client.post('/api/v1/auth/register', json=with_consent(client, payload)).status_code == 201
    login = client.post('/api/v1/auth/login', json={
        'email': payload['email'],
        'password': payload['password'],
    })
    token = login.json()['access_token']
    header, body, signature = token.split('.')

    # For a 32-byte HS256 signature the last Base64URL character has unused
    # low bits. Build a different character that preserves the decoded bytes
    # under permissive Base64URL decoders.
    alphabet = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_'
    last_value = alphabet.index(signature[-1])
    canonical_high_bits = last_value & 0b110000
    alias_value = canonical_high_bits | ((last_value + 1) & 0b001111)
    if alias_value == last_value:
        alias_value = canonical_high_bits | ((last_value + 2) & 0b001111)
    tampered = f'{header}.{body}.{signature[:-1]}{alphabet[alias_value]}'
    assert tampered != token

    response = client.get('/api/v1/users/me', headers={'Authorization': f'Bearer {tampered}'})
    assert response.status_code == 401
