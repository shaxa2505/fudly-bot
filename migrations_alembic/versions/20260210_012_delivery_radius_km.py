"""add_delivery_radius_km

Revision ID: 012_delivery_radius_km
Revises: 011_store_working_hours
Create Date: 2026-02-10 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op


revision: str = "012_delivery_radius_km"
down_revision: Union[str, None] = "011_store_working_hours"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE stores ADD COLUMN IF NOT EXISTS delivery_radius_km INTEGER DEFAULT 10"
    )
    op.execute(
        "UPDATE stores SET delivery_radius_km = 10 WHERE delivery_radius_km IS NULL"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE stores DROP COLUMN IF EXISTS delivery_radius_km")
