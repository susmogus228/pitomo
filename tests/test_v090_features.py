"""End-to-end API checks for receipt, verified reviews, discounts, hits and geo."""
from tests.helpers import with_consent
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.geo import router as geo
from app.main import create_test_app
from app.db.models import OrderORM, OrderItemORM
from app.db.session import Database
from tests.helpers import admin_headers


def customer(client, email='v090-customer@example.com'):
    credentials = {'email': email, 'password': 'StrongPass123', 'first_name': 'Ирина'}
    response = client.post('/api/v1/auth/register', json=with_consent(client, credentials))
    assert response.status_code == 201, response.text
    response = client.post('/api/v1/auth/login', json={'email': email, 'password': credentials['password']})
    assert response.status_code == 200, response.text
    return {'Authorization': f"Bearer {response.json()['access_token']}"}


def order(client, headers, *, payment='cod', quantity=2, variant_id=20, extra=None):
    response = client.post('/api/v1/cart/items', json={'variant_id': variant_id, 'quantity': quantity}, headers=headers)
    assert response.status_code in {200, 201}, response.text
    details = {'contact_name': 'Ирина', 'phone': '+7 700 123 45 67',
               'delivery_method': 'pickup', 'payment_method': payment}
    details.update(extra or {})
    response = client.post('/api/v1/orders', json=details, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()


def test_receipt_review_owner_and_hits():
    with TestClient(create_test_app()) as client:
        owner = customer(client)
        other = customer(client, 'v090-other@example.com')
        purchase = order(client, owner, payment='demo')
        order_id = purchase['id']
        path = '/api/v1/products/2/reviews'
        review = {'order_id': order_id, 'rating': 5, 'body': 'Хороший корм, всё подошло.'}
        assert client.post(path, json=review, headers=owner).status_code == 409
        assert client.post(f'/api/v1/orders/{order_id}/confirm-receipt', headers=other).status_code == 404
        assert client.post(f'/api/v1/orders/{order_id}/confirm-receipt', headers=owner).status_code == 409
        assert client.post(f'/api/v1/orders/{order_id}/demo-payment', json={'outcome': 'success'}, headers=owner).status_code == 200
        receipt = client.post(f'/api/v1/orders/{order_id}/confirm-receipt', headers=owner)
        assert receipt.status_code == 200, receipt.text
        assert receipt.json()['received_at']
        assert client.post(f'/api/v1/orders/{order_id}/confirm-receipt', headers=owner).json()['received_at'] == receipt.json()['received_at']
        assert client.post(f'/api/v1/orders/{order_id}/cancel', headers=owner).status_code == 409
        assert client.post(path, json=review, headers=other).status_code == 404
        posted = client.post(path, json=review, headers=owner)
        assert posted.status_code == 201, posted.text
        assert posted.json()['author_name'] == 'Ирина'
        assert {'id', 'rating', 'body', 'created_at', 'author_name'} <= set(posted.json())
        assert client.post(path, json=review, headers=owner).status_code == 409
        page = client.get(path, params={'limit': 5, 'offset': 0})
        assert page.status_code == 200
        assert page.json()['total'] == 1 and page.json()['average_rating'] == 5.0
        assert client.get('/api/v1/products/2').json()['is_hit'] is True
        hits = client.get('/api/v1/products', params={'hits_only': 'true'}).json()
        assert [item['id'] for item in hits['items']] == [2]


def test_discount_prices_checkout_snapshot_and_delivery_point():
    with TestClient(create_test_app()) as client:
        user = customer(client)
        admin = admin_headers(client)
        path = '/api/v1/admin/products/2/discount'
        assert client.put(path, json={'percent': 20}, headers=user).status_code == 403
        assert client.put(path, json={'percent': 91}, headers=admin).status_code == 422
        start = datetime.now(timezone.utc) + timedelta(days=1)
        future = client.put(path, json={'percent': 30, 'start_at': start.isoformat()}, headers=admin)
        assert future.status_code == 200, future.text
        assert future.json()['discount_percent'] == 30
        assert future.json()['variants'][0]['price'] == '1400.00'
        past = datetime.now(timezone.utc) - timedelta(days=2)
        expired = client.put(path, json={'percent': 30, 'start_at': past.isoformat(),
                                         'end_at': (past + timedelta(days=1)).isoformat()}, headers=admin)
        assert expired.status_code == 200
        assert expired.json()['variants'][0]['price'] == '1400.00'
        response = client.put(path, json={'percent': 20}, headers=admin)
        assert response.status_code == 200, response.text
        assert response.json()['variants'][0]['price'] == '1120.00'
        assert response.json()['variants'][0]['original_price'] == '1400.00'
        assert client.get('/api/v1/products', params={'min_price': 1100, 'max_price': 1150}).json()['items'][0]['id'] == 2
        cart = client.post('/api/v1/cart/items', json={'variant_id': 20, 'quantity': 2}, headers=user)
        assert cart.status_code in {200, 201}, cart.text
        assert cart.json()['items'][0]['unit_price'] == '1120.00'
        details = {'contact_name': 'Ирина', 'phone': '+7 700 123 45 67',
                   'delivery_method': 'delivery', 'address': 'ул. Ленина, дом 10',
                   'delivery_lat': 43.2389, 'delivery_lon': 76.8897, 'payment_method': 'cod'}
        assert client.post('/api/v1/orders', json={**details, 'delivery_lon': None}, headers=user).status_code == 422
        placed = client.post('/api/v1/orders', json=details, headers=user)
        assert placed.status_code == 201, placed.text
        snapshot = placed.json()
        assert snapshot['items'][0]['unit_price'] == '1120.00'
        assert snapshot['items'][0]['original_unit_price'] == '1400.00'
        assert Decimal(snapshot['total']) == Decimal('2240.00')
        assert Decimal(str(snapshot['delivery_lat'])) == Decimal('43.2389000')
        assert client.delete(path, headers=admin).status_code == 204
        assert client.get('/api/v1/products/2').json()['variants'][0]['price'] == '1400.00'
        assert client.get(f"/api/v1/orders/{snapshot['id']}", headers=user).json()['total'] == '2240.00'


def test_cod_receipt_and_cancelled_order_cannot_be_reviewed():
    with TestClient(create_test_app()) as client:
        owner = customer(client)
        first = order(client, owner, payment='cod', quantity=1)
        assert client.post(f"/api/v1/orders/{first['id']}/confirm-receipt", headers=owner).status_code == 200
        assert client.get('/api/v1/products/2').json()['is_hit'] is False
        second = order(client, owner, payment='cod', quantity=1)
        assert client.post(f"/api/v1/orders/{second['id']}/cancel", headers=owner).status_code == 200
        assert client.post(f"/api/v1/orders/{second['id']}/confirm-receipt", headers=owner).status_code == 409
        review = {'order_id': second['id'], 'rating': 3, 'body': 'Товар не был получен.'}
        assert client.post('/api/v1/products/2/reviews', json=review, headers=owner).status_code == 409
        assert client.get('/api/v1/products/2/reviews').json()['average_rating'] is None


def test_hits_top_eight_tie_breaker_and_rolling_window():
    with TestClient(create_test_app()) as client:
        customer(client)
        now = datetime.now(timezone.utc)
        with client.app.state.database.session_factory.begin() as session:
            for product_id in range(1, 11):
                sale = OrderORM(user_id=1, status='created', created_at=now,
                                payment_method='cod', payment_status='cod_pending', received_at=now)
                sale.items = [OrderItemORM(product_id=product_id, product_name='Snapshot',
                                           variant_id=product_id * 10, sku=f'SKU-{product_id}',
                                           variant_label='Pack', unit_price=Decimal('10.00'),
                                           currency='KZT', quantity=2)]
                session.add(sale)
            old = OrderORM(user_id=1, status='created', created_at=now - timedelta(days=31),
                           payment_method='cod', payment_status='cod_pending',
                           received_at=now - timedelta(days=31))
            old.items = [OrderItemORM(product_id=11, product_name='Old', variant_id=110,
                                      sku='OLD', variant_label='Pack', unit_price=Decimal('10.00'),
                                      currency='KZT', quantity=100)]
            session.add(old)
            cancelled = OrderORM(user_id=1, status='cancelled', created_at=now,
                                 payment_method='cod', payment_status='cancelled')
            cancelled.items = [OrderItemORM(product_id=12, product_name='Cancelled', variant_id=120,
                                            sku='CANCELLED', variant_label='Pack',
                                            unit_price=Decimal('10.00'), currency='KZT', quantity=100)]
            session.add(cancelled)
        hits = client.get('/api/v1/products', params={'hits_only': 'true', 'page_size': 100})
        assert hits.status_code == 200, hits.text
        assert hits.json()['total'] == 8
        assert [item['id'] for item in hits.json()['items']] == list(range(1, 9))


def test_delayed_sale_events_count_in_current_window():
    with TestClient(create_test_app()) as client:
        buyer = customer(client)
        demo = order(client, buyer, payment='demo', quantity=2, variant_id=20)
        cod = order(client, buyer, payment='cod', quantity=2, variant_id=30)
        old_date = datetime.now(timezone.utc) - timedelta(days=40)
        with client.app.state.database.session_factory.begin() as session:
            session.get(OrderORM, demo['id']).created_at = old_date
            session.get(OrderORM, cod['id']).created_at = old_date
        assert client.get('/api/v1/products/2').json()['is_hit'] is False
        paid = client.post(f"/api/v1/orders/{demo['id']}/demo-payment",
                           json={'outcome': 'success'}, headers=buyer)
        assert paid.status_code == 200, paid.text
        assert paid.json()['paid_at'] is not None
        assert client.get('/api/v1/products/2').json()['is_hit'] is True
        assert client.get('/api/v1/products/3').json()['is_hit'] is False
        received = client.post(f"/api/v1/orders/{cod['id']}/confirm-receipt", headers=buyer)
        assert received.status_code == 200, received.text
        assert received.json()['paid_at'] is None
        assert client.get('/api/v1/products/3').json()['is_hit'] is True


def test_admin_orders_read_only_and_private_delivery_details():
    with TestClient(create_test_app()) as client:
        buyer = customer(client)
        admin = admin_headers(client)
        delivery = order(client, buyer, payment='cod', quantity=1,
                         extra={'delivery_method': 'delivery', 'address': 'ул. Абая, дом 10',
                                'delivery_lat': 43.2389, 'delivery_lon': 76.8897})
        assert client.get('/api/v1/admin/orders', headers=buyer).status_code == 403
        assert client.get(f"/api/v1/admin/orders/{delivery['id']}", headers=buyer).status_code == 403
        assert client.get('/api/v1/admin/orders').status_code == 401
        listing = client.get('/api/v1/admin/orders', headers=admin,
                             params={'limit': 1, 'offset': 0, 'delivery_method': 'delivery'})
        assert listing.status_code == 200, listing.text
        assert listing.json()['total'] == 1
        assert listing.json()['limit'] == 1 and listing.json()['offset'] == 0
        item = listing.json()['items'][0]
        assert item['id'] == delivery['id']
        assert item['customer_email'] == 'v090-customer@example.com'
        assert item['customer_first_name'] == 'Ирина'
        assert item['address'] == 'ул. Абая, дом 10'
        assert Decimal(str(item['delivery_lat'])) == Decimal('43.2389000')
        assert client.get('/api/v1/admin/orders', headers=admin,
                          params={'limit': 1, 'offset': 1}).json()['items'] == []
        assert client.get('/api/v1/admin/orders', headers=admin,
                          params={'status': 'cancelled'}).json()['total'] == 0
        assert client.get('/api/v1/admin/orders', headers=admin,
                          params={'limit': 101}).status_code == 422
        assert client.get(f"/api/v1/admin/orders/{delivery['id']}", headers=admin).json() == item
        assert client.get('/api/v1/admin/orders/999999', headers=admin).status_code == 404


def test_legacy_paid_order_gets_conservative_sale_timestamp(tmp_path):
    database = Database(f'sqlite+pysqlite:///{tmp_path / "sale-events.db"}')
    config = Config(str(Path(__file__).resolve().parents[1] / 'alembic.ini'))
    config.attributes['database_url'] = database.url
    command.upgrade(config, '0007_v090')
    with database.engine.begin() as connection:
        connection.execute(text("""INSERT INTO users
            (id,email,password_hash,first_name,is_active,role)
            VALUES (1,'legacy@example.com','hash','Legacy',1,'customer')"""))
        connection.execute(text("""INSERT INTO orders
            (id,user_id,status,created_at,delivery_method,payment_method,payment_status)
            VALUES (1,1,'created','2026-08-01 12:00:00','pickup','demo','demo_paid')"""))
    command.upgrade(config, 'head')
    with database.engine.connect() as connection:
        paid_at, created_at = connection.execute(text(
            'SELECT paid_at, created_at FROM orders WHERE id=1')).one()
        assert paid_at == created_at
    command.check(config)
    database.dispose()


def test_geo_validation_mapping_cache_and_upstream_failure(monkeypatch):
    with TestClient(create_test_app()) as client:
        geo._cache.clear()
        calls = []
        def fake_fetch(lat, lon, radius):
            calls.append((lat, lon, radius))
            return {'elements': [
                {'type': 'way', 'id': 42, 'center': {'lat': 43.24, 'lon': 76.89},
                 'tags': {'name': 'Ветцентр', 'addr:street': 'Абая', 'addr:housenumber': '1',
                          'website': 'javascript:alert(1)', 'emergency': 'yes'}},
                {'type': 'node', 'id': 2, 'lat': 43.25, 'lon': 76.9,
                 'tags': {'name': 'Дальняя клиника'}},
                {'type': 'node', 'id': 3, 'lat': 43.241, 'lon': 76.89,
                 'tags': {'name': 'Без экстренного приёма', 'emergency': 'no'}},
            ]}
        monkeypatch.setattr(geo, '_fetch', fake_fetch)
        assert client.get('/api/v1/vets/nearby', params={'lat': 100, 'lon': 76.89}).status_code == 422
        assert client.get('/api/v1/vets/nearby', params={'lat': 43.24, 'lon': 76.89, 'radius_m': 1}).status_code == 422
        response = client.get('/api/v1/vets/nearby', params={'lat': 43.24, 'lon': 76.89, 'radius_m': 5000})
        assert response.status_code == 200, response.text
        assert response.headers['Cache-Control'] == 'private, no-store'
        assert response.json()['source'] == 'OpenStreetMap'
        first = response.json()['items'][0]
        assert first['id'] == 'way:42' and first['emergency'] is True and first['website'] is None
        assert {item['id']: item['emergency'] for item in response.json()['items']} == {
            'way:42': True, 'node:2': None, 'node:3': False}
        assert client.get('/api/v1/vets/nearby', params={'lat': 43.24, 'lon': 76.89, 'radius_m': 5000}).status_code == 200
        assert len(calls) == 1
        assert calls[0] == (43.24, 76.89, 5020)
        geo._cache.clear()
        monkeypatch.setattr(geo, '_fetch', lambda *_: {'elements': [
            {'type': 'node', 'id': 4, 'lat': 43.28498, 'lon': 76.89, 'tags': {'name': 'На границе'}}]})
        outside = client.get('/api/v1/vets/nearby', params={'lat': 43.24, 'lon': 76.89, 'radius_m': 5000})
        inside = client.get('/api/v1/vets/nearby', params={'lat': 43.24004, 'lon': 76.89, 'radius_m': 5000})
        assert outside.json()['items'] == []
        assert [item['id'] for item in inside.json()['items']] == ['node:4']
        monkeypatch.setattr(geo, '_fetch', lambda *_: (_ for _ in ()).throw(TimeoutError()))
        failed = client.get('/api/v1/vets/nearby', params={'lat': 40, 'lon': 70})
        assert failed.status_code == 503
        assert failed.headers['Cache-Control'] == 'private, no-store'
