"""Regression contracts for catalog discovery and administrator work queues."""
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.db.models import OrderItemORM, OrderORM, ProductORM, ProductVariantORM
from app.catalog.repository import InMemoryProductRepository, SQLAlchemyProductRepository
from app.catalog.service import CatalogService
from tests import test_admin_exports as analytics_tests

client = analytics_tests.client


@pytest.fixture
def audit_orders(client):
    now = datetime.now(timezone.utc)
    values = [
        ('warehouse', None, 'cod_pending', None, 'delivery', 'created', 30),
        ('in_transit', None, 'cod_pending', None, 'delivery', 'created', 2),
        ('nearby', None, 'cod_pending', None, 'delivery', 'created', 2),
        ('in_transit', 'engine_failure', 'cod_pending', None, 'delivery', 'created', 30),
        ('nearby', None, 'cod_pending', now, 'delivery', 'created', 2),
        ('warehouse', None, 'pending', None, 'delivery', 'created', 30),
        (None, None, 'cod_pending', None, 'pickup', 'created', 30),
        ('warehouse', None, 'cancelled', None, 'delivery', 'cancelled', 30),
    ]
    ids = []
    with client.app.state.database.session_factory.begin() as session:
        for stage, incident, payment, received, method, status, hours in values:
            row = OrderORM(user_id=1, status=status, created_at=now - timedelta(hours=40),
                delivery_method=method, payment_method='demo' if payment == 'pending' else 'cod',
                payment_status=payment, received_at=received, delivery_stage=stage,
                delivery_incident=incident, delivery_updated_at=now - timedelta(hours=hours),
                delivery_version=1 if incident else 0,
                delivery_incident_note='Private incident note' if incident else None,
                delivery_history=[{'event_type': 'incident_reported', 'stage': stage,
                    'incident': incident, 'note': '=private contact note',
                    'occurred_at': (now - timedelta(hours=hours)).isoformat()}] if incident else [])
            session.add(row)
            session.flush()
            session.add(OrderItemORM(order_id=row.id, product_id=2, variant_id=20,
                product_name='Historical food', variant_label='500 g', sku='HISTORY',
                unit_price=100, currency='KZT', quantity=1))
            ids.append(row.id)
    return ids


@pytest.mark.parametrize('query,pet', [('кошки', 'cat'), ('котёнок', 'cat'), ('котенка', 'cat'),
    ('собаки', 'dog'), ('щенок', 'dog'), ('птицы', 'bird'), ('хомяк', 'small_pet'),
    ('рыбки', 'fish'), ('рептилии', 'reptile'), ('лягушки', 'amphibian'),
    ('пауки', 'invertebrate')])
def test_search_pet_aliases(client, query, pet):
    # Seed one item for every supported pet; the name deliberately contains no pet words.
    with client.app.state.database.session_factory.begin() as session:
        product = ProductORM(name='Alias fixture', name_normalized='alias fixture', pet_type=pet,
            brand='SpecialBrand', brand_normalized='specialbrand', category='food',
            product_kind='food', composition='Test composition')
        session.add(product)
        session.flush()
        session.add(ProductVariantORM(product_id=product.id, sku='ALIAS-FIXTURE',
            sku_normalized='alias-fixture', label='1 kg', price=100, currency='KZT', stock=7))
        fixture_id = product.id
    response = client.get('/api/v1/products', params={'q': query, 'page_size': 100})
    assert response.status_code == 200
    assert fixture_id in {row['id'] for row in response.json()['items']}
    assert all(row['pet_type'] == pet for row in response.json()['items'])


def test_search_brand_kind_filters_and_escaped_literals(client):
    with client.app.state.database.session_factory.begin() as session:
        product = session.get(ProductORM, 2)
        product.name = 'Test food'
        product.brand = 'Brand Only'
        product.pet_type = 'cat'
        product.product_kind = 'food'
    params = {'q': 'корм для кошек Brand', 'category': 'food', 'in_stock': True}
    response = client.get('/api/v1/products', params=params)
    assert response.status_code == 200
    assert [row['id'] for row in response.json()['items']] == [2]
    for query in ['%', '_', "' OR 1=1 --"]:
        assert client.get('/api/v1/products', params={'q': query}).json()['total'] == 0


