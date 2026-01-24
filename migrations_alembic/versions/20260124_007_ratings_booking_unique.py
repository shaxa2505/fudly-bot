"""add_ratings_booking_unique

Revision ID: 20260124_007
Revises: 006_sync_runtime_schema
Create Date: 2026-01-24 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "007_ratings_booking_unique"
down_revision: Union[str, None] = "006_sync_runtime_schema"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_ratings_booking_unique ON ratings(booking_id)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_ratings_booking_unique")
