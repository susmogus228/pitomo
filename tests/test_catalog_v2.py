"""Product-kind compatibility, precise filters and safe demo catalog evolution."""
from collections import Counter
from decimal import Decimal
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from fastapi.testclient import TestClient
import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError

from app.catalog.models import Accessory, Food, ProductVariant
from app.catalog.repository import InMemoryProductRepository, SQLAlchemyProductRepository
from app.catalog.service import CatalogService
from app.catalog.types import PET_TYPES, PRODUCT_KINDS
from app.core.config import Settings
from app.db.models import ProductORM, ProductVariantORM
from app.db.pitomo_assortment import DEMO_PRODUCTS
from app.db.pitomo_seed import ASSORTMENT, refresh_demo_metadata, seed_pitomo_catalog
from app.db.session import Database
from app.main import create_app, create_test_app
from tests.helpers import admin_headers


def insert_v080_demo_rows(connection):
    """Insert the frozen previous seed through SQL before kind exists."""
    ids = {}
    number = 1000
    for group, first, second, third, first_image, second_image, third_image in ASSORTMENT:
        for index, (name, image) in enumerate(zip((first, second, third), (first_image, second_image, third_image)), 1):
            number += 1
            sku = f'PITOMO-DEMO-{group.upper()}-{index:02d}'
            name += ' · Демо'
            connection.execute(text('''INSERT INTO products
                (id,name,name_normalized,pet_type,brand,brand_normalized,category,image_url,composition,material)
                VALUES (:id,:name,:normalized,:pet_type,:brand,:brand_normalized,:category,:image,:composition,:material)'''), {
                'id': number, 'name': name, 'normalized': name.casefold(), 'pet_type': group,
                'brand': 'Питомо · Демо', 'brand_normalized': 'Питомо · Демо'.casefold(),
                'category': 'food' if index == 1 else 'accessory', 'image': f'/media/products/{image}.png',
                'composition': 'Демонстрационный товар; состав подлежит уточнению' if index == 1 else None,
                'material': 'Демонстрационный товар; характеристики подлежат уточнению' if index != 1 else None,
            })
            connection.execute(text('''INSERT INTO product_variants
                (id,product_id,sku,sku_normalized,label,price,currency,stock)
                VALUES (:id,:id,:sku,:normalized,'Custom pack',9123.45,'KZT',17)'''), {
                'id': number, 'sku': sku, 'normalized': sku.casefold(),
            })
            ids[sku] = number
    return ids


def demo_kind_counts(session):
    return Counter(session.scalars(select(ProductORM.product_kind).where(ProductORM.brand == 'Питомо · Демо')))


EXPECTED_DEMO_KINDS = {'food': 8, 'treats': 4, 'toys': 4, 'bowls': 7, 'litter': 2,
                       'habitats': 3, 'walking': 1, 'care': 4, 'aquatics': 4, 'terrariums': 11}


def test_runtime_readiness_accepts_actual_alembic_head_and_rejects_stale_revision(tmp_path):
    url = f'sqlite+pysqlite:///{tmp_path / "runtime-readiness.db"}'
    config = Config(str(Path(__file__).resolve().parents[1] / 'alembic.ini'))
    config.attributes['database_url'] = url
    scripts = ScriptDirectory.from_config(config)
    head = scripts.get_current_head()
    previous = scripts.get_revision(head).down_revision
    command.upgrade(config, 'head')
    # Use the runtime factory: the isolated test factory deliberately skips
    # revision checks, so it cannot catch a stale SCHEMA_REVISION constant.
    with TestClient(create_app(settings=Settings.for_testing(database_url=url))) as client:
        assert client.app.state.isolated_test_schema is False
        response = client.get('/ready')
        assert response.status_code == 200, response.text
        assert response.json() == {'status': 'ready', 'revision': head}
        with client.app.state.database.engine.begin() as connection:
            connection.execute(text('UPDATE alembic_version SET version_num=:revision'), {'revision': previous})
        assert client.get('/health').status_code == 200
        response = client.get('/ready')
        assert response.status_code == 503
        assert response.json() == {'detail': 'Database schema is not ready'}


@pytest.fixture
def db(tmp_path):
    database = Database(f'sqlite+pysqlite:///{tmp_path / "catalog-v2.db"}')
    database.create_schema()
    yield database
    database.dispose()


