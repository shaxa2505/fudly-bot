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

    @staticmethod
    def _normalize_payment_method(payment_method: str | None) -> str:
        """Normalize payment_method to supported values.

        Legacy code sometimes passes incorrect values (e.g. "pending").
        """
        if not payment_method:
            return "cash"

        method = str(payment_method).strip().lower()
        if method == "pending":
            return "card"

        return method

    @classmethod
    def _initial_payment_status(cls, payment_method: str | None) -> str:
        """Initial payment_status derived from payment_method."""
        method = cls._normalize_payment_method(payment_method)

        if method == "cash":
            return "not_required"

        if method in ("click", "payme"):
            return "awaiting_payment"

        # card / card_transfer / unknown
        return "awaiting_proof"

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

        TODO: This method has no transaction protection and no stock checking!
        Should use create_cart_order() instead which has atomic stock reservation.
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

            payment_method_norm = self._normalize_payment_method(payment_method)
            payment_status = self._initial_payment_status(payment_method_norm)

            try:
                # Try with pickup_code and order_type columns
                cursor.execute(
                    """
                    INSERT INTO orders (user_id, store_id, offer_id, quantity, delivery_address,
                                      total_price, payment_method, payment_status, order_status, pickup_code, order_type)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING order_id
                    """,
                    (
                        user_id,
                        store_id,
                        offer_id,
                        quantity,
                        delivery_address,
                        total_amount,
                        payment_method_norm,
                        payment_status,
                        "pending",
                        pickup_code,
                        order_type,
                    ),
                )
                result = cursor.fetchone()
                if result:
                    order_id = result[0]
                    logger.info(f"Order {order_id} created by user {user_id} (type={order_type})")
                    return order_id
                return None
            except Exception as e:
                # Fallback: try without order_type column (for older DB schemas)
                logger.warning(f"Trying order creation without order_type: {e}")
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
                            payment_method_norm,
                            payment_status,
                            "pending",
                            pickup_code,
                        ),
                    )
                    result = cursor.fetchone()
                    if result:
                        order_id = result[0]
                        logger.info(
                            f"Order {order_id} created (fallback) by user {user_id} (type={order_type})"
                        )
                        return order_id
                    return None
                except Exception as e2:
                    # Fallback: try without pickup_code column (for oldest DB schemas)
                    logger.warning(f"Trying order creation without pickup_code: {e2}")
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
                                payment_method_norm,
                                payment_status,
                                "pending",
                            ),
                        )
                        result = cursor.fetchone()
                        if result:
                            order_id = result[0]
                            logger.info(
                                f"Order {order_id} created (oldest fallback) by user {user_id}"
                            )
                            return order_id
                        return None
                    except Exception as e3:
                        logger.error(f"Failed to create order (all methods): {e3}")
                        return None

    def create_cart_order(
        self,
        user_id: int,
        items: list[dict[str, Any]],
        order_type: str,
        delivery_address: str = None,
        payment_method: str = "cash",
        notify_customer: bool = True,
    ) -> dict[str, Any]:
        """Create orders for multiple cart items, grouped by store.

        Args:
            user_id: Customer user ID
            items: List of cart items with offer_id, store_id, quantity, price, delivery_price
            order_type: 'pickup' or 'delivery'
            delivery_address: Delivery address (for delivery orders)
            payment_method: 'cash' or 'card'
            notify_customer: Whether to send notification (deprecated, handled by UnifiedOrderService)

        Returns:
            Dictionary with created_orders list and total info
            
        Note:
            The notify_customer parameter is accepted for backward compatibility
            but ignored. Notifications are now handled by UnifiedOrderService.
        """
        created_orders = []
        failed_items = []

        # Group items by store for single notification per store
        stores_orders: dict[int, list[dict]] = {}

        payment_method_norm = self._normalize_payment_method(payment_method)
        payment_status = self._initial_payment_status(payment_method_norm)

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
                    # First, check and reserve stock for this offer atomically
                    cursor.execute(
                        "SELECT quantity, status FROM offers WHERE offer_id = %s FOR UPDATE",
                        (offer_id,),
                    )
                    offer_row = cursor.fetchone()
                    if not offer_row:
                        logger.warning("Offer %s not found for cart order", offer_id)
                        failed_items.append(item)
                        continue

                    current_qty = offer_row[0] or 0
                    offer_status = offer_row[1]

                    if current_qty < quantity or offer_status != "active":
                        logger.warning(
                            "Insufficient stock or inactive offer %s in cart order (qty=%s, status=%s)",
                            offer_id,
                            current_qty,
                            offer_status,
                        )
                        failed_items.append(item)
                        continue

                    # Try with pickup_code + order_type first, fallback to legacy schemas
                    try:
                        cursor.execute(
                            """
                            INSERT INTO orders (user_id, store_id, offer_id, quantity, delivery_address,
                                              total_price, payment_method, payment_status, order_status, pickup_code, order_type)
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                            RETURNING order_id
                            """,
                            (
                                user_id,
                                store_id,
                                offer_id,
                                quantity,
                                delivery_address,
                                total_amount,
                                payment_method_norm,
                                payment_status,
                                "pending",
                                pickup_code,
                                order_type,
                            ),
                        )
                    except Exception as e:
                        # Older schemas may not have pickup_code or order_type columns
                        if "pickup_code" in str(e) or "order_type" in str(e):
                            logger.warning(
                                f"pickup_code/order_type column missing, trying without: {e}"
                            )
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
                                    payment_method_norm,
                                    payment_status,
                                    "pending",
                                ),
                            )
                        else:
                            raise

                    result = cursor.fetchone()
                    if result:
                        order_id = result[0]

                        # Update offer quantity based on previously locked value
                        new_qty = current_qty - quantity
                        cursor.execute(
                            """
                            UPDATE offers
                            SET quantity = %s,
                                status = CASE WHEN %s <= 0 THEN 'inactive' ELSE status END
                            WHERE offer_id = %s
                            """,
                            (new_qty, new_qty, offer_id),
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

    def update_order_status(self, order_id: int, order_status: str) -> bool:
        """Update order status.

        NOTE: This method only updates order_status field.
        Use update_payment_status() to update payment_status separately.

        Returns:
            True if update was successful
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE orders SET order_status = %s, updated_at = CURRENT_TIMESTAMP WHERE order_id = %s",
                (order_status, order_id),
            )
            return True

    def set_order_customer_message_id(self, order_id: int, message_id: int) -> bool:
        """Save customer notification message_id for live updates."""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "UPDATE orders SET customer_message_id = %s WHERE order_id = %s",
                    (message_id, order_id),
                )
                return True
        except Exception:
            return False

    def set_order_seller_message_id(self, order_id: int, message_id: int) -> bool:
        """Save seller notification message_id for live updates."""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "UPDATE orders SET seller_message_id = %s WHERE order_id = %s",
                    (message_id, order_id),
                )
                logger.info(f"Saved seller_message_id={message_id} for order #{order_id}")
                return True
        except Exception as e:
            logger.warning(f"Failed to save seller_message_id: {e}")
            return False

    def get_user_orders(self, user_id: int):
        """Get all orders for a user."""
        with self.get_connection() as conn:
            cursor = conn.cursor(row_factory=dict_row)
            cursor.execute(
                "SELECT * FROM orders WHERE user_id = %s ORDER BY created_at DESC", (user_id,)
            )
            return [dict(row) for row in cursor.fetchall()]

    def get_order_by_pickup_code(self, pickup_code: str):
        """Get pickup order by pickup_code (used for QR/code verification)."""
        if not pickup_code:
            return None

        with self.get_connection() as conn:
            cursor = conn.cursor(row_factory=dict_row)
            cursor.execute(
                """
                SELECT *
                FROM orders
                WHERE pickup_code = %s
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (pickup_code,),
            )
            row = cursor.fetchone()
            return dict(row) if row else None

    def get_store_orders(self, store_id: int, status: str = None):
        """Get all orders for a store with customer and offer info."""
        with self.get_connection() as conn:
            cursor = conn.cursor(row_factory=dict_row)
            if status:
                cursor.execute(
                    """
                    SELECT o.*,
                           u.first_name, u.phone, u.username,
                           off.title as offer_title, off.discount_price, off.photo_id as offer_photo_id
                    FROM orders o
                    LEFT JOIN users u ON o.user_id = u.user_id
                    LEFT JOIN offers off ON o.offer_id = off.offer_id
                    WHERE o.store_id = %s AND o.order_status = %s
                    ORDER BY o.created_at DESC
                    """,
                    (store_id, status),
                )
            else:
                cursor.execute(
                    """
                    SELECT o.*,
                           u.first_name, u.phone, u.username,
                           off.title as offer_title, off.discount_price, off.photo_id as offer_photo_id
                    FROM orders o
                    LEFT JOIN users u ON o.user_id = u.user_id
                    LEFT JOIN offers off ON o.offer_id = off.offer_id
                    WHERE o.store_id = %s
                    ORDER BY o.created_at DESC
                    """,
                    (store_id,),
                )
            return [dict(row) for row in cursor.fetchall()]

    def get_total_orders(self) -> int:
        """Get total orders count."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM orders")
            return cursor.fetchone()[0]

    def create_cart_order_atomic(
        self,
        user_id: int,
        store_id: int,
        cart_items: list[dict[str, Any]],
        delivery_address: str | None = None,
        delivery_price: int = 0,
        payment_method: str = "cash",
    ):
        """Create one order for multiple cart items atomically.

        cart_items format: [{"offer_id": 1, "quantity": 2, "price": 100, "title": "Item"}, ...]

        Returns: Tuple[bool, Optional[int], Optional[str], Optional[str]]
            - ok: True if order created successfully
            - order_id: ID of created order or None on error
            - pickup_code: Pickup code or None on error
            - error_reason: Reason for failure or None on success
        """
        import json

        logger.info(
            f"🛒 create_cart_order_atomic: user_id={user_id}, store={store_id}, items={len(cart_items)}"
        )

        if not cart_items:
            return (False, None, None, "empty_cart")

        conn = None
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()

                # Ensure user exists
                try:
                    cursor.execute(
                        "INSERT INTO users (user_id) VALUES (%s) ON CONFLICT (user_id) DO NOTHING",
                        (user_id,),
                    )
                except Exception:
                    pass

                # Check and reserve all items
                total_price = 0
                for item in cart_items:
                    offer_id = item["offer_id"]
                    quantity = item["quantity"]

                    cursor.execute(
                        "SELECT quantity, status, discount_price FROM offers WHERE offer_id = %s AND status = 'active' FOR UPDATE",
                        (offer_id,),
                    )
                    row = cursor.fetchone()
                    if not row:
                        logger.warning(f"🛒 Offer {offer_id} not found or inactive")
                        raise ValueError(f"offer_unavailable:{offer_id}")

                    available_qty = row[0] or 0
                    if available_qty < quantity:
                        logger.warning(
                            f"🛒 Offer {offer_id}: requested {quantity}, available {available_qty}"
                        )
                        raise ValueError(f"insufficient_stock:{offer_id}")

                    # Reserve quantity
                    new_qty = available_qty - quantity
                    cursor.execute(
                        """
                        UPDATE offers
                        SET quantity = %s,
                            status = CASE WHEN %s <= 0 THEN 'inactive' ELSE status END
                        WHERE offer_id = %s
                        """,
                        (new_qty, new_qty, offer_id),
                    )
                    logger.info(
                        f"🛒 Reserved offer {offer_id}: {quantity} units (new qty: {new_qty})"
                    )

                    price = item.get("price", row[2] or 0)
                    total_price += price * quantity

                # Add delivery price
                total_price += delivery_price

                order_type = "delivery" if delivery_address else "pickup"
                pickup_code = None
                if order_type == "pickup":
                    pickup_code = "".join(
                        random.choices(string.ascii_uppercase + string.digits, k=6)
                    )

                # Create order with cart_items
                cart_items_json = json.dumps(cart_items, ensure_ascii=False)

                payment_method_norm = self._normalize_payment_method(payment_method)
                payment_status = self._initial_payment_status(payment_method_norm)

                try:
                    cursor.execute(
                        """
                        INSERT INTO orders (
                            user_id, store_id, delivery_address, total_price,
                            payment_method, payment_status, order_status, pickup_code,
                            order_type, cart_items, is_cart_order, quantity
                        )
                        VALUES (%s, %s, %s, %s, %s, %s, 'pending', %s, %s, %s, 1, %s)
                        RETURNING order_id
                        """,
                        (
                            user_id,
                            store_id,
                            delivery_address,
                            total_price,
                            payment_method_norm,
                            payment_status,
                            pickup_code,
                            order_type,
                            cart_items_json,
                            len(cart_items),
                        ),
                    )
                except Exception as e:
                    # Fallback: older schemas without order_type
                    if "order_type" not in str(e):
                        raise
                    cursor.execute(
                        """
                        INSERT INTO orders (
                            user_id, store_id, delivery_address, total_price,
                            payment_method, payment_status, order_status, pickup_code,
                            cart_items, is_cart_order, quantity
                        )
                        VALUES (%s, %s, %s, %s, %s, %s, 'pending', %s, %s, 1, %s)
                        RETURNING order_id
                        """,
                        (
                            user_id,
                            store_id,
                            delivery_address,
                            total_price,
                            payment_method_norm,
                            payment_status,
                            pickup_code,
                            cart_items_json,
                            len(cart_items),
                        ),
                    )
                order_id = cursor.fetchone()[0]

                logger.info(
                    f"🛒✅ Cart order created: id={order_id}, code={pickup_code}, items={len(cart_items)}, total={total_price}"
                )
                return (True, order_id, pickup_code, None)

        except Exception as e:
            logger.error(f"🛒❌ Failed to create cart order: {e}", exc_info=True)
            return (False, None, None, f"error:{str(e)}")

        finally:
            if conn:
                try:
                    conn.autocommit = True
                    self.pool.putconn(conn)
                except Exception:
                    pass
