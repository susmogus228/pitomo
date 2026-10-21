"""Saved-address and repeat/merge contracts use isolated catalog and owner data."""
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event, select

from app.core.security import create_access_token
from app.db.models import (CartItemORM, CartOperationORM, OrderItemORM, OrderORM,
    ProductORM, ProductPhotoORM, ProductVariantORM, UserORM)
from app.main import create_test_app


@pytest.fixture
def client():
    application = create_test_app()
    with TestClient(application) as instance:
        with application.state.database.session_factory.begin() as session:
            session.add_all([UserORM(id=i, email=f'purchases-{i}@example.test', password_hash='unused',
                first_name='Buyer', role='customer', is_active=True) for i in (1, 2)])
        for i in (1, 2):
            setattr(instance, f'owner{i}', {'Authorization': 'Bearer ' + create_access_token(
                subject=i, secret=application.state.settings.jwt_secret, expires_minutes=15)})
        yield instance


ADDRESS = {'city': 'Алматы', 'street': 'Абая', 'house': '10', 'lat': 43.24, 'lon': 76.89}


def test_saved_addresses_owner_default_and_partial_update(client):
    base = '/api/v1/users/me/addresses'
    assert client.get(base).status_code == 401
    first = client.post(base, headers=client.owner1, json=ADDRESS)
    assert first.status_code == 201, first.text
    first = first.json()
    assert first['is_default'] is True
    second = client.post(base, headers=client.owner1, json={**ADDRESS, 'house': '20', 'is_default': True}).json()
    rows = client.get(base, headers=client.owner1).json()['items']
    assert [row['id'] for row in rows if row['is_default']] == [second['id']]
    for verb in ('patch', 'delete'):
        kwargs = {'json': {'house': '99'}} if verb == 'patch' else {}
        assert getattr(client, verb)(f"{base}/{first['id']}", headers=client.owner2, **kwargs).status_code == 404
    assert client.get(base, headers=client.owner2).json()['items'] == []
    changed = client.patch(f"{base}/{first['id']}", headers=client.owner1, json={'details': 'Квартира 2'}).json()
    assert changed['house'] == '10' and changed['details'] == 'Квартира 2'
    assert client.delete(f"{base}/{second['id']}", headers=client.owner1).status_code == 204
    assert client.get(base, headers=client.owner1).json()['items'][0]['is_default'] is True


def test_address_limit_and_validation(client):
    base = '/api/v1/users/me/addresses'
    for n in range(20):
        assert client.post(base, headers=client.owner1, json={**ADDRESS, 'house': str(n)}).status_code == 201
    assert client.post(base, headers=client.owner1, json=ADDRESS).status_code == 409
    for body in ({**ADDRESS, 'lon': None}, {**ADDRESS, 'lat': 100}, {**ADDRESS, 'city': ' '},
                 {**ADDRESS, 'is_default': 'false'}, {**ADDRESS, 'source': 'unknown'}):
        assert client.post(base, headers=client.owner2, json=body).status_code == 422


def _variant(client, *, stock=10, price=100):
    with client.app.state.database.session_factory.begin() as session:
        row = session.scalar(select(ProductVariantORM).order_by(ProductVariantORM.id))
        row.stock, row.price = stock, price
        product = session.get(ProductORM, row.product_id)
        product.image_url = '/media/cart-photo.webp'
        return row.id, row.product_id


