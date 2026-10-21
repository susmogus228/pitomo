"""Add optional storefront product kinds without changing legacy categories."""
from alembic import op
import sqlalchemy as sa

revision = '0006_v081'
down_revision = '0005_v080'
branch_labels = None
depends_on = None

KIND_CHECK = "product_kind IS NULL OR (category = 'food' AND product_kind IN ('food', 'treats')) OR (category = 'accessory' AND product_kind IN ('toys', 'bowls', 'litter', 'habitats', 'walking', 'care', 'aquatics', 'terrariums'))"

# Frozen v0.8.0 seed identities. Do not import the evolving application seed.
LEGACY_DEMO = (
    ('cat', ('Корм для кошек', 'Игрушка с перьями', 'Керамическая миска'), ('food', 'toy', 'bowl'), ('food', 'toys', 'bowls')),
    ('dog', ('Корм для собак', 'Мяч для прогулок', 'Миска для воды'), ('food', 'toy', 'bowl'), ('food', 'toys', 'bowls')),
    ('bird', ('Зерновая смесь для птиц', 'Качели для птиц', 'Домик для птиц'), ('bird-food', 'toy', 'habitat'), ('food', 'toys', 'habitats')),
    ('small_pet', ('Сено для кроликов', 'Туннель для грызунов', 'Домик для грызунов'), ('hay', 'toy', 'habitat'), ('food', 'toys', 'habitats')),
    ('fish', ('Хлопья для рыб', 'Аквариумный декор', 'Аквариум'), ('food', 'aquarium', 'aquarium'), ('food', 'aquatics', 'aquatics')),
    ('reptile', ('Корм для черепах', 'Укрытие для рептилий', 'Субстрат для террариума'), ('food', 'habitat', 'substrate'), ('food', 'terrariums', 'terrariums')),
    ('amphibian', ('Корм для амфибий', 'Поилка для террариума', 'Укрытие для амфибий'), ('food', 'bowl', 'habitat'), ('food', 'bowls', 'terrariums')),
    ('invertebrate', ('Корм для беспозвоночных', 'Кокосовый субстрат', 'Контейнер для наблюдения'), ('food', 'substrate', 'habitat'), ('food', 'terrariums', 'terrariums')),
)


def upgrade():
    with op.batch_alter_table('products') as batch:
        batch.add_column(sa.Column('product_kind', sa.String(32), nullable=True))
        batch.create_check_constraint('ck_products_kind_category', KIND_CHECK)
        batch.create_index('ix_products_pet_type_kind', ['pet_type', 'product_kind'])
    op.execute("UPDATE products SET product_kind = 'food' WHERE category = 'food' AND product_kind IS NULL")
    statement = sa.text("""
        UPDATE products SET product_kind = :kind
        WHERE product_kind IS NULL AND brand = :brand AND pet_type = :pet_type
          AND category = :category AND name = :name AND image_url = :image_url
          AND ((category = 'food' AND composition = :detail)
               OR (category = 'accessory' AND material = :detail))
          AND EXISTS (SELECT 1 FROM product_variants v
                      WHERE v.product_id = products.id AND v.sku = :sku
                        AND v.sku_normalized = :sku_normalized)
          AND (SELECT COUNT(*) FROM product_variants v WHERE v.product_id = products.id) = 1
    """)
    connection = op.get_bind()
    for pet_type, names, images, kinds in LEGACY_DEMO:
        for number, (name, image, kind) in enumerate(zip(names, images, kinds), 1):
            sku = f'PITOMO-DEMO-{pet_type.upper()}-{number:02d}'
            category = 'food' if number == 1 else 'accessory'
            connection.execute(statement, {
                'kind': kind, 'brand': 'Питомо · Демо', 'pet_type': pet_type,
                'category': category, 'name': name + ' · Демо',
                'image_url': f'/media/products/{image}.png', 'sku': sku,
                'sku_normalized': sku.casefold(),
                'detail': ('Демонстрационный товар; состав подлежит уточнению' if number == 1
                           else 'Демонстрационный товар; характеристики подлежат уточнению'),
            })


def downgrade():
    raise RuntimeError('Catalog downgrade discards classification; roll back application code while retaining this additive schema')
