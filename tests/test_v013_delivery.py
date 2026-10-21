"""Delivery state machine, administrator boundaries and persistent journey history."""
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.db.session import Database
from app.main import create_test_app
from tests.helpers import admin_headers
from tests.test_v090_features import customer, order


@pytest.fixture
def shop():
    with TestClient(create_test_app()) as client:
        owner = customer(client, 'delivery-owner@example.test')
        admin = admin_headers(client)
        yield client, owner, admin


def purchase(shop, *, payment='cod', method='delivery'):
    client, owner, _ = shop
    return order(client, owner, payment=payment, quantity=1,
                 extra={'delivery_method': method, 'address': 'Алматы, улица Абая, дом 10'} if method == 'delivery' else {})


def update(shop, purchase_id, version, **values):
    client, _, admin = shop
    return client.patch(f'/api/v1/admin/orders/{purchase_id}/delivery', headers=admin,
                        json={'expected_version': version, **values})


def test_three_stages_incidents_history_and_receipt(shop):
    client, owner, admin = shop
    placed = purchase(shop)
    order_id = placed['id']
    tracking = placed['delivery_tracking']
    assert tracking['stage'] == 'warehouse' and tracking['version'] == 0
    assert tracking['incident'] is None and tracking['incident_note'] is None
    assert tracking['updated_at'] == placed['created_at']
    assert [item['event_type'] for item in tracking['history']] == ['created']
    assert client.post(f'/api/v1/orders/{order_id}/confirm-receipt', headers=owner).status_code == 409
    assert update(shop, order_id, 0, stage='nearby').status_code == 409
    unchanged = update(shop, order_id, 0, stage='warehouse')
    assert unchanged.status_code == 200 and unchanged.json()['delivery_tracking'] == tracking
    moving = update(shop, order_id, 0, stage='in_transit')
    assert moving.status_code == 200, moving.text
    assert moving.json()['customer_email'] == 'delivery-owner@example.test'
    assert update(shop, order_id, 0, stage='in_transit').status_code == 409
    assert update(shop, order_id, 1, stage='warehouse').status_code == 409
    broken = update(shop, order_id, 1, incident='flat_tire', incident_note='  Меняем колесо  ')
    assert broken.status_code == 200, broken.text
    broken_tracking = broken.json()['delivery_tracking']
    assert broken_tracking['stage'] == 'in_transit' and broken_tracking['incident_note'] == 'Меняем колесо'
    assert update(shop, order_id, 2, incident='flat_tire', incident_note='Меняем колесо').json()['delivery_tracking'] == broken_tracking
    assert update(shop, order_id, 2, stage='nearby').status_code == 409
    assert client.post(f'/api/v1/orders/{order_id}/cancel', headers=owner).status_code == 409
    assert update(shop, order_id, 2, incident=None).status_code == 200
    arrived = update(shop, order_id, 3, stage='nearby')
    assert arrived.status_code == 200, arrived.text
    nearby_tracking = arrived.json()['delivery_tracking']
    assert nearby_tracking['version'] == 4
    assert nearby_tracking['incident'] is None and nearby_tracking['incident_note'] is None
    assert [item['event_type'] for item in nearby_tracking['history']] == [
        'created', 'stage_changed', 'incident_reported', 'incident_resolved', 'stage_changed']
    event_times = [item['occurred_at'] for item in nearby_tracking['history']]
    assert event_times == sorted(event_times)
    assert nearby_tracking['history'][2]['incident'] == 'flat_tire'
    assert nearby_tracking['history'][3]['incident'] is None
    assert client.get(f'/api/v1/orders/{order_id}', headers=owner).json()['delivery_tracking'] == nearby_tracking
    assert client.get('/api/v1/orders', headers=owner).json()[0]['delivery_tracking'] == nearby_tracking
    assert client.get(f'/api/v1/admin/orders/{order_id}', headers=admin).json()['delivery_tracking'] == nearby_tracking
    assert client.get('/api/v1/admin/orders', headers=admin).json()['items'][0]['delivery_tracking'] == nearby_tracking
    # Nearby means the customer may receive the order, not that it was received automatically.
    review_path = '/api/v1/products/2/reviews'
    review = {'order_id': order_id, 'rating': 5, 'body': 'Всё пришло, спасибо за доставку.'}
    assert client.post(review_path, headers=owner, json=review).status_code == 409
    receipt = client.post(f'/api/v1/orders/{order_id}/confirm-receipt', headers=owner)
    assert receipt.status_code == 200, receipt.text
    assert receipt.json()['received_at']
    assert client.post(f'/api/v1/orders/{order_id}/confirm-receipt', headers=owner).json()['received_at'] == receipt.json()['received_at']
    assert update(shop, order_id, 4, incident='flat_tire').status_code == 409
    assert update(shop, order_id, 4, stage='nearby').status_code == 409
    assert client.post(review_path, headers=owner, json=review).status_code == 201


