"""v0.6.0: initial PostgreSQL/SQLAlchemy persistence schema.

Revision ID: 0001_v060
Revises: None
"""
from alembic import op
import sqlalchemy as sa

revision = '0001_v060'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'users',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('email', sa.String(length=320), nullable=False),
        sa.Column('password_hash', sa.Text(), nullable=False),
        sa.Column('first_name', sa.String(length=120), nullable=False),
        sa.Column('last_name', sa.String(length=120), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.create_index('ix_users_email', 'users', ['email'], unique=True)

    op.create_table(
        'products',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('pet_type', sa.String(length=20), nullable=False),
        sa.Column('brand', sa.String(length=160), nullable=False),
        sa.Column('category', sa.String(length=32), nullable=False),
        sa.Column('composition', sa.Text(), nullable=True),
        sa.Column('material', sa.Text(), nullable=True),
        sa.CheckConstraint("pet_type IN ('cat', 'dog')", name='ck_products_pet_type'),
        sa.CheckConstraint("category IN ('food', 'accessory')", name='ck_products_category'),
    )
    op.create_index('ix_products_pet_type', 'products', ['pet_type'])
    op.create_index('ix_products_brand', 'products', ['brand'])
    op.create_index('ix_products_category', 'products', ['category'])

    op.create_table(
        'product_variants',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('product_id', sa.Integer(), sa.ForeignKey('products.id', ondelete='CASCADE'), nullable=False),
        sa.Column('sku', sa.String(length=120), nullable=False),
        sa.Column('label', sa.String(length=120), nullable=False),
        sa.Column('price', sa.Numeric(12, 2), nullable=False),
        sa.Column('currency', sa.String(length=3), nullable=False, server_default='KZT'),
        sa.Column('stock', sa.Integer(), nullable=False, server_default='0'),
        sa.CheckConstraint('price >= 0', name='ck_product_variants_price_nonnegative'),
        sa.CheckConstraint('stock >= 0', name='ck_product_variants_stock_nonnegative'),
    )
    op.create_index('ix_product_variants_product_id', 'product_variants', ['product_id'])
    op.create_index('ix_product_variants_sku', 'product_variants', ['sku'], unique=True)

    op.create_table(
        'carts',
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='CASCADE'), primary_key=True),
    )
    op.create_table(
        'cart_items',
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('carts.user_id', ondelete='CASCADE'), primary_key=True),
        sa.Column('variant_id', sa.Integer(), primary_key=True),
        sa.Column('quantity', sa.Integer(), nullable=False),
        sa.CheckConstraint('quantity > 0', name='ck_cart_items_quantity_positive'),
    )

    op.create_table(
        'orders',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('status', sa.String(length=32), nullable=False, server_default='created'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("status = 'created'", name='ck_orders_status_created'),
    )
    op.create_index('ix_orders_user_id', 'orders', ['user_id'])

    op.create_table(
        'order_items',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('order_id', sa.Integer(), sa.ForeignKey('orders.id', ondelete='CASCADE'), nullable=False),
        sa.Column('product_id', sa.Integer(), nullable=False),
        sa.Column('product_name', sa.String(length=255), nullable=False),
        sa.Column('variant_id', sa.Integer(), nullable=False),
        sa.Column('sku', sa.String(length=120), nullable=False),
        sa.Column('variant_label', sa.String(length=120), nullable=False),
        sa.Column('unit_price', sa.Numeric(12, 2), nullable=False),
        sa.Column('currency', sa.String(length=3), nullable=False, server_default='KZT'),
        sa.Column('quantity', sa.Integer(), nullable=False),
        sa.CheckConstraint('unit_price >= 0', name='ck_order_items_price_nonnegative'),
        sa.CheckConstraint('quantity > 0', name='ck_order_items_quantity_positive'),
    )
    op.create_index('ix_order_items_order_id', 'order_items', ['order_id'])

    products = sa.table(
        'products',
        sa.column('id', sa.Integer), sa.column('name', sa.String), sa.column('pet_type', sa.String),
        sa.column('brand', sa.String), sa.column('category', sa.String),
        sa.column('composition', sa.Text), sa.column('material', sa.Text),
    )
    variants = sa.table(
        'product_variants',
        sa.column('id', sa.Integer), sa.column('product_id', sa.Integer), sa.column('sku', sa.String),
        sa.column('label', sa.String), sa.column('price', sa.Numeric(12, 2)),
        sa.column('currency', sa.String), sa.column('stock', sa.Integer),
    )
    product_rows = []
    variant_rows = []
    for i in range(1, 21):
        pet = 'cat' if i % 2 else 'dog'
        animal = 'кошек' if pet == 'cat' else 'собак'
        is_food = i <= 10
        product_rows.append({
            'id': i,
            'name': f'{"Корм" if is_food else "Ошейник"} для {animal} №{i}',
            'pet_type': pet,
            'brand': 'DemoPet' if is_food else 'DemoZoo',
            'category': 'food' if is_food else 'accessory',
            'composition': 'курица, рис' if is_food else None,
            'material': None if is_food else 'нейлон',
        })
        variant_rows.append({
            'id': i * 10,
            'product_id': i,
            'sku': f'DEMO-{i}-S',
            'label': '400 г' if is_food else 'S',
            'price': 1000 if i == 1 else 1000 + i * 200,
            'currency': 'KZT',
            'stock': 0 if i == 1 else (5 if i % 4 else 0),
        })
        if i <= 5:
            variant_rows.append({
                'id': i * 10 + 1,
                'product_id': i,
                'sku': f'DEMO-{i}-L',
                'label': '2 кг',
                'price': 6000,
                'currency': 'KZT',
                'stock': 3,
            })
    op.bulk_insert(products, product_rows)
    op.bulk_insert(variants, variant_rows)

    bind = op.get_bind()
    if bind.dialect.name == 'postgresql':
        op.execute("SELECT setval(pg_get_serial_sequence('products','id'), (SELECT MAX(id) FROM products), true)")
        op.execute("SELECT setval(pg_get_serial_sequence('product_variants','id'), (SELECT MAX(id) FROM product_variants), true)")


def downgrade() -> None:
    op.drop_index('ix_order_items_order_id', table_name='order_items')
    op.drop_table('order_items')
    op.drop_index('ix_orders_user_id', table_name='orders')
    op.drop_table('orders')
    op.drop_table('cart_items')
    op.drop_table('carts')
    op.drop_index('ix_product_variants_sku', table_name='product_variants')
    op.drop_index('ix_product_variants_product_id', table_name='product_variants')
    op.drop_table('product_variants')
    op.drop_index('ix_products_category', table_name='products')
    op.drop_index('ix_products_brand', table_name='products')
    op.drop_index('ix_products_pet_type', table_name='products')
    op.drop_table('products')
    op.drop_index('ix_users_email', table_name='users')
    op.drop_table('users')
