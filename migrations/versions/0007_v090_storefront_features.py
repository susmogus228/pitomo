"""Add verified reviews, scheduled discounts, receipt and delivery coordinates."""
from alembic import op
import sqlalchemy as sa

revision = '0007_v090'
down_revision = '0006_v081'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('products') as batch:
        batch.add_column(sa.Column('discount_percent', sa.Integer(), nullable=True))
        batch.add_column(sa.Column('discount_start_at', sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column('discount_end_at', sa.DateTime(timezone=True), nullable=True))
        batch.create_check_constraint('ck_products_discount_percent',
                                      'discount_percent IS NULL OR discount_percent BETWEEN 1 AND 90')
        batch.create_check_constraint('ck_products_discount_period',
                                      'discount_start_at IS NULL OR discount_end_at IS NULL OR discount_start_at < discount_end_at')
    with op.batch_alter_table('orders') as batch:
        batch.add_column(sa.Column('received_at', sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column('delivery_lat', sa.Numeric(10, 7), nullable=True))
        batch.add_column(sa.Column('delivery_lon', sa.Numeric(10, 7), nullable=True))
        batch.create_check_constraint('ck_orders_delivery_lat', 'delivery_lat IS NULL OR delivery_lat BETWEEN -90 AND 90')
        batch.create_check_constraint('ck_orders_delivery_lon', 'delivery_lon IS NULL OR delivery_lon BETWEEN -180 AND 180')
        batch.create_check_constraint('ck_orders_delivery_point_pair', '(delivery_lat IS NULL) = (delivery_lon IS NULL)')
        batch.create_index('ix_orders_created_sales', ['created_at', 'status', 'payment_status'])
    with op.batch_alter_table('order_items') as batch:
        batch.add_column(sa.Column('original_unit_price', sa.Numeric(12, 2), nullable=True))
        batch.create_check_constraint('ck_order_items_original_price',
                                      'original_unit_price IS NULL OR original_unit_price >= unit_price')
        batch.create_index('ix_order_items_product_order', ['product_id', 'order_id'])
    op.create_table(
        'product_reviews',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('product_id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('order_id', sa.Integer(), sa.ForeignKey('orders.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('rating', sa.Integer(), nullable=False),
        sa.Column('body', sa.String(2000), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint('rating BETWEEN 1 AND 5', name='ck_product_reviews_rating'),
        sa.UniqueConstraint('user_id', 'product_id', name='uq_product_reviews_user_product'),
    )
    op.create_index('ix_product_reviews_product_created', 'product_reviews', ['product_id', 'created_at', 'id'])


def downgrade():
    raise RuntimeError('v0.9 reviews and order data must be retained; roll back application code only')
