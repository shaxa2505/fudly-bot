"""offer_favorites

Revision ID: 010_offer_favorites
Revises: 009_search_perf_indexes
Create Date: 2026-02-02
"""
from typing import Sequence, Union

from alembic import op


revision: str = "010_offer_favorites"
down_revision: Union[str, None] = "009_search_perf_indexes"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS favorite_offers (
            favorite_id SERIAL PRIMARY KEY,
            user_id BIGINT NOT NULL,
            offer_id INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(user_id),
            FOREIGN KEY (offer_id) REFERENCES offers(offer_id),
            UNIQUE(user_id, offer_id)
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_favorite_offers_user ON favorite_offers(user_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_favorite_offers_offer ON favorite_offers(offer_id)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_favorite_offers_offer")
    op.execute("DROP INDEX IF EXISTS idx_favorite_offers_user")
    op.execute("DROP TABLE IF EXISTS favorite_offers")