def create_legacy_demo(session):
    """Reproduce the previous seed without depending on its current version."""
    repo = SQLAlchemyProductRepository(session)
    for group, first, second, third, first_image, second_image, third_image in ASSORTMENT:
        for number, (name, image) in enumerate(zip((first, second, third), (first_image, second_image, third_image)), 1):
            variant = ProductVariant(repo.next_variant_id(), f'PITOMO-DEMO-{group.upper()}-{number:02d}',
                                     '500 г' if number == 1 else '1 шт.', str(1800 + 550 * number), 20)
            args = (repo.next_product_id(), name + ' · Демо', group, 'Питомо · Демо', [variant])
            product = (Food(*args, composition='Демонстрационный товар; состав подлежит уточнению') if number == 1
                       else Accessory(*args, material='Демонстрационный товар; характеристики подлежат уточнению'))
            product.image_url = f'/media/products/{image}.png'
            repo.add(product)


def variant_snapshot(session):
    return [tuple(row) for row in session.execute(select(
        ProductVariantORM.id, ProductVariantORM.product_id, ProductVariantORM.sku,
        ProductVariantORM.label, ProductVariantORM.price, ProductVariantORM.stock,
    ).order_by(ProductVariantORM.id))]


def test_fresh_assortment_counts_uniqueness_and_idempotence(db):
    with db.session_factory.begin() as session:
        assert seed_pitomo_catalog(session) == 48
        rows = SQLAlchemyProductRepository(session).all()
        assert Counter(row.pet_type for row in rows) == {pet: 6 for pet in PET_TYPES}
        assert Counter(row.product_kind for row in rows) == EXPECTED_DEMO_KINDS
        assert len({row.variants[0].sku for row in rows}) == 48
        for row, spec in zip(rows, DEMO_PRODUCTS):
            assert row.image_url == spec.image_url
            assert row.category == spec.category
        original = variant_snapshot(session)
    with db.session_factory.begin() as session:
        assert seed_pitomo_catalog(session) == 0
        assert variant_snapshot(session) == original


def test_existing_demo_expands_without_replacing_inventory_or_metadata(db):
    with db.session_factory.begin() as session:
        create_legacy_demo(session)
        row = session.scalar(select(ProductVariantORM).where(ProductVariantORM.sku == 'PITOMO-DEMO-CAT-01'))
        row.stock, row.price, row.label = 17, Decimal('9123.45'), 'Custom pack'
        session.flush()
        before = variant_snapshot(session)
        old_name = row.product.name
        assert seed_pitomo_catalog(session) == 24
        assert variant_snapshot(session)[:24] == before
        assert row.product.name == old_name
        assert row.product.image_url == '/media/products/food.png'
        assert seed_pitomo_catalog(session) == 0


def test_metadata_dry_run_then_apply_preserves_variants_and_repeats(db):
    with db.session_factory.begin() as session:
        create_legacy_demo(session)
        row = session.scalar(select(ProductVariantORM).where(ProductVariantORM.sku == 'PITOMO-DEMO-DOG-01'))
        row.stock, row.price, row.label = 17, Decimal('4567.89'), 'Custom pack'
        session.flush()
        before = variant_snapshot(session)
        planned = refresh_demo_metadata(session)
        assert len(planned['updated']) == 24
        assert row.product.image_url == '/media/products/food.png'
        result = refresh_demo_metadata(session, apply=True)
        assert len(result['updated']) == 24
        session.expire_all()
        assert row.product.image_url == '/media/products/v2/dog-food.webp'
        assert variant_snapshot(session) == before
        repeated = refresh_demo_metadata(session, apply=True)
        assert repeated['updated'] == []
        assert len(repeated['unchanged']) == 24


@pytest.mark.parametrize('field,value', [('name', 'Custom name'), ('image_url', '/custom.webp'),
                                        ('material', 'Custom material'), ('product_kind', 'care')])
def test_refresh_skips_user_edited_metadata(db, field, value):
    with db.session_factory.begin() as session:
        create_legacy_demo(session)
        row = session.scalar(select(ProductORM).join(ProductVariantORM).where(
            ProductVariantORM.sku == 'PITOMO-DEMO-CAT-02'))
        setattr(row, field, value)
        session.flush()
        result = refresh_demo_metadata(session, apply=True)
        assert {'sku': 'PITOMO-DEMO-CAT-02', 'reason': 'metadata-changed'} in result['skipped']
        session.expire_all()
        assert getattr(row, field) == value
        assert row.image_url == (value if field == 'image_url' else '/media/products/toy.png')