def test_inmemory_search_matches_sql_adapter_with_filters_and_sort(client):
    with client.app.state.database.session_factory() as session:
        sql = SQLAlchemyProductRepository(session)
        domain = CatalogService(InMemoryProductRepository(list(sql.all())))
        for query in ['кошки', 'корм для собак DemoPet', 'аксессуары', 'DEMO-2-S', '%']:
            filters = {'q': query, 'in_stock': True, 'sort': 'price_desc', 'page_size': 3}
            expected = CatalogService(sql).list_products(**filters)
            actual = domain.list_products(**filters)
            assert actual['total'] == expected['total']
            assert [row['id'] for row in actual['items']] == [row['id'] for row in expected['items']]


def test_food_kind_alias_preserves_legacy_category_without_product_kind(client):
    with client.app.state.database.session_factory.begin() as session:
        for product in session.scalars(select(ProductORM).where(ProductORM.category == 'food')):
            product.product_kind = None
    result = client.get('/api/v1/products', params={'q': 'корма для кошек'}).json()
    assert {row['id'] for row in result['items']} == {1, 3, 5, 7, 9}


@pytest.mark.parametrize('queue,indices', [('active', [0, 1, 2, 3, 5, 6]),
    ('warehouse', [0]), ('in_transit', [1]), ('incidents', [3]),
    ('awaiting_receipt', [2]), ('received', [4])])
def test_queue_counts_match_list(client, audit_orders, queue, indices):
    response = client.get('/api/v1/admin/orders', headers=client.admin, params={'queue': queue})
    assert response.status_code == 200
    assert {row['id'] for row in response.json()['items']} == {audit_orders[i] for i in indices}
    dashboard = client.get('/api/v1/admin/dashboard', headers=client.admin).json()
    assert dashboard['order_queues'][queue] == response.json()['total']


def test_delivery_filters_compose_and_stale_only_active_delivery(client, audit_orders):
    response = client.get('/api/v1/admin/orders', headers=client.admin,
        params={'delivery_stage': 'in_transit', 'delivery_incident': 'engine_failure',
                'received': False, 'stale_hours': 24})
    assert response.status_code == 200
    assert [row['id'] for row in response.json()['items']] == [audit_orders[3]]
    response = client.get('/api/v1/admin/orders', headers=client.admin, params={'stale_hours': 24})
    assert {row['id'] for row in response.json()['items']} == {
        audit_orders[0], audit_orders[3], audit_orders[5]}


@pytest.mark.parametrize('params', [{'delivery_stage': 'flying'}, {'delivery_incident': 'invalid'},
    {'received': 'maybe'}, {'queue': 'unknown'}, {'stale_hours': 0}, {'stale_hours': 8761}])
def test_invalid_work_queue_filters_rejected(client, params):
    assert client.get('/api/v1/admin/orders', headers=client.admin, params=params).status_code == 422


def test_admin_products_stock_filter_and_user_page_backwards_compatibility(client):
    with client.app.state.database.session_factory.begin() as session:
        variants = session.scalars(select(ProductVariantORM).order_by(ProductVariantORM.id)).all()
        for variant in variants:
            variant.stock = 10
        variant = next(row for row in variants if row.product_id == 2)
        variant.stock = 2
        variant.sku = 'LOW-ONLY'
    assert client.get('/api/v1/admin/products').status_code == 401
    assert client.get('/api/v1/admin/products', headers=client.customer).status_code == 403
    result = client.get('/api/v1/admin/products', headers=client.admin,
        params={'stock_max': 5, 'q': 'LOW-ONLY', 'page_size': 1}).json()
    assert result['total'] == 1 and result['items'][0]['id'] == 2
    assert result['page_size'] == result['page'] == 1
    dashboard = client.get('/api/v1/admin/dashboard', headers=client.admin).json()
    assert dashboard['low_stock_products'] == dashboard['low_stock_variants'] == 1
    page = client.get('/api/v1/admin/users/page', headers=client.admin,
        params={'limit': 1, 'offset': 2})
    assert page.status_code == 200
    assert page.json() == {'items': [], 'total': 2, 'limit': 1, 'offset': 2}
    assert isinstance(client.get('/api/v1/admin/users', headers=client.admin).json(), list)
    for params in ({'stock_max': -1}, {'q': 'a' * 101}, {'page': 0}):
        assert client.get('/api/v1/admin/products', headers=client.admin, params=params).status_code == 422
