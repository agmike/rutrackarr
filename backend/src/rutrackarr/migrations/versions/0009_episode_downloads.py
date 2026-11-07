"""downloads: single-episode releases (episode, video file)

Revision ID: 0009
Revises: 0008
"""

import sqlalchemy as sa
from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("downloads") as t:
        t.add_column(sa.Column("episode", sa.Integer(), nullable=True))
        t.add_column(sa.Column("file", sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("downloads") as t:
        t.drop_column("file")
        t.drop_column("episode")
