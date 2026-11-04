"""rutracker session

Revision ID: 0002
Revises: 0001
"""

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "rutracker_session",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("cookies", sa.Text()),
        sa.Column("user_agent", sa.Text()),
        sa.Column("username", sa.String(200)),
        sa.Column("logged_in_at", sa.DateTime(timezone=True)),
        sa.Column("last_ok_at", sa.DateTime(timezone=True)),
        sa.Column("cf_solved_at", sa.DateTime(timezone=True)),
        sa.Column("last_error", sa.Text()),
        sa.Column("last_error_at", sa.DateTime(timezone=True)),
    )


def downgrade() -> None:
    op.drop_table("rutracker_session")
