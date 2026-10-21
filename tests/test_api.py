from fastapi.testclient import TestClient
import pytest


@pytest.fixture
def client():
    from app.main import create_test_app as create_app
    return TestClient(create_app())


def test_catalog_pages_and_variants(client):
    response = client.get('/api/v1/products?page_size=3&page=2')
    assert response.status_code == 200
    data = response.json()
    assert data['total'] == 20
    assert [p['id'] for p in data['items']] == [4, 5, 6]
    item = client.get('/api/v1/products/1').json()
    assert len(item['variants']) == 2
    assert item['variants'][0]['currency'] == 'KZT'
    assert isinstance(item['variants'][0]['price'], str)


def test_search_and_filters(client):
    data = client.get('/api/v1/products', params={
        'q': 'КОРМ', 'pet_type': 'cat', 'category': 'food', 'brand': 'DemoPet',
        'min_price': '2000', 'max_price': '5000', 'in_stock': True,
    }).json()
    assert data['items']
    for p in data['items']:
        assert p['pet_type'] == 'cat'
        assert any(2000 <= float(v['price']) <= 5000 and v['stock'] > 0
                   for v in p['variants'])


def test_price_and_stock_must_match_same_variant(client):
    # Product 1: small pack at 1000 is sold out, large at 6000 is in stock.
    data = client.get('/api/v1/products?max_price=1500&in_stock=true').json()
    assert 1 not in [p['id'] for p in data['items']]


@pytest.mark.parametrize('query', ['page=0', 'page_size=101', 'min_price=-1',
                                   'min_price=500&max_price=100', 'pet_type=dragon',
                                   'min_price=NaN', 'sort=unknown'])
def test_invalid_filters(client, query):
    assert client.get('/api/v1/products?' + query).status_code == 422


def test_missing_and_empty_results(client):
    assert client.get('/api/v1/products/999').status_code == 404
    assert client.get('/api/v1/products?q=doesnotexist').json()['items'] == []
    assert client.get('/api/v1/products?page=999').json()['items'] == []


def test_docs_and_references(client):
    assert client.get('/health').json() == {'status': 'ok', 'storage': 'memory'}
    assert client.get('/docs').status_code == 200
    assert '/api/v1/products' in client.get('/openapi.json').json()['paths']
    assert client.get('/api/v1/categories').json() == [
        {'id': 'food', 'name': 'Корма'}, {'id': 'accessory', 'name': 'Аксессуары'}]
    assert client.get('/api/v1/brands').json() == ['DemoPet', 'DemoZoo']
