"""add_missing_fk_indexes

Revision ID: 013_add_fk_indexes
Revises: 012_delivery_radius_km
Create Date: 2026-02-10 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op


revision: str = "013_add_fk_indexes"
down_revision: Union[str, None] = "012_delivery_radius_km"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add indexes for foreign key columns that currently lack them.
    op.execute("CREATE INDEX IF NOT EXISTS idx_orders_offer_id ON orders(offer_id)")
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_store_admins_added_by ON store_admins(added_by)"
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_ratings_order_id ON ratings(order_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_promo_usage_order_id ON promo_usage(order_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_promo_usage_promo_id ON promo_usage(promo_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_promo_usage_user_id ON promo_usage(user_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_referrals_referrer ON referrals(referrer_user_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_referrals_referred ON referrals(referred_user_id)")
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_recently_viewed_offer_id ON recently_viewed(offer_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_uzum_transactions_order_id ON uzum_transactions(order_id)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_uzum_transactions_order_id")
    op.execute("DROP INDEX IF EXISTS idx_recently_viewed_offer_id")
    op.execute("DROP INDEX IF EXISTS ix_referrals_referred")
    op.execute("DROP INDEX IF EXISTS ix_referrals_referrer")
    op.execute("DROP INDEX IF EXISTS idx_promo_usage_user_id")
    op.execute("DROP INDEX IF EXISTS idx_promo_usage_promo_id")
    op.execute("DROP INDEX IF EXISTS idx_promo_usage_order_id")
    op.execute("DROP INDEX IF EXISTS idx_ratings_order_id")
    op.execute("DROP INDEX IF EXISTS idx_store_admins_added_by")
    op.execute("DROP INDEX IF EXISTS idx_orders_offer_id")