"""Real PostgreSQL regressions. Every test owns a disposable random schema.

Set PETSHOP_TEST_POSTGRES_URL to a dedicated database whose name contains test.
No fallback URL, production schema or public table is modified by this suite.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier, Event
import os
import uuid

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError
from sqlalchemy.schema import CreateSchema, DropSchema

from app.admin.schemas import AdminUserUpdate
from app.admin.service import AdminService
from app.cart.models import Cart, CartItem
from app.cart.repository import SQLAlchemyCartRepository as Carts
from app.cart.service import CartService
from app.catalog.exceptions import DuplicateSKUError
from app.catalog.models import Food, ProductVariant
from app.catalog.repository import SQLAlchemyProductRepository as Products
from app.catalog.schemas import ProductUpdate, VariantUpdate
from app.catalog.service import CatalogService
from app.db.session import Database
from app.orders.exceptions import EmptyCartError, OrderCheckoutError
from app.orders.repository import SQLAlchemyOrderRepository as Orders
from app.orders.service import OrderService
from app.users.exceptions import EmailAlreadyExistsError
from app.users.models import User
from app.users.repository import SQLAlchemyUserRepository as Users
from app.users.schemas import UserUpdate
from app.users.service import UserService

pytestmark = pytest.mark.postgresql


@pytest.fixture
def pg_empty():
    url = os.getenv('PETSHOP_TEST_POSTGRES_URL')
    if not url:
        pytest.skip('PETSHOP_TEST_POSTGRES_URL is not configured; PostgreSQL locks are not validated')
    parsed = make_url(url)
    if parsed.get_backend_name() != 'postgresql' or 'test' not in (parsed.database or '').lower():
        pytest.fail('PostgreSQL suite requires an explicitly isolated database with test in its name')
    schema = 'petshop_v071_' + uuid.uuid4().hex
    admin_engine = create_engine(url, pool_pre_ping=True, connect_args={'connect_timeout': 5})
    with admin_engine.begin() as connection:
        connection.execute(CreateSchema(schema))
    db = Database(url)
    db._engine = create_engine(url, pool_pre_ping=True, connect_args={
        'connect_timeout': 5,
        'options': f'-csearch_path={schema} -clock_timeout=5000 -cstatement_timeout=15000',
    })
    try:
        yield db
    finally:
        db.dispose()
        # schema comes exclusively from uuid4 above and belongs to this fixture.
        assert schema.startswith('petshop_v071_') and len(schema) == 45
        with admin_engine.begin() as connection:
            connection.execute(DropSchema(schema, cascade=True))
        admin_engine.dispose()


@pytest.fixture
def pg(pg_empty):
    db = pg_empty
    db.create_schema()
    with db.session_factory.begin() as session:
        Products(session).add(Food(1, 'Product', 'cat', 'Brand', [
            ProductVariant(1, 'SKU-A', 'A', '10.00', 10),
            ProductVariant(2, 'SKU-B', 'B', '20.00', 10),
        ], 'Composition'))
        Users(session).add(User(1, 'one@example.com', 'hash', 'One', role='admin'))
        Users(session).add(User(2, 'two@example.com', 'hash', 'Two'))
        for table in ('users', 'products', 'product_variants'):
            session.execute(text(f"SELECT setval(pg_get_serial_sequence('{table}', 'id'), (SELECT MAX(id) FROM {table}), true)"))
    return db


def checkout(session, user_id, key=None):
    return OrderService(Orders(session), Carts(session), Products(session)).checkout(user_id, idempotency_key=key)


def parallel(*operations):
    barrier = Barrier(len(operations))
    def run(operation):
        barrier.wait(timeout=10)
        return operation()
    with ThreadPoolExecutor(max_workers=len(operations)) as executor:
        futures = [executor.submit(run, operation) for operation in operations]
        return [future.result(timeout=20) for future in futures]


def test_two_customers_cannot_buy_same_last_item(pg):
    with pg.session_factory.begin() as session:
        Products(session).set_variant_stock(1, 1)
        for user_id in (1, 2):
            Carts(session).save(Cart(user_id, [CartItem(1, 1)]))
    def buy(user_id):
        try:
            with pg.session_factory.begin() as session:
                checkout(session, user_id)
            return 'created'
        except OrderCheckoutError:
            return 'out_of_stock'
    assert sorted(parallel(lambda: buy(1), lambda: buy(2))) == ['created', 'out_of_stock']
    with pg.session_factory() as session:
        assert Products(session).find_variant(1)[1].stock == 0
        assert session.scalar(text('SELECT COUNT(*) FROM orders')) == 1


@pytest.mark.parametrize('key', [None, 'same-attempt'])
def test_same_cart_checkout_is_serialized(pg, key):
    with pg.session_factory.begin() as session:
        Carts(session).save(Cart(1, [CartItem(1, 1)]))
    def buy():
        try:
            with pg.session_factory.begin() as session:
                return checkout(session, 1, key)['id']
        except EmptyCartError:
            return None
    results = parallel(buy, buy)
    assert len(set(value for value in results if value is not None)) == 1
    assert results.count(None) == (1 if key is None else 0)
    with pg.session_factory() as session:
        assert session.scalar(text('SELECT COUNT(*) FROM orders')) == 1
        assert Products(session).find_variant(1)[1].stock == 9


@pytest.mark.parametrize('initial', [0, 1])
def test_cart_additions_and_first_cart_creation_are_serialized(pg, initial):
    if initial:
        with pg.session_factory.begin() as session:
            Carts(session).save(Cart(1, [CartItem(1, initial)]))
    def add():
        with pg.session_factory.begin() as session:
            return CartService(Carts(session), Products(session)).add_item(1, 1, 1)
    parallel(add, add)
    with pg.session_factory() as session:
        assert Carts(session).get_by_user_id(1).items[0].quantity == initial + 2


def test_checkout_reads_fresh_sibling_stock_after_wait(pg):
    first_sku_locked, other_committed = Event(), Event()
    with pg.session_factory.begin() as session:
        Carts(session).save(Cart(1, [CartItem(1, 1), CartItem(2, 1)]))
        Carts(session).save(Cart(2, [CartItem(2, 1)]))
    class CoordinatedProducts(Products):
        def find_variant(self, variant_id, *, for_update=False):
            found = super().find_variant(variant_id, for_update=for_update)
            if variant_id == 1 and for_update:
                first_sku_locked.set()
                assert other_committed.wait(10)
            return found
    def first():
        with pg.session_factory.begin() as session:
            return OrderService(Orders(session), Carts(session), CoordinatedProducts(session)).checkout(1)
    def second():
        assert first_sku_locked.wait(10)
        try:
            with pg.session_factory.begin() as session:
                checkout(session, 2)
        finally:
            other_committed.set()
    parallel(first, second)
    with pg.session_factory() as session:
        assert Products(session).find_variant(2)[1].stock == 8
        assert session.scalar(text('SELECT SUM(quantity) FROM order_items WHERE variant_id=2')) == 2


def test_metadata_patch_does_not_restore_checkout_stock(pg):
    loaded, purchased = Event(), Event()
    with pg.session_factory.begin() as session:
        Carts(session).save(Cart(2, [CartItem(1, 1)]))
    class InterruptedProducts(Products):
        def get(self, product_id):
            snapshot = super().get(product_id)
            loaded.set()
            assert purchased.wait(10)
            return snapshot
    def patch():
        with pg.session_factory.begin() as session:
            CatalogService(InterruptedProducts(session)).update_product(1, ProductUpdate(name='Changed'))
    def buy():
        assert loaded.wait(10)
        try:
            with pg.session_factory.begin() as session:
                checkout(session, 2)
        finally:
            purchased.set()
    parallel(patch, buy)
    with pg.session_factory() as session:
        assert Products(session).find_variant(1)[1].stock == 9
        assert Products(session).get(1).name == 'Changed'


def test_profile_patch_cannot_restore_concurrent_moderation(pg):
    loaded, moderated = Event(), Event()
    class InterruptedUsers(Users):
        def get(self, user_id):
            snapshot = super().get(user_id)
            loaded.set()
            assert moderated.wait(10)
            return snapshot
    def patch():
        with pg.session_factory.begin() as session:
            UserService(InterruptedUsers(session)).update_profile(1, UserUpdate(first_name='Changed'))
    def moderate():
        assert loaded.wait(10)
        try:
            with pg.session_factory.begin() as session:
                AdminService(Users(session)).update_user(Users(session).get(2), 1, AdminUserUpdate(role='customer', is_active=False))
        finally:
            moderated.set()
    parallel(patch, moderate)
    with pg.session_factory() as session:
        user = Users(session).get(1)
        assert (user.role, user.is_active, user.first_name) == ('customer', False, 'Changed')


def test_concurrent_email_constraint_becomes_domain_conflict(pg):
    prechecked = Barrier(2)
    def register():
        try:
            with pg.session_factory.begin() as session:
                repo = Users(session)
                assert repo.get_by_email('race@example.com') is None
                prechecked.wait(timeout=10)
                repo.add(User(repo.next_user_id(), 'race@example.com', 'hash', 'Race'))
            return 'created'
        except EmailAlreadyExistsError:
            return 'conflict'
    assert sorted(parallel(register, register)) == ['conflict', 'created']


def test_concurrent_casefold_sku_constraint_becomes_domain_conflict(pg):
    prechecked = Barrier(2)
    def change(variant_id, sku):
        try:
            with pg.session_factory.begin() as session:
                class CoordinatedProducts(Products):
                    def sku_exists(self, sku, exclude_variant_id=None):
                        result = super().sku_exists(sku, exclude_variant_id)
                        prechecked.wait(timeout=10)
                        return result
                CatalogService(CoordinatedProducts(session)).update_variant(1, variant_id, VariantUpdate(sku=sku))
            return 'updated'
        except DuplicateSKUError:
            return 'conflict'
    assert sorted(parallel(lambda: change(1, 'STRASSE'), lambda: change(2, 'STRAßE'))) == ['conflict', 'updated']


def test_real_stock_lock_blocks_another_writer(pg):
    from concurrent.futures import TimeoutError
    started = Event()
    with pg.session_factory() as first:
        Products(first).find_variant(1, for_update=True)
        def update_stock():
            with pg.session_factory.begin() as second:
                started.set()
                Products(second).set_variant_stock(1, 9)
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(update_stock)
            assert started.wait(5)
            with pytest.raises(TimeoutError):
                future.result(timeout=0.2)
            first.commit()
            future.result(timeout=10)


def test_failed_checkout_rolls_back_without_manual_compensation(pg):
    with pg.session_factory.begin() as session:
        Carts(session).save(Cart(1, [CartItem(1, 1)]))
    class BrokenOrders(Orders):
        def add(self, order, **kwargs):
            raise RuntimeError('deliberate order failure')
    with pytest.raises(RuntimeError, match='deliberate'):
        with pg.session_factory.begin() as session:
            OrderService(BrokenOrders(session), Carts(session), Products(session)).checkout(1)
    with pg.session_factory() as session:
        assert Products(session).find_variant(1)[1].stock == 10
        assert Carts(session).get_by_user_id(1).items[0].quantity == 1
        assert session.scalar(text('SELECT COUNT(*) FROM orders')) == 0


def test_migrations_preserve_legacy_data_and_match_metadata(pg_empty):
    db = pg_empty
    config = Config(str(Path(__file__).resolve().parents[1] / 'alembic.ini'))
    with db.engine.begin() as connection:
        config.attributes['connection'] = connection
        command.upgrade(config, '0002_v070')
        connection.execute(text("INSERT INTO users(id,email,password_hash,first_name,is_active,role) VALUES(1,'keep@example.com','keep-hash','Keep',true,'admin')"))
        connection.execute(text("INSERT INTO orders(id,user_id,status,created_at) VALUES(1,1,'created',CURRENT_TIMESTAMP)"))
        connection.execute(text("INSERT INTO order_items(order_id,product_id,product_name,variant_id,sku,variant_label,unit_price,currency,quantity) VALUES(1,2,'Historical',20,'OLD','Old',9.99,'KZT',1)"))
        command.upgrade(config, 'head')
        command.check(config)
        assert connection.scalar(text('SELECT password_hash FROM users WHERE id=1')) == 'keep-hash'
        assert connection.scalar(text('SELECT product_name FROM order_items')) == 'Historical'
        assert connection.scalar(text('SELECT COUNT(*) FROM products')) == 20
    assert 'sku_normalized' in {column['name'] for column in inspect(db.engine).get_columns('product_variants')}


def test_postgresql_constraints_reject_invalid_rows(pg):
    with pytest.raises(IntegrityError):
        with pg.session_factory.begin() as session:
            session.execute(text('UPDATE product_variants SET stock=-1 WHERE id=1'))
    with pytest.raises(IntegrityError):
        with pg.session_factory.begin() as session:
            session.execute(text('INSERT INTO carts(user_id) VALUES(999999)'))


def test_checkout_read_and_replay_json_match_non_utc_database_timezone(pg):
    from app.orders.schemas import OrderResponse
    with pg.session_factory.begin() as session:
        Carts(session).save(Cart(1, [CartItem(1, 1)]))
        first = checkout(session, 1, 'timezone-test')
    with pg.session_factory.begin() as session:
        session.execute(text("SET LOCAL TIME ZONE 'Asia/Almaty'"))
        replay = checkout(session, 1, 'timezone-test')
        read = OrderService(Orders(session), Carts(session), Products(session)).get_order(1, first['id'])
    first_json = OrderResponse.model_validate(first).model_dump(mode='json')
    assert OrderResponse.model_validate(replay).model_dump(mode='json') == first_json
    assert OrderResponse.model_validate(read).model_dump(mode='json') == first_json
