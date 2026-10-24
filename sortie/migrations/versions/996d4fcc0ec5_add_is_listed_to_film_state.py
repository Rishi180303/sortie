"""add is_listed to film_state

Revision ID: 996d4fcc0ec5
Revises: f542cd993273
Create Date: 2026-10-23 18:32:17.188847

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "996d4fcc0ec5"
down_revision: str | Sequence[str] | None = "f542cd993273"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "film_state",
        sa.Column("is_listed", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column("film_state", "is_listed")
