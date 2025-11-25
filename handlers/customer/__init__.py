"""Customer handlers - browsing offers, bookings, orders, profile."""

from .router import router as customer_router
from . import profile, favorites, menu, features

__all__ = ["customer_router", "profile", "favorites", "menu", "features"]
