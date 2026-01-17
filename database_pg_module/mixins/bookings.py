"""
Booking-related database operations.
"""
from __future__ import annotations

import os
import random
import string
from typing import Any

from psycopg.rows import dict_row

try:
    from logging_config import logger
except ImportError:
    import logging

    logger = logging.getLogger(__name__)

# Configuration
BOOKING_DURATION_HOURS = int(os.environ.get("BOOKING_DURATION_HOURS", "2"))
MAX_ACTIVE_BOOKINGS_PER_USER = int(os.environ.get("MAX_ACTIVE_BOOKINGS_PER_USER", "20"))


class BookingMixin:
    """Mixin for booking-related database operations."""

    def create_booking_atomic(
        self,
        offer_id: int,
        user_id: int,
        quantity: int = 1,
        pickup_time: str | None = None,
        pickup_address: str | None = None,
    ):
        """Atomically reserve product and create booking in one transaction.

        Returns: Tuple[bool, Optional[int], Optional[str], Optional[str]]
            - ok: True if booking created successfully
            - booking_id: ID of created booking or None on error
            - booking_code: Booking code or None on error
            - error_reason: Reason for failure or None on success
        """
        logger.info(
            f"🔵 create_booking_atomic START: offer_id={offer_id}, user_id={user_id}, quantity={quantity}"
        )

        conn = None
        try:
            conn = self.pool.getconn()
            # Reset any failed transaction state before starting
            try:
                conn.rollback()
            except Exception:
                pass
            conn.autocommit = False
            cursor = conn.cursor()

            # Ensure user exists
            try:
                cursor.execute(
                    "INSERT INTO users (user_id) VALUES (%s) ON CONFLICT (user_id) DO NOTHING",
                    (user_id,),
                )
            except Exception:
                pass

            # Enforce per-user active booking limit
            try:
                # Log all bookings for this user for debugging
                cursor.execute(
                    "SELECT booking_id, status FROM bookings WHERE user_id = %s", (user_id,)
                )
                all_bookings = cursor.fetchall()
                logger.info(f"🔍 User {user_id} all bookings: {all_bookings}")

                # Count active bookings (no FOR UPDATE with aggregate)
                cursor.execute(
                    "SELECT COUNT(*) FROM bookings WHERE user_id = %s AND status IN ('active','pending','confirmed')",
                    (user_id,),
                )
                active_count = cursor.fetchone()[0] or 0
                logger.info(f"🔍 User {user_id} active count: {active_count}")
            except Exception as e:
                logger.error(f"Error checking booking limit: {e}")
                active_count = 0

            if active_count >= MAX_ACTIVE_BOOKINGS_PER_USER:
                conn.rollback()
                logger.warning(
                    f"🔵 User {user_id} has {active_count} active bookings (limit {MAX_ACTIVE_BOOKINGS_PER_USER})"
                )
                return (False, None, None, f"booking_limit:{active_count}")

            # Check and reserve product atomically
            cursor.execute(
                """
                SELECT quantity, stock_quantity, status, store_id
                FROM offers
                WHERE offer_id = %s AND status = 'active'
                FOR UPDATE
            """,
                (offer_id,),
            )
            offer = cursor.fetchone()

            if not offer:
                conn.rollback()
                logger.warning(f"🔵 Offer {offer_id} not found or not active")
                return (False, None, None, "offer_not_found")

            current_qty = offer[0]
            stock_qty = offer[1]
            available_qty = stock_qty if stock_qty is not None else current_qty

            if available_qty is None or available_qty < quantity:
                conn.rollback()
                logger.warning(
                    f"🔵 Offer {offer_id} insufficient quantity: {available_qty} < {quantity}"
                )
                return (False, None, None, f"insufficient_qty:{available_qty}")

            if offer[2] != "active":
                conn.rollback()
                logger.warning(f"🔵 Offer {offer_id} status is '{offer[2]}', not active")
                return (False, None, None, f"offer_inactive:{offer[2]}")

            store_id = offer[3]  # store_id from offers table
            new_quantity = available_qty - quantity

            logger.info(f"🔍 Offer {offer_id}: qty={available_qty}, store_id={store_id}")

            # Update quantity atomically
            cursor.execute(
                """
                UPDATE offers
                SET quantity = %s,
                    stock_quantity = %s,
                    status = CASE
                        WHEN %s <= 0 AND status IN ('active','out_of_stock') THEN 'out_of_stock'
                        WHEN %s > 0 AND status = 'out_of_stock' THEN 'active'
                        ELSE status
                    END
                WHERE offer_id = %s
            """,
                (new_quantity, new_quantity, new_quantity, new_quantity, offer_id),
            )
            if cursor.rowcount == 0:
                conn.rollback()
                logger.warning(f"🔵 Offer {offer_id} concurrent update detected")
                return (False, None, None, "concurrent_update")

            # Generate unique booking code
            booking_code = "".join(random.choices(string.ascii_uppercase + string.digits, k=6))

            # Handle pickup slot if provided
            if pickup_time and store_id is not None:
                if not self._reserve_pickup_slot(cursor, store_id, pickup_time, quantity):
                    conn.rollback()
                    logger.warning(f"🔵 Failed to reserve pickup slot for store {store_id}")
                    return (False, None, None, "pickup_slot_full")

            # Create booking with expiry
            cursor.execute(
                """
                INSERT INTO bookings (offer_id, user_id, store_id, booking_code, status, quantity, pickup_time, pickup_address, expiry_time)
                VALUES (%s, %s, %s, %s, 'pending', %s, %s, %s, now() + (%s * INTERVAL '1 hour'))
                RETURNING booking_id
            """,
                (
                    offer_id,
                    user_id,
                    store_id,
                    booking_code,
                    quantity,
                    pickup_time,
                    pickup_address,
                    BOOKING_DURATION_HOURS,
                ),
            )
            booking_id = cursor.fetchone()[0]

            conn.commit()
            logger.info(
                f"✅ create_booking_atomic SUCCESS: booking_id={booking_id}, code={booking_code}"
            )
            return (True, booking_id, booking_code, None)

        except Exception as e:
            if conn:
                try:
                    conn.rollback()
                except Exception:
                    pass
            logger.error(f"❌ Error creating booking atomically: {type(e).__name__}: {e}")
            import traceback

            traceback.print_exc()
            return (False, None, None, f"exception:{type(e).__name__}:{str(e)[:100]}")
        finally:
            if conn:
                conn.autocommit = True
                self.pool.putconn(conn)

    def _reserve_pickup_slot(self, cursor, store_id: int, pickup_time: str, quantity: int) -> bool:
        """Reserve pickup slot capacity."""
        try:
            DEFAULT_SLOT_CAPACITY = int(os.environ.get("PICKUP_SLOT_CAPACITY", "5"))
        except Exception:
            DEFAULT_SLOT_CAPACITY = 5

        try:
            cursor.execute(
                """
                INSERT INTO pickup_slots (store_id, slot_ts, capacity, reserved, created_at)
                VALUES (%s, %s, %s, 0, now())
                ON CONFLICT (store_id, slot_ts) DO NOTHING
            """,
                (store_id, pickup_time, DEFAULT_SLOT_CAPACITY),
            )
        except Exception:
            logger.debug("pickup_slots table missing; skipping slot reservation")
            return True  # Allow booking without slot reservation

        cursor.execute(
            "SELECT reserved, capacity FROM pickup_slots WHERE store_id = %s AND slot_ts = %s FOR UPDATE",
            (store_id, pickup_time),
        )
        slot = cursor.fetchone()
        if not slot:
            return False

        cur_reserved, cur_capacity = slot[0] or 0, slot[1] or 0
        if cur_reserved + quantity > cur_capacity:
            logger.warning("Pickup slot capacity exceeded")
            return False

        cursor.execute(
            "UPDATE pickup_slots SET reserved = reserved + %s WHERE store_id = %s AND slot_ts = %s AND reserved = %s",
            (quantity, store_id, pickup_time, cur_reserved),
        )
        return cursor.rowcount > 0

    def get_booking(self, booking_id: int):
        """Get booking by ID."""
        with self.get_connection() as conn:
            cursor = conn.cursor(row_factory=dict_row)
            cursor.execute(
                """
                SELECT booking_id, offer_id, user_id, status, booking_code,
                       pickup_time, COALESCE(quantity, 1) as quantity, created_at,
                       store_id, cart_items, is_cart_booking, customer_message_id
                FROM bookings
                WHERE booking_id = %s
            """,
                (booking_id,),
            )
            result = cursor.fetchone()
            return dict(result) if result else None

    def get_booking_model(self, booking_id: int) -> Any | None:
        """Get booking as Pydantic model."""
        try:
            from app.domain import Booking
        except ImportError:
            logger.error("Domain models not available. Install pydantic.")
            return None

        booking_tuple = self.get_booking(booking_id)
        if not booking_tuple:
            return None

        try:
            return Booking.from_db_row(booking_tuple)
        except Exception as e:
            logger.error(f"Failed to convert booking {booking_id} to model: {e}")
            return None

    def get_booking_by_code(self, booking_code: str):
        """Get booking by code."""
        with self.get_connection() as conn:
            cursor = conn.cursor(row_factory=dict_row)
            cursor.execute(
                """
                SELECT b.booking_id, b.offer_id, b.user_id, b.status, b.booking_code,
                       b.pickup_time, COALESCE(b.quantity, 1) as quantity, b.created_at,
                       u.first_name, u.username
                FROM bookings b
                JOIN users u ON b.user_id = u.user_id
                WHERE b.booking_code = %s AND b.status = 'pending'
            """,
                (booking_code,),
            )
            result = cursor.fetchone()
            return dict(result) if result else None

    def get_store_bookings(self, store_id: int):
        """Get all bookings for store."""
        with self.get_connection() as conn:
            cursor = conn.cursor(row_factory=dict_row)
            cursor.execute(
                """
                SELECT b.*, o.title, u.first_name, u.username, u.phone
                FROM bookings b
                JOIN offers o ON b.offer_id = o.offer_id
                JOIN users u ON b.user_id = u.user_id
                WHERE o.store_id = %s
                ORDER BY b.created_at DESC
            """,
                (store_id,),
            )
            return [dict(row) for row in cursor.fetchall()]

    def get_booking_history(self, user_id: int, limit: int = 50):
        """Get user's booking history."""
        with self.get_connection() as conn:
            cursor = conn.cursor(row_factory=dict_row)
            cursor.execute(
                """
                SELECT b.*, o.title, o.discount_price, s.name as store_name, s.address
                FROM bookings b
                JOIN offers o ON b.offer_id = o.offer_id
                JOIN stores s ON o.store_id = s.store_id
                WHERE b.user_id = %s
                ORDER BY b.created_at DESC
                LIMIT %s
            """,
                (user_id, limit),
            )
            return [dict(row) for row in cursor.fetchall()]

    def get_user_bookings(self, user_id: int):
        """Get all user bookings (not just active)."""
        with self.get_connection() as conn:
            cursor = conn.cursor(row_factory=dict_row)
            cursor.execute(
                """
                SELECT b.booking_id, b.offer_id, b.user_id, b.status, b.booking_code,
                       b.pickup_time, COALESCE(b.quantity, 1) as quantity, b.created_at,
                       COALESCE(o.title, 'Удалённый товар') as title,
                       COALESCE(o.discount_price, 0) as discount_price,
                       o.available_until,
                       COALESCE(s.name, 'Магазин') as name,
                       COALESCE(s.address, '') as address,
                       s.city
                FROM bookings b
                LEFT JOIN offers o ON b.offer_id = o.offer_id
                LEFT JOIN stores s ON o.store_id = s.store_id
                WHERE b.user_id = %s
                ORDER BY b.created_at DESC
            """,
                (user_id,),
            )
            return [dict(row) for row in cursor.fetchall()]

    def get_user_bookings_by_status(self, user_id: int, status: str):
        """Get user bookings filtered by status.

        Args:
            user_id: User ID
            status: 'active', 'completed', or 'cancelled'

        Returns:
            List of booking dicts
        """
        with self.get_connection() as conn:
            cursor = conn.cursor(row_factory=dict_row)

            # Map status to database values
            if status == "active":
                # Treat both legacy "confirmed" and unified "preparing" as active
                status_values = ("pending", "confirmed", "preparing")
            elif status == "completed":
                status_values = ("completed",)
            elif status == "cancelled":
                # Include both cancelled by user and rejected by seller
                status_values = ("cancelled", "rejected")
            else:
                status_values = ("pending", "confirmed", "preparing")

            cursor.execute(
                """
                SELECT b.booking_id, b.offer_id, b.user_id, b.status, b.booking_code,
                       b.pickup_time, COALESCE(b.quantity, 1) as quantity, b.created_at,
                       COALESCE(o.title, 'Удалённый товар') as title,
                       COALESCE(o.discount_price, 0) as discount_price,
                       o.available_until,
                       COALESCE(s.name, 'Магазин') as name,
                       COALESCE(s.address, '') as address,
                       s.city
                FROM bookings b
                LEFT JOIN offers o ON b.offer_id = o.offer_id
                LEFT JOIN stores s ON o.store_id = s.store_id
                WHERE b.user_id = %s AND b.status = ANY(%s)
                ORDER BY b.created_at DESC
            """,
                (user_id, list(status_values)),
            )
            return [dict(row) for row in cursor.fetchall()]

    def update_booking_status(self, booking_id: int, status: str):
        """Update booking status."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE bookings SET status = %s, updated_at = CURRENT_TIMESTAMP WHERE booking_id = %s",
                (status, booking_id),
            )

    def set_booking_customer_message_id(self, booking_id: int, message_id: int) -> bool:
        """Save customer notification message_id for live updates."""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "UPDATE bookings SET customer_message_id = %s WHERE booking_id = %s",
                    (message_id, booking_id),
                )
                logger.info(f"✅ Saved customer_message_id={message_id} for booking #{booking_id}")
                return True
        except Exception as e:
            logger.error(f"❌ Failed to save customer_message_id: {e}")
            return False

    def set_booking_seller_message_id(self, booking_id: int, message_id: int) -> bool:
        """Save seller notification message_id for live updates."""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "UPDATE bookings SET seller_message_id = %s WHERE booking_id = %s",
                    (message_id, booking_id),
                )
                logger.info(f"✅ Saved seller_message_id={message_id} for booking #{booking_id}")
                return True
        except Exception as e:
            logger.error(f"❌ Failed to save seller_message_id: {e}")
            return False

    def complete_booking(self, booking_id: int):
        """Complete booking."""
        self.update_booking_status(booking_id, "completed")

    def cancel_booking(self, booking_id: int):
        """Cancel booking and return reserved quantity to offer atomically."""
        conn = None
        try:
            conn = self.pool.getconn()
            conn.autocommit = False
            cursor = conn.cursor()

            # Lock booking row
            cursor.execute(
                "SELECT status, offer_id, quantity, is_cart_booking, cart_items FROM bookings WHERE booking_id = %s FOR UPDATE",
                (booking_id,),
            )
            row = cursor.fetchone()
            if not row:
                conn.rollback()
                return False

            status, offer_id, qty = row[0], row[1], row[2]
            is_cart_booking = int(row[3] or 0)
            cart_items = row[4]
            if status in ("cancelled", "completed", "rejected"):
                conn.rollback()
                return False

            qty_to_return = int(qty or 0)

            # Return quantity to offer(s)
            if is_cart_booking and cart_items:
                import json

                try:
                    items = json.loads(cart_items) if isinstance(cart_items, str) else cart_items
                except Exception:
                    items = []

                for item in items or []:
                    item_offer_id = item.get("offer_id")
                    item_qty = int(item.get("quantity", 1))
                    if not item_offer_id:
                        continue
                    cursor.execute(
                        """
                        UPDATE offers
                        SET quantity = COALESCE(quantity, 0) + %s,
                            stock_quantity = COALESCE(stock_quantity, quantity, 0) + %s,
                            status = CASE
                                WHEN COALESCE(stock_quantity, quantity, 0) + %s > 0
                                     AND status = 'out_of_stock' THEN 'active'
                                ELSE status
                            END
                        WHERE offer_id = %s
                        """,
                        (item_qty, item_qty, item_qty, item_offer_id),
                    )
            elif offer_id:
                cursor.execute(
                    """
                    UPDATE offers
                    SET quantity = COALESCE(quantity, 0) + %s,
                        stock_quantity = COALESCE(stock_quantity, quantity, 0) + %s,
                        status = CASE
                            WHEN COALESCE(stock_quantity, quantity, 0) + %s > 0
                                 AND status = 'out_of_stock' THEN 'active'
                            ELSE status
                        END
                    WHERE offer_id = %s
                    """,
                    (qty_to_return, qty_to_return, qty_to_return, offer_id),
                )

            # Mark as cancelled
            cursor.execute(
                "UPDATE bookings SET status = %s, updated_at = CURRENT_TIMESTAMP WHERE booking_id = %s",
                ("cancelled", booking_id),
            )

            conn.commit()
            return True
        except Exception:
            if conn:
                try:
                    conn.rollback()
                except Exception:
                    pass
            raise
        finally:
            if conn:
                try:
                    conn.autocommit = True
                    self.pool.putconn(conn)
                except Exception:
                    pass

    def set_booking_payment_proof(self, booking_id: int, file_id: str) -> bool:
        """Store payment proof file_id for a booking."""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "UPDATE bookings SET payment_proof_photo_id = %s WHERE booking_id = %s",
                    (file_id, booking_id),
                )
            return True
        except Exception as e:
            logger.error(f"Failed to set payment_proof for booking {booking_id}: {e}")
            return False

    def mark_reminder_sent(self, booking_id: int) -> bool:
        """Mark a booking's reminder_sent flag."""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "UPDATE bookings SET reminder_sent = 1 WHERE booking_id = %s", (booking_id,)
                )
            return True
        except Exception as e:
            logger.error(f"Failed to mark reminder_sent for booking {booking_id}: {e}")
            return False

    def add_booking(self, user_id: int, offer_id: int, store_id: int, quantity: int = 1):
        """Add new booking (simple version)."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO bookings (user_id, offer_id, store_id, quantity, expiry_time)
                VALUES (%s, %s, %s, %s, now() + (%s * INTERVAL '1 hour'))
                RETURNING booking_id
            """,
                (user_id, offer_id, store_id, quantity, BOOKING_DURATION_HOURS),
            )
            return cursor.fetchone()[0]

    def create_cart_booking_atomic(
        self,
        user_id: int,
        store_id: int,
        cart_items: list[dict[str, Any]],
        pickup_time: str | None = None,
    ):
        """Create one booking for multiple cart items atomically.

        cart_items format: [{"offer_id": 1, "quantity": 2, "price": 100, "title": "Item"}, ...]

        Returns: Tuple[bool, Optional[int], Optional[str], Optional[str]]
            - ok: True if booking created successfully
            - booking_id: ID of created booking or None on error
            - booking_code: Booking code or None on error
            - error_reason: Reason for failure or None on success
        """
        import json

        logger.info(
            f"🛒 create_cart_booking_atomic: user_id={user_id}, store={store_id}, items={len(cart_items)}"
        )

        if not cart_items:
            return (False, None, None, "empty_cart")

        conn = None
        try:
            conn = self.pool.getconn()
            try:
                conn.rollback()
            except Exception:
                pass
            conn.autocommit = False
            cursor = conn.cursor()

            # Ensure user exists
            try:
                cursor.execute(
                    "INSERT INTO users (user_id) VALUES (%s) ON CONFLICT (user_id) DO NOTHING",
                    (user_id,),
                )
            except Exception:
                pass

            # Check active bookings limit
            try:
                cursor.execute(
                    "SELECT COUNT(*) FROM bookings WHERE user_id = %s AND status IN ('active','pending','confirmed')",
                    (user_id,),
                )
                active_count = cursor.fetchone()[0] or 0
            except Exception:
                active_count = 0

            if active_count >= MAX_ACTIVE_BOOKINGS_PER_USER:
                conn.rollback()
                logger.warning(f"🛒 User {user_id} reached booking limit: {active_count}")
                return (False, None, None, f"booking_limit:{active_count}")

            # Check and reserve all items
            total_price = 0
            for item in cart_items:
                offer_id = item["offer_id"]
                quantity = item["quantity"]

                cursor.execute(
                    "SELECT quantity, stock_quantity, status, store_id FROM offers WHERE offer_id = %s AND status = 'active' FOR UPDATE",
                    (offer_id,),
                )
                row = cursor.fetchone()
                if not row:
                    conn.rollback()
                    logger.warning(f"🛒 Offer {offer_id} not found or inactive")
                    return (False, None, None, f"offer_unavailable:{offer_id}")

                current_qty = row[0]
                stock_qty = row[1]
                available_qty = stock_qty if stock_qty is not None else (current_qty or 0)
                if available_qty < quantity:
                    conn.rollback()
                    logger.warning(
                        f"🛒 Offer {offer_id}: requested {quantity}, available {available_qty}"
                    )
                    return (False, None, None, f"insufficient_stock:{offer_id}")

                # Reserve quantity
                new_qty = available_qty - quantity
                cursor.execute(
                    """
                    UPDATE offers
                    SET quantity = %s,
                        stock_quantity = %s,
                        status = CASE
                            WHEN %s <= 0 AND status IN ('active','out_of_stock') THEN 'out_of_stock'
                            WHEN %s > 0 AND status = 'out_of_stock' THEN 'active'
                            ELSE status
                        END
                    WHERE offer_id = %s
                    """,
                    (new_qty, new_qty, new_qty, new_qty, offer_id),
                )
                logger.info(f"🛒 Reserved offer {offer_id}: {quantity} units (new qty: {new_qty})")

                total_price += item.get("price", 0) * quantity

            # Generate booking code
            booking_code = "".join(random.choices(string.ascii_uppercase + string.digits, k=6))

            # Create booking with cart_items
            cart_items_json = json.dumps(cart_items, ensure_ascii=False)

            cursor.execute(
                """
                INSERT INTO bookings (
                    user_id, store_id, booking_code, pickup_time, status,
                    cart_items, is_cart_booking, quantity, expiry_time
                )
                VALUES (%s, %s, %s, %s, 'pending', %s, 1, %s, now() + (%s * INTERVAL '1 hour'))
                RETURNING booking_id
                """,
                (
                    user_id,
                    store_id,
                    booking_code,
                    pickup_time,
                    cart_items_json,
                    len(cart_items),
                    BOOKING_DURATION_HOURS,
                ),
            )
            booking_id = cursor.fetchone()[0]

            conn.commit()
            logger.info(
                f"🛒✅ Cart booking created: id={booking_id}, code={booking_code}, items={len(cart_items)}"
            )
            return (True, booking_id, booking_code, None)

        except Exception as e:
            logger.error(f"🛒❌ Failed to create cart booking: {e}", exc_info=True)
            if conn:
                try:
                    conn.rollback()
                except Exception:
                    pass
            return (False, None, None, f"error:{str(e)}")

        finally:
            if conn:
                try:
                    conn.autocommit = True
                    self.pool.putconn(conn)
                except Exception:
                    pass
