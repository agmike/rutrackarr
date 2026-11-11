"""tracked_topics: per-topic TTL (days without an update before it's untracked)

Revision ID: 0010
Revises: 0009
"""

import sqlalchemy as sa
from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("tracked_topics") as t:
        t.add_column(sa.Column("ttl_days", sa.Integer(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("tracked_topics") as t:
        t.drop_column("ttl_days")
