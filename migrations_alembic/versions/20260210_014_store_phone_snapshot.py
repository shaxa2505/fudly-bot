"""add_store_phone_snapshot

Revision ID: 014_store_phone_snapshot
Revises: 013_add_fk_indexes
Create Date: 2026-02-10 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op


revision: str = "014_store_phone_snapshot"
down_revision: Union[str, None] = "013_add_fk_indexes"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE orders ADD COLUMN IF NOT EXISTS store_phone TEXT")
    op.execute("ALTER TABLE bookings ADD COLUMN IF NOT EXISTS store_phone TEXT")


def downgrade() -> None:
    op.execute("ALTER TABLE bookings DROP COLUMN IF EXISTS store_phone")
    op.execute("ALTER TABLE orders DROP COLUMN IF EXISTS store_phone")
