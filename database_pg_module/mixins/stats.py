"""
Statistics and admin-related database operations.
"""
from __future__ import annotations

from psycopg.rows import dict_row

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
            
            cursor.execute('SELECT COUNT(*) FROM users')
            stats['users'] = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(*) FROM users WHERE role = 'customer'")
            stats['customers'] = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(*) FROM users WHERE role = 'seller'")
            stats['sellers'] = cursor.fetchone()[0]
            
            cursor.execute('SELECT COUNT(*) FROM stores')
            stats['stores'] = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(*) FROM stores WHERE status = 'active'")
            stats['approved_stores'] = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(*) FROM stores WHERE status = 'pending'")
            stats['pending_stores'] = cursor.fetchone()[0]
            
            cursor.execute('SELECT COUNT(*) FROM offers')
            stats['offers'] = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(*) FROM offers WHERE status = 'active'")
            stats['active_offers'] = cursor.fetchone()[0]
            
            cursor.execute('SELECT COUNT(*) FROM bookings')
            stats['bookings'] = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(*) FROM bookings WHERE status = 'completed'")
            stats['completed_bookings'] = cursor.fetchone()[0]
            
            return stats

    def get_total_users(self) -> int:
        """Get total users count."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT COUNT(*) FROM users')
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
        """Get platform payment card."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT value FROM platform_settings WHERE key = 'payment_card'")
            result = cursor.fetchone()
            return result[0] if result else None

    def set_platform_payment_card(self, card_number: str) -> None:
        """Set platform payment card."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO platform_settings (key, value) VALUES ('payment_card', %s)
                ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value
            ''', (card_number,))
