"""Three-stage delivery with persistent incidents and versioned event history."""
from alembic import op
import sqlalchemy as sa

revision = '0011_v013'
down_revision = '0010_v012'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('orders') as batch:
        batch.add_column(sa.Column('delivery_stage', sa.String(20), nullable=True))
        batch.add_column(sa.Column('delivery_incident', sa.String(20), nullable=True))
        batch.add_column(sa.Column('delivery_incident_note', sa.String(500), nullable=True))
        batch.add_column(sa.Column('delivery_updated_at', sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column('delivery_version', sa.Integer(), nullable=False, server_default='0'))
        batch.add_column(sa.Column('delivery_history', sa.JSON(), nullable=False, server_default=sa.text("'[]'")))
        batch.create_check_constraint('ck_orders_delivery_stage',
            "delivery_stage IS NULL OR delivery_stage IN ('warehouse', 'in_transit', 'nearby')")
        batch.create_check_constraint('ck_orders_delivery_incident',
            "delivery_incident IS NULL OR delivery_incident IN ('flat_tire', 'overturned', 'engine_failure')")
        batch.create_check_constraint('ck_orders_delivery_version', 'delivery_version >= 0')
    # Existing rows have no trustworthy shipping timestamps. Initialize current
    # state only; do not invent a journey or past delivery events.
    op.execute(sa.text("UPDATE orders SET delivery_stage = CASE WHEN received_at IS NOT NULL "
                       "THEN 'nearby' ELSE 'warehouse' END WHERE delivery_method = 'delivery'"))


def downgrade():
    raise RuntimeError('Delivery history must be retained; restore a verified pre-upgrade backup')
