"""Product galleries and explicit versioned consent receipts; no backfill."""
from alembic import op
import sqlalchemy as sa

revision = '0010_v012'
down_revision = '0009_v010'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('product_photos',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('product_id', sa.Integer(), sa.ForeignKey('products.id', ondelete='CASCADE'), nullable=False),
        sa.Column('filename', sa.String(40), nullable=False, unique=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False))
    op.create_index('ix_product_photos_product_id', 'product_photos', ['product_id'])
    op.create_table('consent_receipts',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('purpose', sa.String(20), nullable=False),
        sa.Column('decision', sa.String(20), nullable=False),
        sa.Column('version', sa.String(100), nullable=False),
        sa.Column('subject_name', sa.String(310), nullable=False),
        sa.Column('document', sa.Text(), nullable=False),
        sa.Column('document_sha256', sa.String(64), nullable=False),
        sa.Column('source', sa.String(20), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("purpose IN ('service', 'analytics')", name='ck_consent_receipts_purpose'),
        sa.CheckConstraint("decision IN ('accepted', 'declined', 'withdrawn')", name='ck_consent_receipts_decision'))
    op.create_index('ix_consent_receipts_user_purpose_id', 'consent_receipts', ['user_id', 'purpose', 'id'])


def downgrade():
    raise RuntimeError('Consent evidence and product photo metadata must be retained; restore a verified backup instead')
