"""Catalog evolution against isolated PostgreSQL schemas only."""
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import select, text
import pytest

from app.catalog.repository import SQLAlchemyProductRepository
from app.db.models import ProductVariantORM
from app.db.pitomo_seed import refresh_demo_metadata, seed_pitomo_catalog
from tests import test_postgresql as pg_support
from tests.test_catalog_v2 import create_legacy_demo, insert_v080_demo_rows, demo_kind_counts, EXPECTED_DEMO_KINDS

pg_empty = pg_support.pg_empty
parallel = pg_support.parallel
pytestmark = pytest.mark.postgresql


def test_concurrent_catalog_seed_adds_exactly_48_products(pg_empty):
    pg_empty.create_schema()
    def seed():
        with pg_empty.session_factory.begin() as session:
            return seed_pitomo_catalog(session)
    assert sorted(parallel(seed, seed)) == [0, 48]
    with pg_empty.session_factory() as session:
        assert session.scalar(text('SELECT COUNT(*) FROM products')) == 48
        assert session.scalar(text('SELECT COUNT(DISTINCT sku) FROM product_variants')) == 48


def test_metadata_refresh_cannot_overwrite_concurrent_stock_write(pg_empty):
    pg_empty.create_schema()
    with pg_empty.session_factory.begin() as session:
        create_legacy_demo(session)
        variant_id = session.scalar(select(ProductVariantORM.id).where(ProductVariantORM.sku == 'PITOMO-DEMO-CAT-01'))
    def refresh():
        with pg_empty.session_factory.begin() as session:
            return refresh_demo_metadata(session, apply=True)
    def change_stock():
        with pg_empty.session_factory.begin() as session:
            SQLAlchemyProductRepository(session).set_variant_stock(variant_id, 17)
    parallel(refresh, change_stock)
    with pg_empty.session_factory() as session:
        row = session.get(ProductVariantORM, variant_id)
        assert row.stock == 17
        assert row.product.image_url == '/media/products/v2/cat-food.webp'


def test_v080_migration_and_seed_backfill_legacy_kinds_without_refresh(pg_empty):
    config = Config(str(Path(__file__).resolve().parents[1] / 'alembic.ini'))
    with pg_empty.engine.connect() as connection:
        config.attributes['connection'] = connection
        command.upgrade(config, '0005_v080')
        insert_v080_demo_rows(connection)
        for table in ('products', 'product_variants'):
            connection.execute(text(f"SELECT setval(pg_get_serial_sequence('{table}', 'id'), (SELECT MAX(id) FROM {table}), true)"))
        before = connection.execute(text('SELECT id,product_id,sku,label,price,stock FROM product_variants ORDER BY id')).all()
        connection.commit()
        command.upgrade(config, 'head')
        command.check(config)
        connection.commit()
    with pg_empty.session_factory.begin() as session:
        assert seed_pitomo_catalog(session) == 24
        assert demo_kind_counts(session) == EXPECTED_DEMO_KINDS
        after = session.execute(text('SELECT id,product_id,sku,label,price,stock FROM product_variants WHERE id<=1024 ORDER BY id')).all()
        assert after == before
