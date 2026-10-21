"""Regression coverage for the v0.7.1 data integrity repairs."""
from dataclasses import FrozenInstanceError
from decimal import Decimal

import pytest
from pydantic import ValidationError
from sqlalchemy import event, text
from sqlalchemy.exc import IntegrityError

from app.admin.service import AdminService
from app.cart.models import Cart, CartItem
from app.cart.repository import SQLAlchemyCartRepository as Carts
from app.cart.service import CartService
from app.catalog.exceptions import DuplicateSKUError
from app.catalog.models import Food, ProductVariant
from app.catalog.repository import SQLAlchemyProductRepository as Products
from app.catalog.schemas import ProductUpdate, VariantCreate, VariantUpdate
from app.catalog.service import CatalogService
from app.db.models import UserORM
from app.db.session import Database
from app.orders.models import OrderItem
from app.orders.repository import SQLAlchemyOrderRepository as Orders
from app.orders.service import OrderService
from app.users.exceptions import EmailAlreadyExistsError
from app.users.models import User
from app.users.repository import SQLAlchemyUserRepository as Users
from app.users.schemas import UserUpdate
from app.users.service import UserService


@pytest.fixture
def db():
    database = Database('sqlite+pysqlite:///:memory:')
    database.create_schema()
    with database.session_factory.begin() as session:
        Products(session).add(Food(1, 'Straße Food', 'cat', 'Brand', [
            ProductVariant(1, 'SKU-A', 'A', '10.00', 10),
            ProductVariant(2, 'SKU-B', 'B', '20.00', 10),
        ], 'Composition'))
        Users(session).add(User(1, 'one@example.com', 'hash', 'One', role='admin'))
        Users(session).add(User(2, 'two@example.com', 'hash', 'Two'))
    yield database
    database.dispose()


def test_profile_patch_cannot_restore_stale_access(db):
    class InterruptedUsers(Users):
        def get(self, user_id):
            snapshot = super().get(user_id)
            with db.session_factory.begin() as other:
                row = other.get(UserORM, user_id)
                row.role, row.is_active = 'customer', False
            return snapshot

    with db.session_factory.begin() as session:
        UserService(InterruptedUsers(session)).update_profile(1, UserUpdate(first_name='Updated'))
    with db.session_factory() as session:
        user = Users(session).get(1)
        assert (user.role, user.is_active, user.first_name) == ('customer', False, 'Updated')


def test_catalog_metadata_does_not_overwrite_stock(db):
    class InterruptedProducts(Products):
        def get(self, product_id):
            snapshot = super().get(product_id)
            with db.session_factory.begin() as other:
                Products(other).set_variant_stock(1, 9)
            return snapshot

    with db.session_factory.begin() as session:
        CatalogService(InterruptedProducts(session)).update_product(1, ProductUpdate(name='Updated'))
    with db.session_factory() as session:
        product = Products(session).get(1)
        assert (product.name, product.get_variant(1).stock) == ('Updated', 9)


def test_variant_label_does_not_overwrite_concurrent_stock(db):
    class InterruptedProducts(Products):
        def get(self, product_id):
            snapshot = super().get(product_id)
            with db.session_factory.begin() as other:
                Products(other).set_variant_stock(1, 8)
                Products(other).set_variant_stock(2, 7)
            return snapshot

    with db.session_factory.begin() as session:
        CatalogService(InterruptedProducts(session)).update_variant(1, 1, VariantUpdate(label='Updated'))
    with db.session_factory() as session:
        assert [v.stock for v in Products(session).get(1).variants] == [8, 7]


def test_locked_variant_refreshes_preloaded_identity_map(db):
    with db.session_factory() as session:
        from app.db.models import ProductORM
        retained_row = session.get(ProductORM, 1)
        assert retained_row.variants[1].stock == 10
        with db.session_factory.begin() as other:
            Products(other).set_variant_stock(2, 8)
        _, variant = Products(session).find_variant(2, for_update=True)
        assert variant.stock == 8


