"""Audit query/export regressions on a disposable PostgreSQL schema."""
from io import BytesIO

from fastapi.testclient import TestClient
from openpyxl import load_workbook
import pytest
from sqlalchemy import text
from sqlalchemy.engine import make_url

from app.catalog.repository import SQLAlchemyProductRepository
from app.main import create_test_app
from tests import test_postgresql as pg_support
from tests.helpers import admin_headers
from tests.test_v090_features import customer

pytestmark = pytest.mark.postgresql
pg_empty = pg_support.pg_empty
pg = pg_support.pg


def test_admin_audit_search_queue_and_export_snapshot_on_postgresql(pg):
    with pg.engine.connect() as connection:
        schema = connection.scalar(text('SELECT current_schema()'))
    isolated_url = make_url(pg.url).update_query_dict({'options': f'-csearch_path={schema} -clock_timeout=10000'})
    app = create_test_app(isolated_url.render_as_string(hide_password=False))
    app.state.isolated_test_schema = True
    client = TestClient(app)
    owner = customer(client, 'audit-pg-owner@example.test')
    admin = admin_headers(client, 'audit-pg-admin@example.test')
    result = client.get('/api/v1/products', params={'q': 'кошки Brand'})
    assert result.status_code == 200
    assert [row['id'] for row in result.json()['items']] == [1]
    with pg.session_factory.begin() as session:
        SQLAlchemyProductRepository(session).set_variant_stock(2, 2)
    low = client.get('/api/v1/admin/products', headers=admin, params={'stock_max': 5})
    assert low.status_code == 200 and low.json()['total'] == 1
    assert client.get('/api/v1/admin/products', headers=owner).status_code == 403
    assert client.post('/api/v1/cart/items', headers=owner,
                       json={'variant_id': 1, 'quantity': 1}).status_code == 200
    purchase = client.post('/api/v1/orders', headers=owner, json={
        'contact_name': 'Audit buyer', 'phone': '77001234567',
        'delivery_method': 'delivery', 'address': 'Almaty, Abay 10',
        'payment_method': 'demo'})
    assert purchase.status_code == 201
    order_id = purchase.json()['id']
    assert client.patch(f'/api/v1/admin/orders/{order_id}/delivery', headers=admin, json={
        'expected_version': 0, 'incident': 'engine_failure',
        'incident_note': 'Private note 77001234567'}).status_code == 200
    queue = client.get('/api/v1/admin/orders', headers=admin, params={'queue': 'incidents'})
    assert queue.status_code == 200 and [row['id'] for row in queue.json()['items']] == [order_id]
    dashboard = client.get('/api/v1/admin/dashboard', headers=admin).json()
    assert dashboard['order_queues']['incidents'] == 1
    response = client.get('/api/v1/admin/exports/orders', headers=admin,
                          params={'queue': 'incidents'})
    assert response.status_code == 200
    workbook = load_workbook(BytesIO(response.content), read_only=True, data_only=True)
    try:
        orders = list(workbook['Orders'].values)
        events = list(workbook['DeliveryEvents'].values)
        columns = orders[0]
        assert orders[1][columns.index('id')] == order_id
        assert orders[1][columns.index('delivery_incident')] == 'engine_failure'
        assert 'delivery_incident_note' not in columns
        assert 'note' not in events[0]
        assert len(events) == 3
    finally:
        workbook.close()
    users = client.get('/api/v1/admin/users/page', headers=admin,
                       params={'offset': 100, 'limit': 50}).json()
    assert users['items'] == [] and users['total'] == 4
