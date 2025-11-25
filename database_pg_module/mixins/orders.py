"""
Order-related database operations.
"""
from __future__ import annotations

import random
import string
from typing import List, Optional

from psycopg.rows import dict_row

try:
    from logging_config import logger
except ImportError:
    import logging
    logger = logging.getLogger(__name__)


class OrderMixin:
    """Mixin for order-related database operations."""

    def create_order(self, user_id: int, store_id: int, offer_id: int, quantity: int,
                     order_type: str, delivery_address: str = None, delivery_price: int = 0,
                     payment_method: str = None):
        """Create new order."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            offer = self.get_offer(offer_id)
            if not offer:
                return None
            
            discount_price = offer['discount_price']
            total_amount = (discount_price * quantity) + delivery_price
            
            pickup_code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6)) if order_type == 'pickup' else None
            
            cursor.execute('''
                INSERT INTO orders (user_id, store_id, offer_id, quantity, delivery_address,
                                  total_price, payment_method, payment_status, order_status)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING order_id
            ''', (user_id, store_id, offer_id, quantity, delivery_address,
                  total_amount, payment_method or 'card', 'pending', 'pending'))
            order_id = cursor.fetchone()[0]
            logger.info(f"Order {order_id} created by user {user_id}")
            return order_id

    def get_order(self, order_id: int):
        """Get order by ID."""
        with self.get_connection() as conn:
            cursor = conn.cursor(row_factory=dict_row)
            cursor.execute('SELECT * FROM orders WHERE order_id = %s', (order_id,))
            result = cursor.fetchone()
            return dict(result) if result else None

    def update_order_payment_proof(self, order_id: int, photo_id: str):
        """Update order with payment proof photo."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE orders SET payment_proof_photo_id = %s, payment_status = %s 
                WHERE order_id = %s
            ''', (photo_id, 'proof_submitted', order_id))

    def update_payment_status(self, order_id: int, status: str, photo_id: str = None):
        """Update payment status."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            if photo_id:
                cursor.execute('''
                    UPDATE orders SET payment_status = %s, payment_proof_photo_id = %s
                    WHERE order_id = %s
                ''', (status, photo_id, order_id))
            else:
                cursor.execute('''
                    UPDATE orders SET payment_status = %s
                    WHERE order_id = %s
                ''', (status, order_id))

    def update_order_status(self, order_id: int, order_status: str, payment_status: str = None):
        """Update order status."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            if payment_status:
                cursor.execute('''
                    UPDATE orders SET order_status = %s, payment_status = %s 
                    WHERE order_id = %s
                ''', (order_status, payment_status, order_id))
            else:
                cursor.execute('UPDATE orders SET order_status = %s WHERE order_id = %s', 
                             (order_status, order_id))

    def get_user_orders(self, user_id: int):
        """Get all orders for a user."""
        with self.get_connection() as conn:
            cursor = conn.cursor(row_factory=dict_row)
            cursor.execute('SELECT * FROM orders WHERE user_id = %s ORDER BY created_at DESC', 
                         (user_id,))
            return [dict(row) for row in cursor.fetchall()]

    def get_store_orders(self, store_id: int, status: str = None):
        """Get all orders for a store."""
        with self.get_connection() as conn:
            cursor = conn.cursor(row_factory=dict_row)
            if status:
                cursor.execute('SELECT * FROM orders WHERE store_id = %s AND order_status = %s ORDER BY created_at DESC', 
                             (store_id, status))
            else:
                cursor.execute('SELECT * FROM orders WHERE store_id = %s ORDER BY created_at DESC', 
                             (store_id,))
            return [dict(row) for row in cursor.fetchall()]

    def get_total_orders(self) -> int:
        """Get total orders count."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT COUNT(*) FROM orders')
            return cursor.fetchone()[0]
