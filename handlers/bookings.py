"""Booking handlers aggregator.

This module composes the booking-related routers that are currently split
into smaller files (`bookings_flow.py`, `bookings_create.py`). It exposes a
single `router` object and `setup_dependencies` to wire dependencies.
"""
from handlers.bookings_flow import router as router, setup_dependencies as setup_flow
from handlers.bookings_create import setup_dependencies as setup_create


def setup_dependencies(database, cache_manager, bot_instance, metrics):
    """Setup dependencies for booking modules."""
    # bookings_flow expects (database, bot_instance)
    setup_flow(database, bot_instance)
    # bookings_create expects (database, bot_instance, metrics)
    setup_create(database, bot_instance, metrics)
