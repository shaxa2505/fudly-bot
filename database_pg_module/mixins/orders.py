"""
Order-related database operations.
"""
from __future__ import annotations

import random
import string
from typing import Any

from psycopg.rows import dict_row

try:
    from logging_config import logger
except ImportError:
    import logging

    logger = logging.getLogger(__name__)


class OrderMixin:
    """Mixin for order-related database operations."""

    def create_order(
        self,
        user_id: int,
        store_id: int,
        offer_id: int,
        quantity: int,
        order_type: str,
        delivery_address: str = None,
        delivery_price: int = 0,
        payment_method: str = None,
    ) -> int | None:
        """Create new order.

        Args:
            user_id: Customer user ID
            store_id: Store ID
            offer_id: Offer ID
            quantity: Order quantity
            order_type: 'pickup' or 'delivery'
            delivery_address: Delivery address (for delivery orders)
            delivery_price: Delivery cost
            payment_method: 'cash' or 'card'

        Returns:
            order_id if successful, None otherwise
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()

            offer = self.get_offer(offer_id)
            if not offer:
                logger.error(f"Offer {offer_id} not found for order creation")
                return None

            discount_price = offer.get("discount_price", 0) if isinstance(offer, dict) else offer[5]
            total_amount = int((discount_price * quantity) + delivery_price)

            # Generate pickup code for pickup orders
            pickup_code = None
            if order_type == "pickup":
                pickup_code = "".join(random.choices(string.ascii_uppercase + string.digits, k=6))

            try:
                # Try with pickup_code column
                cursor.execute(
                    """
                    INSERT INTO orders (user_id, store_id, offer_id, quantity, delivery_address,
                                      total_price, payment_method, payment_status, order_status, pickup_code)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING order_id
                    """,
                    (
                        user_id,
                        store_id,
                        offer_id,
                        quantity,
                        delivery_address,
                        total_amount,
                        payment_method or "cash",
                        "pending",
                        "pending",
                        pickup_code,
                    ),
                )
                result = cursor.fetchone()
                if result:
                    order_id = result[0]
                    logger.info(f"Order {order_id} created by user {user_id} (type={order_type})")
                    return order_id
                return None
            except Exception as e:
                # Fallback: try without pickup_code column (for older DB schemas)
                logger.warning(f"Trying order creation without pickup_code: {e}")
                try:
                    cursor.execute(
                        """
                        INSERT INTO orders (user_id, store_id, offer_id, quantity, delivery_address,
                                          total_price, payment_method, payment_status, order_status)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                        RETURNING order_id
                        """,
                        (
                            user_id,
                            store_id,
                            offer_id,
                            quantity,
                            delivery_address,
                            total_amount,
                            payment_method or "cash",
                            "pending",
                            "pending",
                        ),
                    )
                    result = cursor.fetchone()
                    if result:
                        order_id = result[0]
                        logger.info(f"Order {order_id} created (fallback) by user {user_id}")
                        return order_id
                    return None
                except Exception as e2:
                    logger.error(f"Failed to create order (fallback): {e2}")
                    return None

    def create_cart_order(
        self,
        user_id: int,
        items: list[dict[str, Any]],
        order_type: str,
        delivery_address: str = None,
        payment_method: str = "cash",
    ) -> dict[str, Any]:
        """Create orders for multiple cart items, grouped by store.

        Args:
            user_id: Customer user ID
            items: List of cart items with offer_id, store_id, quantity, price, delivery_price
            order_type: 'pickup' or 'delivery'
            delivery_address: Delivery address (for delivery orders)
            payment_method: 'cash' or 'card'

        Returns:
            Dictionary with created_orders list and total info
        """
        created_orders = []
        failed_items = []

        # Group items by store for single notification per store
        stores_orders: dict[int, list[dict]] = {}

        with self.get_connection() as conn:
            cursor = conn.cursor()

            for item in items:
                offer_id = item.get("offer_id")
                store_id = item.get("store_id")
                quantity = item.get("quantity", 1)
                price = item.get("price", 0)
                delivery_price = item.get("delivery_price", 0) if order_type == "delivery" else 0

                total_amount = int((price * quantity) + delivery_price)

                # Generate pickup code for pickup orders
                pickup_code = None
                if order_type == "pickup":
                    pickup_code = "".join(
                        random.choices(string.ascii_uppercase + string.digits, k=6)
                    )

                try:
                    # Try with pickup_code first, fallback to without if column doesn't exist
                    try:
                        cursor.execute(
                            """
                            INSERT INTO orders (user_id, store_id, offer_id, quantity, delivery_address,
                                              total_price, payment_method, payment_status, order_status, pickup_code)
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                            RETURNING order_id
                            """,
                            (
                                user_id,
                                store_id,
                                offer_id,
                                quantity,
                                delivery_address,
                                total_amount,
                                payment_method,
                                "pending",
                                "pending",
                                pickup_code,
                            ),
                        )
                    except Exception as e:
                        if "pickup_code" in str(e):
                            logger.warning(f"pickup_code column missing, trying without: {e}")
                            cursor.execute(
                                """
                                INSERT INTO orders (user_id, store_id, offer_id, quantity, delivery_address,
                                                  total_price, payment_method, payment_status, order_status)
                                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                                RETURNING order_id
                                """,
                                (
                                    user_id,
                                    store_id,
                                    offer_id,
                                    quantity,
                                    delivery_address,
                                    total_amount,
                                    payment_method,
                                    "pending",
                                    "pending",
                                ),
                            )
                        else:
                            raise
                    result = cursor.fetchone()
                    if result:
                        order_id = result[0]

                        # Update offer quantity
                        cursor.execute(
                            "UPDATE offers SET quantity = quantity - %s WHERE offer_id = %s",
                            (quantity, offer_id),
                        )

                        order_info = {
                            "order_id": order_id,
                            "offer_id": offer_id,
                            "store_id": store_id,
                            "quantity": quantity,
                            "price": price,
                            "total": total_amount,
                            "pickup_code": pickup_code,
                            "title": item.get("title", ""),
                            "store_name": item.get("store_name", ""),
                            "store_address": item.get("store_address", ""),
                            "delivery_price": delivery_price,
                        }
                        created_orders.append(order_info)

                        # Group by store
                        if store_id not in stores_orders:
                            stores_orders[store_id] = []
                        stores_orders[store_id].append(order_info)

                        logger.info(f"Cart order {order_id} created for user {user_id}")
                    else:
                        failed_items.append(item)
                except Exception as e:
                    logger.error(f"Failed to create cart order for offer {offer_id}: {e}")
                    failed_items.append(item)

        return {
            "created_orders": created_orders,
            "failed_items": failed_items,
            "stores_orders": stores_orders,
            "order_type": order_type,
            "delivery_address": delivery_address,
            "payment_method": payment_method,
        }

    def get_order(self, order_id: int):
        """Get order by ID."""
        with self.get_connection() as conn:
            cursor = conn.cursor(row_factory=dict_row)
            cursor.execute("SELECT * FROM orders WHERE order_id = %s", (order_id,))
            result = cursor.fetchone()
            return dict(result) if result else None

    def update_order_payment_proof(self, order_id: int, photo_id: str):
        """Update order with payment proof photo."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE orders SET payment_proof_photo_id = %s, payment_status = %s
                WHERE order_id = %s
            """,
                (photo_id, "proof_submitted", order_id),
            )

    def update_payment_status(self, order_id: int, status: str, photo_id: str = None):
        """Update payment status."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            if photo_id:
                cursor.execute(
                    """
                    UPDATE orders SET payment_status = %s, payment_proof_photo_id = %s
                    WHERE order_id = %s
                """,
                    (status, photo_id, order_id),
                )
            else:
                cursor.execute(
                    """
                    UPDATE orders SET payment_status = %s
                    WHERE order_id = %s
                """,
                    (status, order_id),
                )

    def update_order_status(self, order_id: int, order_status: str, payment_status: str = None):
        """Update order status."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            if payment_status:
                cursor.execute(
                    """
                    UPDATE orders SET order_status = %s, payment_status = %s
                    WHERE order_id = %s
                """,
                    (order_status, payment_status, order_id),
                )
            else:
                cursor.execute(
                    "UPDATE orders SET order_status = %s WHERE order_id = %s",
                    (order_status, order_id),
                )

    def get_user_orders(self, user_id: int):
        """Get all orders for a user."""
        with self.get_connection() as conn:
            cursor = conn.cursor(row_factory=dict_row)
            cursor.execute(
                "SELECT * FROM orders WHERE user_id = %s ORDER BY created_at DESC", (user_id,)
            )
            return [dict(row) for row in cursor.fetchall()]

    def get_store_orders(self, store_id: int, status: str = None):
        """Get all orders for a store."""
        with self.get_connection() as conn:
            cursor = conn.cursor(row_factory=dict_row)
            if status:
                cursor.execute(
                    "SELECT * FROM orders WHERE store_id = %s AND order_status = %s ORDER BY created_at DESC",
                    (store_id, status),
                )
            else:
                cursor.execute(
                    "SELECT * FROM orders WHERE store_id = %s ORDER BY created_at DESC", (store_id,)
                )
            return [dict(row) for row in cursor.fetchall()]

    def get_total_orders(self) -> int:
        """Get total orders count."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM orders")
            return cursor.fetchone()[0]
