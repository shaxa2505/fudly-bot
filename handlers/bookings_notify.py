"""Booking notification shim: re-export partner/notification handlers.

This module groups the partner confirmation/rejection and booking lifecycle
callbacks so notification logic appears in a separate module.
"""
from handlers.bookings import (
    partner_confirm,
    partner_reject,
    complete_booking,
    customer_received,
    rate_booking,
    save_booking_rating,
    cancel_booking_confirm,
    do_cancel_booking,
)

__all__ = [
    "partner_confirm",
    "partner_reject",
    "complete_booking",
    "customer_received",
    "rate_booking",
    "save_booking_rating",
    "cancel_booking_confirm",
    "do_cancel_booking",
]