@pytest.mark.parametrize('stage,version', [('warehouse', 0), ('in_transit', 1), ('nearby', 2)])
@pytest.mark.parametrize('incident', ['flat_tire', 'overturned', 'engine_failure'])
def test_each_incident_blocks_any_stage_until_resolved(shop, stage, version, incident):
    client, owner, _ = shop
    order_id = purchase(shop)['id']
    for expected, next_stage in enumerate(('in_transit', 'nearby')[:version]):
        assert update(shop, order_id, expected, stage=next_stage).status_code == 200
    broken = update(shop, order_id, version, incident=incident, incident_note='Тестовая поломка')
    assert broken.status_code == 200, broken.text
    assert broken.json()['delivery_tracking']['stage'] == stage
    assert broken.json()['delivery_tracking']['incident'] == incident
    assert client.post(f'/api/v1/orders/{order_id}/confirm-receipt', headers=owner).status_code == 409
    if stage != 'nearby':
        next_stage = 'in_transit' if stage == 'warehouse' else 'nearby'
        assert update(shop, order_id, version + 1, stage=next_stage).status_code == 409
    resolved = update(shop, order_id, version + 1, incident=None)
    assert resolved.status_code == 200 and resolved.json()['delivery_tracking']['incident'] is None
    assert resolved.json()['delivery_tracking']['stage'] == stage


def test_payment_pickup_cancelled_and_inventory_guards(shop):
    client, owner, _ = shop
    demo = purchase(shop, payment='demo')
    path = f"/api/v1/orders/{demo['id']}"
    assert update(shop, demo['id'], 0, stage='in_transit').status_code == 409
    assert client.post(path + '/demo-payment', headers=owner, json={'outcome': 'failure'}).status_code == 200
    assert update(shop, demo['id'], 0, stage='in_transit').status_code == 409
    assert client.post(path + '/demo-payment', headers=owner, json={'outcome': 'success'}).status_code == 200
    assert update(shop, demo['id'], 0, stage='in_transit').status_code == 200
    pickup = purchase(shop, method='pickup')
    assert pickup['delivery_tracking'] is None
    assert update(shop, pickup['id'], 0, stage='in_transit').status_code == 409
    assert client.post(f"/api/v1/orders/{pickup['id']}/confirm-receipt", headers=owner).status_code == 200
    cancelled = purchase(shop)
    stock = client.get('/api/v1/products/2').json()['variants'][0]['stock']
    assert client.post(f"/api/v1/orders/{cancelled['id']}/cancel", headers=owner).status_code == 200
    assert client.get('/api/v1/products/2').json()['variants'][0]['stock'] == stock + 1
    assert update(shop, cancelled['id'], 0, stage='in_transit').status_code == 409
    assert update(shop, cancelled['id'], 0, incident='overturned').status_code == 409
    assert client.post(f"/api/v1/orders/{cancelled['id']}/cancel", headers=owner).status_code == 200
    assert client.get('/api/v1/products/2').json()['variants'][0]['stock'] == stock + 1