@pytest.mark.parametrize('operation', ['get', 'add', 'update', 'remove', 'clear', 'checkout'])
def test_cart_operation_locks_user_before_read(db, operation):
    with db.session_factory.begin() as session:
        Carts(session).save(Cart(1, [CartItem(1, 1)]))
    class GuardedCarts(Carts):
        locked = False
        def lock_user(self, user_id):
            self.locked = True
            return super().lock_user(user_id)
        def get_by_user_id(self, user_id):
            assert self.locked, 'Must lock the stable user row before reading cart state'
            return super().get_by_user_id(user_id)
    with db.session_factory.begin() as session:
        carts = GuardedCarts(session)
        service = CartService(carts, Products(session))
        if operation == 'get':
            service.get_cart(1)
        elif operation == 'add':
            service.add_item(1, 1, 1)
        elif operation == 'update':
            service.update_item(1, 1, 2)
        elif operation == 'remove':
            service.remove_item(1, 1)
        elif operation == 'clear':
            service.clear_cart(1)
        else:
            OrderService(Orders(session), carts, Products(session)).checkout(1)


def test_checkout_key_replays_without_consuming_refilled_cart(db):
    with db.session_factory.begin() as session:
        Carts(session).save(Cart(1, [CartItem(1, 1)]))
    with db.session_factory.begin() as session:
        first = OrderService(Orders(session), Carts(session), Products(session)).checkout(1, idempotency_key='retry-1')
    with db.session_factory.begin() as session:
        Carts(session).save(Cart(1, [CartItem(2, 2)]))
    with db.session_factory.begin() as session:
        replay = OrderService(Orders(session), Carts(session), Products(session)).checkout(1, idempotency_key='retry-1')
        assert replay == first
        assert Carts(session).get_by_user_id(1).items[0].quantity == 2
        assert Products(session).get(1).get_variant(1).stock == 9


def test_unicode_sku_normalization_is_enforced(db):
    with db.session_factory.begin() as session:
        CatalogService(Products(session)).update_variant(1, 1, VariantUpdate(sku='STRASSE'))
    with db.session_factory.begin() as session:
        with pytest.raises(DuplicateSKUError):
            CatalogService(Products(session)).update_variant(1, 2, VariantUpdate(sku='STRAßE'))


def test_sqlite_id_not_reused_after_highest_variant_deleted(db):
    with db.session_factory.begin() as session:
        CatalogService(Products(session)).delete_variant(1, 2)
    with db.session_factory.begin() as session:
        variant = CatalogService(Products(session)).add_variant(1, VariantCreate(sku='NEW', label='N', price='1.00', stock=1))
        assert variant.id > 2


def test_sqlite_enforces_foreign_keys(db):
    with db.session_factory() as session:
        assert session.scalar(text('PRAGMA foreign_keys')) == 1


def test_stock_transport_matches_int4_bound():
    with pytest.raises(ValidationError):
        VariantCreate(sku='A', label='A', price='1.00', stock=2**31)


def test_stock_domain_matches_int4_bound():
    with pytest.raises(ValueError):
        ProductVariant(1, 'A', 'A', '1.00', 2**31)


def test_stock_db_matches_int4_bound(db):
    with db.session_factory() as session:
        with pytest.raises(IntegrityError):
            session.execute(text('UPDATE product_variants SET stock=2147483648 WHERE id=1'))


def test_order_snapshot_is_immutable():
    item = OrderItem(product_id=1, product_name='A', variant_id=1, sku='S', variant_label='L', unit_price='1.00', quantity=1)
    with pytest.raises((FrozenInstanceError, AttributeError)):
        item.quantity = 9


def test_catalog_page_is_limited_in_sql_and_casefold_search(db):
    sql = []
    def capture(conn, cursor, statement, parameters, context, executemany):
        sql.append(statement)
    event.listen(db.engine, 'before_cursor_execute', capture)
    try:
        with db.session_factory() as session:
            result = CatalogService(Products(session)).list_products(q='strasse', page_size=1)
        assert result['total'] == 1
        assert any('LIMIT' in s.upper() for s in sql)
        assert any('COUNT' in s.upper() for s in sql)
    finally:
        event.remove(db.engine, 'before_cursor_execute', capture)


