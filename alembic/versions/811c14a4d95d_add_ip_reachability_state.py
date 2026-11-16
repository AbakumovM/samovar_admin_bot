"""add ip reachability state

Revision ID: 811c14a4d95d
Revises: a8a1a41b9486
Create Date: 2026-11-16 20:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '811c14a4d95d'
down_revision: Union[str, None] = 'a8a1a41b9486'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'ip_reachability_state',
        sa.Column('ip', sa.String(length=64), nullable=False),
        sa.Column('status', sa.String(length=16), nullable=True),
        sa.Column('pending_status', sa.String(length=16), nullable=True),
        sa.Column('pending_count', sa.Integer(), nullable=False),
        sa.Column('last_results', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('changed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('checked_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('ip'),
    )


def downgrade() -> None:
    op.drop_table('ip_reachability_state')