def test_merge_caps_preserves_cart_and_receipt_is_idempotent(client):
    variant, _ = _variant(client, stock=7)
    assert client.post('/api/v1/cart/items', headers=client.owner1,
        json={'variant_id': variant, 'quantity': 3}).status_code == 200
    body = {'operation_key': 'merge-12345', 'items': [{'variant_id': variant, 'quantity': 6},
            {'variant_id': 2147483600, 'quantity': 2}]}
    response = client.post('/api/v1/cart/merge', headers=client.owner1, json=body)
    assert response.status_code == 200, response.text
    result = response.json()
    assert result['cart']['items'][0]['quantity'] == 7
    assert result['cart']['items'][0]['image_url'] == '/media/cart-photo.webp'
    assert result['items'][0]['added_quantity'] == 4 and result['items'][0]['remaining_quantity'] == 2
    assert result['items'][1]['status'] == 'missing'
    assert client.post('/api/v1/cart/merge', headers=client.owner1, json=body).json()['replayed'] is True
    assert client.get('/api/v1/cart', headers=client.owner1).json()['total_items'] == 7
    assert client.post('/api/v1/cart/merge', headers=client.owner1,
        json={**body, 'items': [{'variant_id': variant, 'quantity': 1}]}).status_code == 409
    # Another owner may safely use the same key.
    assert client.post('/api/v1/cart/merge', headers=client.owner2, json=body).json()['replayed'] is False


def test_restore_caps_after_stock_change_and_move_is_atomic(client):
    variant, product = _variant(client, stock=4)
    base = '/api/v1/cart'
    client.post(base + '/items', headers=client.owner1, json={'variant_id': variant, 'quantity': 3})
    assert client.delete(f'{base}/items/{variant}', headers=client.owner1).status_code == 204
    with client.app.state.database.session_factory.begin() as session:
        session.get(ProductVariantORM, variant).stock = 2
    body = {'variant_id': variant, 'quantity': 3, 'operation_key': 'restore-1234'}
    restored = client.post(base + '/items/restore', headers=client.owner1, json=body).json()
    assert restored['items'][0]['added_quantity'] == 2
    assert restored['items'][0]['remaining_quantity'] == 1
    moved = client.post(f'{base}/items/{variant}/favorite', headers=client.owner1,
        json={'operation_key': 'favorite-1234'})
    assert moved.status_code == 200, moved.text
    assert moved.json()['cart']['items'] == [] and moved.json()['product_id'] == product
    assert any(row['id'] == product for row in client.get('/api/v1/favorites', headers=client.owner1).json())
    assert client.post(f'{base}/items/{variant}/favorite', headers=client.owner1,
        json={'operation_key': 'favorite-1234'}).json()['replayed'] is True


def _order(client, variant, product):
    with client.app.state.database.session_factory.begin() as session:
        order = OrderORM(user_id=1, status='created', created_at=datetime.now(timezone.utc))
        session.add(order)
        session.flush()
        session.add(OrderItemORM(order_id=order.id, product_id=product, variant_id=variant,
            product_name='Old name', variant_label='Old pack', sku='OLD-SKU',
            unit_price=50, currency='KZT', quantity=4))
        return order.id


def test_repeat_requires_fresh_preview_preserves_history_and_current_cart(client):
    variant, product = _variant(client, stock=8, price=100)
    order = _order(client, variant, product)
    base = f'/api/v1/orders/{order}'
    assert client.get(base + '/repeat-preview', headers=client.owner2).status_code == 404
    client.post('/api/v1/cart/items', headers=client.owner1, json={'variant_id': variant, 'quantity': 2})
    preview = client.get(base + '/repeat-preview', headers=client.owner1).json()
    assert preview['items'][0]['unit_price'] == '100.00' and preview['items'][0]['changes']
    with client.app.state.database.session_factory.begin() as session:
        session.get(ProductVariantORM, variant).stock = 3
    body = {'operation_key': 'repeat-12345', 'fingerprint': preview['fingerprint']}
    assert client.post(base + '/repeat', headers=client.owner1, json=body).status_code == 409
    assert client.get('/api/v1/cart', headers=client.owner1).json()['total_items'] == 2
    preview = client.get(base + '/repeat-preview', headers=client.owner1).json()
    assert preview['items'][0]['add_quantity'] == 1 and preview['items'][0]['status'] == 'reduced'
    body['fingerprint'] = preview['fingerprint']
    response = client.post(base + '/repeat', headers=client.owner1, json=body)
    assert response.status_code == 200, response.text
    assert response.json()['cart']['total_items'] == 3
    assert client.post(base + '/repeat', headers=client.owner1, json=body).json()['replayed'] is True
    with client.app.state.database.session_factory() as session:
        assert str(session.scalar(select(OrderItemORM.unit_price).where(OrderItemORM.order_id == order))) == '50.00'
        assert session.get(ProductVariantORM, variant).stock == 3
        assert session.get(CartItemORM, (1, variant)).quantity == 3


