"""offer_package_size

Revision ID: 017_offer_package_size
Revises: 016_runtime_schema_compat
Create Date: 2026-02-13 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op


revision: str = "017_offer_package_size"
down_revision: Union[str, None] = "016_runtime_schema_compat"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE offers ADD COLUMN IF NOT EXISTS package_value REAL")
    op.execute("ALTER TABLE offers ADD COLUMN IF NOT EXISTS package_unit TEXT")


def downgrade() -> None:
    op.execute("ALTER TABLE offers DROP COLUMN IF EXISTS package_unit")
    op.execute("ALTER TABLE offers DROP COLUMN IF EXISTS package_value")

