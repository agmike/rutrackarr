"""tracked_topics; downloads: what Sonarr/Radarr grabbed a torrent as

Revision ID: 0008
Revises: 0007
"""

import sqlalchemy as sa
from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("downloads") as t:
        t.add_column(sa.Column("content_kind", sa.String(8), nullable=True))
        t.add_column(sa.Column("content_id", sa.Integer(), nullable=True))
        t.add_column(sa.Column("season", sa.Integer(), nullable=True))
    op.create_table(
        "tracked_topics",
        sa.Column("topic_id", sa.Integer(), primary_key=True),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("forum", sa.Text(), nullable=False),
        sa.Column("forum_id", sa.Integer(), nullable=True),
        sa.Column("size", sa.BigInteger(), nullable=False),
        sa.Column("seeders", sa.Integer(), nullable=False),
        sa.Column("info_hash", sa.String(40), nullable=False),
        sa.Column("source", sa.String(8), nullable=False),
        sa.Column("state", sa.String(8), nullable=False),
        sa.Column("content_kind", sa.String(8), nullable=True),
        sa.Column("content_id", sa.Integer(), nullable=True),
        sa.Column("season", sa.Integer(), nullable=True),
        sa.Column("content_title", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_changed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
    )
    op.create_index("ix_tracked_topics_info_hash", "tracked_topics", ["info_hash"])


def downgrade() -> None:
    op.drop_index("ix_tracked_topics_info_hash", "tracked_topics")
    op.drop_table("tracked_topics")
    with op.batch_alter_table("downloads") as t:
        for c in ("season", "content_id", "content_kind"):
            t.drop_column(c)
