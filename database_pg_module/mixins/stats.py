"""
Statistics and admin-related database operations.
"""
from __future__ import annotations

try:
    from logging_config import logger
except ImportError:
    import logging

    logger = logging.getLogger(__name__)


class StatsMixin:
    """Mixin for statistics and admin operations."""

    def get_statistics(self):
        """Get platform statistics."""
        with self.get_connection() as conn:
            cursor = conn.cursor()

            stats = {}

            cursor.execute("SELECT COUNT(*) FROM users")
            stats["users"] = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(*) FROM users WHERE role = 'customer'")
            stats["customers"] = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(*) FROM users WHERE role = 'seller'")
            stats["sellers"] = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(*) FROM stores")
            stats["stores"] = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(*) FROM stores WHERE status = 'active'")
            stats["approved_stores"] = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(*) FROM stores WHERE status = 'pending'")
            stats["pending_stores"] = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(*) FROM offers")
            stats["offers"] = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(*) FROM offers WHERE status = 'active'")
            stats["active_offers"] = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(*) FROM bookings")
            stats["bookings"] = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(*) FROM bookings WHERE status = 'completed'")
            stats["completed_bookings"] = cursor.fetchone()[0]

            return stats

    def get_total_users(self) -> int:
        """Get total users count."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM users")
            return cursor.fetchone()[0]

    def get_total_stores(self) -> int:
        """Get total active stores count."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM stores WHERE status = 'approved'")
            return cursor.fetchone()[0]

    def get_total_offers(self) -> int:
        """Get total active offers count."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM offers WHERE status = 'active'")
            return cursor.fetchone()[0]

    def get_platform_payment_card(self):
        """Get platform payment card from platform_settings table."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            # Read from platform_settings table (key-value storage)
            cursor.execute("SELECT value FROM platform_settings WHERE key = 'payment_card'")
            card_result = cursor.fetchone()
            cursor.execute("SELECT value FROM platform_settings WHERE key = 'payment_card_holder'")
            holder_result = cursor.fetchone()

            if card_result:
                card_number = card_result[0]
                card_holder = holder_result[0] if holder_result else "FUDLY PLATFORM"
                return {"card_number": card_number, "card_holder": card_holder}
            return None

    def set_platform_payment_card(
        self, card_number: str, card_holder: str = "FUDLY PLATFORM"
    ) -> None:
        """Set platform payment card in platform_settings table."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO platform_settings (key, value) VALUES ('payment_card', %s)
                ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value
            """,
                (card_number,),
            )
            cursor.execute(
                """
                INSERT INTO platform_settings (key, value) VALUES ('payment_card_holder', %s)
                ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value
            """,
                (card_holder,),
            )
