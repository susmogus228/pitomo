"""Delivery analytics stay aligned with work queues and contact opt-in."""
import pytest
from sqlalchemy import select

from app.db.models import OrderORM, ProductVariantORM

from tests import test_admin_exports as analytics_tests
from tests import test_audit_repairs as repair_tests

client = analytics_tests.client
audit_orders = repair_tests.audit_orders
_xlsx_response, _sheet, _zip_response = (
    analytics_tests._xlsx_response, analytics_tests._sheet, analytics_tests._zip_response)


def test_delivery_export_filters_history_and_contact_notes(client, audit_orders):
    params = {'delivery_stage': 'in_transit', 'delivery_incident': 'engine_failure',
              'received': False, 'stale_hours': 24, 'queue': 'incidents'}
    workbook = _xlsx_response(client, 'orders', **params)
    try:
        orders = _sheet(workbook, 'Orders')
        assert [row['id'] for row in orders] == [audit_orders[3]]
        assert orders[0]['delivery_stage'] == 'in_transit'
        assert orders[0]['delivery_incident'] == 'engine_failure'
        assert orders[0]['delivery_version'] == 1
        assert orders[0]['delivery_updated_at']
        assert 'delivery_incident_note' not in orders[0]
        events = _sheet(workbook, 'DeliveryEvents')
        assert len(events) == 1 and events[0]['order_id'] == audit_orders[3]
        assert events[0]['event_type'] == 'incident_reported' and 'note' not in events[0]
        metadata = {row['key']: row['value'] for row in _sheet(workbook, 'Metadata')}
        for key, value in params.items():
            assert metadata[key] == value
    finally:
        workbook.close()
    archive = _zip_response(client, 'orders', include_contacts='true', **params)
    assert archive['Orders.csv'][0]['delivery_incident_note'] == 'Private incident note'
    assert archive['DeliveryEvents.csv'][0]['note'] == "'=private contact note"


@pytest.mark.parametrize('params', [{'delivery_stage': 'flying'}, {'delivery_incident': 'invalid'},
    {'received': 'maybe'}, {'queue': 'unknown'}, {'stale_hours': 0}, {'stale_hours': 8761},
    {'stock_max': -1}])
def test_export_validates_new_filter_bounds(client, params):
    assert client.get('/api/v1/admin/exports/orders', headers=client.admin,
        params=params).status_code == 422


def test_low_stock_export_matches_products_list_and_preserves_sibling_skus(client):
    with client.app.state.database.session_factory.begin() as session:
        for row in session.scalars(select(ProductVariantORM)):
            row.stock = 10
        session.get(ProductVariantORM, 20).stock = 2
    workbook = _xlsx_response(client, 'products', stock_max=5)
    try:
        assert [row['id'] for row in _sheet(workbook, 'Products')] == [2]
        assert {row['id'] for row in _sheet(workbook, 'Variants')} == {20, 21}
        assert {row['key']: row['value'] for row in _sheet(workbook, 'Metadata')}['stock_max'] == 5
    finally:
        workbook.close()


@pytest.mark.parametrize('payment_status', ['pending', 'failed'])
def test_warehouse_incident_before_payment_is_visible_in_queue_counts_and_export(
        client, audit_orders, payment_status):
    order_id = audit_orders[5]
    with client.app.state.database.session_factory.begin() as session:
        session.get(OrderORM, order_id).payment_status = payment_status
    # Reporting an incident on the warehouse stage is allowed before payment.
    response = client.patch(f'/api/v1/admin/orders/{order_id}/delivery', headers=client.admin,
        json={'expected_version': 0, 'incident': 'engine_failure'})
    assert response.status_code == 200, response.text
    queue = client.get('/api/v1/admin/orders', headers=client.admin,
        params={'queue': 'incidents'}).json()
    assert {row['id'] for row in queue['items']} == {audit_orders[3], order_id}
    dashboard = client.get('/api/v1/admin/dashboard', headers=client.admin).json()
    assert dashboard['order_queues']['incidents'] == queue['total'] == 2
    archive = _zip_response(client, 'orders', queue='incidents')
    assert {int(row['id']) for row in archive['Orders.csv']} == {audit_orders[3], order_id}
    warehouse = client.get('/api/v1/admin/orders', headers=client.admin,
        params={'queue': 'warehouse'}).json()
    assert {row['id'] for row in warehouse['items']} == {audit_orders[0]}
