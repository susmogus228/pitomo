from tests.helpers import with_consent
from decimal import Decimal

from fastapi.testclient import TestClient
import pytest

from app.orders.models import Order, OrderItem
from tests.helpers import admin_headers


@pytest.fixture
def client():
    from app.main import create_test_app as create_app
    return TestClient(create_app())


def register_and_token(client, email='orders@example.com'):
    payload = {
        'email': email,
        'password': 'StrongPass123',
        'first_name': 'Order',
        'last_name': 'User',
    }
    registered = client.post('/api/v1/auth/register', json=with_consent(client, payload))
    assert registered.status_code == 201
    login = client.post('/api/v1/auth/login', json={
        'email': email,
        'password': payload['password'],
    })
    assert login.status_code == 200
    return registered.json(), {'Authorization': f"Bearer {login.json()['access_token']}"}


def test_order_domain_calculates_snapshot_totals():
    item = OrderItem(
        product_id=2,
        product_name='Корм',
        variant_id=20,
        sku='SKU-20',
        variant_label='400 г',
        unit_price='1400.00',
        quantity=3,
    )
    order = Order(id=1, user_id=1, items=[item])
    assert item.line_total == Decimal('4200.00')
    assert order.total_items == 3
    assert order.total == Decimal('4200.00')
    assert order.items == (item,)


@pytest.mark.parametrize('method,path', [
    ('post', '/api/v1/orders'),
    ('get', '/api/v1/orders'),
    ('get', '/api/v1/orders/1'),
])
def test_order_routes_require_authentication(client, method, path):
    response = client.request(method, path)
    assert response.status_code == 401


def test_checkout_empty_cart_returns_409(client):
    _, headers = register_and_token(client)
    response = client.post('/api/v1/orders', headers=headers)
    assert response.status_code == 409
    assert 'пуста' in response.json()['detail'].casefold()


def test_checkout_creates_order_and_clears_cart(client):
    user, headers = register_and_token(client)
    assert client.post('/api/v1/cart/items', headers=headers, json={
        'variant_id': 20,
        'quantity': 2,
    }).status_code == 200

    response = client.post('/api/v1/orders', headers=headers)
    assert response.status_code == 201
    data = response.json()
    assert data['id'] == 1
    assert data['user_id'] == user['id']
    assert data['status'] == 'created'
    assert data['total_items'] == 2
    assert data['total'] == '2800.00'
    assert data['currency'] == 'KZT'
    assert data['items'] == [{
        'product_id': 2,
        'product_name': 'Корм для собак №2',
        'variant_id': 20,
        'sku': 'DEMO-2-S',
        'variant_label': '400 г',
        'unit_price': '1400.00',
        'original_unit_price': None,
        'currency': 'KZT',
        'quantity': 2,
        'line_total': '2800.00',
    }]
    assert data['created_at']

    cart = client.get('/api/v1/cart', headers=headers).json()
    assert cart['items'] == []
    assert cart['subtotal'] == '0.00'


def test_checkout_decrements_catalog_stock(client):
    _, headers = register_and_token(client)
    before = client.get('/api/v1/products/2').json()
    assert next(v for v in before['variants'] if v['id'] == 20)['stock'] == 5

    client.post('/api/v1/cart/items', headers=headers, json={'variant_id': 20, 'quantity': 2})
    assert client.post('/api/v1/orders', headers=headers).status_code == 201

    after = client.get('/api/v1/products/2').json()
    assert next(v for v in after['variants'] if v['id'] == 20)['stock'] == 3


def test_checkout_multiple_lines_decrements_all_stock(client):
    _, headers = register_and_token(client)
    client.post('/api/v1/cart/items', headers=headers, json={'variant_id': 20, 'quantity': 2})
    client.post('/api/v1/cart/items', headers=headers, json={'variant_id': 21, 'quantity': 1})

    before = client.get('/api/v1/products/2').json()
    stock20 = next(v for v in before['variants'] if v['id'] == 20)['stock']
    stock21 = next(v for v in before['variants'] if v['id'] == 21)['stock']

    order = client.post('/api/v1/orders', headers=headers)
    assert order.status_code == 201
    assert order.json()['total_items'] == 3
    assert order.json()['total'] == '8800.00'

    after = client.get('/api/v1/products/2').json()
    assert next(v for v in after['variants'] if v['id'] == 20)['stock'] == stock20 - 2
    assert next(v for v in after['variants'] if v['id'] == 21)['stock'] == stock21 - 1


def test_checkout_revalidates_stock_and_is_all_or_nothing(client):
    _, headers = register_and_token(client)
    client.post('/api/v1/cart/items', headers=headers, json={'variant_id': 20, 'quantity': 2})
    client.post('/api/v1/cart/items', headers=headers, json={'variant_id': 21, 'quantity': 1})

    # Simulate a stock change after items were put into the cart.
    assert client.patch('/api/v1/products/2/variants/21', headers=admin_headers(client, 'v05-stock-admin@example.com'), json={'stock': 0}).status_code == 200
    stock20_before = next(
        v for v in client.get('/api/v1/products/2').json()['variants'] if v['id'] == 20
    )['stock']

    response = client.post('/api/v1/orders', headers=headers)
    assert response.status_code == 409
    assert 'недостаточно' in response.json()['detail'].casefold()

    # First line must not be partially decremented and cart must remain intact.
    stock20_after = next(
        v for v in client.get('/api/v1/products/2').json()['variants'] if v['id'] == 20
    )['stock']
    assert stock20_after == stock20_before
    assert client.get('/api/v1/cart', headers=headers).json()['total_items'] == 3
    assert client.get('/api/v1/orders', headers=headers).json() == []


