"""
Favorites-related database operations.
"""
from __future__ import annotations

from psycopg.rows import dict_row

try:
    from logging_config import logger
except ImportError:
    import logging

    logger = logging.getLogger(__name__)


class FavoritesMixin:
    """Mixin for favorites-related database operations."""

    def add_to_favorites(self, user_id: int, store_id: int):
        """Add store to user's favorites."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO favorites (user_id, store_id)
                VALUES (%s, %s)
                ON CONFLICT (user_id, store_id) DO NOTHING
            """,
                (user_id, store_id),
            )

    def add_favorite(self, user_id: int, store_id: int) -> None:
        """Backward-compatible alias for add_to_favorites."""
        self.add_to_favorites(user_id, store_id)

    def remove_from_favorites(self, user_id: int, store_id: int):
        """Remove store from user's favorites."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "DELETE FROM favorites WHERE user_id = %s AND store_id = %s", (user_id, store_id)
            )

    def remove_favorite(self, user_id: int, store_id: int) -> None:
        """Backward-compatible alias for remove_from_favorites."""
        self.remove_from_favorites(user_id, store_id)

    def get_favorites(self, user_id: int) -> list[dict]:
        """Get user's favorite stores."""
        with self.get_connection() as conn:
            cursor = conn.cursor(row_factory=dict_row)
            cursor.execute(
                """
                SELECT s.* FROM stores s
                JOIN favorites f ON s.store_id = f.store_id
                WHERE f.user_id = %s AND s.status = 'active'
                ORDER BY f.created_at DESC
            """,
                (user_id,),
            )
            return cursor.fetchall()

    def is_favorite(self, user_id: int, store_id: int) -> bool:
        """Check if store is in user's favorites."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT 1 FROM favorites WHERE user_id = %s AND store_id = %s", (user_id, store_id)
            )
            return cursor.fetchone() is not None

    def add_offer_favorite(self, user_id: int, offer_id: int) -> None:
        """Add offer to user's favorites."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO favorite_offers (user_id, offer_id)
                VALUES (%s, %s)
                ON CONFLICT (user_id, offer_id) DO NOTHING
            """,
                (user_id, offer_id),
            )

    def remove_offer_favorite(self, user_id: int, offer_id: int) -> None:
        """Remove offer from user's favorites."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "DELETE FROM favorite_offers WHERE user_id = %s AND offer_id = %s",
                (user_id, offer_id),
            )

    def get_favorite_offer_ids(self, user_id: int) -> list[int]:
        """Get user's favorite offer IDs."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT offer_id
                FROM favorite_offers
                WHERE user_id = %s
                ORDER BY created_at DESC
            """,
                (user_id,),
            )
            rows = cursor.fetchall()
            return [row[0] for row in rows] if rows else []

    def get_favorite_offers(self, user_id: int) -> list[dict]:
        """Get user's favorite offers with store info."""
        with self.get_connection() as conn:
            cursor = conn.cursor(row_factory=dict_row)
            cursor.execute(
                """
                SELECT
                    o.*,
                    s.name AS store_name,
                    s.address AS store_address,
                    s.rating AS store_rating,
                    s.delivery_enabled,
                    s.delivery_price,
                    s.min_order_amount
                FROM favorite_offers f
                JOIN offers o ON o.offer_id = f.offer_id
                LEFT JOIN stores s ON s.store_id = o.store_id
                WHERE f.user_id = %s
                ORDER BY f.created_at DESC
            """,
                (user_id,),
            )
            return cursor.fetchall()