def test_repeat_deleted_variant_explained_and_empty_repeat_has_no_writes(client):
    variant, product = _variant(client)
    order = _order(client, variant, product)
    with client.app.state.database.session_factory.begin() as session:
        session.delete(session.get(ProductVariantORM, variant))
    preview = client.get(f'/api/v1/orders/{order}/repeat-preview', headers=client.owner1).json()
    assert preview['items'][0]['status'] == 'missing' and preview['can_repeat'] is False
    assert client.post(f'/api/v1/orders/{order}/repeat', headers=client.owner1,
        json={'operation_key': 'repeat-empty', 'fingerprint': preview['fingerprint']}).status_code == 409


@pytest.mark.parametrize('items', [[{'variant_id': 1, 'quantity': 1}] * 2,
    [{'variant_id': 1, 'quantity': 10001}], [{'variant_id': True, 'quantity': 1}], []])
def test_merge_rejects_invalid_batch_without_writes(client, items):
    assert client.post('/api/v1/cart/merge', headers=client.owner1,
        json={'operation_key': 'invalid-batch', 'items': items}).status_code == 422
    assert client.get('/api/v1/cart', headers=client.owner1).json()['items'] == []


def test_cart_gallery_fallback_and_repeat_live_discount(client):
    variant, product = _variant(client, stock=10, price=100)
    order = _order(client, variant, product)
    with client.app.state.database.session_factory.begin() as session:
        row = session.get(ProductORM, product)
        row.image_url = None
        row.discount_percent = 25
        session.add(ProductPhotoORM(product_id=product, filename='a' * 32 + '.webp',
            created_at=datetime.now(timezone.utc)))
    result = client.post('/api/v1/cart/items', headers=client.owner1,
        json={'variant_id': variant, 'quantity': 1}).json()
    assert result['items'][0]['image_url'] == '/media/products/' + 'a' * 32 + '.webp'
    preview = client.get(f'/api/v1/orders/{order}/repeat-preview', headers=client.owner1).json()
    assert preview['items'][0]['unit_price'] == '75.00'
    assert preview['items'][0]['original_unit_price'] == '100.00'
    assert preview['items'][0]['image_url'] == result['items'][0]['image_url']


def test_image_batch_prefers_cover_and_oldest_gallery_photo_in_one_query(client):
    from app.cart.images import product_images
    now = datetime.now(timezone.utc)
    with client.app.state.database.session_factory.begin() as session:
        session.get(ProductORM, 1).image_url = '/media/explicit-cover.webp'
        session.get(ProductORM, 2).image_url = None
        session.get(ProductORM, 3).image_url = None
        session.get(ProductORM, 4).image_url = ''
        session.add_all([
            ProductPhotoORM(product_id=1, filename='a' * 32 + '.webp', created_at=now),
            ProductPhotoORM(product_id=2, filename='b' * 32 + '.webp', created_at=now),
            ProductPhotoORM(product_id=2, filename='c' * 32 + '.webp', created_at=now - timedelta(days=1)),
            ProductPhotoORM(product_id=4, filename='d' * 32 + '.webp', created_at=now),
        ])
    statements = []
    def capture(conn, cursor, statement, parameters, context, executemany):
        if statement.lstrip().upper().startswith('SELECT'):
            statements.append(statement)
    engine = client.app.state.database.engine
    event.listen(engine, 'before_cursor_execute', capture)
    try:
        with client.app.state.database.session_factory() as session:
            images = product_images(session, {1, 2, 3, 4})
        assert images == {1: '/media/explicit-cover.webp', 2: '/media/products/' + 'c' * 32 + '.webp',
            3: None, 4: '/media/products/' + 'd' * 32 + '.webp'}
        assert len(statements) == 1
    finally:
        event.remove(engine, 'before_cursor_execute', capture)


