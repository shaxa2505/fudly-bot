"""search_perf_indexes

Revision ID: 009_search_perf_indexes
Revises: 008_geo_normalization
Create Date: 2026-01-27
"""
from typing import Sequence, Union

from alembic import op


revision: str = "009_search_perf_indexes"
down_revision: Union[str, None] = "008_geo_normalization"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Enable trigram search support
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm;")

    # Compatibility for clean Alembic databases:
    # `stock_quantity` historically came from runtime schema init, but some
    # databases were created from migrations only.
    op.execute("ALTER TABLE offers ADD COLUMN IF NOT EXISTS stock_quantity REAL DEFAULT 0")
    op.execute(
        """
        UPDATE offers
        SET stock_quantity = COALESCE(quantity, 0)
        WHERE stock_quantity IS NULL
           OR (stock_quantity = 0 AND COALESCE(quantity, 0) > 0)
        """
    )

    # Common filter indexes (safe if already present)
    op.execute("CREATE INDEX IF NOT EXISTS idx_offers_status ON offers(status);")
    op.execute("CREATE INDEX IF NOT EXISTS idx_offers_category ON offers(category);")
    op.execute("CREATE INDEX IF NOT EXISTS idx_offers_expiry ON offers(expiry_date);")
    op.execute("CREATE INDEX IF NOT EXISTS idx_offers_stock ON offers(stock_quantity);")
    op.execute("CREATE INDEX IF NOT EXISTS idx_offers_store ON offers(store_id);")
    op.execute("CREATE INDEX IF NOT EXISTS idx_offers_status_store ON offers(status, store_id);")

    op.execute("CREATE INDEX IF NOT EXISTS idx_stores_status ON stores(status);")
    op.execute("CREATE INDEX IF NOT EXISTS idx_stores_city_slug_status ON stores(city_slug, status);")
    op.execute("CREATE INDEX IF NOT EXISTS idx_stores_region_slug ON stores(region_slug);")
    op.execute("CREATE INDEX IF NOT EXISTS idx_stores_district_slug ON stores(district_slug);")

    # Partial index for active, in-stock offers
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_offers_active_instock
        ON offers (store_id, expiry_date)
        WHERE status = 'active'
          AND COALESCE(stock_quantity, quantity) > 0
        """
    )

    # Trigram indexes for fast ILIKE/partial matches
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_offers_title_trgm ON offers USING GIN (LOWER(title) gin_trgm_ops);"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_offers_description_trgm ON offers USING GIN (LOWER(description) gin_trgm_ops);"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_stores_name_trgm ON stores USING GIN (LOWER(name) gin_trgm_ops);"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_stores_city_trgm ON stores USING GIN (LOWER(city) gin_trgm_ops);"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_stores_region_trgm ON stores USING GIN (LOWER(region) gin_trgm_ops);"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_stores_district_trgm ON stores USING GIN (LOWER(district) gin_trgm_ops);"
    )


def downgrade() -> None:
    # Drop only indexes introduced specifically for search performance.
    op.execute("DROP INDEX IF EXISTS idx_offers_title_trgm;")
    op.execute("DROP INDEX IF EXISTS idx_offers_description_trgm;")
    op.execute("DROP INDEX IF EXISTS idx_stores_name_trgm;")
    op.execute("DROP INDEX IF EXISTS idx_stores_city_trgm;")
    op.execute("DROP INDEX IF EXISTS idx_stores_region_trgm;")
    op.execute("DROP INDEX IF EXISTS idx_stores_district_trgm;")
    op.execute("DROP INDEX IF EXISTS idx_offers_active_instock;")
