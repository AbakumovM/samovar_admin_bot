"""drop user traffic hourly

Revision ID: c3f1d2a7b9e4
Revises: 8381131d2418
Create Date: 2026-11-18 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c3f1d2a7b9e4'
down_revision: Union[str, None] = '8381131d2418'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_index('ix_user_traffic_hourly_user_recorded', table_name='user_traffic_hourly')
    op.drop_index(op.f('ix_user_traffic_hourly_recorded_at'), table_name='user_traffic_hourly')
    op.drop_table('user_traffic_hourly')


def downgrade() -> None:
    op.create_table('user_traffic_hourly',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('user_uuid', sa.String(length=255), nullable=False),
    sa.Column('recorded_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('delta_bytes', sa.BigInteger(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_user_traffic_hourly_recorded_at'), 'user_traffic_hourly', ['recorded_at'], unique=False)
    op.create_index('ix_user_traffic_hourly_user_recorded', 'user_traffic_hourly', ['user_uuid', 'recorded_at'], unique=False)
