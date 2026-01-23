"""
Payment-related database operations.
"""
from __future__ import annotations

import json

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

    def get_click_fiscalization(self, order_id: int, payment_id: str) -> dict | None:
        """Get Click fiscalization record."""
        with self.get_connection() as conn:
            cursor = conn.cursor(row_factory=dict_row)
            cursor.execute(
                "SELECT * FROM click_fiscalization WHERE order_id = %s AND payment_id = %s",
                (order_id, str(payment_id)),
            )
            result = cursor.fetchone()
            return dict(result) if result else None

    def upsert_click_fiscalization(
        self,
        order_id: int,
        payment_id: str,
        service_id: str | None = None,
        status: str | None = None,
        error_code: int | None = None,
        error_note: str | None = None,
        request_payload: dict | None = None,
        response_payload: dict | None = None,
        qr_code_url: str | None = None,
    ) -> None:
        """Insert or update Click fiscalization record."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO click_fiscalization (
                    order_id, payment_id, service_id, status, error_code, error_note,
                    request_payload, response_payload, qr_code_url
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (order_id, payment_id) DO UPDATE SET
                    service_id = EXCLUDED.service_id,
                    status = COALESCE(EXCLUDED.status, click_fiscalization.status),
                    error_code = COALESCE(EXCLUDED.error_code, click_fiscalization.error_code),
                    error_note = COALESCE(EXCLUDED.error_note, click_fiscalization.error_note),
                    request_payload = COALESCE(EXCLUDED.request_payload, click_fiscalization.request_payload),
                    response_payload = COALESCE(EXCLUDED.response_payload, click_fiscalization.response_payload),
                    qr_code_url = COALESCE(EXCLUDED.qr_code_url, click_fiscalization.qr_code_url),
                    updated_at = CURRENT_TIMESTAMP
                """,
                (
                    order_id,
                    str(payment_id),
                    service_id,
                    status,
                    error_code,
                    error_note,
                    json.dumps(request_payload) if request_payload is not None else None,
                    json.dumps(response_payload) if response_payload is not None else None,
                    qr_code_url,
                ),
            )

    def get_click_transaction(self, click_trans_id: int) -> dict | None:
        """Get Click transaction by click_trans_id."""
        with self.get_connection() as conn:
            cursor = conn.cursor(row_factory=dict_row)
            cursor.execute(
                "SELECT * FROM click_transactions WHERE click_trans_id = %s",
                (int(click_trans_id),),
            )
            result = cursor.fetchone()
            return dict(result) if result else None

    def upsert_click_transaction(
        self,
        click_trans_id: int,
        merchant_trans_id: str,
        merchant_prepare_id: str | None = None,
        service_id: str | None = None,
        amount: str | None = None,
        status: str | None = None,
        error_code: int | None = None,
        error_note: str | None = None,
    ) -> None:
        """Insert or update Click transaction."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO click_transactions (
                    click_trans_id, merchant_trans_id, merchant_prepare_id,
                    service_id, amount, status, error_code, error_note
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (click_trans_id) DO UPDATE SET
                    merchant_trans_id = EXCLUDED.merchant_trans_id,
                    merchant_prepare_id = COALESCE(EXCLUDED.merchant_prepare_id, click_transactions.merchant_prepare_id),
                    service_id = COALESCE(EXCLUDED.service_id, click_transactions.service_id),
                    amount = COALESCE(EXCLUDED.amount, click_transactions.amount),
                    status = COALESCE(EXCLUDED.status, click_transactions.status),
                    error_code = COALESCE(EXCLUDED.error_code, click_transactions.error_code),
                    error_note = COALESCE(EXCLUDED.error_note, click_transactions.error_note),
                    updated_at = CURRENT_TIMESTAMP
                """,
                (
                    int(click_trans_id),
                    str(merchant_trans_id),
                    merchant_prepare_id,
                    service_id,
                    amount,
                    status,
                    error_code,
                    error_note,
                ),
            )
