"""
Rating-related database operations.
"""
from __future__ import annotations

from psycopg.rows import dict_row

try:
    from logging_config import logger
except ImportError:
    import logging

    logger = logging.getLogger(__name__)


class RatingMixin:
    """Mixin for rating-related database operations."""

    def add_rating(
        self, booking_id: int, user_id: int, store_id: int, rating: int, comment: str = None
    ):
        """Add a rating."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO ratings (booking_id, user_id, store_id, rating, comment)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (booking_id) DO UPDATE SET rating = %s, comment = %s
                RETURNING rating_id
            """,
                (booking_id, user_id, store_id, rating, comment, rating, comment),
            )
            row = cursor.fetchone()
            return row[0] if row else None

    def update_rating_review(self, booking_id: int, user_id: int, review_text: str) -> bool:
        """Update rating with review text."""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    UPDATE ratings SET comment = %s
                    WHERE booking_id = %s AND user_id = %s
                """,
                    (review_text, booking_id, user_id),
                )
                return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"Error updating rating review: {e}")
            return False

    def save_booking_rating(self, booking_id: int, rating: int) -> bool:
        """Save booking rating (used in bookings handlers)."""
        try:
            booking = self.get_booking(booking_id)
            if not booking:
                logger.error(f"Booking {booking_id} not found")
                return False

            user_id = booking.get("user_id") if isinstance(booking, dict) else booking[1]
            offer_id = booking.get("offer_id") if isinstance(booking, dict) else booking[2]

            offer = self.get_offer(offer_id)
            if not offer:
                logger.error(f"Offer {offer_id} not found")
                return False

            store_id = offer.get("store_id") if isinstance(offer, dict) else offer[1]

            self.add_rating(booking_id, user_id, store_id, rating)
            return True
        except Exception as e:
            logger.error(f"Error saving booking rating: {e}")
            return False

    def get_store_ratings(self, store_id: int) -> list[dict]:
        """Get all ratings for a store."""
        with self.get_connection() as conn:
            cursor = conn.cursor(row_factory=dict_row)
            cursor.execute(
                """
                SELECT r.*, u.first_name, u.username
                FROM ratings r
                JOIN users u ON r.user_id = u.user_id
                WHERE r.store_id = %s
                ORDER BY r.created_at DESC
            """,
                (store_id,),
            )
            return cursor.fetchall()

    def get_store_average_rating(self, store_id: int) -> float:
        """Get average rating for a store."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT AVG(rating) FROM ratings WHERE store_id = %s", (store_id,))
            result = cursor.fetchone()
            return round(result[0], 1) if result and result[0] else 0.0

    def get_store_rating_summary(self, store_id: int) -> tuple[float, int]:
        """Get store rating summary (average, count)."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT AVG(rating), COUNT(*) FROM ratings WHERE store_id = %s", (store_id,)
            )
            result = cursor.fetchone()
            avg_rating = round(result[0], 1) if result and result[0] else 0.0
            count = result[1] if result and result[1] else 0
            return (avg_rating, count)

    def has_rated_booking(self, booking_id: int) -> bool:
        """Check if booking has been rated."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM ratings WHERE booking_id = %s", (booking_id,))
            count = cursor.fetchone()[0]
            return count > 0

    def get_store_sales_stats(self, store_id: int) -> dict:
        """Get store sales statistics."""
        with self.get_connection() as conn:
            cursor = conn.cursor()

            stats = {}

            cursor.execute(
                """
                SELECT COUNT(*), SUM(o.discount_price)
                FROM bookings b
                JOIN offers o ON b.offer_id = o.offer_id
                WHERE o.store_id = %s AND b.status = 'completed'
            """,
                (store_id,),
            )
            result = cursor.fetchone()
            stats["total_sales"] = result[0] if result[0] else 0
            stats["total_revenue"] = result[1] if result[1] else 0

            cursor.execute(
                """
                SELECT COUNT(*)
                FROM bookings b
                JOIN offers o ON b.offer_id = o.offer_id
                WHERE o.store_id = %s AND b.status = 'pending'
            """,
                (store_id,),
            )
            stats["pending_bookings"] = cursor.fetchone()[0]

            return stats
