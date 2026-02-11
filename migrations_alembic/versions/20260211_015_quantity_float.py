"""quantity_float

Revision ID: 015_quantity_float
Revises: 014_store_phone_snapshot
Create Date: 2026-02-11 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op


revision: str = "015_quantity_float"
down_revision: Union[str, None] = "014_store_phone_snapshot"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE offers ALTER COLUMN quantity TYPE REAL USING quantity::real"
    )
    op.execute(
        "ALTER TABLE offers ALTER COLUMN stock_quantity TYPE REAL USING stock_quantity::real"
    )
    op.execute("ALTER TABLE orders ALTER COLUMN quantity TYPE REAL USING quantity::real")
    op.execute(
        "ALTER TABLE bookings ALTER COLUMN quantity TYPE REAL USING quantity::real"
    )
    op.execute("ALTER TABLE offers ALTER COLUMN quantity SET DEFAULT 1")
    op.execute("ALTER TABLE offers ALTER COLUMN stock_quantity SET DEFAULT 0")
    op.execute("ALTER TABLE orders ALTER COLUMN quantity SET DEFAULT 1")
    op.execute("ALTER TABLE bookings ALTER COLUMN quantity SET DEFAULT 1")


def downgrade() -> None:
    op.execute(
        "ALTER TABLE offers ALTER COLUMN quantity TYPE INTEGER USING quantity::integer"
    )
    op.execute(
        "ALTER TABLE offers ALTER COLUMN stock_quantity TYPE INTEGER USING stock_quantity::integer"
    )
    op.execute(
        "ALTER TABLE orders ALTER COLUMN quantity TYPE INTEGER USING quantity::integer"
    )
    op.execute(
        "ALTER TABLE bookings ALTER COLUMN quantity TYPE INTEGER USING quantity::integer"
    )
    op.execute("ALTER TABLE offers ALTER COLUMN quantity SET DEFAULT 1")
    op.execute("ALTER TABLE offers ALTER COLUMN stock_quantity SET DEFAULT 0")
    op.execute("ALTER TABLE orders ALTER COLUMN quantity SET DEFAULT 1")
    op.execute("ALTER TABLE bookings ALTER COLUMN quantity SET DEFAULT 1")