def test_seed_reserved_sku_conflict_fails_without_adopting_foreign_product(db):
    with db.session_factory.begin() as session:
        SQLAlchemyProductRepository(session).add(Food(1, 'Mine', 'cat', 'Custom', [
            ProductVariant(1, 'PITOMO-DEMO-CAT-01', 'Mine', '1.00', 7)], 'Mine'))
    with pytest.raises(ValueError, match='Reserved demo SKU conflict'):
        with db.session_factory.begin() as session:
            seed_pitomo_catalog(session)
    with db.session_factory() as session:
        assert session.scalar(text('SELECT COUNT(*) FROM products')) == 1
        assert session.get(ProductVariantORM, 1).stock == 7


def test_repository_add_does_not_duplicate_loaded_variants(db):
    product = Accessory(1, 'Toy', 'cat', 'Brand', [
        ProductVariant(1, 'TOY-SMALL', 'Small', '10', 2),
        ProductVariant(2, 'TOY-LARGE', 'Large', '20', 3)], 'Cotton')
    with db.session_factory.begin() as session:
        repo = SQLAlchemyProductRepository(session)
        repo.add(product)
        row = session.get(ProductORM, product.id)
        assert [variant.id for variant in row.variants] == [1, 2]
        # Keep the row alive: a database reload must not hide duplicated
        # relationship entries in the current identity map.
        assert repo.get(product.id).to_dict() == product.to_dict()


def test_filter_and_counts_sql_memory_parity_do_not_mix_variants(db):
    products = [Accessory(1, 'A', 'cat', 'Brand', [
        ProductVariant(1, 'A-cheap', 'Small', '10', 0),
        ProductVariant(2, 'A-stock', 'Large', '100', 5)], 'Cotton'),
        Accessory(2, 'B', 'cat', 'Brand', [ProductVariant(3, 'B', 'One', '15', 4)], 'Cotton'),
        Accessory(3, 'C', 'dog', 'Brand', [ProductVariant(4, 'C', 'One', '15', 4)], 'Cotton')]
    for product in products:
        product.change_product_kind('toys')
    memory = CatalogService(InMemoryProductRepository(products))
    with db.session_factory.begin() as session:
        repo = SQLAlchemyProductRepository(session)
        for product in products:
            repo.add(product)
        sql = CatalogService(repo)
        params = {'pet_type': 'cat', 'category': 'accessory', 'product_kind': 'toys',
                  'max_price': Decimal('20'), 'in_stock': True, 'sort': 'price_asc'}
        assert sql.list_products(**params) == memory.list_products(**params)
        assert [row['id'] for row in sql.list_products(**params)['items']] == [2]
        assert sql.product_kinds(pet_type='cat') == memory.product_kinds(pet_type='cat')
        counts = {item['id']: item['count'] for item in sql.product_kinds(pet_type='cat')}
        assert counts['toys'] == 2
        assert len(counts) == 10
        assert sql.list_products(category='food', product_kind='toys')['total'] == 0


