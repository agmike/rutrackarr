"""queries (Torznab query log) and events (activity log)

Revision ID: 0006
Revises: 0005
"""

import sqlalchemy as sa
from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "queries",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("caller", sa.String(32), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("query", sa.Text(), nullable=False),
        sa.Column("results", sa.Integer(), nullable=False),
        sa.Column("rutracker_requests", sa.Integer(), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
    )
    op.create_index("ix_queries_at", "queries", ["at"])
    op.create_table(
        "events",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("level", sa.String(8), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("topic_id", sa.Integer(), nullable=True),
    )
    op.create_index("ix_events_at", "events", ["at"])


def downgrade() -> None:
    op.drop_index("ix_events_at", "events")
    op.drop_table("events")
    op.drop_index("ix_queries_at", "queries")
    op.drop_table("queries")
