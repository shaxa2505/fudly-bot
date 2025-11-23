"""Booking notification shim: re-export partner/notification handlers.

This module now re-exports handlers from `handlers.bookings_flow` to keep
backwards compatibility for imports that expect `handlers.bookings_notify`.
"""
from handlers.bookings_flow import (
    partner_confirm,
    partner_reject,
    cancel_booking_confirm,
    do_cancel_booking,
    booking_details,
)

__all__ = [
    "partner_confirm",
    "partner_reject",
    "cancel_booking_confirm",
    "do_cancel_booking",
    "booking_details",
]
