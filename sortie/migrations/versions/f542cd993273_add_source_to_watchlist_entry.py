"""add source to watchlist entry

Revision ID: f542cd993273
Revises: ff928c62498f
Create Date: 2026-10-23 18:30:14.652786

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f542cd993273"
down_revision: str | Sequence[str] | None = "ff928c62498f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # every existing row came from the watchlist
    op.add_column(
        "watchlist_entry",
        sa.Column("source", sa.String(length=300), nullable=False, server_default="watchlist"),
    )
    op.drop_constraint("watchlist_entry_pkey", "watchlist_entry", type_="primary")
    op.create_primary_key("watchlist_entry_pkey", "watchlist_entry", ["source", "letterboxd_slug"])


def downgrade() -> None:
    # the old key is the slug alone, so only watchlist rows can stay
    op.execute("DELETE FROM watchlist_entry WHERE source <> 'watchlist'")
    op.drop_constraint("watchlist_entry_pkey", "watchlist_entry", type_="primary")
    op.create_primary_key("watchlist_entry_pkey", "watchlist_entry", ["letterboxd_slug"])
    op.drop_column("watchlist_entry", "source")
