"""add reachability notified_at

Revision ID: 8381131d2418
Revises: 811c14a4d95d
Create Date: 2026-11-16 21:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '8381131d2418'
down_revision: Union[str, None] = '811c14a4d95d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'ip_reachability_state',
        sa.Column('notified_at', sa.DateTime(timezone=True), nullable=True),
    )
    # Already-blocked IPs were alerted when their status changed; don't re-remind right
    # after deploy.
    op.execute(
        "UPDATE ip_reachability_state SET notified_at = changed_at "
        "WHERE status IN ('partial', 'blocked')"
    )


def downgrade() -> None:
    op.drop_column('ip_reachability_state', 'notified_at')
