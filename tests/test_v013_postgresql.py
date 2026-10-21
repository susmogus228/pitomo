"""Delivery concurrency is checked against real disposable PostgreSQL schemas."""
import pytest

from app.cart.models import Cart, CartItem
from app.cart.repository import SQLAlchemyCartRepository as Carts
from app.catalog.repository import SQLAlchemyProductRepository as Products
from app.orders.exceptions import OrderCheckoutError
from app.orders.repository import SQLAlchemyOrderRepository as Orders
from app.orders.schemas import CheckoutRequest, DeliveryUpdateRequest
from tests import test_postgresql as pg_support
from tests.test_pitomo_postgresql import service

pg = pg_support.pg
pg_empty = pg_support.pg_empty
parallel = pg_support.parallel
pytestmark = pytest.mark.postgresql


def create_delivery(db):
    with db.session_factory.begin() as session:
        Carts(session).save(Cart(1, [CartItem(1, 1)]))
        details = CheckoutRequest(contact_name='Buyer', phone='77001234567',
                                  delivery_method='delivery', address='Almaty, Abay 10')
        return service(session).checkout(1, details=details)['id']


def mutate(db, order_id, version, **command):
    try:
        with db.session_factory.begin() as session:
            return service(session).update_delivery(order_id,
                DeliveryUpdateRequest(expected_version=version, **command))['delivery_tracking']
    except OrderCheckoutError:
        return 'conflict'


@pytest.mark.parametrize('second_command', [{'stage': 'in_transit'}, {'incident': 'flat_tire'}, {'incident': 'engine_failure'}])
def test_parallel_admin_commands_have_one_winner_and_no_lost_history(pg, second_command):
    order_id = create_delivery(pg)
    results = parallel(lambda: mutate(pg, order_id, 0, stage='in_transit'),
                       lambda: mutate(pg, order_id, 0, **second_command))
    assert results.count('conflict') == 1
    winner = next(result for result in results if result != 'conflict')
    with pg.session_factory() as session:
        tracking = Orders(session).get(order_id).delivery_tracking
        assert tracking.version == 1 and len(tracking.history) == 2
        assert tracking.payload() == winner
        assert (tracking.stage, tracking.incident) in {('in_transit', None), ('warehouse', 'flat_tire'), ('warehouse', 'engine_failure')}
        assert Products(session).find_variant(1)[1].stock == 9


def test_dispatch_and_cancellation_have_one_consistent_winner(pg):
    order_id = create_delivery(pg)
    def cancel():
        try:
            with pg.session_factory.begin() as session:
                return service(session).cancel(1, order_id)['status']
        except OrderCheckoutError:
            return 'conflict'
    results = parallel(lambda: mutate(pg, order_id, 0, stage='in_transit'), cancel)
    assert results.count('conflict') == 1
    with pg.session_factory() as session:
        order_row = Orders(session).get(order_id)
        stock = Products(session).find_variant(1)[1].stock
        assert (order_row.status, order_row.delivery_tracking.stage, stock) in {
            ('created', 'in_transit', 9), ('cancelled', 'warehouse', 10)}
        assert order_row.delivery_tracking.version == (1 if order_row.status == 'created' else 0)


def test_receipt_and_incident_cannot_both_succeed(pg):
    order_id = create_delivery(pg)
    assert mutate(pg, order_id, 0, stage='in_transit') != 'conflict'
    assert mutate(pg, order_id, 1, stage='nearby') != 'conflict'
    def receive():
        try:
            with pg.session_factory.begin() as session:
                return service(session).confirm_receipt(1, order_id)['received_at']
        except OrderCheckoutError:
            return 'conflict'
    results = parallel(lambda: mutate(pg, order_id, 2, incident='overturned'), receive)
    assert results.count('conflict') == 1
    with pg.session_factory() as session:
        order_row = Orders(session).get(order_id)
        assert (order_row.received_at is not None) != (order_row.delivery_tracking.incident is not None)
        assert order_row.delivery_tracking.version == (2 if order_row.received_at else 3)
        assert Products(session).find_variant(1)[1].stock == 9
