"""downloads: release name, real torrent hash and category (qBittorrent proxy)

Revision ID: 0005
Revises: 0004
"""

import sqlalchemy as sa
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("downloads") as t:
        t.add_column(sa.Column("release", sa.Text(), nullable=True))
        t.add_column(sa.Column("real_hash", sa.String(40), nullable=True))
        t.add_column(sa.Column("category", sa.Text(), nullable=True))
        t.add_column(sa.Column("added_at", sa.DateTime(timezone=True), nullable=True))
        t.create_index("ix_downloads_real_hash", ["real_hash"])


def downgrade() -> None:
    with op.batch_alter_table("downloads") as t:
        t.drop_index("ix_downloads_real_hash")
        for c in ("added_at", "category", "real_hash", "release"):
            t.drop_column(c)