@pytest.mark.parametrize('change', ['price', 'discount', 'cart', 'sku'])
def test_repeat_revalidates_every_confirmation_change_without_receipt(client, change):
    variant, product = _variant(client, stock=10, price=100)
    order = _order(client, variant, product)
    base = f'/api/v1/orders/{order}'
    preview = client.get(base + '/repeat-preview', headers=client.owner1).json()
    if change == 'cart':
        client.post('/api/v1/cart/items', headers=client.owner1,
            json={'variant_id': variant, 'quantity': 1})
    else:
        with client.app.state.database.session_factory.begin() as session:
            if change == 'price':
                session.get(ProductVariantORM, variant).price = 105
            elif change == 'discount':
                session.get(ProductORM, product).discount_percent = 10
            else:
                session.get(ProductVariantORM, variant).sku = 'NEW-SKU'
    assert client.post(base + '/repeat', headers=client.owner1,
        json={'operation_key': 'fresh-preview-123', 'fingerprint': preview['fingerprint']}).status_code == 409
    with client.app.state.database.session_factory() as session:
        assert session.scalar(select(CartOperationORM.id)) is None
        item = session.get(CartItemORM, (1, variant))
        assert (item.quantity if item else 0) == (1 if change == 'cart' else 0)


def test_restore_max_quantity_cap_and_retry_after_catalog_deleted(client):
    variant, _ = _variant(client, stock=20000)
    client.post('/api/v1/cart/items', headers=client.owner1, json={'variant_id': variant, 'quantity': 9999})
    body = {'variant_id': variant, 'quantity': 5, 'operation_key': 'max-restore-123'}
    response = client.post('/api/v1/cart/items/restore', headers=client.owner1, json=body).json()
    assert response['cart']['total_items'] == 10000 and response['items'][0]['added_quantity'] == 1
    with client.app.state.database.session_factory.begin() as session:
        session.delete(session.get(ProductVariantORM, variant))
    repeated = client.post('/api/v1/cart/items/restore', headers=client.owner1, json=body)
    assert repeated.status_code == 200 and repeated.json()['replayed'] is True
    assert client.post('/api/v1/cart/items/restore', headers=client.owner1,
        json={**body, 'operation_key': 'max-restore-124'}).json()['items'][0]['status'] == 'missing'


def test_move_deleted_product_does_not_drop_cart_item_or_create_receipt(client):
    variant, _ = _variant(client)
    client.post('/api/v1/cart/items', headers=client.owner1, json={'variant_id': variant, 'quantity': 2})
    with client.app.state.database.session_factory.begin() as session:
        session.delete(session.get(ProductVariantORM, variant))
    response = client.post(f'/api/v1/cart/items/{variant}/favorite', headers=client.owner1,
        json={'operation_key': 'deleted-favorite'})
    assert response.status_code == 409
    with client.app.state.database.session_factory() as session:
        assert session.get(CartItemORM, (1, variant)).quantity == 2
        assert session.scalar(select(CartOperationORM.id)) is None


def test_address_point_clear_and_default_cannot_be_orphaned(client):
    base = '/api/v1/users/me/addresses'
    first = client.post(base, headers=client.owner1, json=ADDRESS).json()
    assert isinstance(first['lat'], float)
    url = f"{base}/{first['id']}"
    assert client.patch(url, headers=client.owner1, json={'is_default': False}).status_code == 409
    assert client.patch(url, headers=client.owner1, json={'lat': None}).status_code == 422
    cleared = client.patch(url, headers=client.owner1, json={'lat': None, 'lon': None, 'source': 'manual'})
    assert cleared.status_code == 200 and cleared.json()['lat'] is None
    assert client.get(base, headers=client.owner1).json()['items'][0]['is_default'] is True


