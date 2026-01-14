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
