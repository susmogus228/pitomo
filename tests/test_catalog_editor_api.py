"""Editable category fields and base-price semantics for the admin editor."""
from fastapi.testclient import TestClient

from app.main import create_test_app
from tests.helpers import admin_headers


def test_editor_fields_create_edit_and_discount_base_price():
    with TestClient(create_test_app()) as client:
        admin = admin_headers(client)
        payload = {'name': 'Корм редактора', 'pet_type': 'cat', 'brand': 'Питомо',
                   'category': 'food', 'product_kind': 'food', 'composition': 'Мясо, рис',
                   'variants': [{'sku': 'EDITOR-FOOD', 'label': '500 г', 'price': '1000.00', 'stock': 4}]}
        created = client.post('/api/v1/products', json=payload, headers=admin)
        assert created.status_code == 201, created.text
        product = created.json()
        path = f"/api/v1/products/{product['id']}"
        assert product['composition'] == payload['composition'] and product['material'] is None
        updated = client.patch(path, json={'composition': 'Мясо, рис, овощи'}, headers=admin)
        assert updated.json()['composition'] == 'Мясо, рис, овощи'
        assert client.patch(path, json={'material': 'Пластик'}, headers=admin).status_code == 422
        assert client.patch(path, json={'category': 'accessory'}, headers=admin).status_code == 422
        assert client.put(f"/api/v1/admin/products/{product['id']}/discount",
                          json={'percent': 20}, headers=admin).status_code == 200
        detail = client.get(path).json()
        variant = detail['variants'][0]
        assert variant['price'] == '800.00' and variant['original_price'] == '1000.00'
        variant_path = f"{path}/variants/{variant['id']}"
        saved = client.patch(variant_path, json={'label': 'Упаковка 500 г', 'price': variant['original_price']}, headers=admin)
        assert saved.status_code == 200, saved.text
        assert saved.json()['price'] == '800.00' and saved.json()['stock'] == 4
        assert client.get(path).json()['variants'][0]['original_price'] == '1000.00'
        assert client.get('/api/v1/products', params={'q': payload['name']}).json()['items'][0]['composition'] == 'Мясо, рис, овощи'


def test_accessory_editor_reads_material_and_customer_cannot_edit():
    with TestClient(create_test_app()) as client:
        admin = admin_headers(client)
        payload = {'name': 'Миска редактора', 'pet_type': 'bird', 'brand': 'Питомо',
                   'category': 'accessory', 'product_kind': 'bowls', 'material': 'Керамика',
                   'variants': [{'sku': 'EDITOR-BOWL', 'label': '300 мл', 'price': '900.00', 'stock': 2}]}
        created = client.post('/api/v1/products', json=payload, headers=admin)
        assert created.status_code == 201, created.text
        product = created.json()
        assert product['material'] == 'Керамика' and product['composition'] is None
        client.cookies.clear()
        assert client.patch(f"/api/v1/products/{product['id']}", json={'material': 'Металл'}).status_code == 401