def test_catalog_filters_require_same_matching_variant(db):
    with db.session_factory.begin() as session:
        Products(session).set_variant_stock(1, 0)
    with db.session_factory() as session:
        service = CatalogService(Products(session))
        assert service.list_products(max_price=Decimal('15'), in_stock=True)['total'] == 0


def test_cart_loading_has_bounded_query_count(db):
    with db.session_factory.begin() as session:
        service = CatalogService(Products(session))
        for i in range(3, 13):
            service.add_variant(1, VariantCreate(sku=f'SKU-{i}', label='A', price='1.00', stock=10))
        variants = Products(session).get(1).variants
        Carts(session).save(Cart(1, [CartItem(v.id, 1) for v in variants]))
    sql = []
    def capture(conn, cursor, statement, parameters, context, executemany):
        if statement.lstrip().upper().startswith('SELECT'):
            sql.append(statement)
    event.listen(db.engine, 'before_cursor_execute', capture)
    try:
        with db.session_factory.begin() as session:
            result = CartService(Carts(session), Products(session)).get_cart(1)
        assert result['total_items'] == 12
        assert len(sql) <= 5, sql
    finally:
        event.remove(db.engine, 'before_cursor_execute', capture)


def test_user_list_has_bounded_paging(db):
    with db.session_factory() as session:
        assert [u.id for u in AdminService(Users(session)).list_users(limit=1, offset=1)] == [2]


def test_duplicate_email_flush_translates_known_constraint(db):
    with db.session_factory() as session:
        with pytest.raises(EmailAlreadyExistsError):
            Users(session).add(User(3, 'one@example.com', 'hash', 'Duplicate'))


def test_duplicate_sku_flush_translates_known_constraint(db):
    with db.session_factory() as session:
        with pytest.raises(DuplicateSKUError):
            Products(session).add(Food(2, 'Duplicate', 'cat', 'B', [ProductVariant(3, 'SKU-A', 'D', '1.00', 1)], 'C'))


def test_additive_migration_preserves_legacy_data(tmp_path, monkeypatch):
    from pathlib import Path
    from alembic import command
    from alembic.config import Config
    from sqlalchemy import create_engine, inspect
    url = f'sqlite+pysqlite:///{tmp_path / "legacy.db"}'
    monkeypatch.setenv('PETSHOP_DATABASE_URL', url)
    config = Config(str(Path(__file__).resolve().parents[1] / 'alembic.ini'))
    command.upgrade(config, '0002_v070')
    engine = create_engine(url)
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO users (id,email,password_hash,first_name,is_active,role) VALUES (1,'keep@example.com','preserved-hash','Keep',1,'admin')"))
        conn.execute(text("INSERT INTO orders (id,user_id,status,created_at) VALUES (1,1,'created','2026-01-01 00:00:00')"))
        conn.execute(text("INSERT INTO order_items (order_id,product_id,product_name,variant_id,sku,variant_label,unit_price,currency,quantity) VALUES (1,2,'Snapshot',20,'OLD','Old',12.34,'KZT',2)"))
    command.upgrade(config, 'head')
    assert 'sku_normalized' in {c['name'] for c in inspect(engine).get_columns('product_variants')}
    with engine.connect() as conn:
        assert conn.scalar(text("SELECT password_hash FROM users WHERE id=1")) == 'preserved-hash'
        assert conn.scalar(text('SELECT product_name FROM order_items')) == 'Snapshot'
        assert conn.scalar(text('SELECT COUNT(*) FROM products')) == 20
        assert conn.execute(text('PRAGMA foreign_key_check')).all() == []
    engine.dispose()


def test_migration_normalization_conflict_stops_without_deleting_data(tmp_path, monkeypatch):
    from pathlib import Path
    from alembic import command
    from alembic.config import Config
    from sqlalchemy import create_engine
    url = f'sqlite+pysqlite:///{tmp_path / "conflict.db"}'
    monkeypatch.setenv('PETSHOP_DATABASE_URL', url)
    config = Config(str(Path(__file__).resolve().parents[1] / 'alembic.ini'))
    command.upgrade(config, '0002_v070')
    engine = create_engine(url)
    with engine.begin() as conn:
        conn.execute(text("UPDATE product_variants SET sku='STRASSE' WHERE id=10"))
        conn.execute(text("UPDATE product_variants SET sku='STRAßE' WHERE id=11"))
    with pytest.raises(RuntimeError, match='normalization conflict'):
        command.upgrade(config, 'head')
    with engine.connect() as conn:
        assert conn.scalar(text('SELECT COUNT(*) FROM product_variants')) == 25
        assert conn.scalar(text('SELECT version_num FROM alembic_version')) == '0002_v070'
    engine.dispose()


