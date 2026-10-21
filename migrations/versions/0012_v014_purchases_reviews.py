"""Owner addresses, idempotent cart actions and explicit review moderation."""
from alembic import op
import sqlalchemy as sa

revision = '0012_v014'
down_revision = '0011_v013'
branch_labels = None
depends_on = None


def upgrade():
    # Nullable timestamps preserve the meaning of legacy public reviews.
    with op.batch_alter_table('product_reviews') as batch:
        batch.add_column(sa.Column('hidden_at', sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column('edited_at', sa.DateTime(timezone=True), nullable=True))
    with op.batch_alter_table('review_replies') as batch:
        batch.add_column(sa.Column('edited_at', sa.DateTime(timezone=True), nullable=True))
    op.create_table('saved_addresses',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('label', sa.String(80), nullable=False),
        sa.Column('city', sa.String(120), nullable=False),
        sa.Column('street', sa.String(200), nullable=False),
        sa.Column('house', sa.String(40), nullable=False),
        sa.Column('details', sa.String(200), nullable=False),
        sa.Column('lat', sa.Numeric(10, 7), nullable=True),
        sa.Column('lon', sa.Numeric(10, 7), nullable=True),
        sa.Column('source', sa.String(20), nullable=False),
        sa.Column('is_default', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint('lat IS NULL OR lat BETWEEN -90 AND 90', name='ck_saved_addresses_lat'),
        sa.CheckConstraint('lon IS NULL OR lon BETWEEN -180 AND 180', name='ck_saved_addresses_lon'),
        sa.CheckConstraint('(lat IS NULL) = (lon IS NULL)', name='ck_saved_addresses_point_pair'),
        sa.CheckConstraint("source IN ('manual', 'geoapify', 'map', 'geolocation')", name='ck_saved_addresses_source'),
        sqlite_autoincrement=True)
    op.create_index('ix_saved_addresses_user_id', 'saved_addresses', ['user_id', 'id'])
    op.create_index('uq_saved_addresses_default', 'saved_addresses', ['user_id'], unique=True,
        postgresql_where=sa.text('is_default'), sqlite_where=sa.text('is_default = 1'))
    op.create_table('cart_operations',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('operation_key', sa.String(128), nullable=False),
        sa.Column('kind', sa.String(20), nullable=False),
        sa.Column('request_hash', sa.String(64), nullable=False),
        sa.Column('response', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint('user_id', 'operation_key', name='uq_cart_operations_user_key'),
        sa.CheckConstraint("kind IN ('merge', 'restore', 'favorite', 'repeat')", name='ck_cart_operations_kind'),
        sqlite_autoincrement=True)
    op.create_index('ix_cart_operations_user_created', 'cart_operations', ['user_id', 'created_at'])
    op.create_table('review_reports',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('review_id', sa.Integer(), sa.ForeignKey('product_reviews.id', ondelete='CASCADE'), nullable=False),
        sa.Column('reporter_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('reason', sa.String(20), nullable=False),
        sa.Column('details', sa.String(500), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('status', sa.String(20), nullable=False),
        sa.Column('resolved_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('resolved_by', sa.Integer(), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.UniqueConstraint('reporter_id', 'review_id', name='uq_review_reports_reporter_review'),
        sa.CheckConstraint("reason IN ('spam', 'abuse', 'irrelevant', 'other')", name='ck_review_reports_reason'),
        sa.CheckConstraint("status IN ('pending', 'dismissed', 'actioned')", name='ck_review_reports_status'),
        sqlite_autoincrement=True)
    op.create_index('ix_review_reports_status_created', 'review_reports', ['status', 'created_at', 'id'])
    op.create_index('ix_review_reports_review_id', 'review_reports', ['review_id'])
    op.create_table('review_moderation_events',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('review_id', sa.Integer(), sa.ForeignKey('product_reviews.id', ondelete='CASCADE'), nullable=False),
        sa.Column('admin_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('action', sa.String(20), nullable=False),
        sa.Column('reason', sa.String(500), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("action IN ('hide', 'restore', 'dismiss_reports')", name='ck_review_moderation_events_action'),
        sqlite_autoincrement=True)
    op.create_index('ix_review_moderation_events_review_created', 'review_moderation_events',
        ['review_id', 'created_at', 'id'])


def downgrade():
    raise RuntimeError('Address and moderation records must be retained; restore a verified pre-upgrade backup')
