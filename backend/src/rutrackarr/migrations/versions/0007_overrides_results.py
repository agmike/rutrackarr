"""overrides (per series/film) and query_results (per logged query)

Revision ID: 0007
Revises: 0006
"""

import sqlalchemy as sa
from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "overrides",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("kind", sa.String(8), nullable=False),
        sa.Column("external_id", sa.Integer(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("extra_titles", sa.Text(), nullable=False),
        sa.Column("replace_titles", sa.Boolean(), nullable=False),
        sa.Column("release_title", sa.Text(), nullable=True),
        sa.Column("season_offset", sa.Integer(), nullable=True),
        sa.Column("include_regex", sa.Text(), nullable=True),
        sa.Column("exclude_regex", sa.Text(), nullable=True),
        sa.Column("pins", sa.Text(), nullable=False),
        sa.Column("note", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("kind", "external_id", name="uq_overrides_kind_id"),
    )
    op.create_table(
        "query_results",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("query_id", sa.Integer(), nullable=False),
        sa.Column("topic_id", sa.Integer(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("forum", sa.Text(), nullable=False),
        sa.Column("release", sa.Text(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
    )
    op.create_index("ix_query_results_query_id", "query_results", ["query_id"])


def downgrade() -> None:
    op.drop_index("ix_query_results_query_id", "query_results")
    op.drop_table("query_results")
    op.drop_table("overrides")
