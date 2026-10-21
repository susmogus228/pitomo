from tests.helpers import with_consent
from fastapi.testclient import TestClient
import pytest

from app.cart.models import Cart
from tests.helpers import admin_headers


@pytest.fixture
def client():
    from app.main import create_test_app as create_app
    return TestClient(create_app())


def register_and_token(client, email='cart@example.com'):
    payload = {
        'email': email,
        'password': 'StrongPass123',
        'first_name': 'Cart',
        'last_name': 'User',
    }
    registered = client.post('/api/v1/auth/register', json=with_consent(client, payload))
    assert registered.status_code == 201
    login = client.post('/api/v1/auth/login', json={
        'email': email,
        'password': 'StrongPass123',
    })
    assert login.status_code == 200
    return registered.json(), {'Authorization': f"Bearer {login.json()['access_token']}"}


def test_cart_domain_model_encapsulates_items_and_quantity():
    cart = Cart(user_id=1)
    cart.add_item(20, 2)
    cart.add_item(20, 1)
    cart.add_item(21, 4)
    assert cart.total_items == 7
    assert len(cart.items) == 2
    assert cart.get_item(20).quantity == 3

    cart.set_quantity(20, 5)
    assert cart.get_item(20).quantity == 5
    assert cart.remove_item(20).variant_id == 20
    cart.clear()
    assert cart.items == ()


@pytest.mark.parametrize(
    ('method', 'path', 'json'),
    [
        ('get', '/api/v1/cart', None),
        ('post', '/api/v1/cart/items', {'variant_id': 20, 'quantity': 1}),
        ('patch', '/api/v1/cart/items/20', {'quantity': 1}),
        ('delete', '/api/v1/cart/items/20', None),
        ('delete', '/api/v1/cart', None),
    ],
)
def test_cart_routes_require_authentication(client, method, path, json):
    response = client.request(method, path, json=json)
    assert response.status_code == 401


def test_new_user_has_empty_cart(client):
    user, headers = register_and_token(client)
    response = client.get('/api/v1/cart', headers=headers)
    assert response.status_code == 200
    assert response.json() == {
        'user_id': user['id'],
        'items': [],
        'total_items': 0,
        'subtotal': '0.00',
        'currency': 'KZT',
        'can_checkout': False,
    }


def test_add_item_to_cart(client):
    user, headers = register_and_token(client)
    response = client.post(
        '/api/v1/cart/items',
        headers=headers,
        json={'variant_id': 20, 'quantity': 2},
    )
    assert response.status_code == 200
    data = response.json()
    assert data['user_id'] == user['id']
    assert data['total_items'] == 2
    assert data['subtotal'] == '2800.00'
    assert data['can_checkout'] is True
    assert data['items'][0] == {
        'product_id': 2,
        'product_name': 'Корм для собак №2',
        'image_url': None,
        'variant_id': 20,
        'sku': 'DEMO-2-S',
        'label': '400 г',
        'unit_price': '1400.00',
        'original_unit_price': None,
        'currency': 'KZT',
        'quantity': 2,
        'available_stock': 5,
        'is_available': True,
        'line_total': '2800.00',
    }


def test_adding_same_variant_increases_existing_quantity(client):
    _, headers = register_and_token(client)
    client.post('/api/v1/cart/items', headers=headers, json={'variant_id': 20, 'quantity': 2})
    response = client.post('/api/v1/cart/items', headers=headers, json={'variant_id': 20, 'quantity': 1})
    assert response.status_code == 200
    assert len(response.json()['items']) == 1
    assert response.json()['items'][0]['quantity'] == 3
    assert response.json()['total_items'] == 3


def test_cart_multiple_items_and_subtotal(client):
    _, headers = register_and_token(client)
    client.post('/api/v1/cart/items', headers=headers, json={'variant_id': 20, 'quantity': 2})
    response = client.post('/api/v1/cart/items', headers=headers, json={'variant_id': 21, 'quantity': 1})
    assert response.status_code == 200
    data = response.json()
    assert data['total_items'] == 3
    assert len(data['items']) == 2
    assert data['subtotal'] == '8800.00'
    assert data['can_checkout'] is True


def test_patch_cart_item_sets_exact_quantity(client):
    _, headers = register_and_token(client)
    client.post('/api/v1/cart/items', headers=headers, json={'variant_id': 20, 'quantity': 1})
    response = client.patch('/api/v1/cart/items/20', headers=headers, json={'quantity': 4})
    assert response.status_code == 200
    assert response.json()['items'][0]['quantity'] == 4
    assert response.json()['subtotal'] == '5600.00'


def test_delete_cart_item(client):
    _, headers = register_and_token(client)
    client.post('/api/v1/cart/items', headers=headers, json={'variant_id': 20, 'quantity': 1})
    response = client.delete('/api/v1/cart/items/20', headers=headers)
    assert response.status_code == 204
    assert client.get('/api/v1/cart', headers=headers).json()['items'] == []


def test_clear_cart(client):
    _, headers = register_and_token(client)
    client.post('/api/v1/cart/items', headers=headers, json={'variant_id': 20, 'quantity': 1})
    client.post('/api/v1/cart/items', headers=headers, json={'variant_id': 21, 'quantity': 1})
    assert client.delete('/api/v1/cart', headers=headers).status_code == 204
    data = client.get('/api/v1/cart', headers=headers).json()
    assert data['items'] == []
    assert data['subtotal'] == '0.00'
    assert data['can_checkout'] is False