def test_password_rehash_compare_and_swap_preserves_admin_change(db):
    with db.session_factory.begin() as session:
        original = Users(session).get(1).password_hash
        with db.session_factory.begin() as other:
            other.get(UserORM, 1).password_hash = 'new-admin-password'
        assert not Users(session).rehash_password(1, original, 'rehash-of-old-password')
    with db.session_factory.begin() as session:
        assert Users(session).get(1).password_hash == 'new-admin-password'
        assert Users(session).rehash_password(1, 'new-admin-password', 'rehash-of-new-password')


def test_empty_database_initializer_is_seed_optional_and_refuses_existing(tmp_path, monkeypatch):
    from app.db.cli import initialize_database
    url = f'sqlite+pysqlite:///{tmp_path / "empty-init.db"}'
    monkeypatch.setenv('PETSHOP_DATABASE_URL', url)
    initialize_database(url)
    database = Database(url)
    try:
        with database.session_factory() as session:
            assert session.scalar(text('SELECT COUNT(*) FROM products')) == 0
            assert session.scalar(text('SELECT version_num FROM alembic_version')) == '0012_v014'
        with pytest.raises(RuntimeError, match='empty database'):
            initialize_database(url)
    finally:
        database.dispose()


def test_upgrade_command_initializes_empty_and_preserves_existing(tmp_path, monkeypatch):
    from app.db.cli import upgrade_database
    url = f'sqlite+pysqlite:///{tmp_path / "upgrade.db"}'
    monkeypatch.setenv('PETSHOP_DATABASE_URL', url)
    upgrade_database(url)
    db = Database(url)
    try:
        with db.session_factory.begin() as session:
            assert session.scalar(text('SELECT COUNT(*) FROM products')) == 0
            Users(session).add(User(1, 'keep@example.com', 'kept', 'Keep'))
        upgrade_database(url)
        with db.session_factory() as session:
            assert Users(session).get(1).password_hash == 'kept'
    finally:
        db.dispose()


def test_http_idempotency_is_scoped_to_user_and_preserves_new_cart():
    from fastapi.testclient import TestClient
    from app.main import create_test_app
    from tests.helpers import admin_headers
    with TestClient(create_test_app()) as client:
        first_headers = admin_headers(client, 'first@example.com')
        second_headers = admin_headers(client, 'second@example.com')
        key = {'Idempotency-Key': 'one-attempt'}
        for headers in (first_headers, second_headers):
            assert client.post('/api/v1/cart/items', headers=headers, json={'variant_id': 20, 'quantity': 1}).status_code == 200
        first = client.post('/api/v1/orders', headers={**first_headers, **key})
        second = client.post('/api/v1/orders', headers={**second_headers, **key})
        assert first.status_code == second.status_code == 201
        assert first.json()['id'] != second.json()['id']
        client.post('/api/v1/cart/items', headers=first_headers, json={'variant_id': 20, 'quantity': 1})
        replay = client.post('/api/v1/orders', headers={**first_headers, **key})
        assert replay.json() == first.json()
        assert client.get('/api/v1/cart', headers=first_headers).json()['total_items'] == 1
        assert client.post('/api/v1/orders', headers={**first_headers, 'Idempotency-Key': ''}).status_code == 422


