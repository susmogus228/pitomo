"""Analytics download contracts, reconciliation, privacy and spreadsheet safety."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from io import BytesIO, StringIO
import csv
from zipfile import ZipFile

import pytest
from fastapi.testclient import TestClient
from openpyxl import load_workbook
from sqlalchemy import select

from app.admin import exports
from app.core.security import create_access_token
from app.db.models import (
    OrderItemORM, OrderORM, ProductORM, ProductVariantORM, ReviewORM, ReviewPhotoORM,
    ReviewReplyORM, StockReplenishmentORM, UserORM,
)
from app.main import create_test_app

BASE = '/api/v1/admin/exports'
NOW = datetime(2026, 10, 5, 12, tzinfo=timezone.utc)


@pytest.fixture
def client():
    application = create_test_app()
    assert BASE + '/{dataset}' in application.openapi()['paths']
    with TestClient(application) as instance:
        # Auth hashing is covered separately. Signed JWTs still exercise real DB-backed role checks.
        with instance.app.state.database.session_factory.begin() as session:
            session.add_all([
                UserORM(id=1, email='analytics-customer@example.com', password_hash='private-hash-sentinel',
                        first_name='Customer', last_name='Private', role='customer', is_active=True),
                UserORM(id=2, email='analytics-admin@example.com', password_hash='private-hash-sentinel',
                        first_name='Admin', last_name='Private', role='admin', is_active=True),
            ])
        settings = instance.app.state.settings
        instance.customer = {'Authorization': 'Bearer ' + create_access_token(
            subject=1, secret=settings.jwt_secret, expires_minutes=settings.access_token_minutes)}
        instance.admin = {'Authorization': 'Bearer ' + create_access_token(
            subject=2, secret=settings.jwt_secret, expires_minutes=settings.access_token_minutes)}
        yield instance


def _seed_orders(client, *, count=1, dates=None):
    ids = []
    with client.app.state.database.session_factory.begin() as session:
        user_id = session.scalar(select(UserORM.id).where(UserORM.email == 'analytics-customer@example.com'))
        for index in range(count):
            order = OrderORM(user_id=user_id, status='created', created_at=dates[index] if dates else NOW,
                contact_name='Private Name', phone='+77001234567', address='Private Address',
                comment='Private Comment', delivery_method='delivery', payment_method='cod',
                payment_status='cod_pending', delivery_lat=Decimal('43.2389'),
                delivery_lon=Decimal('76.8897'), idempotency_key=f'private-key-{index}',
                checkout_fingerprint='private-fingerprint')
            session.add(order)
            session.flush()
            session.add(OrderItemORM(order_id=order.id, product_id=2, variant_id=20,
                product_name='Historical food', variant_label='500 g', sku='001-HISTORY',
                unit_price=Decimal('1120.00'), original_unit_price=Decimal('1400.00'),
                currency='KZT', quantity=2))
            ids.append(order.id)
    return ids


def _xlsx_response(client, dataset, **params):
    response = client.get(BASE + '/' + dataset, headers=client.admin, params=params)
    assert response.status_code == 200, response.text[:500]
    assert response.headers['content-type'].startswith('application/vnd.openxmlformats')
    assert response.headers['content-disposition'].startswith('attachment; filename="pitomo-')
    assert response.headers['cache-control'] == 'no-store'
    return load_workbook(BytesIO(response.content))


def _sheet(workbook, name):
    rows = list(workbook[name].values)
    return [dict(zip(rows[0], row)) for row in rows[1:]]


def _csv_rows(payload):
    assert payload.startswith(b'\xef\xbb\xbf')
    return list(csv.DictReader(StringIO(payload.decode('utf-8-sig'))))


def _zip_response(client, dataset, **params):
    response = client.get(BASE + '/' + dataset, headers=client.admin, params={'format': 'csv', **params})
    assert response.status_code == 200, response.text[:500]
    assert response.headers['content-type'] == 'application/zip'
    assert response.headers['content-disposition'].endswith('.zip"')
    with ZipFile(BytesIO(response.content)) as archive:
        assert archive.testzip() is None
        return {name: _csv_rows(archive.read(name)) for name in archive.namelist()}


@pytest.mark.parametrize('dataset', ['overview', 'orders', 'products', 'replenishments',
                                   'users', 'reviews', 'discounts', 'all'])
def test_export_authorization_for_every_dataset(client, dataset):
    assert client.get(BASE + '/' + dataset).status_code == 401
    assert client.get(BASE + '/' + dataset, headers=client.customer).status_code == 403
    response = client.get(BASE + '/' + dataset, headers=client.admin)
    assert response.status_code == 200, response.text[:500]


def test_orders_export_all_pages_historical_values_and_complete_csv_zip(client):
    ids = _seed_orders(client, count=75)
    with client.app.state.database.session_factory.begin() as session:
        product = session.get(ProductORM, 2)
        product.name = 'New current product name'
        variant = session.get(ProductVariantORM, 20)
        variant.price = Decimal('9999.99')
        variant.sku = 'NEW-CURRENT-SKU'
    workbook = _xlsx_response(client, 'orders', limit=1, offset=999, page=2)
    try:
        orders, items = _sheet(workbook, 'Orders'), _sheet(workbook, 'OrderItems')
        assert {row['id'] for row in orders} == set(ids)
        assert len(items) == 75
        assert all(row['total'] == 2240 for row in orders)
        assert all(row['unit_price'] == 1120 and row['line_total'] == 2240
                   and row['original_unit_price'] == 1400 and row['line_discount'] == 560 for row in items)
        assert all(row['sku'] == '001-HISTORY' and row['product_name'] == 'Historical food' for row in items)
        assert workbook['OrderItems'].freeze_panes == 'A2'
        assert workbook['OrderItems'].auto_filter.ref.endswith('76')
        assert workbook['OrderItems']['K2'].data_type == 'n'
    finally:
        workbook.close()
    archive = _zip_response(client, 'orders', status='created')
    assert set(archive) == {'Metadata.csv', 'Orders.csv', 'OrderItems.csv'}
    assert len(archive['Orders.csv']) == len(archive['OrderItems.csv']) == 75
    assert Decimal(archive['Orders.csv'][0]['total']) == Decimal('2240.00')


def test_kazakhstan_inclusive_date_range_filters_and_validation(client):
    dates = [datetime(2026, 10, 4, 18, 59, 59, tzinfo=timezone.utc),
             datetime(2026, 10, 4, 19, 0, tzinfo=timezone.utc),
             datetime(2026, 10, 5, 18, 59, 59, tzinfo=timezone.utc),
             datetime(2026, 10, 5, 19, 0, tzinfo=timezone.utc)]
    ids = _seed_orders(client, count=4, dates=dates)
    archive = _zip_response(client, 'orders', date_from='2026-10-05', date_to='2026-10-05')
    assert {int(row['id']) for row in archive['Orders.csv']} == set(ids[1:3])
    assert archive['Orders.csv'][0]['created_at'] == '2026-10-05T00:00:00+05:00'
    for params in ({'date_from': '2026-10-06', 'date_to': '2026-10-05'},
                   {'date_from': 'invalid'}, {'payment_status': 'paid'}, {'status': 'arrived'},
                   {'delivery_method': 'helicopter'}, {'q': 'x' * 101}, {'format': 'sql'},
                   {'user_id': -1}, {'variant_id': 0}):
        assert client.get(BASE + '/orders', params=params, headers=client.admin).status_code == 422
    assert client.get(BASE + '/orders', params={'date_from': '0001-01-01', 'date_to': '9999-12-31'},
                      headers=client.admin).status_code == 200


def test_summary_separates_cancelled_receipt_and_demo_and_user_stats(client):
    ids = _seed_orders(client, count=3)
    with client.app.state.database.session_factory.begin() as session:
        cancelled = session.get(OrderORM, ids[0])
        cancelled.status = 'cancelled'
        cancelled.payment_status = 'cancelled'
        demo = session.get(OrderORM, ids[1])
        demo.payment_method = 'demo'
        demo.payment_status = 'demo_paid'
        demo.paid_at = NOW
        received = session.get(OrderORM, ids[2])
        received.received_at = NOW
    workbook = _xlsx_response(client, 'all')
    try:
        summary = {row['metric']: row for row in _sheet(workbook, 'Overview') if row['product_id'] is None}
        assert summary['created_orders_count']['orders_count'] == 2
        assert summary['cancelled_orders_count']['orders_count'] == 1
        assert summary['received_orders_count']['orders_count'] == 1
        assert summary['demo_paid_orders_count']['orders_count'] == 1
        assert summary['created_order_value']['amount'] == 4480
        assert summary['cancelled_order_value']['amount'] == 2240
        assert summary['received_order_value']['amount'] == summary['demo_paid_order_value']['amount'] == 2240
        assert {row['payment_status'] for row in _sheet(workbook, 'Orders')} == {'cancelled', 'demo_paid', 'cod_pending'}
        users = _sheet(workbook, 'Users')
        assert users[0]['orders_count'] == 3
        assert users[0]['created_order_value'] == 4480
        assert users[0]['cancelled_order_value'] == 2240
        assert users[1]['orders_count'] == 0
    finally:
        workbook.close()
    filtered = _zip_response(client, 'all', payment_status='demo_paid')
    assert len(filtered['Orders.csv']) == len(filtered['OrderItems.csv']) == 1
    assert filtered['Users.csv'][0]['orders_count'] == '1'


def test_contacts_opt_in_and_explicit_allowlist_never_export_secrets(client):
    _seed_orders(client)
    excluded = _zip_response(client, 'all')
    assert not {'customer_email', 'customer_first_name', 'customer_last_name', 'contact_name',
                'phone', 'address', 'comment', 'delivery_lat', 'delivery_lon'} & excluded['Orders.csv'][0].keys()
    assert not {'email', 'first_name', 'last_name'} & excluded['Users.csv'][0].keys()
    included = _zip_response(client, 'all', include_contacts='true')
    assert included['Orders.csv'][0]['contact_name'] == 'Private Name'
    assert included['Orders.csv'][0]['address'] == 'Private Address'
    assert included['Orders.csv'][0]['customer_email'] == 'analytics-customer@example.com'
    assert included['Orders.csv'][0]['delivery_lat'] == '43.2389000'
    assert included['Users.csv'][0]['email'] == 'analytics-customer@example.com'
    for archive in (excluded, included):
        text = str(archive)
        for secret in ('password_hash', 'token_hash', 'browser_sessions', 'idempotency_key',
                       'checkout_fingerprint', 'private-key-', 'private-fingerprint', 'private-hash-sentinel'):
            assert secret not in text


def test_reviews_csv_keeps_every_reply_and_xlsx_omits_deleted_content(client):
    order_id = _seed_orders(client)[0]
    with client.app.state.database.session_factory.begin() as session:
        review = ReviewORM(user_id=1, product_id=2, order_id=order_id, rating=5,
                           body='Customer root review', created_at=NOW, updated_at=NOW)
        session.add(review)
        session.flush()
        ordinary = ReviewReplyORM(review_id=review.id, user_id=1, body='Customer reply',
                                 is_official=False, is_pinned=False, created_at=NOW, updated_at=NOW)
        official = ReviewReplyORM(review_id=review.id, user_id=2, body='Official pinned reply',
                                 is_official=True, is_pinned=True, created_at=NOW, updated_at=NOW)
        deleted = ReviewReplyORM(review_id=review.id, user_id=1, body='Deleted private reply',
                                is_official=False, is_pinned=False, created_at=NOW, updated_at=NOW,
                                deleted_at=NOW)
        session.add_all([ordinary, official, deleted])
        session.flush()
        session.add(ReviewReplyORM(review_id=review.id, parent_reply_id=ordinary.id, user_id=2,
            body='Official nested reply', is_official=True, is_pinned=False, created_at=NOW, updated_at=NOW))
        session.add_all([
            ReviewPhotoORM(review_id=review.id, uploader_id=1, filename='a' * 32 + '.webp', created_at=NOW),
            ReviewPhotoORM(reply_id=ordinary.id, uploader_id=1, filename='b' * 32 + '.webp', created_at=NOW),
            ReviewPhotoORM(reply_id=deleted.id, uploader_id=1, filename='c' * 32 + '.webp', created_at=NOW),
        ])
    response = client.get(BASE + '/reviews', headers=client.admin, params={'format': 'csv'})
    assert response.status_code == 200, response.text
    assert response.headers['content-type'].startswith('text/csv; charset=utf-8')
    rows = _csv_rows(response.content)
    assert {row['body'] for row in rows} == {'Customer root review', 'Customer reply',
                                            'Official pinned reply', 'Official nested reply'}
    assert sum(row['record_type'] == 'review' for row in rows) == 1
    assert sum(row['record_type'] == 'reply' for row in rows) == 3
    assert '/media/reviews/' + 'a' * 32 + '.webp' in rows[0]['photo_urls']
    assert 'c' * 32 + '.webp' not in response.text
    workbook = _xlsx_response(client, 'reviews', unanswered_only='true')
    try:
        assert _sheet(workbook, 'Reviews') == _sheet(workbook, 'ReviewReplies') == []
    finally:
        workbook.close()
    workbook = _xlsx_response(client, 'reviews', date_from='2026-10-06')
    try:
        assert _sheet(workbook, 'Reviews') == _sheet(workbook, 'ReviewReplies') == []
    finally:
        workbook.close()


def test_search_literal_wildcards_and_current_discount_snapshot(client):
    with client.app.state.database.session_factory.begin() as session:
        product = session.get(ProductORM, 2)
        product.name = 'Корм 100% для кошек'
        product.discount_percent = 25
        product.discount_start_at = NOW - timedelta(days=10)
        product.discount_end_at = NOW + timedelta(days=10)
    response = client.get(BASE + '/products', headers=client.admin, params={'format': 'csv', 'q': '100%'})
    assert response.status_code == 200
    assert all(row['id'] == '2' for row in _csv_rows(response.content))
    assert len(_csv_rows(client.get(BASE + '/products', headers=client.admin,
                                   params={'format': 'csv', 'q': 'НЕСУЩЕСТВУЮЩИЙ'}).content)) == 0
    workbook = _xlsx_response(client, 'discounts', q='КОРМ', date_from='2050-01-01')
    try:
        discounts = _sheet(workbook, 'Discounts')
        assert len(discounts) == 1 and discounts[0]['discount_percent'] == 25
        assert discounts[0]['product_id'] == 2
    finally:
        workbook.close()


def test_replenishment_period_search_and_preserved_snapshot(client):
    with client.app.state.database.session_factory.begin() as session:
        session.add(StockReplenishmentORM(variant_id=20, actor_id=2, product_name='Исторический Корм',
            variant_label='500 г', sku='СТАРЫЙ-SKU', quantity=7, stock_before=3, stock_after=10,
            reason='Поставка', created_at=NOW))
    response = client.get(BASE + '/replenishments', headers=client.admin,
                          params={'format': 'csv', 'q': 'исторический', 'date_from': '2026-10-05',
                                  'date_to': '2026-10-05', 'variant_id': 20})
    assert response.status_code == 200, response.text
    rows = _csv_rows(response.content)
    assert len(rows) == 1 and rows[0]['sku'] == 'СТАРЫЙ-SKU'
    assert rows[0]['stock_after'] == '10'


def test_user_text_is_never_formula_but_money_and_sku_types_are_preserved(client):
    _seed_orders(client)
    dangerous = '  =HYPERLINK("https://invalid.test","click")'
    with client.app.state.database.session_factory.begin() as session:
        item = session.scalar(select(OrderItemORM))
        item.product_name = '=SUM(1,2)'
        item.sku = '00123'
        item.variant_label = dangerous
        session.get(OrderORM, item.order_id).comment = '\t@SUM(1,2)'
        session.get(ProductORM, 2).name = '=1+1'
    workbook = _xlsx_response(client, 'all', include_contacts='true')
    try:
        for sheet in workbook:
            assert all(cell.data_type != 'f' for row in sheet for cell in row)
        assert _sheet(workbook, 'OrderItems')[0]['sku'] == '00123'
        assert _sheet(workbook, 'OrderItems')[0]['variant_label'] == dangerous
        assert _sheet(workbook, 'OrderItems')[0]['unit_price'] == 1120
    finally:
        workbook.close()
    archive = _zip_response(client, 'all', include_contacts='true')
    assert archive['OrderItems.csv'][0]['product_name'] == "'=SUM(1,2)"
    assert archive['OrderItems.csv'][0]['variant_label'] == "'" + dangerous
    assert archive['Orders.csv'][0]['comment'].startswith("'\t@")


def test_export_limit_is_explicit_and_releases_slot(client, monkeypatch):
    _seed_orders(client, count=3)
    original = exports.MAX_EXPORT_ROWS
    monkeypatch.setattr(exports, 'MAX_EXPORT_ROWS', 3)
    response = client.get(BASE + '/orders', headers=client.admin)
    assert response.status_code == 413
    assert 'слишком большая' in response.json()['detail']
    monkeypatch.setattr(exports, 'MAX_EXPORT_ROWS', original)
    assert client.get(BASE + '/orders', headers=client.admin).status_code == 200
    assert exports._EXPORT_SLOTS.acquire(blocking=False)
    assert exports._EXPORT_SLOTS.acquire(blocking=False)
    try:
        response = client.get(BASE + '/products', headers=client.admin)
        assert response.status_code == 429 and response.headers['retry-after'] == '3'
    finally:
        exports._EXPORT_SLOTS.release()
        exports._EXPORT_SLOTS.release()


def test_export_byte_limits_and_binary_openapi(client, monkeypatch):
    responses = client.app.openapi()['paths'][BASE + '/{dataset}']['get']['responses']['200']['content']
    assert set(responses) == {'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                              'application/zip', 'text/csv'}
    monkeypatch.setattr(exports, 'MAX_DATA_BYTES', 1)
    assert client.get(BASE + '/products', headers=client.admin).status_code == 413
    monkeypatch.setattr(exports, 'MAX_DATA_BYTES', 20 * 1024 * 1024)
    monkeypatch.setattr(exports, 'MAX_EXPORT_BYTES', 128)
    assert client.get(BASE + '/products', headers=client.admin).status_code == 413
    assert client.get(BASE + '/products', headers=client.admin, params={'format': 'csv'}).status_code == 413


def test_excel_long_cell_is_rejected_instead_of_silent_truncation(client):
    with client.app.state.database.session_factory.begin() as session:
        session.get(ProductORM, 2).composition = 'x' * 32768
    response = client.get(BASE + '/products', headers=client.admin)
    assert response.status_code == 413 and '32767' in response.json()['detail']
    response = client.get(BASE + '/products', headers=client.admin, params={'format': 'csv'})
    assert response.status_code == 200
    assert any(len(row['composition']) == 32768 for row in _csv_rows(response.content))