def test_new_cart_actions_reject_cross_tab_owner_change_before_receipts_or_writes(client):
    variant, product = _variant(client)
    order = _order(client, variant, product)
    preview = client.get(f'/api/v1/orders/{order}/repeat-preview', headers=client.owner1).json()
    for path, body in [('/api/v1/cart/merge', {'items': [{'variant_id': variant, 'quantity': 1}]}),
        ('/api/v1/cart/items/restore', {'variant_id': variant, 'quantity': 1}),
        (f'/api/v1/cart/items/{variant}/favorite', {}),
        (f'/api/v1/orders/{order}/repeat', {'fingerprint': preview['fingerprint']})]:
        response = client.post(path, headers=client.owner2,
            json={**body, 'operation_key': 'cross-tab-owner', 'expected_user_id': 1})
        assert response.status_code == 409 and 'Аккаунт изменился' in response.text
    with client.app.state.database.session_factory() as session:
        assert session.scalar(select(CartOperationORM.id)) is None
        assert session.scalar(select(CartItemORM.variant_id)) is None


def test_expected_owner_is_part_of_receipt_payload(client):
    variant, _ = _variant(client)
    body = {'operation_key': 'explicit-owner-key', 'expected_user_id': 1,
        'items': [{'variant_id': variant, 'quantity': 1}]}
    assert client.post('/api/v1/cart/merge', headers=client.owner1, json=body).status_code == 200
    body.pop('expected_user_id')
    assert client.post('/api/v1/cart/merge', headers=client.owner1, json=body).status_code == 409


@pytest.mark.parametrize('action', ['merge', 'favorite', 'repeat'])
def test_receipt_storage_failure_rolls_back_the_entire_action(client, monkeypatch, action):
    from fastapi import HTTPException
    from app.cart.operations import CartOperations
    from app.db.models import FavoriteORM
    variant, product = _variant(client)
    order = _order(client, variant, product)
    client.post('/api/v1/cart/items', headers=client.owner1, json={'variant_id': variant, 'quantity': 1})
    preview = client.get(f'/api/v1/orders/{order}/repeat-preview', headers=client.owner1).json()
    def broken_receipt(*args, **kwargs):
        raise HTTPException(503, 'Receipt storage unavailable')
    monkeypatch.setattr(CartOperations, 'finish', broken_receipt)
    endpoints = {
        'merge': ('/api/v1/cart/merge', {'items': [{'variant_id': variant, 'quantity': 2}]}),
        'favorite': (f'/api/v1/cart/items/{variant}/favorite', {}),
        'repeat': (f'/api/v1/orders/{order}/repeat', {'fingerprint': preview['fingerprint']}),
    }
    path, body = endpoints[action]
    assert client.post(path, headers=client.owner1,
        json={**body, 'operation_key': 'failed-receipt-storage'}).status_code == 503
    with client.app.state.database.session_factory() as session:
        assert session.get(CartItemORM, (1, variant)).quantity == 1
        assert session.get(FavoriteORM, (1, product)) is None
        assert session.scalar(select(CartOperationORM.id)) is None


def test_address_expected_owner_rejects_cookie_switch_without_private_data_write(client):
    base = '/api/v1/users/me/addresses'
    response = client.post(base, headers=client.owner2, json={**ADDRESS, 'expected_user_id': 1})
    assert response.status_code == 409 and 'Аккаунт изменился' in response.text
    assert client.get(base, headers=client.owner2).json()['items'] == []
    created = client.post(base, headers=client.owner1, json={**ADDRESS, 'expected_user_id': 1})
    assert created.status_code == 201 and 'expected_user_id' not in created.json()
    response = client.patch(f"{base}/{created.json()['id']}", headers=client.owner2,
        json={'details': 'Private apartment', 'expected_user_id': 1})
    assert response.status_code == 409
    assert client.get(base, headers=client.owner1).json()['items'][0]['details'] == ''
