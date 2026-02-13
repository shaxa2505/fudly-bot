"""runtime_schema_compat

Revision ID: 016_runtime_schema_compat
Revises: 015_quantity_float
Create Date: 2026-02-13 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op


revision: str = "016_runtime_schema_compat"
down_revision: Union[str, None] = "015_quantity_float"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # users
    op.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS view_mode TEXT DEFAULT 'customer'")
    op.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS last_delivery_address TEXT")
    op.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS region TEXT")
    op.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS district TEXT")
    op.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS latitude REAL")
    op.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS longitude REAL")
    op.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS region_id INTEGER")
    op.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS district_id INTEGER")

    # stores
    op.execute("ALTER TABLE stores ADD COLUMN IF NOT EXISTS photo TEXT")
    op.execute("ALTER TABLE stores ADD COLUMN IF NOT EXISTS latitude REAL")
    op.execute("ALTER TABLE stores ADD COLUMN IF NOT EXISTS longitude REAL")
    op.execute("ALTER TABLE stores ADD COLUMN IF NOT EXISTS rating REAL DEFAULT 0")
    op.execute("ALTER TABLE stores ADD COLUMN IF NOT EXISTS city_slug TEXT")
    op.execute("ALTER TABLE stores ADD COLUMN IF NOT EXISTS region TEXT")
    op.execute("ALTER TABLE stores ADD COLUMN IF NOT EXISTS region_slug TEXT")
    op.execute("ALTER TABLE stores ADD COLUMN IF NOT EXISTS district TEXT")
    op.execute("ALTER TABLE stores ADD COLUMN IF NOT EXISTS district_slug TEXT")

    # offers
    op.execute("ALTER TABLE offers ADD COLUMN IF NOT EXISTS stock_quantity REAL DEFAULT 0")
    op.execute(
        """
        UPDATE offers
        SET stock_quantity = COALESCE(quantity, 0)
        WHERE stock_quantity IS NULL
           OR (stock_quantity = 0 AND COALESCE(quantity, 0) > 0)
        """
    )

    # bookings
    op.execute("ALTER TABLE bookings ADD COLUMN IF NOT EXISTS store_phone TEXT")
    op.execute("ALTER TABLE bookings ADD COLUMN IF NOT EXISTS cart_items JSONB")
    op.execute("ALTER TABLE bookings ADD COLUMN IF NOT EXISTS is_cart_booking INTEGER DEFAULT 0")
    op.execute("ALTER TABLE bookings ADD COLUMN IF NOT EXISTS customer_message_id BIGINT")
    op.execute("ALTER TABLE bookings ADD COLUMN IF NOT EXISTS seller_message_id BIGINT")
    op.execute("ALTER TABLE bookings ADD COLUMN IF NOT EXISTS rating_reminder_sent BOOLEAN DEFAULT false")
    op.execute("ALTER TABLE bookings ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP")
    op.execute("ALTER TABLE bookings ADD COLUMN IF NOT EXISTS delivery_option INTEGER DEFAULT 0")
    op.execute("ALTER TABLE bookings ADD COLUMN IF NOT EXISTS delivery_address TEXT")
    op.execute("ALTER TABLE bookings ADD COLUMN IF NOT EXISTS delivery_cost INTEGER DEFAULT 0")
    op.execute("ALTER TABLE bookings ADD COLUMN IF NOT EXISTS expiry_time TIMESTAMP")
    op.execute("ALTER TABLE bookings ADD COLUMN IF NOT EXISTS reminder_sent INTEGER DEFAULT 0")
    op.execute("ALTER TABLE bookings ADD COLUMN IF NOT EXISTS payment_proof_photo_id TEXT")
    op.execute("ALTER TABLE bookings ADD COLUMN IF NOT EXISTS pickup_address TEXT")
    op.execute("ALTER TABLE bookings ADD COLUMN IF NOT EXISTS partner_reminder_sent INTEGER DEFAULT 0")
    op.execute("ALTER TABLE bookings ADD COLUMN IF NOT EXISTS delivery_city TEXT")
    op.execute("ALTER TABLE bookings ADD COLUMN IF NOT EXISTS delivery_region TEXT")
    op.execute("ALTER TABLE bookings ADD COLUMN IF NOT EXISTS delivery_district TEXT")
    op.execute("ALTER TABLE bookings ADD COLUMN IF NOT EXISTS delivery_lat REAL")
    op.execute("ALTER TABLE bookings ADD COLUMN IF NOT EXISTS delivery_lon REAL")
    op.execute("ALTER TABLE bookings ADD COLUMN IF NOT EXISTS delivery_structured JSONB")

    # orders
    op.execute("ALTER TABLE orders ADD COLUMN IF NOT EXISTS store_phone TEXT")
    op.execute("ALTER TABLE orders ADD COLUMN IF NOT EXISTS comment TEXT")
    op.execute("ALTER TABLE orders ADD COLUMN IF NOT EXISTS delivery_city TEXT")
    op.execute("ALTER TABLE orders ADD COLUMN IF NOT EXISTS delivery_region TEXT")
    op.execute("ALTER TABLE orders ADD COLUMN IF NOT EXISTS delivery_district TEXT")
    op.execute("ALTER TABLE orders ADD COLUMN IF NOT EXISTS delivery_lat REAL")
    op.execute("ALTER TABLE orders ADD COLUMN IF NOT EXISTS delivery_lon REAL")
    op.execute("ALTER TABLE orders ADD COLUMN IF NOT EXISTS delivery_structured JSONB")
    op.execute("ALTER TABLE orders ADD COLUMN IF NOT EXISTS delivery_price INTEGER")
    op.execute("ALTER TABLE orders ADD COLUMN IF NOT EXISTS item_title TEXT")
    op.execute("ALTER TABLE orders ADD COLUMN IF NOT EXISTS item_price INTEGER")
    op.execute("ALTER TABLE orders ADD COLUMN IF NOT EXISTS item_original_price INTEGER")
    op.execute("ALTER TABLE orders ADD COLUMN IF NOT EXISTS pickup_code TEXT")
    op.execute("ALTER TABLE orders ADD COLUMN IF NOT EXISTS cart_items JSONB")
    op.execute("ALTER TABLE orders ADD COLUMN IF NOT EXISTS is_cart_order INTEGER DEFAULT 0")
    op.execute("ALTER TABLE orders ADD COLUMN IF NOT EXISTS customer_message_id BIGINT")
    op.execute("ALTER TABLE orders ADD COLUMN IF NOT EXISTS seller_message_id BIGINT")
    op.execute("ALTER TABLE orders ADD COLUMN IF NOT EXISTS order_type TEXT DEFAULT 'delivery'")
    op.execute("ALTER TABLE orders ADD COLUMN IF NOT EXISTS rating_reminder_sent BOOLEAN DEFAULT false")
    op.execute("ALTER TABLE orders ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP")
    op.execute("ALTER TABLE orders ADD COLUMN IF NOT EXISTS cancel_reason VARCHAR(50)")
    op.execute("ALTER TABLE orders ADD COLUMN IF NOT EXISTS cancel_comment TEXT")


def downgrade() -> None:
    # Non-destructive compatibility migration: no-op downgrade.
    pass

