"""add antifraud soft cooldown and violation counts

Revision ID: 4e9ad6f533f0
Revises: 8e2f87763af0
Create Date: 2026-08-19 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '4e9ad6f533f0'
down_revision: Union[str, None] = '8e2f87763af0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        'antifraud_notified_users', 'notified_at',
        existing_type=sa.DateTime(timezone=True),
        nullable=True,
    )
    op.add_column(
        'antifraud_notified_users',
        sa.Column('soft_notified_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.create_table(
        'antifraud_violation_counts',
        sa.Column('remnawave_id', sa.BigInteger(), autoincrement=False, nullable=False),
        sa.Column('count', sa.Integer(), nullable=False),
        sa.Column('window_expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('remnawave_id'),
    )


def downgrade() -> None:
    op.drop_table('antifraud_violation_counts')
    op.drop_column('antifraud_notified_users', 'soft_notified_at')
    op.alter_column(
        'antifraud_notified_users', 'notified_at',
        existing_type=sa.DateTime(timezone=True),
        nullable=False,
    )
