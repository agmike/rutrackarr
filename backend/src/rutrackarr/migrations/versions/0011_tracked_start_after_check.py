"""tracked_topics: start the topic's new torrent once its recheck is done (after an update)

Revision ID: 0011
Revises: 0010
"""

import sqlalchemy as sa
from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("tracked_topics") as t:
        t.add_column(sa.Column("start_after_check", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("tracked_topics") as t:
        t.drop_column("start_after_check")
