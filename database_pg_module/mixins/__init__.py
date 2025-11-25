"""Database mixins for modular database operations."""
from __future__ import annotations

from .bookings import BookingMixin
from .favorites import FavoritesMixin
from .notifications import NotificationMixin
from .offers import OfferMixin
from .orders import OrderMixin
from .payments import PaymentMixin
from .ratings import RatingMixin
from .search import SearchMixin
from .stats import StatsMixin
from .stores import StoreMixin
from .users import UserMixin

__all__ = [
    "BookingMixin",
    "FavoritesMixin",
    "NotificationMixin",
    "OfferMixin",
    "OrderMixin",
    "PaymentMixin",
    "RatingMixin",
    "SearchMixin",
    "StatsMixin",
    "StoreMixin",
    "UserMixin",
]