def test_admin_ownership_json_and_cookie_origin_guards(shop):
    client, owner, admin = shop
    placed = purchase(shop)
    path = f"/api/v1/admin/orders/{placed['id']}/delivery"
    valid = {'expected_version': 0, 'stage': 'in_transit'}
    assert client.patch(path, json=valid).status_code == 401
    assert client.patch(path, json=valid, headers=owner).status_code == 403
    other = customer(client, 'delivery-other@example.test')
    assert client.get(f"/api/v1/orders/{placed['id']}", headers=other).status_code == 404
    assert client.patch(f"/api/v1/orders/{placed['id']}/delivery", json=valid, headers=owner).status_code == 404
    invalid = [{}, {'expected_version': 0}, {'expected_version': 0, 'stage': None},
               {'expected_version': 0, 'stage': 'in_transit', 'incident': None},
               {'expected_version': -1, 'stage': 'in_transit'},
               {'expected_version': True, 'stage': 'in_transit'},
               {'expected_version': 0, 'stage': 'flying'},
               {'expected_version': 0, 'incident': 'unknown'},
               {'expected_version': 0, 'stage': 'in_transit', 'incident_note': 'Text'},
               {'expected_version': 0, 'incident': None, 'incident_note': 'Text'},
               {'expected_version': 0, 'incident': 'flat_tire', 'incident_note': 'x' * 501},
               {'expected_version': 0, 'incident': 'flat_tire', 'extra': True}]
    for body in invalid:
        response = client.patch(path, headers=admin, json=body)
        assert response.status_code == 422, (body, response.text)
    assert client.patch('/api/v1/admin/orders/2147483647/delivery', json=valid, headers=admin).status_code == 404
    # Session-cookie administrator writes require a trusted Origin, like all admin writes.
    response = client.post('/api/v1/auth/browser/login', json={
        'email': 'test-admin@example.com', 'password': 'StrongAdmin123'},
        headers={'Origin': 'http://testserver'})
    assert response.status_code == 200
    csrf = {'Origin': 'http://testserver', 'X-CSRF-Token': client.cookies['pitomo_csrf']}
    assert client.patch(path, json=valid, headers={'Origin': 'http://testserver'}).status_code == 403
    assert client.patch(path, json=valid, headers={**csrf, 'Origin': 'https://untrusted.example'}).status_code == 403
    assert client.get(f"/api/v1/orders/{placed['id']}", headers=owner).json()['delivery_tracking']['version'] == 0
    assert client.patch(path, json=valid, headers=csrf).status_code == 200


def test_upgrade_preserves_old_orders_without_fabricating_history(tmp_path):
    database = Database(f'sqlite+pysqlite:///{tmp_path / "delivery-migration.db"}')
    config = Config(str(Path(__file__).resolve().parents[1] / 'alembic.ini'))
    config.attributes['database_url'] = database.url
    try:
        command.upgrade(config, '0010_v012')
        with database.engine.begin() as connection:
            connection.execute(text("INSERT INTO users(id,email,password_hash,first_name,is_active,role) "
                "VALUES(1,'legacy@example.test','hash','Legacy',1,'customer')"))
            for order_id, method, received, status in [
                (1, 'delivery', None, 'created'), (2, 'delivery', '2026-10-01T10:00:00', 'created'),
                (3, 'delivery', None, 'cancelled'), (4, 'pickup', None, 'created')]:
                connection.execute(text("INSERT INTO orders(id,user_id,status,created_at,delivery_method,"
                    "payment_method,payment_status,received_at) VALUES(:id,1,:status,'2026-10-01T09:00:00',"
                    ":method,'cod',:payment,:received)"),
                    {'id': order_id, 'method': method, 'received': received,
                     'status': status, 'payment': 'cancelled' if status == 'cancelled' else 'cod_pending'})
            connection.execute(text("INSERT INTO order_items(id,order_id,product_id,product_name,"
                "variant_id,sku,variant_label,unit_price,currency,quantity) "
                "VALUES(1,1,7,'Legacy food',70,'LEGACY-SKU','500 g',10.25,'KZT',2)"))
        command.upgrade(config, 'head')
        with database.engine.connect() as connection:
            records = connection.execute(text('SELECT id,delivery_stage,delivery_incident,delivery_updated_at,'
                'delivery_version,delivery_history FROM orders ORDER BY id')).all()
            assert records == [(1, 'warehouse', None, None, 0, '[]'),
                               (2, 'nearby', None, None, 0, '[]'),
                               (3, 'warehouse', None, None, 0, '[]'),
                               (4, None, None, None, 0, '[]')]
            assert connection.scalar(text('SELECT COUNT(*) FROM users')) == 1
            assert connection.scalar(text('SELECT COUNT(*) FROM orders')) == 4
            assert connection.execute(text('SELECT id,order_id,product_name,unit_price,quantity '
                                           'FROM order_items')).one() == (1, 1, 'Legacy food', 10.25, 2)
            assert connection.exec_driver_sql('PRAGMA foreign_key_check').first() is None
            assert connection.scalar(text('SELECT version_num FROM alembic_version')) == '0012_v014'
        command.check(config)
    finally:
        database.dispose()
