"""Concurrency guarantees on disposable PostgreSQL schemas only."""
from datetime import datetime, timezone

from fastapi import HTTPException
import pytest
from sqlalchemy import func, select

from app.cart.operations import CartOperations
from app.cart.repository import SQLAlchemyCartRepository
from app.db.models import CartOperationORM, OrderItemORM, OrderORM, ProductVariantORM, SavedAddressORM
from app.saved_addresses.router import AddressCreate, create_address
from tests import test_postgresql as support

pytestmark = pytest.mark.postgresql
pg_empty = support.pg_empty
pg = support.pg


def test_parallel_merge_same_receipt_only_adds_once(pg):
    def merge():
        with pg.session_factory.begin() as session:
            return CartOperations(session, 1).additions('parallel-merge-123', 'merge',
                [{'variant_id': 1, 'quantity': 4}])
    results = support.parallel(merge, merge)
    assert sorted(row['replayed'] for row in results) == [False, True]
    with pg.session_factory() as session:
        assert SQLAlchemyCartRepository(session).get_by_user_id(1).total_items == 4
        assert session.scalar(select(func.count()).select_from(CartOperationORM)) == 1
        assert session.get(ProductVariantORM, 1).stock == 10


def test_parallel_merge_distinct_keys_cap_to_stock(pg):
    def merge(key):
        with pg.session_factory.begin() as session:
            return CartOperations(session, 1).additions(key, 'merge', [{'variant_id': 1, 'quantity': 8}])
    results = support.parallel(lambda: merge('parallel-key-one'), lambda: merge('parallel-key-two'))
    assert sorted(row['items'][0]['added_quantity'] for row in results) == [2, 8]
    with pg.session_factory() as session:
        assert SQLAlchemyCartRepository(session).get_by_user_id(1).total_items == 10


def test_parallel_address_default_remains_unique(pg):
    from types import SimpleNamespace
    def add(house):
        with pg.session_factory.begin() as session:
            return create_address(AddressCreate(city='Алматы', street='Абая', house=house,
                is_default=True), SimpleNamespace(id=1), session).id
    ids = support.parallel(lambda: add('1'), lambda: add('2'))
    assert len(set(ids)) == 2
    with pg.session_factory() as session:
        rows = session.scalars(select(SavedAddressORM)).all()
        assert len(rows) == 2 and sum(row.is_default for row in rows) == 1


def test_parallel_twentieth_address_enforces_limit(pg):
    from types import SimpleNamespace
    with pg.session_factory.begin() as session:
        now = datetime.now(timezone.utc)
        session.add_all([SavedAddressORM(user_id=1, label='Address', city='City', street='Street',
            house=str(i), details='', source='manual', is_default=i == 0,
            created_at=now, updated_at=now) for i in range(19)])
    def add(house):
        try:
            with pg.session_factory.begin() as session:
                create_address(AddressCreate(city='City', street='Street', house=house),
                    SimpleNamespace(id=1), session)
            return 201
        except HTTPException as exc:
            return exc.status_code
    assert sorted(support.parallel(lambda: add('20'), lambda: add('21'))) == [201, 409]
    with pg.session_factory() as session:
        assert session.scalar(select(func.count()).select_from(SavedAddressORM)) == 20


def test_parallel_repeat_confirmations_with_different_keys_have_one_winner(pg):
    from types import SimpleNamespace
    from app.orders.repeat import RepeatRequest, repeat_order, repeat_preview
    user = SimpleNamespace(id=1)
    with pg.session_factory.begin() as session:
        order = OrderORM(user_id=1, status='created', created_at=datetime.now(timezone.utc))
        session.add(order)
        session.flush()
        order_id = order.id
        session.add(OrderItemORM(order_id=order_id, product_id=1, variant_id=1,
            product_name='Product', variant_label='A', sku='SKU-A', unit_price=10, quantity=4))
    with pg.session_factory.begin() as session:
        fingerprint = repeat_preview(order_id, user, session)['fingerprint']
    def repeat(key):
        try:
            with pg.session_factory.begin() as session:
                repeat_order(order_id, RepeatRequest(operation_key=key, fingerprint=fingerprint,
                    expected_user_id=1), user, session)
            return 200
        except HTTPException as exc:
            return exc.status_code
    assert sorted(support.parallel(lambda: repeat('repeat-race-one'), lambda: repeat('repeat-race-two'))) == [200, 409]
    with pg.session_factory() as session:
        assert SQLAlchemyCartRepository(session).get_by_user_id(1).total_items == 4
        assert session.scalar(select(func.count()).select_from(CartOperationORM)) == 1