@pytest.mark.parametrize('operation', ['patch', 'delete'])
def test_missing_cart_item_returns_404(client, operation):
    _, headers = register_and_token(client)
    if operation == 'patch':
        response = client.patch('/api/v1/cart/items/20', headers=headers, json={'quantity': 1})
    else:
        response = client.delete('/api/v1/cart/items/20', headers=headers)
    assert response.status_code == 404
    assert 'корзин' in response.json()['detail'].casefold()


def test_missing_catalog_variant_returns_404(client):
    _, headers = register_and_token(client)
    response = client.post(
        '/api/v1/cart/items',
        headers=headers,
        json={'variant_id': 99999, 'quantity': 1},
    )
    assert response.status_code == 404
    assert 'вариант' in response.json()['detail'].casefold()


def test_out_of_stock_variant_cannot_be_added(client):
    _, headers = register_and_token(client)
    response = client.post(
        '/api/v1/cart/items',
        headers=headers,
        json={'variant_id': 10, 'quantity': 1},
    )
    assert response.status_code == 409
    assert 'доступно 0' in response.json()['detail']


def test_quantity_above_stock_is_rejected(client):
    _, headers = register_and_token(client)
    response = client.post(
        '/api/v1/cart/items',
        headers=headers,
        json={'variant_id': 20, 'quantity': 6},
    )
    assert response.status_code == 409
    assert 'доступно 5' in response.json()['detail']


def test_increment_cannot_push_quantity_above_stock(client):
    _, headers = register_and_token(client)
    assert client.post('/api/v1/cart/items', headers=headers, json={'variant_id': 20, 'quantity': 4}).status_code == 200
    response = client.post('/api/v1/cart/items', headers=headers, json={'variant_id': 20, 'quantity': 2})
    assert response.status_code == 409
    assert client.get('/api/v1/cart', headers=headers).json()['items'][0]['quantity'] == 4


@pytest.mark.parametrize(
    'payload',
    [
        {'variant_id': 20, 'quantity': 0},
        {'variant_id': -1, 'quantity': 1},
        {'variant_id': 20, 'quantity': -1},
        {'variant_id': 20, 'quantity': 1, 'unknown': True},
    ],
)
def test_add_item_rejects_invalid_payload(client, payload):
    _, headers = register_and_token(client)
    assert client.post('/api/v1/cart/items', headers=headers, json=payload).status_code == 422


def test_carts_are_isolated_between_users(client):
    _, first_headers = register_and_token(client, 'first-cart@example.com')
    _, second_headers = register_and_token(client, 'second-cart@example.com')

    client.post('/api/v1/cart/items', headers=first_headers, json={'variant_id': 20, 'quantity': 2})
    first = client.get('/api/v1/cart', headers=first_headers).json()
    second = client.get('/api/v1/cart', headers=second_headers).json()

    assert first['total_items'] == 2
    assert second['total_items'] == 0
    assert second['items'] == []


def test_cart_uses_current_catalog_price(client):
    _, headers = register_and_token(client)
    client.post('/api/v1/cart/items', headers=headers, json={'variant_id': 20, 'quantity': 2})

    updated = client.patch('/api/v1/products/2/variants/20', headers=admin_headers(client, 'v04-price-admin@example.com'), json={'price': '1500.50'})
    assert updated.status_code == 200

    cart = client.get('/api/v1/cart', headers=headers).json()
    assert cart['items'][0]['unit_price'] == '1500.50'
    assert cart['items'][0]['line_total'] == '3001.00'
    assert cart['subtotal'] == '3001.00'


def test_stock_drop_marks_existing_cart_unavailable(client):
    _, headers = register_and_token(client)
    client.post('/api/v1/cart/items', headers=headers, json={'variant_id': 20, 'quantity': 3})
    assert client.patch('/api/v1/products/2/variants/20', headers=admin_headers(client, 'v04-stock-admin@example.com'), json={'stock': 1}).status_code == 200

    cart = client.get('/api/v1/cart', headers=headers).json()
    assert cart['items'][0]['quantity'] == 3
    assert cart['items'][0]['available_stock'] == 1
    assert cart['items'][0]['is_available'] is False
    assert cart['can_checkout'] is False


def test_deleted_catalog_variant_is_pruned_from_cart(client):
    _, headers = register_and_token(client)
    client.post('/api/v1/cart/items', headers=headers, json={'variant_id': 20, 'quantity': 1})
    assert client.delete('/api/v1/products/2/variants/20', headers=admin_headers(client, 'v04-delete-admin@example.com')).status_code == 204

    cart = client.get('/api/v1/cart', headers=headers).json()
    assert cart['items'] == []
    assert cart['total_items'] == 0
    assert cart['subtotal'] == '0.00'


def test_cart_memory_isolated_between_application_instances():
    from app.main import create_test_app as create_app

    first = TestClient(create_app())
    second = TestClient(create_app())
    _, first_headers = register_and_token(first, 'same@example.com')
    _, second_headers = register_and_token(second, 'same@example.com')

    first.post('/api/v1/cart/items', headers=first_headers, json={'variant_id': 20, 'quantity': 1})
    assert first.get('/api/v1/cart', headers=first_headers).json()['total_items'] == 1
    assert second.get('/api/v1/cart', headers=second_headers).json()['total_items'] == 0


def test_openapi_reports_v04_and_cart_routes(client):
    schema = client.get('/openapi.json').json()
    assert schema['info']['version'] == '0.14.0'
    assert '/api/v1/cart' in schema['paths']
    assert '/api/v1/cart/items' in schema['paths']
    assert '/api/v1/cart/items/{variant_id}' in schema['paths']
    assert 'HTTPBearer' in schema['components']['securitySchemes']
