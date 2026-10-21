from fastapi.testclient import TestClient
import pytest

from tests.helpers import admin_headers


@pytest.fixture
def client():
    from app.main import create_test_app as create_app
    client = TestClient(create_app())
    client.headers.update(admin_headers(client, 'catalog-v02-admin@example.com'))
    return client


def food_payload(sku='NEW-FOOD-400'):
    return {
        'name': 'Новый корм',
        'pet_type': 'cat',
        'brand': 'TestBrand',
        'category': 'food',
        'composition': 'индейка, рис',
        'variants': [
            {'sku': sku, 'label': '400 г', 'price': '3200.00', 'stock': 10},
        ],
    }


def accessory_payload(sku='NEW-ACC-S'):
    return {
        'name': 'Новый ошейник',
        'pet_type': 'dog',
        'brand': 'TestBrand',
        'category': 'accessory',
        'material': 'нейлон',
        'variants': [
            {'sku': sku, 'label': 'S', 'price': '2500.00', 'stock': 5},
        ],
    }


def test_create_food_and_read_it(client):
    response = client.post('/api/v1/products', json=food_payload())
    assert response.status_code == 201
    product = response.json()
    assert product['id'] == 21
    assert product['category'] == 'food'
    assert product['description'].endswith('Состав: индейка, рис.')
    assert product['variants'][0]['currency'] == 'KZT'
    assert client.get(f"/api/v1/products/{product['id']}").json() == product


def test_create_accessory(client):
    response = client.post('/api/v1/products', json=accessory_payload())
    assert response.status_code == 201
    assert response.json()['category'] == 'accessory'
    assert 'Материал: нейлон.' in response.json()['description']


@pytest.mark.parametrize(
    ('payload', 'detail'),
    [
        ({**food_payload(), 'composition': None}, 'composition'),
        ({**accessory_payload(), 'material': None}, 'material'),
        ({**food_payload(), 'material': 'лишнее поле'}, 'material'),
        ({**accessory_payload(), 'composition': 'лишнее поле'}, 'composition'),
    ],
)
def test_category_specific_fields(client, payload, detail):
    response = client.post('/api/v1/products', json=payload)
    assert response.status_code == 422
    assert detail in response.json()['detail']


def test_duplicate_sku_conflict(client):
    payload = food_payload('DEMO-1-S')
    response = client.post('/api/v1/products', json=payload)
    assert response.status_code == 409


def test_duplicate_sku_inside_same_request(client):
    payload = food_payload('X-1')
    payload['variants'].append({'sku': 'x-1', 'label': '2 кг', 'price': '6000', 'stock': 2})
    assert client.post('/api/v1/products', json=payload).status_code == 409


def test_patch_product(client):
    response = client.patch('/api/v1/products/1', json={
        'name': 'Обновлённый корм',
        'brand': 'UpdatedBrand',
        'composition': 'лосось',
    })
    assert response.status_code == 200
    data = response.json()
    assert data['name'] == 'Обновлённый корм'
    assert data['brand'] == 'UpdatedBrand'
    assert data['description'].endswith('Состав: лосось.')


def test_patch_wrong_category_field(client):
    response = client.patch('/api/v1/products/1', json={'material': 'кожа'})
    assert response.status_code == 422


def test_product_category_cannot_be_patched(client):
    response = client.patch('/api/v1/products/1', json={'category': 'accessory'})
    assert response.status_code == 422


def test_add_and_update_variant(client):
    created = client.post('/api/v1/products/1/variants', json={
        'sku': 'NEW-VARIANT', 'label': '5 кг', 'price': '9000', 'stock': 4,
    })
    assert created.status_code == 201
    variant_id = created.json()['id']

    updated = client.patch(f'/api/v1/products/1/variants/{variant_id}', json={
        'sku': 'NEW-VARIANT-UPDATED', 'price': '9500.50', 'stock': 7,
    })
    assert updated.status_code == 200
    assert updated.json()['sku'] == 'NEW-VARIANT-UPDATED'
    assert updated.json()['price'] == '9500.50'
    assert updated.json()['stock'] == 7


def test_variant_duplicate_sku_conflict(client):
    response = client.post('/api/v1/products/1/variants', json={
        'sku': 'DEMO-2-S', 'label': 'test', 'price': '1', 'stock': 0,
    })
    assert response.status_code == 409


def test_delete_variant(client):
    response = client.delete('/api/v1/products/1/variants/11')
    assert response.status_code == 204
    ids = [v['id'] for v in client.get('/api/v1/products/1').json()['variants']]
    assert 11 not in ids


def test_cannot_delete_only_variant(client):
    response = client.delete('/api/v1/products/6/variants/60')
    assert response.status_code == 422


def test_missing_variant(client):
    assert client.patch('/api/v1/products/1/variants/99999', json={'stock': 1}).status_code == 404
    assert client.delete('/api/v1/products/1/variants/99999').status_code == 404


def test_delete_product(client):
    assert client.delete('/api/v1/products/20').status_code == 204
    assert client.get('/api/v1/products/20').status_code == 404
    assert client.get('/api/v1/products').json()['total'] == 19


def test_delete_missing_product(client):
    assert client.delete('/api/v1/products/999').status_code == 404


@pytest.mark.parametrize(
    'payload',
    [
        {**food_payload(), 'name': '   '},
        {**food_payload(), 'variants': []},
        {**food_payload(), 'variants': [{'sku': 'BAD', 'label': 'x', 'price': '-1', 'stock': 1}]},
        {**food_payload(), 'variants': [{'sku': 'BAD', 'label': 'x', 'price': '1', 'stock': -1}]},
    ],
)
def test_invalid_create_payload(client, payload):
    assert client.post('/api/v1/products', json=payload).status_code == 422


def test_new_brand_appears_after_create(client):
    assert 'TestBrand' not in client.get('/api/v1/brands').json()
    client.post('/api/v1/products', json=food_payload())
    assert 'TestBrand' in client.get('/api/v1/brands').json()


def test_catalog_write_routes_remain_in_openapi(client):
    schema = client.get('/openapi.json').json()
    assert schema['info']['version'] == '0.14.0'
    assert 'post' in schema['paths']['/api/v1/products']
    assert 'patch' in schema['paths']['/api/v1/products/{product_id}']
    assert 'post' in schema['paths']['/api/v1/products/{product_id}/variants']


def test_patch_rejects_null(client):
    assert client.patch('/api/v1/products/1', json={'name': None}).status_code == 422
    assert client.patch('/api/v1/products/1/variants/10', json={'sku': None}).status_code == 422


def test_root_endpoint_returns_api_info(client):
    response = client.get('/')
    assert response.status_code == 200
    assert response.json() == {
        'name': 'Petshop API',
        'version': '0.14.0',
        'status': 'running',
        'docs': '/docs',
        'health': '/health',
        'ready': '/ready',
    }
