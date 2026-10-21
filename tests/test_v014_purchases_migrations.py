"""Additive 0.13 -> 0.14 migration preserves historical review and order facts."""
from pathlib import Path

from alembic import command
from alembic.config import Config
import pytest
from sqlalchemy import create_engine, text

from tests import test_postgresql as support

pg_empty = support.pg_empty


def _upgrade_and_reconcile(config, connection):
    config.attributes['connection'] = connection
    command.upgrade(config, '0011_v013')
    connection.execute(text("INSERT INTO users(id,email,password_hash,first_name,is_active,role) "
        "VALUES(1,'keep-v014@example.test','keep-v014-hash','Keep',true,'customer')"))
    connection.execute(text("INSERT INTO orders(id,user_id,status,created_at,received_at,delivery_method,payment_method,payment_status) "
        "VALUES(1,1,'created',CURRENT_TIMESTAMP,CURRENT_TIMESTAMP,'pickup','cod','cod_pending')"))
    connection.execute(text("INSERT INTO order_items(order_id,product_id,product_name,variant_id,sku,"
        "variant_label,unit_price,currency,quantity) VALUES(1,2,'Historical',20,'OLD','Old',9.99,'KZT',1)"))
    connection.execute(text("INSERT INTO product_reviews(id,product_id,user_id,order_id,rating,body,created_at,updated_at) "
        "VALUES(1,2,1,1,5,'Keep review',CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)"))
    connection.execute(text("INSERT INTO review_replies(id,review_id,user_id,body,is_official,is_pinned,created_at,updated_at) "
        "VALUES(1,1,1,'Keep reply',false,false,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)"))
    before = {table: connection.execute(text(f'SELECT * FROM {table} ORDER BY id')).mappings().all()
        for table in ('users', 'orders', 'order_items', 'product_reviews', 'review_replies')}
    command.upgrade(config, '0012_v014')
    command.check(config)
    for table, original in before.items():
        current = connection.execute(text(f'SELECT * FROM {table} ORDER BY id')).mappings().all()
        assert len(current) == len(original)
        for old, new in zip(original, current):
            assert all(new[key] == value for key, value in old.items())
    review = connection.execute(text('SELECT hidden_at,edited_at FROM product_reviews')).one()
    assert review == (None, None)
    assert connection.scalar(text('SELECT edited_at FROM review_replies')) is None
    for table in ('saved_addresses', 'cart_operations', 'review_reports', 'review_moderation_events'):
        assert connection.scalar(text(f'SELECT COUNT(*) FROM {table}')) == 0
    assert connection.scalar(text('SELECT version_num FROM alembic_version')) == '0012_v014'


def test_v014_sqlite_additive_migration_preserves_data_and_metadata(tmp_path):
    config = Config(str(Path(__file__).resolve().parents[1] / 'alembic.ini'))
    database_url = f'sqlite:///{(tmp_path / "migration.sqlite").as_posix()}'
    config.attributes['database_url'] = database_url
    engine = create_engine(database_url)
    try:
        with engine.begin() as connection:
            _upgrade_and_reconcile(config, connection)
            assert connection.exec_driver_sql('PRAGMA foreign_key_check').first() is None
    finally:
        engine.dispose()


@pytest.mark.postgresql
def test_v014_postgresql_additive_migration_preserves_data_and_metadata(pg_empty):
    config = Config(str(Path(__file__).resolve().parents[1] / 'alembic.ini'))
    with pg_empty.engine.begin() as connection:
        _upgrade_and_reconcile(config, connection)
