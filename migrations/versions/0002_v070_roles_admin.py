"""v0.7.0: user roles and admin authorization.

Revision ID: 0002_v070
Revises: 0001_v060
"""
from alembic import op
import sqlalchemy as sa

revision = '0002_v070'
down_revision = '0001_v060'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # batch_alter_table keeps this migration compatible with SQLite-based
    # migration tests while PostgreSQL performs a regular ALTER TABLE.
    with op.batch_alter_table('users') as batch:
        batch.add_column(
            sa.Column('role', sa.String(length=32), nullable=False, server_default='customer')
        )
        batch.create_check_constraint(
            'ck_users_role',
            "role IN ('customer', 'admin')",
        )


def downgrade() -> None:
    with op.batch_alter_table('users') as batch:
        batch.drop_constraint('ck_users_role', type_='check')
        batch.drop_column('role')
