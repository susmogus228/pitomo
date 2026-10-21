"""Track actual demo payment time for rolling bestseller windows."""
from alembic import op
import sqlalchemy as sa

revision = '0008_v090'
down_revision = '0007_v090'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('orders') as batch:
        batch.add_column(sa.Column('paid_at', sa.DateTime(timezone=True), nullable=True))
        batch.create_index('ix_orders_paid_at', ['paid_at'])
        batch.create_index('ix_orders_received_at', ['received_at'])
    # Prior releases stored payment status without its event time. created_at
    # is the best available historical approximation; new payments use now().
    op.execute("UPDATE orders SET paid_at = created_at WHERE payment_method = 'demo' AND payment_status = 'demo_paid' AND paid_at IS NULL")


def downgrade():
    raise RuntimeError('v0.9 sale event timestamps must be retained; roll back application code only')