def test_http_contract_old_clients_new_kind_and_validation():
    with TestClient(create_test_app()) as client:
        headers = admin_headers(client)
        data = {'name': 'New', 'pet_type': 'cat', 'brand': 'Custom', 'category': 'accessory',
                'material': 'Cotton', 'variants': [{'sku': 'V2-TEST', 'label': 'One', 'price': '12', 'stock': 2}]}
        created = client.post('/api/v1/products', json=data, headers=headers)
        assert created.status_code == 201
        assert created.json()['product_kind'] is None
        path = f"/api/v1/products/{created.json()['id']}"
        assert client.patch(path, json={'product_kind': 'toys'}, headers=headers).json()['product_kind'] == 'toys'
        assert client.patch(path, json={'product_kind': 'food'}, headers=headers).status_code == 422
        assert client.patch(path, json={'product_kind': None}, headers=headers).status_code == 422
        assert client.get(path).json()['product_kind'] == 'toys'
        assert client.get('/api/v1/products?product_kind=toys&category=food').json()['total'] == 0
        assert client.get('/api/v1/products?product_kind=invalid').status_code == 422
        assert client.get('/api/v1/product-kinds?pet_type=dragon').status_code == 422
        kinds = client.get('/api/v1/product-kinds?pet_type=cat').json()
        assert [item['id'] for item in kinds] == [kind for kind, _ in PRODUCT_KINDS]
        assert next(item for item in kinds if item['id'] == 'toys')['count'] == 1
        assert {item['id'] for item in client.get('/api/v1/categories').json()} == {'food', 'accessory'}
        incompatible = {**data, 'product_kind': 'treats', 'variants': [{**data['variants'][0], 'sku': 'V2-INVALID'}]}
        assert client.post('/api/v1/products', json=incompatible, headers=headers).status_code == 422
        legacy_food = {**data, 'category': 'food', 'composition': 'Composition',
                       'variants': [{**data['variants'][0], 'sku': 'V2-FOOD'}]}
        del legacy_food['material']
        assert client.post('/api/v1/products', json=legacy_food, headers=headers).json()['product_kind'] == 'food'


@pytest.mark.parametrize('kind', ['treats', 'unknown'])
def test_database_rejects_invalid_kind_category_pairs(db, kind):
    with db.session_factory.begin() as session:
        SQLAlchemyProductRepository(session).add(Accessory(1, 'Item', 'cat', 'Brand', [
            ProductVariant(1, 'One', 'One', '1', 1)], 'Cotton'))
    with pytest.raises(IntegrityError):
        with db.engine.begin() as connection:
            connection.execute(text('UPDATE products SET product_kind=:kind WHERE id=1'), {'kind': kind})


def test_v080_upgrade_and_normal_seed_classify_all_48_without_metadata_refresh(tmp_path):
    db = Database(f'sqlite+pysqlite:///{tmp_path / "v080-catalog.db"}')
    config = Config(str(Path(__file__).resolve().parents[1] / 'alembic.ini'))
    config.attributes['database_url'] = db.url
    command.upgrade(config, '0005_v080')
    with db.engine.begin() as connection:
        ids = insert_v080_demo_rows(connection)
        before = connection.execute(text('SELECT id,product_id,sku,label,price,stock FROM product_variants ORDER BY id')).all()
    command.upgrade(config, 'head')
    command.check(config)
    with db.session_factory.begin() as session:
        assert seed_pitomo_catalog(session) == 24
        assert demo_kind_counts(session) == EXPECTED_DEMO_KINDS
        assert session.get(ProductORM, ids['PITOMO-DEMO-CAT-02']).name == 'Игрушка с перьями · Демо'
        assert session.get(ProductORM, ids['PITOMO-DEMO-CAT-02']).image_url == '/media/products/toy.png'
        after = session.execute(text('SELECT id,product_id,sku,label,price,stock FROM product_variants WHERE id<=1024 ORDER BY id')).all()
        assert after == before


@pytest.mark.parametrize('change', ['name', 'brand', 'pet_type', 'image_url', 'material', 'sku', 'second_variant'])
def test_migration_skips_edited_or_ambiguous_accessories(tmp_path, change):
    db = Database(f'sqlite+pysqlite:///{tmp_path / "edited-catalog.db"}')
    config = Config(str(Path(__file__).resolve().parents[1] / 'alembic.ini'))
    config.attributes['database_url'] = db.url
    command.upgrade(config, '0005_v080')
    with db.engine.begin() as connection:
        product_id = insert_v080_demo_rows(connection)['PITOMO-DEMO-CAT-02']
        if change == 'sku':
            connection.execute(text("UPDATE product_variants SET sku='Custom',sku_normalized='custom' WHERE product_id=:id"), {'id': product_id})
        elif change == 'second_variant':
            connection.execute(text('''INSERT INTO product_variants
                (id,product_id,sku,sku_normalized,label,price,currency,stock)
                VALUES (9999,:id,'Extra','extra','Extra',1,'KZT',1)'''), {'id': product_id})
        else:
            value = 'dog' if change == 'pet_type' else 'Custom'
            connection.execute(text(f'UPDATE products SET {change}=:value WHERE id=:id'), {'id': product_id, 'value': value})
    command.upgrade(config, 'head')
    with db.session_factory() as session:
        assert session.get(ProductORM, product_id).product_kind is None