def test_http_list_paging_defaults_bounds_and_ids():
    from fastapi.testclient import TestClient
    from app.main import create_test_app
    from app.orders.models import Order
    from tests.helpers import admin_headers
    with TestClient(create_test_app()) as client:
        headers = admin_headers(client, 'paging@example.com')
        user_id = client.get('/api/v1/users/me', headers=headers).json()['id']
        with client.app.state.database.session_factory.begin() as session:
            users, orders = Users(session), Orders(session)
            for i in range(52):
                users.add(User(users.next_user_id(), f'page-{i}@example.com', 'hash', 'Page'))
                orders.add(Order(id=orders.next_order_id(), user_id=user_id, items=[OrderItem(
                    product_id=1, product_name='P', variant_id=1, sku='S', variant_label='L', unit_price='1.00', quantity=1,
                )]))
        for path in ('/api/v1/admin/users', '/api/v1/orders'):
            assert len(client.get(path, headers=headers).json()) == 50
            assert len(client.get(path, headers=headers, params={'limit': 1, 'offset': 50}).json()) == 1
            for params in ({'limit': 101}, {'limit': 0}, {'offset': -1}):
                assert client.get(path, headers=headers, params=params).status_code == 422
        for path in ('/api/v1/products/2147483648', '/api/v1/orders/2147483648', '/api/v1/admin/users/2147483648'):
            assert client.get(path, headers=headers).status_code == 422


def test_catalog_page_cannot_overflow_database_offset():
    from fastapi.testclient import TestClient
    from app.main import create_test_app
    with TestClient(create_test_app()) as client:
        assert client.get('/api/v1/products', params={'page': 2**100}).status_code == 422


def test_database_schema_helpers_register_auth_models_in_isolated_process(tmp_path):
    import subprocess
    import sys
    from pathlib import Path
    url = f'sqlite+pysqlite:///{tmp_path / "standalone-schema.db"}'
    root = Path(__file__).resolve().parents[1]
    create = subprocess.run([sys.executable, '-c', '''
import sys
from sqlalchemy import inspect
from app.db.session import Database
db = Database(sys.argv[1])
try:
    db.create_schema()
    assert 'app.main' not in sys.modules
    assert 'login_attempts' in inspect(db.engine).get_table_names()
finally:
    db.dispose()
''', url], cwd=root, capture_output=True, text=True, timeout=30)
    assert create.returncode == 0, create.stderr
    # A second fresh interpreter must also discover the auth table before drop.
    drop = subprocess.run([sys.executable, '-c', '''
import sys
from sqlalchemy import inspect
from app.db.session import Database
db = Database(sys.argv[1])
try:
    db.drop_schema()
    assert 'app.main' not in sys.modules
    assert inspect(db.engine).get_table_names() == []
finally:
    db.dispose()
''', url], cwd=root, capture_output=True, text=True, timeout=30)
    assert drop.returncode == 0, drop.stderr


def test_postgresql_connections_receive_finite_driver_timeout(monkeypatch):
    import psycopg
    observed = {}
    def unavailable_connection(*args, **kwargs):
        observed.update(kwargs)
        raise RuntimeError('simulated unavailable PostgreSQL')
    monkeypatch.setattr(psycopg, 'connect', unavailable_connection)
    database = Database('postgresql+psycopg://test@127.0.0.1/petshop_test')
    try:
        with pytest.raises(RuntimeError, match='simulated unavailable'):
            database.engine.connect()
        assert observed.get('connect_timeout') == 5
    finally:
        database.dispose()


def test_alembic_requires_explicit_target_before_opening_engine(monkeypatch):
    from pathlib import Path
    from alembic import command
    from alembic.config import Config
    import sqlalchemy
    monkeypatch.delenv('PETSHOP_DATABASE_URL', raising=False)
    def forbid_implicit_engine(*args, **kwargs):
        raise AssertionError('Migration attempted an implicit database connection')
    monkeypatch.setattr(sqlalchemy, 'engine_from_config', forbid_implicit_engine)
    config = Config(str(Path(__file__).resolve().parents[1] / 'alembic.ini'))
    with pytest.raises(RuntimeError, match='PETSHOP_DATABASE_URL'):
        command.current(config)


def test_database_initializer_uses_explicit_connection_without_environment(tmp_path, monkeypatch):
    from app.db.cli import initialize_database
    monkeypatch.delenv('PETSHOP_DATABASE_URL', raising=False)
    url = f'sqlite+pysqlite:///{tmp_path / "explicit-target.db"}'
    initialize_database(url)
    database = Database(url)
    try:
        with database.session_factory() as session:
            assert session.scalar(text('SELECT version_num FROM alembic_version')) == '0012_v014'
    finally:
        database.dispose()
