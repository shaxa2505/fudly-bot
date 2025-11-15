"""Booking repository for booking-related database operations."""
from __future__ import annotations

from typing import Any, Optional

from app.core.exceptions import BookingNotFoundException, DatabaseException

from .base import BaseRepository


class BookingRepository(BaseRepository):
    """Repository for booking-related database operations."""

    def get_booking(self, booking_id: int) -> Optional[dict[str, Any]]:
        """Get booking by ID.

        Args:
            booking_id: Booking ID

        Returns:
            Booking data as dict or None if not found

        Raises:
            DatabaseException: If database operation fails
        """
        try:
            return self.db.get_booking(booking_id)
        except Exception as e:
            self._handle_db_error("get_booking", e)

    def get_booking_or_raise(self, booking_id: int) -> dict[str, Any]:
        """Get booking by ID or raise exception.

        Args:
            booking_id: Booking ID

        Returns:
            Booking data as dict

        Raises:
            BookingNotFoundException: If booking not found
            DatabaseException: If database operation fails
        """
        booking = self.get_booking(booking_id)
        if not booking:
            raise BookingNotFoundException(booking_id)
        return booking

    def add_booking(
        self,
        offer_id: int,
        user_id: int,
        quantity: int = 1,
        delivery_address: Optional[str] = None,
    ) -> int:
        """Add new booking.

        Args:
            offer_id: Offer ID
            user_id: User ID
            quantity: Quantity to book
            delivery_address: Delivery address (if delivery requested)

        Returns:
            New booking ID

        Raises:
            DatabaseException: If database operation fails
        """
        try:
            return self.db.add_booking(offer_id, user_id, quantity, delivery_address)
        except Exception as e:
            self._handle_db_error("add_booking", e)
            return -1

    def set_booking_status(self, booking_id: int, status: str) -> None:
        """Set booking status.

        Args:
            booking_id: Booking ID
            status: New status (pending, confirmed, cancelled, completed)

        Raises:
            DatabaseException: If database operation fails
        """
        try:
            self.db.set_booking_status(booking_id, status)
        except Exception as e:
            self._handle_db_error("set_booking_status", e)

    def get_user_bookings(self, user_id: int) -> list[dict[str, Any]]:
        """Get all bookings for a user.

        Args:
            user_id: User ID

        Returns:
            List of booking dicts

        Raises:
            DatabaseException: If database operation fails
        """
        try:
            return self.db.get_user_bookings(user_id)
        except Exception as e:
            self._handle_db_error("get_user_bookings", e)
            return []

    def get_store_bookings(self, store_id: int) -> list[dict[str, Any]]:
        """Get all bookings for a store.

        Args:
            store_id: Store ID

        Returns:
            List of booking dicts

        Raises:
            DatabaseException: If database operation fails
        """
        try:
            return self.db.get_store_bookings(store_id)
        except Exception as e:
            self._handle_db_error("get_store_bookings", e)
            return []

    def get_offer_bookings(self, offer_id: int) -> list[dict[str, Any]]:
        """Get all bookings for an offer.

        Args:
            offer_id: Offer ID

        Returns:
            List of booking dicts

        Raises:
            DatabaseException: If database operation fails
        """
        try:
            return self.db.get_offer_bookings(offer_id)
        except Exception as e:
            self._handle_db_error("get_offer_bookings", e)
            return []

    def cancel_booking(self, booking_id: int) -> None:
        """Cancel booking.

        Args:
            booking_id: Booking ID

        Raises:
            DatabaseException: If database operation fails
        """
        try:
            self.set_booking_status(booking_id, "cancelled")
        except Exception as e:
            self._handle_db_error("cancel_booking", e)

    def confirm_booking(self, booking_id: int) -> None:
        """Confirm booking.

        Args:
            booking_id: Booking ID

        Raises:
            DatabaseException: If database operation fails
        """
        try:
            self.set_booking_status(booking_id, "confirmed")
        except Exception as e:
            self._handle_db_error("confirm_booking", e)

    def complete_booking(self, booking_id: int) -> None:
        """Complete booking.

        Args:
            booking_id: Booking ID

        Raises:
            DatabaseException: If database operation fails
        """
        try:
            self.set_booking_status(booking_id, "completed")
        except Exception as e:
            self._handle_db_error("complete_booking", e)
