"""store_working_hours

Revision ID: 011_store_working_hours
Revises: 010_offer_favorites
Create Date: 2026-02-05 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op


revision: str = "011_store_working_hours"
down_revision: Union[str, None] = "010_offer_favorites"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE stores ADD COLUMN IF NOT EXISTS working_hours TEXT DEFAULT '08:00 - 23:00'"
    )
    op.execute(
        "UPDATE stores SET working_hours = '08:00 - 23:00' WHERE working_hours IS NULL"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE stores DROP COLUMN IF EXISTS working_hours")
