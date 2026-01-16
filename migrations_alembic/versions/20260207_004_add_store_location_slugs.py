"""add_store_location_slugs

Revision ID: 20260207_004
Revises: 003_unified_schema
Create Date: 2026-02-07 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "004_store_location_slugs"
down_revision: Union[str, None] = "003_unified_schema"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("stores", sa.Column("city_slug", sa.Text(), nullable=True))
    op.add_column("stores", sa.Column("region_slug", sa.Text(), nullable=True))
    op.add_column("stores", sa.Column("district_slug", sa.Text(), nullable=True))

    conn = op.get_bind()
    from database_pg_module.mixins.offers import canonicalize_geo_slug

    rows = conn.execute(
        sa.text(
            """
            SELECT store_id, city, region, district
            FROM stores
            WHERE city_slug IS NULL OR region_slug IS NULL OR district_slug IS NULL
            """
        )
    ).fetchall()

    if rows:
        update_sql = sa.text(
            """
            UPDATE stores
            SET city_slug = :city_slug,
                region_slug = :region_slug,
                district_slug = :district_slug
            WHERE store_id = :store_id
            """
        )
        payloads = []
        for row in rows:
            city_slug = canonicalize_geo_slug(row[1])
            region_slug = canonicalize_geo_slug(row[2])
            district_slug = canonicalize_geo_slug(row[3])
            payloads.append(
                {
                    "store_id": row[0],
                    "city_slug": city_slug,
                    "region_slug": region_slug,
                    "district_slug": district_slug,
                }
            )
        conn.execute(update_sql, payloads)

    op.create_index("idx_stores_city_slug", "stores", ["city_slug"])
    op.create_index("idx_stores_region_slug", "stores", ["region_slug"])
    op.create_index("idx_stores_district_slug", "stores", ["district_slug"])
    op.create_index("idx_stores_city_slug_status", "stores", ["city_slug", "status"])


def downgrade() -> None:
    op.drop_index("idx_stores_city_slug_status", table_name="stores")
    op.drop_index("idx_stores_district_slug", table_name="stores")
    op.drop_index("idx_stores_region_slug", table_name="stores")
    op.drop_index("idx_stores_city_slug", table_name="stores")
    op.drop_column("stores", "district_slug")
    op.drop_column("stores", "region_slug")
    op.drop_column("stores", "city_slug")
