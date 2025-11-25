"""Bookings module - handles all booking-related functionality.

Structure:
- router.py: Main router that combines all booking handlers
- customer.py: Customer actions (create booking, cancel, view, rate)
- partner.py: Partner actions (confirm, reject, complete)
- utils.py: Shared utilities and helpers
"""
from .router import router, setup_dependencies

__all__ = ["router", "setup_dependencies"]
