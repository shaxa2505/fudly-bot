"""
Main Database class combining all mixins.
"""
from __future__ import annotations

from .core import DatabaseCore
from .mixins import (
    BookingMixin,
    FavoritesMixin,
    NotificationMixin,
    OfferMixin,
    OrderMixin,
    PaymentMixin,
    RatingMixin,
    SearchMixin,
    StatsMixin,
    StoreMixin,
    UserMixin,
)
from .schema import SchemaMixin

try:
    from logging_config import logger
except ImportError:
    import logging

    logger = logging.getLogger(__name__)


class Database(
    DatabaseCore,
    SchemaMixin,
    UserMixin,
    StoreMixin,
    OfferMixin,
    BookingMixin,
    OrderMixin,
    RatingMixin,
    FavoritesMixin,
    SearchMixin,
    StatsMixin,
    PaymentMixin,
    NotificationMixin,
):
    """
    PostgreSQL Database for Fudly Bot.

    Combines all database functionality through mixins:
    - UserMixin: User CRUD operations
    - StoreMixin: Store management
    - OfferMixin: Offer management
    - BookingMixin: Booking with atomic operations
    - OrderMixin: Order management
    - RatingMixin: Ratings and reviews
    - FavoritesMixin: User favorites
    - SearchMixin: Full-text search
    - StatsMixin: Platform statistics
    - PaymentMixin: Payment settings
    - NotificationMixin: User notifications
    """

    def __init__(self, database_url=None):
        """Initialize database with connection pool and schema."""
        import os

        super().__init__(database_url)
        # Skip init_db if SKIP_DB_INIT is set (for existing databases)
        if not os.getenv("SKIP_DB_INIT"):
            self.init_db()
            logger.info("✅ Database initialized with all mixins")
        else:
            logger.info("⏭️  Skipping database initialization (SKIP_DB_INIT=1)")
