"""Explicit additive demonstration assortment, never a startup side effect."""
from sqlalchemy import func, select, text, update

from app.catalog.models import Accessory, Food, ProductVariant
from app.catalog.repository import SQLAlchemyProductRepository
from app.db.models import ProductORM, ProductVariantORM
from app.db.pitomo_assortment import DEMO_PRODUCTS

# These are illustrative products, not offers from real manufacturers.
ASSORTMENT = (
    ('cat', 'Корм для кошек', 'Игрушка с перьями', 'Керамическая миска', 'food', 'toy', 'bowl'),
    ('dog', 'Корм для собак', 'Мяч для прогулок', 'Миска для воды', 'food', 'toy', 'bowl'),
    ('bird', 'Зерновая смесь для птиц', 'Качели для птиц', 'Домик для птиц', 'bird-food', 'toy', 'habitat'),
    ('small_pet', 'Сено для кроликов', 'Туннель для грызунов', 'Домик для грызунов', 'hay', 'toy', 'habitat'),
    ('fish', 'Хлопья для рыб', 'Аквариумный декор', 'Аквариум', 'food', 'aquarium', 'aquarium'),
    ('reptile', 'Корм для черепах', 'Укрытие для рептилий', 'Субстрат для террариума', 'food', 'habitat', 'substrate'),
    ('amphibian', 'Корм для амфибий', 'Поилка для террариума', 'Укрытие для амфибий', 'food', 'bowl', 'habitat'),
    ('invertebrate', 'Корм для беспозвоночных', 'Кокосовый субстрат', 'Контейнер для наблюдения', 'food', 'substrate', 'habitat'),
)


def _lock_demo_updates(session) -> None:
    if session.get_bind().dialect.name == 'postgresql':
        session.execute(text('SELECT pg_advisory_xact_lock(716280081)'))
    elif session.get_bind().dialect.name == 'sqlite':
        # Acquire write ownership before checking keys, including an empty DB.
        session.execute(text("UPDATE id_counters SET value=value WHERE name='products'"))

def seed_pitomo_catalog(session) -> int:
    """Insert missing dedicated demo SKUs, leaving all existing rows untouched."""
    _lock_demo_updates(session)
    repo = SQLAlchemyProductRepository(session)
    created = 0
    for spec in DEMO_PRODUCTS:
        existing = session.scalar(select(ProductVariantORM).where(ProductVariantORM.sku_normalized == spec.sku.casefold()))
        if existing:
            product = existing.product
            if (product.brand, product.pet_type, product.category) != ('Питомо · Демо', spec.pet_type, spec.category):
                raise ValueError(f'Reserved demo SKU conflict: {spec.sku}')
            continue
        variant = ProductVariant(repo.next_variant_id(), spec.sku, spec.label, str(1800 + 550 * spec.number), 20)
        args = (repo.next_product_id(), spec.full_name, spec.pet_type, 'Питомо · Демо', [variant])
        if spec.category == 'food':
            product = Food(*args, composition=spec.detail)
        else:
            product = Accessory(*args, material=spec.detail)
        product.image_url = spec.image_url
        product.change_product_kind(spec.product_kind)
        repo.add(product)
        created += 1
    return created


def refresh_demo_metadata(session, *, apply: bool = False) -> dict:
    """Compare known legacy metadata and update only product fields, never variants.

    The caller owns the transaction. Dry-run executes no writes. Report values
    contain only reserved SKUs and field names, not customer or order data.
    """
    if apply:
        _lock_demo_updates(session)
    legacy = {row[0]: row for row in ASSORTMENT}
    report = {'mode': 'apply' if apply else 'dry-run', 'updated': [], 'unchanged': [], 'skipped': []}
    for spec in DEMO_PRODUCTS:
        if spec.number > 3:
            continue
        statement = select(ProductVariantORM).where(ProductVariantORM.sku_normalized == spec.sku.casefold())
        # Only product metadata is locked. Inventory rows remain available to
        # checkout, whose multi-SKU lock order must not be inverted here.
        variant = session.scalar(statement)
        if variant is None:
            report['skipped'].append({'sku': spec.sku, 'reason': 'missing'})
            continue
        statement = select(ProductORM).where(ProductORM.id == variant.product_id)
        row = session.scalar(statement.with_for_update() if apply else statement)
        if row is None or (row.brand, row.pet_type, row.category) != ('Питомо · Демо', spec.pet_type, spec.category) or len(row.variants) != 1:
            report['skipped'].append({'sku': spec.sku, 'reason': 'identity-changed'})
            continue
        old = legacy[spec.pet_type]
        old_name = old[spec.number] + ' · Демо'
        old_image = f'/media/products/{old[spec.number + 3]}.png'
        detail_field = 'composition' if spec.category == 'food' else 'material'
        old_detail = ('Демонстрационный товар; состав подлежит уточнению' if spec.category == 'food'
                      else 'Демонстрационный товар; характеристики подлежат уточнению')
        expected = {'name': {old_name, spec.full_name}, 'image_url': {old_image, spec.image_url},
                    'product_kind': {None, spec.product_kind}, detail_field: {old_detail, spec.detail}}
        if any(getattr(row, field) not in allowed for field, allowed in expected.items()):
            report['skipped'].append({'sku': spec.sku, 'reason': 'metadata-changed'})
            continue
        desired = {'name': spec.full_name, 'image_url': spec.image_url,
                   'product_kind': spec.product_kind, detail_field: spec.detail}
        changes = {key: value for key, value in desired.items() if getattr(row, key) != value}
        if not changes:
            report['unchanged'].append(spec.sku)
            continue
        report['updated'].append({'sku': spec.sku, 'fields': sorted(changes)})
        if apply:
            guards = [ProductORM.id == row.id, ProductORM.brand == row.brand,
                      ProductORM.pet_type == row.pet_type, ProductORM.category == row.category]
            guards += [getattr(ProductORM, key) == getattr(row, key) for key in desired]
            guards.append(select(ProductVariantORM.id).where(
                ProductVariantORM.id == variant.id, ProductVariantORM.product_id == row.id,
                ProductVariantORM.sku_normalized == spec.sku.casefold()).exists())
            guards.append(select(func.count()).select_from(ProductVariantORM).where(
                ProductVariantORM.product_id == row.id).scalar_subquery() == 1)
            if 'name' in changes:
                changes['name_normalized'] = spec.full_name.casefold()
            result = session.execute(update(ProductORM).where(*guards).values(**changes),
                                     execution_options={'synchronize_session': False})
            if result.rowcount != 1:
                raise ValueError(f'Concurrent demo metadata change: {spec.sku}')
            session.expire(row)
    if apply:
        session.flush()
    return report
