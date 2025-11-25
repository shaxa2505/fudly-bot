"""Booking service layer: encapsulates booking business logic.

Minimal initial version used for progressive refactor out of the large
`handlers/bookings.py` module. Handlers will call these functions instead of
embedding business rules directly as refactor proceeds.
"""
from __future__ import annotations

from typing import Any, Optional, Tuple
from logging_config import logger

from database_protocol import DatabaseProtocol
from handlers.bookings.utils import (
    get_offer_field,
    get_store_field,
    get_booking_field,
)


class BookingService:
    """Service providing booking-related operations using a DB protocol."""

    def __init__(self, db: DatabaseProtocol):
        self.db = db

    # -------------------- Retrieval helpers --------------------
    def fetch_offer_and_store(self, offer_id: int) -> Tuple[Any, Any]:
        offer = self.db.get_offer(offer_id)
        store_id = get_offer_field(offer, 'store_id') if offer else None
        store = self.db.get_store(store_id) if store_id else None
        return offer, store

    def get_booking(self, booking_id: int) -> Any:
        return self.db.get_booking(booking_id)

    # -------------------- Creation --------------------
    def create_atomic_booking(self, offer_id: int, user_id: int, quantity: int) -> tuple[bool, Optional[int], Optional[str]]:
        """Atomically create a booking and decrement quantity.

        Returns (ok, booking_id, booking_code).
        """
        try:
            return self.db.create_booking_atomic(offer_id, user_id, quantity)
        except Exception as e:
            logger.error(f"create_atomic_booking failed: {e}")
            return False, None, None

    # -------------------- Status transitions --------------------
    def confirm(self, booking_id: int) -> bool:
        try:
            self.db.update_booking_status(booking_id, 'confirmed')
            return True
        except Exception as e:
            logger.error(f"Failed to confirm booking {booking_id}: {e}")
            return False

    def reject(self, booking_id: int) -> bool:
        try:
            # cancel_booking already restores quantities
            return self.db.cancel_booking(booking_id)
        except Exception as e:
            logger.error(f"Failed to reject booking {booking_id}: {e}")
            return False

    def complete(self, booking_id: int) -> bool:
        try:
            return self.db.complete_booking(booking_id)
        except Exception as e:
            logger.error(f"Failed to complete booking {booking_id}: {e}")
            return False

    def cancel(self, booking_id: int) -> bool:
        try:
            return self.db.cancel_booking(booking_id)
        except Exception as e:
            logger.error(f"Failed to cancel booking {booking_id}: {e}")
            return False

    def cancel_with_restore(self, booking: Any) -> bool:
        """Cancel booking and restore offer quantity atomically at app level.

        DB adapter may already restore quantity; this ensures restoration when
        not handled internally. Safe best-effort increment.
        """
        booking_id = get_booking_field(booking, 'booking_id')
        offer_id = get_booking_field(booking, 'offer_id')
        quantity = int(get_booking_field(booking, 'quantity', 1) or 1)
        if not booking_id:
            return False
        ok = self.cancel(booking_id)
        if ok and offer_id:
            try:
                self.adjust_offer_quantity(offer_id, quantity)
            except Exception:
                pass
        return ok

    def rate(self, booking_id: int, rating: int) -> bool:
        try:
            return self.db.save_booking_rating(booking_id, rating)
        except Exception as e:
            logger.error(f"Failed to rate booking {booking_id}: {e}")
            return False

    # -------------------- Inventory adjustments --------------------
    def adjust_offer_quantity(self, offer_id: int, delta: int) -> None:
        try:
            self.db.increment_offer_quantity_atomic(offer_id, delta)
        except Exception as e:
            logger.error(f"Failed to adjust offer {offer_id} by {delta}: {e}")

    # -------------------- Permission helpers --------------------
    def is_store_owner(self, booking: Any, user_id: int) -> bool:
        store_id = get_booking_field(booking, 'store_id')
        if not store_id:
            return False
        try:
            store = self.db.get_store(store_id)
            owner_id = get_store_field(store, 'owner_id') if store else None
            return owner_id == user_id
        except Exception:
            return False

    def is_booking_user(self, booking: Any, user_id: int) -> bool:
        return get_booking_field(booking, 'user_id') == user_id

    def can_modify_booking(self, booking: Any, user_id: int) -> bool:
        return self.is_booking_user(booking, user_id) or self.is_store_owner(booking, user_id)

    # -------------------- Active booking limit --------------------
    def active_booking_count(self, user_id: int) -> int:
        try:
            bookings = self.db.get_user_bookings(user_id) or []
        except Exception:
            return 0
        count = 0
        for b in bookings:
            status_val = get_booking_field(b, 'status')
            if status_val in ('active', 'pending', 'confirmed'):
                count += 1
        return count

    def below_active_limit(self, user_id: int, max_allowed: int) -> bool:
        return self.active_booking_count(user_id) < max_allowed

    # -------------------- High-level creation wrapper --------------------
    def create_booking_with_limit(self, offer_id: int, user_id: int, quantity: int, max_allowed: int) -> tuple[bool, Optional[int], Optional[str], str]:
        """Check user active limit then atomically create booking.

        Returns: (ok, booking_id, code, reason)
        reason: '' if ok else error message key.
        """
        if not self.below_active_limit(user_id, max_allowed):
            return False, None, None, 'limit_exceeded'
        ok, booking_id, code = self.create_atomic_booking(offer_id, user_id, quantity)
        return ok, booking_id, code, '' if ok else 'atomic_failed'

    # -------------------- Delivery update --------------------
    def update_delivery_details(self, booking_id: int, delivery_option: int, address: str, cost: int, payment_proof: Optional[str] = None) -> None:
        """Persist delivery info & optional payment proof for a booking."""
        try:
            if payment_proof:
                try:
                    self.db.set_booking_payment_proof(booking_id, payment_proof)  # type: ignore[attr-defined]
                except Exception:
                    pass
            # Fallback raw SQL when connection method exposed
            try:
                with self.db.get_connection() as conn:  # type: ignore[attr-defined]
                    cursor = conn.cursor()
                    cursor.execute(
                        """
                        UPDATE bookings
                        SET delivery_option = %s, delivery_address = %s, delivery_cost = %s
                        WHERE booking_id = %s
                        """,
                        (delivery_option, address, cost, booking_id),
                    )
            except Exception:
                # ignore if adapter does not support direct connection usage
                pass
        except Exception as e:
            logger.error(f"update_delivery_details failed for booking {booking_id}: {e}")

    # -------------------- Convenience create + delivery --------------------
    def finalize_booking(
        self,
        offer_id: int,
        user_id: int,
        quantity: int,
        max_allowed: int,
        delivery_option: int,
        delivery_address: str,
        delivery_cost: int,
        payment_proof: Optional[str] = None,
    ) -> tuple[bool, Optional[int], Optional[str], str]:
        """Create booking with limit + attach delivery details.

        Returns (ok, booking_id, code, reason) where reason is error key or ''.
        """
        ok, booking_id, code, reason = self.create_booking_with_limit(offer_id, user_id, quantity, max_allowed)
        if not ok or not booking_id:
            return ok, booking_id, code, reason
        if delivery_option == 1:
            self.update_delivery_details(booking_id, delivery_option, delivery_address, delivery_cost, payment_proof)
        return ok, booking_id, code, ''