def test_deleted_variant_blocks_checkout_without_clearing_cart_reference(client):
    _, headers = register_and_token(client)
    client.post('/api/v1/cart/items', headers=headers, json={'variant_id': 20, 'quantity': 1})
    assert client.delete('/api/v1/products/2/variants/20', headers=admin_headers(client, 'v05-delete-admin@example.com')).status_code == 204

    response = client.post('/api/v1/orders', headers=headers)
    assert response.status_code == 409
    assert 'недоступен' in response.json()['detail'].casefold()
    assert client.get('/api/v1/orders', headers=headers).json() == []


def test_list_orders_returns_only_current_users_orders(client):
    _, first_headers = register_and_token(client, 'first-orders@example.com')
    _, second_headers = register_and_token(client, 'second-orders@example.com')

    client.post('/api/v1/cart/items', headers=first_headers, json={'variant_id': 20, 'quantity': 1})
    first_order = client.post('/api/v1/orders', headers=first_headers)
    assert first_order.status_code == 201

    assert len(client.get('/api/v1/orders', headers=first_headers).json()) == 1
    assert client.get('/api/v1/orders', headers=second_headers).json() == []


def test_get_own_order_by_id(client):
    _, headers = register_and_token(client)
    client.post('/api/v1/cart/items', headers=headers, json={'variant_id': 20, 'quantity': 1})
    order = client.post('/api/v1/orders', headers=headers).json()

    response = client.get(f"/api/v1/orders/{order['id']}", headers=headers)
    assert response.status_code == 200
    assert response.json() == order


def test_foreign_order_is_hidden_as_404(client):
    _, first_headers = register_and_token(client, 'owner@example.com')
    _, second_headers = register_and_token(client, 'other@example.com')
    client.post('/api/v1/cart/items', headers=first_headers, json={'variant_id': 20, 'quantity': 1})
    order_id = client.post('/api/v1/orders', headers=first_headers).json()['id']

    response = client.get(f'/api/v1/orders/{order_id}', headers=second_headers)
    assert response.status_code == 404
    assert response.json()['detail'] == 'Заказ не найден'


def test_missing_order_returns_404(client):
    _, headers = register_and_token(client)
    assert client.get('/api/v1/orders/99999', headers=headers).status_code == 404


def test_order_snapshot_does_not_change_with_catalog(client):
    _, headers = register_and_token(client)
    client.post('/api/v1/cart/items', headers=headers, json={'variant_id': 20, 'quantity': 2})
    order = client.post('/api/v1/orders', headers=headers).json()
    assert order['items'][0]['unit_price'] == '1400.00'
    assert order['items'][0]['product_name'] == 'Корм для собак №2'

    assert client.patch('/api/v1/products/2/variants/20', headers=admin_headers(client, 'v05-snapshot2-admin@example.com'), json={
        'price': '9999.99',
        'label': 'Новая упаковка',
    }).status_code == 200
    assert client.patch('/api/v1/products/2', headers=admin_headers(client, 'v05-name-admin@example.com'), json={'name': 'Новое название'}).status_code == 200

    historical = client.get(f"/api/v1/orders/{order['id']}", headers=headers).json()
    assert historical['items'][0]['unit_price'] == '1400.00'
    assert historical['items'][0]['variant_label'] == '400 г'
    assert historical['items'][0]['product_name'] == 'Корм для собак №2'
    assert historical['total'] == '2800.00'


def test_second_checkout_gets_new_order_id_and_new_snapshot(client):
    _, headers = register_and_token(client)
    client.post('/api/v1/cart/items', headers=headers, json={'variant_id': 20, 'quantity': 1})
    first = client.post('/api/v1/orders', headers=headers).json()

    assert client.patch('/api/v1/products/2/variants/20', headers=admin_headers(client, 'v05-price-admin@example.com'), json={'price': '1500.00'}).status_code == 200
    client.post('/api/v1/cart/items', headers=headers, json={'variant_id': 20, 'quantity': 1})
    second = client.post('/api/v1/orders', headers=headers).json()

    assert first['id'] == 1
    assert second['id'] == 2
    assert first['items'][0]['unit_price'] == '1400.00'
    assert second['items'][0]['unit_price'] == '1500.00'


def test_orders_are_isolated_between_application_instances():
    from app.main import create_test_app as create_app

    first_app = TestClient(create_app())
    second_app = TestClient(create_app())
    _, first_headers = register_and_token(first_app, 'same@example.com')
    _, second_headers = register_and_token(second_app, 'same@example.com')

    first_app.post('/api/v1/cart/items', headers=first_headers, json={'variant_id': 20, 'quantity': 1})
    assert first_app.post('/api/v1/orders', headers=first_headers).status_code == 201
    assert len(first_app.get('/api/v1/orders', headers=first_headers).json()) == 1
    assert second_app.get('/api/v1/orders', headers=second_headers).json() == []


def test_openapi_reports_v05_and_order_routes(client):
    schema = client.get('/openapi.json').json()
    assert schema['info']['version'] == '0.14.0'
    assert '/api/v1/orders' in schema['paths']
    assert '/api/v1/orders/{order_id}' in schema['paths']
    assert {'HTTPBearer': []} in schema['paths']['/api/v1/orders']['post']['security']
    assert {'201', '401', '409', '422'} <= set(schema['paths']['/api/v1/orders']['post']['responses'])
    assert {'200', '401', '404', '422'} <= set(schema['paths']['/api/v1/orders/{order_id}']['get']['responses'])
