"""Data integrity, bounded values and checkout idempotency."""
from alembic import op
import sqlalchemy as sa

revision = '0003_v071'
down_revision = '0002_v070'
branch_labels = None
depends_on = None


CHECKS = {
    'users': [('ck_users_id_bounds', 'id BETWEEN 1 AND 2147483647')],
    'products': [('ck_products_id_bounds', 'id BETWEEN 1 AND 2147483647')],
    'product_variants': [
        ('ck_product_variants_id_bounds', 'id BETWEEN 1 AND 2147483647'),
        ('ck_product_variants_stock_max', 'stock <= 2147483647'),
        ('ck_product_variants_price_max', 'price <= 9999999999.99'),
    ],
    'cart_items': [
        ('ck_cart_items_variant_id_bounds', 'variant_id BETWEEN 1 AND 2147483647'),
        ('ck_cart_items_quantity_max', 'quantity <= 10000'),
    ],
    'orders': [('ck_orders_id_bounds', 'id BETWEEN 1 AND 2147483647')],
    'order_items': [
        ('ck_order_items_product_id_bounds', 'product_id BETWEEN 1 AND 2147483647'),
        ('ck_order_items_variant_id_bounds', 'variant_id BETWEEN 1 AND 2147483647'),
        ('ck_order_items_quantity_max', 'quantity <= 10000'),
        ('ck_order_items_price_max', 'unit_price <= 9999999999.99'),
    ],
}


def upgrade():
    bind = op.get_bind()
    if op.get_context().as_sql:
        raise RuntimeError('0003 requires an online migration for Python Unicode casefold backfill and data validation')
    # Validate every new invariant before the first DDL operation. Never merge
    # colliding SKUs or silently alter legacy quantities/passwords/snapshots.
    normalized = {}
    for row in bind.execute(sa.text('SELECT id, sku FROM product_variants')):
        key = row.sku.strip().casefold()
        if key in normalized:
            raise RuntimeError(f'SKU normalization conflict for variant IDs {normalized[key]} and {row.id}; resolve explicitly before retrying')
        normalized[key] = row.id
    for table, checks in CHECKS.items():
        for name, condition in checks:
            if bind.scalar(sa.text(f'SELECT COUNT(*) FROM {table} WHERE NOT ({condition})')):
                raise RuntimeError(f'Legacy rows violate {name}; resolve explicitly before retrying')

    op.add_column('products', sa.Column('name_normalized', sa.Text(), nullable=True))
    op.add_column('products', sa.Column('brand_normalized', sa.Text(), nullable=True))
    op.add_column('product_variants', sa.Column('sku_normalized', sa.Text(), nullable=True))
    for row in bind.execute(sa.text('SELECT id, name, brand FROM products')).all():
        bind.execute(sa.text('UPDATE products SET name_normalized=:name, brand_normalized=:brand WHERE id=:id'),
                     {'name': row.name.strip().casefold(), 'brand': row.brand.strip().casefold(), 'id': row.id})
    for key, variant_id in normalized.items():
        bind.execute(sa.text('UPDATE product_variants SET sku_normalized=:sku WHERE id=:id'), {'sku': key, 'id': variant_id})

    for table, checks in CHECKS.items():
        with op.batch_alter_table(table) as batch:
            for name, condition in checks:
                batch.create_check_constraint(name, condition)
            if table == 'products':
                batch.alter_column('name_normalized', existing_type=sa.Text(), nullable=False)
                batch.alter_column('brand_normalized', existing_type=sa.Text(), nullable=False)
                batch.create_index('ix_products_brand_normalized', ['brand_normalized'])
            elif table == 'product_variants':
                batch.alter_column('sku_normalized', existing_type=sa.Text(), nullable=False)
                batch.create_unique_constraint('uq_product_variants_sku_normalized', ['sku_normalized'])
            elif table == 'orders':
                batch.add_column(sa.Column('idempotency_key', sa.String(128), nullable=True))
                batch.create_unique_constraint('uq_orders_user_idempotency_key', ['user_id', 'idempotency_key'])
                batch.create_index('ix_orders_user_created_id', ['user_id', 'created_at', 'id'])

    op.create_table('id_counters', sa.Column('name', sa.String(40), primary_key=True), sa.Column('value', sa.Integer(), nullable=False))
    maxima = {
        'users': 'SELECT COALESCE(MAX(id),0) FROM users',
        'products': 'SELECT COALESCE(MAX(value),0) FROM (SELECT id AS value FROM products UNION ALL SELECT product_id FROM order_items) AS ids',
        'product_variants': 'SELECT COALESCE(MAX(value),0) FROM (SELECT id AS value FROM product_variants UNION ALL SELECT variant_id FROM cart_items UNION ALL SELECT variant_id FROM order_items) AS ids',
        'orders': 'SELECT COALESCE(MAX(id),0) FROM orders',
    }
    for name, query in maxima.items():
        bind.execute(sa.text('INSERT INTO id_counters (name,value) VALUES (:name,:value)'), {'name': name, 'value': bind.scalar(sa.text(query))})


def downgrade():
    # Downgrading would discard idempotency records and allow ID reuse. Restore
    # a verified pre-upgrade backup if the application must return to v0.7.0.
    raise RuntimeError('0003 downgrade is intentionally blocked; restore a pre-upgrade backup')
