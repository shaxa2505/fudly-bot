"""
Payment-related database operations.
"""
from __future__ import annotations

from psycopg.rows import dict_row

try:
    from logging_config import logger
except ImportError:
    import logging
    logger = logging.getLogger(__name__)


class PaymentMixin:
    """Mixin for payment-related database operations."""

    def set_payment_card(self, store_id: int, card_number: str, card_holder: str = None,
                         card_expiry: str = None, payment_instructions: str = None):
        """Set payment card for store."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO payment_settings (store_id, card_number, card_holder, 
                                              card_expiry, payment_instructions)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (store_id) DO UPDATE SET
                    card_number = EXCLUDED.card_number,
                    card_holder = EXCLUDED.card_holder,
                    card_expiry = EXCLUDED.card_expiry,
                    payment_instructions = EXCLUDED.payment_instructions
            ''', (store_id, card_number, card_holder, card_expiry, payment_instructions))

    def get_payment_card(self, store_id: int):
        """Get payment card for store."""
        with self.get_connection() as conn:
            cursor = conn.cursor(row_factory=dict_row)
            cursor.execute('SELECT * FROM payment_settings WHERE store_id = %s', (store_id,))
            result = cursor.fetchone()
            return dict(result) if result else None
