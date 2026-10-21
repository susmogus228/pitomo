"""Pitomo species, revocable browser sessions, favorites and checkout details."""
from alembic import op
import sqlalchemy as sa

revision = '0005_v080'
down_revision = '0004_v071'
branch_labels = None
depends_on = None

PET_TYPES_SQL = "pet_type IN ('cat', 'dog', 'bird', 'small_pet', 'fish', 'reptile', 'amphibian', 'invertebrate')"


def upgrade():
    with op.batch_alter_table('products') as batch:
        batch.drop_constraint('ck_products_pet_type', type_='check')
        batch.create_check_constraint('ck_products_pet_type', PET_TYPES_SQL)
        batch.add_column(sa.Column('image_url', sa.String(500), nullable=True))
    with op.batch_alter_table('orders') as batch:
        batch.drop_constraint('ck_orders_status_created', type_='check')
        batch.create_check_constraint('ck_orders_status_created', "status IN ('created', 'cancelled')")
        batch.add_column(sa.Column('checkout_fingerprint', sa.String(64), nullable=True))
        batch.add_column(sa.Column('contact_name', sa.String(100), nullable=True))
        batch.add_column(sa.Column('phone', sa.String(32), nullable=True))
        batch.add_column(sa.Column('address', sa.String(500), nullable=True))
        batch.add_column(sa.Column('comment', sa.String(1000), nullable=True))
        batch.add_column(sa.Column('delivery_method', sa.String(20), nullable=False, server_default='pickup'))
        batch.add_column(sa.Column('payment_method', sa.String(20), nullable=False, server_default='cod'))
        batch.add_column(sa.Column('payment_status', sa.String(20), nullable=False, server_default='cod_pending'))
        batch.create_check_constraint('ck_orders_payment_method', "payment_method IN ('demo', 'cod')")
        batch.create_check_constraint('ck_orders_payment_status', "payment_status IN ('pending', 'demo_paid', 'failed', 'cod_pending', 'cancelled')")
        batch.create_check_constraint('ck_orders_delivery_method', "delivery_method IN ('pickup', 'delivery')")
    with op.batch_alter_table('orders') as batch:
        for column in ('delivery_method', 'payment_method', 'payment_status'):
            batch.alter_column(column, existing_type=sa.String(20), server_default=None)
    op.create_table('browser_sessions',
        sa.Column('token_hash', sa.String(64), primary_key=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False))
    op.create_index('ix_browser_sessions_user_id', 'browser_sessions', ['user_id'])
    op.create_index('ix_browser_sessions_expires_at', 'browser_sessions', ['expires_at'])
    op.create_table('favorites',
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='CASCADE'), primary_key=True),
        sa.Column('product_id', sa.Integer(), sa.ForeignKey('products.id', ondelete='CASCADE'), primary_key=True))


def downgrade():
    # An old release cannot represent the new checkout/species/session state.
    # Restore a verified pre-upgrade backup instead of silently dropping it.
    raise RuntimeError('Pitomo downgrade would discard storefront data; restore the pre-upgrade backup')
