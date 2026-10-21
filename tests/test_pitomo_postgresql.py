"""Cancellation/payment races on a disposable PostgreSQL schema."""
from sqlalchemy import text
import pytest

from app.cart.models import Cart, CartItem
from app.cart.repository import SQLAlchemyCartRepository as Carts
from app.catalog.repository import SQLAlchemyProductRepository as Products
from app.orders.exceptions import OrderCheckoutError
from app.orders.repository import SQLAlchemyOrderRepository as Orders
from app.orders.schemas import CheckoutRequest
from app.orders.service import OrderService
from tests import test_postgresql as pg_support

pg = pg_support.pg
pg_empty = pg_support.pg_empty
parallel = pg_support.parallel

pytestmark = pytest.mark.postgresql


def service(session):
    return OrderService(Orders(session), Carts(session), Products(session))


def create_order(db, *, method='demo'):
    with db.session_factory.begin() as session:
        Carts(session).save(Cart(1, [CartItem(1, 1)]))
        details = CheckoutRequest(contact_name='Test Buyer', phone='77001234567', payment_method=method)
        return service(session).checkout(1, details=details, demo_enabled=True, idempotency_key='race')['id']


def test_concurrent_cancellations_restore_inventory_only_once(pg):
    order_id = create_order(pg)
    def cancel():
        with pg.session_factory.begin() as session:
            return service(session).cancel(1, order_id)
    results = parallel(cancel, cancel)
    assert results[0] == results[1]
    with pg.session_factory() as session:
        assert Products(session).find_variant(1)[1].stock == 10
        assert session.scalar(text('SELECT COUNT(*) FROM orders')) == 1


def test_payment_and_cancel_race_has_one_consistent_winner(pg):
    order_id = create_order(pg)
    def cancel():
        try:
            with pg.session_factory.begin() as session:
                return service(session).cancel(1, order_id)['status']
        except OrderCheckoutError:
            return 'conflict'
    def pay():
        try:
            with pg.session_factory.begin() as session:
                return service(session).demo_payment(1, order_id, 'success', enabled=True)['payment_status']
        except OrderCheckoutError:
            return 'conflict'
    results = parallel(cancel, pay)
    assert results.count('conflict') == 1
    with pg.session_factory() as session:
        order = Orders(session).get(order_id)
        stock = Products(session).find_variant(1)[1].stock
        assert (order.status, order.payment_status, stock) in {
            ('created', 'demo_paid', 9), ('cancelled', 'cancelled', 10)}


def test_concurrent_demo_payment_retries_do_not_mutate_stock(pg):
    order_id = create_order(pg)
    def pay():
        with pg.session_factory.begin() as session:
            return service(session).demo_payment(1, order_id, 'success', enabled=True)
    results = parallel(pay, pay)
    assert results[0] == results[1]
    with pg.session_factory() as session:
        assert Products(session).find_variant(1)[1].stock == 9
        assert session.scalar(text('SELECT COUNT(*) FROM orders')) == 1
