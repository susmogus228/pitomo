"""Authentication throttling storage (independent from request rollbacks)."""
from alembic import op
import sqlalchemy as sa

revision = '0004_v071'
down_revision = '0003_v071'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('login_attempts', sa.Column('key', sa.String(96), primary_key=True),
                    sa.Column('window_started', sa.Float(), nullable=False),
                    sa.Column('attempts', sa.Integer(), nullable=False))
    op.create_index('ix_login_attempts_window_started', 'login_attempts', ['window_started'])


def downgrade():
    op.drop_table('login_attempts')
