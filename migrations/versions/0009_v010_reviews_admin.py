"""Review discussions, image metadata and audited stock replenishments."""
from alembic import op
import sqlalchemy as sa

revision = '0009_v010'
down_revision = '0008_v090'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('product_reviews') as batch:
        batch.add_column(sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True))
    op.create_table('review_replies',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('review_id', sa.Integer(), sa.ForeignKey('product_reviews.id', ondelete='CASCADE'), nullable=False),
        sa.Column('parent_reply_id', sa.Integer(), sa.ForeignKey('review_replies.id', ondelete='SET NULL'), nullable=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('body', sa.String(2000), nullable=False),
        sa.Column('is_official', sa.Boolean(), nullable=False),
        sa.Column('is_pinned', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True))
    op.create_index('ix_review_replies_review_created', 'review_replies', ['review_id', 'created_at', 'id'])
    op.create_index('uq_review_replies_one_official', 'review_replies', ['review_id'], unique=True,
                    postgresql_where=sa.text('is_pinned AND deleted_at IS NULL'),
                    sqlite_where=sa.text('is_pinned = 1 AND deleted_at IS NULL'))
    op.create_table('review_photos',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('uploader_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('review_id', sa.Integer(), sa.ForeignKey('product_reviews.id', ondelete='CASCADE'), nullable=True),
        sa.Column('reply_id', sa.Integer(), sa.ForeignKey('review_replies.id', ondelete='CASCADE'), nullable=True),
        sa.Column('filename', sa.String(64), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint('(review_id IS NOT NULL) != (reply_id IS NOT NULL)', name='ck_review_photos_one_parent'),
        sa.UniqueConstraint('filename', name='uq_review_photos_filename'))
    op.create_index('ix_review_photos_review_id', 'review_photos', ['review_id'])
    op.create_index('ix_review_photos_reply_id', 'review_photos', ['reply_id'])
    op.create_table('stock_replenishments',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('variant_id', sa.Integer(), nullable=False),
        sa.Column('product_name', sa.String(255), nullable=False),
        sa.Column('variant_label', sa.String(120), nullable=False),
        sa.Column('sku', sa.String(120), nullable=False),
        sa.Column('actor_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('quantity', sa.Integer(), nullable=False),
        sa.Column('stock_before', sa.Integer(), nullable=False),
        sa.Column('stock_after', sa.Integer(), nullable=False),
        sa.Column('reason', sa.String(300), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint('quantity > 0', name='ck_stock_replenishments_quantity_positive'),
        sa.CheckConstraint('stock_after = stock_before + quantity', name='ck_stock_replenishments_balance'))
    op.create_index('ix_stock_replenishments_variant_created', 'stock_replenishments', ['variant_id', 'created_at', 'id'])


def downgrade():
    raise RuntimeError('v0.10 reviews and stock audit must be retained; roll back application code only')
