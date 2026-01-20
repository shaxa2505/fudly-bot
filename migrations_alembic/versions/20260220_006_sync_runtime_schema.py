"""sync_runtime_schema

Revision ID: 006_sync_runtime_schema
Revises: 005_geo_reference
Create Date: 2026-02-20 00:00:00.000000
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "006_sync_runtime_schema"
down_revision: Union[str, None] = "005_geo_reference"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _ensure_orders_cancel_fields() -> None:
    op.execute("ALTER TABLE orders ADD COLUMN IF NOT EXISTS cancel_reason VARCHAR(50)")
    op.execute("ALTER TABLE orders ADD COLUMN IF NOT EXISTS cancel_comment TEXT")
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_orders_cancel_reason ON orders(cancel_reason)"
    )


def _ensure_aux_tables() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS store_admins (
            id SERIAL PRIMARY KEY,
            store_id INTEGER NOT NULL,
            user_id BIGINT NOT NULL,
            role TEXT DEFAULT 'admin',
            added_by BIGINT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (store_id) REFERENCES stores(store_id),
            FOREIGN KEY (user_id) REFERENCES users(user_id),
            FOREIGN KEY (added_by) REFERENCES users(user_id),
            UNIQUE(store_id, user_id)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS store_payment_integrations (
            id SERIAL PRIMARY KEY,
            store_id INTEGER NOT NULL,
            provider TEXT NOT NULL,
            merchant_id TEXT,
            service_id TEXT,
            secret_key TEXT,
            is_active INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (store_id) REFERENCES stores(store_id),
            UNIQUE(store_id, provider)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS uzum_transactions (
            id SERIAL PRIMARY KEY,
            trans_id UUID UNIQUE NOT NULL,
            order_id INTEGER NOT NULL,
            service_id BIGINT,
            amount BIGINT NOT NULL,
            status TEXT NOT NULL,
            payload JSONB,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (order_id) REFERENCES orders(order_id)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS recently_viewed (
            id SERIAL PRIMARY KEY,
            user_id BIGINT NOT NULL,
            offer_id INTEGER NOT NULL,
            viewed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(user_id),
            FOREIGN KEY (offer_id) REFERENCES offers(offer_id)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS search_history (
            id SERIAL PRIMARY KEY,
            user_id BIGINT NOT NULL,
            query TEXT NOT NULL,
            searched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(user_id)
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_recently_viewed_user ON recently_viewed(user_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_search_history_user ON search_history(user_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_store_admins_user_store ON store_admins(user_id, store_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_store_payment_integrations_lookup ON store_payment_integrations(store_id, provider)"
    )


def _ensure_fsm_states_schema() -> None:
    op.execute("ALTER TABLE fsm_states ADD COLUMN IF NOT EXISTS chat_id BIGINT")
    op.execute("ALTER TABLE fsm_states ADD COLUMN IF NOT EXISTS expires_at TIMESTAMP")
    op.execute(
        "ALTER TABLE fsm_states ADD COLUMN IF NOT EXISTS created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP"
    )
    op.execute("ALTER TABLE fsm_states ADD COLUMN IF NOT EXISTS state_name TEXT")
    op.execute(
        "UPDATE fsm_states SET chat_id = user_id WHERE chat_id IS NULL"
    )
    op.execute(
        "UPDATE fsm_states SET created_at = updated_at WHERE created_at IS NULL"
    )
    op.execute("ALTER TABLE fsm_states DROP CONSTRAINT IF EXISTS fsm_states_pkey")
    op.execute(
        "ALTER TABLE fsm_states ADD CONSTRAINT fsm_states_pkey PRIMARY KEY (user_id, chat_id)"
    )


def _backfill_geo_ids(conn: sa.Connection) -> None:
    try:
        from database_pg_module.mixins.offers import canonicalize_geo_slug
    except Exception:
        canonicalize_geo_slug = None

    if canonicalize_geo_slug is None:
        return

    def resolve_region_id(region: str | None) -> int | None:
        if not region:
            return None
        slug = canonicalize_geo_slug(region)
        if slug:
            row = conn.execute(
                sa.text(
                    """
                    SELECT region_id
                    FROM geo_regions
                    WHERE slug_ru = :slug OR slug_uz = :slug
                    LIMIT 1
                    """
                ),
                {"slug": slug},
            ).fetchone()
            if row:
                return row[0]
        row = conn.execute(
            sa.text(
                """
                SELECT region_id
                FROM geo_regions
                WHERE lower(name_ru) = lower(:name) OR lower(name_uz) = lower(:name)
                LIMIT 1
                """
            ),
            {"name": region},
        ).fetchone()
        return row[0] if row else None

    def resolve_district_id(
        district: str | None, region_id: int | None
    ) -> int | None:
        if not district:
            return None
        slug = canonicalize_geo_slug(district)
        if slug:
            row = conn.execute(
                sa.text(
                    """
                    SELECT district_id
                    FROM geo_districts
                    WHERE (slug_ru = :slug OR slug_uz = :slug)
                      AND (:region_id IS NULL OR region_id = :region_id)
                    LIMIT 1
                    """
                ),
                {"slug": slug, "region_id": region_id},
            ).fetchone()
            if row:
                return row[0]
        row = conn.execute(
            sa.text(
                """
                SELECT district_id
                FROM geo_districts
                WHERE (lower(name_ru) = lower(:name) OR lower(name_uz) = lower(:name))
                  AND (:region_id IS NULL OR region_id = :region_id)
                LIMIT 1
                """
            ),
            {"name": district, "region_id": region_id},
        ).fetchone()
        return row[0] if row else None

    users = conn.execute(
        sa.text(
            """
            SELECT user_id, region, district, region_id, district_id
            FROM users
            WHERE (region IS NOT NULL AND region_id IS NULL)
               OR (district IS NOT NULL AND district_id IS NULL)
            """
        )
    ).fetchall()
    for user_id, region, district, region_id, district_id in users:
        new_region_id = region_id or resolve_region_id(region)
        new_district_id = district_id or resolve_district_id(district, new_region_id)
        if new_region_id is not None or new_district_id is not None:
            conn.execute(
                sa.text(
                    """
                    UPDATE users
                    SET region_id = COALESCE(:region_id, region_id),
                        district_id = COALESCE(:district_id, district_id)
                    WHERE user_id = :user_id
                    """
                ),
                {
                    "region_id": new_region_id,
                    "district_id": new_district_id,
                    "user_id": user_id,
                },
            )

    stores = conn.execute(
        sa.text(
            """
            SELECT store_id, region, district, region_id, district_id
            FROM stores
            WHERE (region IS NOT NULL AND region_id IS NULL)
               OR (district IS NOT NULL AND district_id IS NULL)
            """
        )
    ).fetchall()
    for store_id, region, district, region_id, district_id in stores:
        new_region_id = region_id or resolve_region_id(region)
        new_district_id = district_id or resolve_district_id(district, new_region_id)
        if new_region_id is not None or new_district_id is not None:
            conn.execute(
                sa.text(
                    """
                    UPDATE stores
                    SET region_id = COALESCE(:region_id, region_id),
                        district_id = COALESCE(:district_id, district_id)
                    WHERE store_id = :store_id
                    """
                ),
                {
                    "region_id": new_region_id,
                    "district_id": new_district_id,
                    "store_id": store_id,
                },
            )


def _ensure_geo_indexes() -> None:
    op.execute("CREATE INDEX IF NOT EXISTS idx_users_region_id ON users(region_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_users_district_id ON users(district_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_stores_region_id ON stores(region_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_stores_district_id ON stores(district_id)")


def upgrade() -> None:
    _ensure_orders_cancel_fields()
    _ensure_aux_tables()
    _ensure_fsm_states_schema()
    _ensure_geo_indexes()
    conn = op.get_bind()
    _backfill_geo_ids(conn)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_orders_cancel_reason")
    op.execute("ALTER TABLE orders DROP COLUMN IF EXISTS cancel_reason")
    op.execute("ALTER TABLE orders DROP COLUMN IF EXISTS cancel_comment")

    op.execute("DROP INDEX IF EXISTS idx_store_payment_integrations_lookup")
    op.execute("DROP INDEX IF EXISTS idx_store_admins_user_store")
    op.execute("DROP INDEX IF EXISTS idx_search_history_user")
    op.execute("DROP INDEX IF EXISTS idx_recently_viewed_user")
    op.execute("DROP TABLE IF EXISTS search_history")
    op.execute("DROP TABLE IF EXISTS recently_viewed")
    op.execute("DROP TABLE IF EXISTS uzum_transactions")
    op.execute("DROP TABLE IF EXISTS store_payment_integrations")
    op.execute("DROP TABLE IF EXISTS store_admins")

    op.execute("ALTER TABLE fsm_states DROP CONSTRAINT IF EXISTS fsm_states_pkey")
    op.execute("ALTER TABLE fsm_states ADD CONSTRAINT fsm_states_pkey PRIMARY KEY (user_id)")
    op.execute("ALTER TABLE fsm_states DROP COLUMN IF EXISTS chat_id")
    op.execute("ALTER TABLE fsm_states DROP COLUMN IF EXISTS expires_at")
    op.execute("ALTER TABLE fsm_states DROP COLUMN IF EXISTS created_at")
    op.execute("ALTER TABLE fsm_states DROP COLUMN IF EXISTS state_name")
