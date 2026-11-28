"""tracked_topics: drop start_after_check (an update's torrent is started before its recheck
again, and stays started through it)

Revision ID: 0012
Revises: 0011
"""

import sqlalchemy as sa
from alembic import op

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("tracked_topics") as t:
        t.drop_column("start_after_check")


def downgrade() -> None:
    with op.batch_alter_table("tracked_topics") as t:
        t.add_column(sa.Column("start_after_check", sa.DateTime(timezone=True), nullable=True))
