"""
PostgreSQL Database Module for Fudly Bot.

Modular database implementation with mixins for clean separation of concerns.

Usage:
    from database_pg_module import Database
    db = Database()  # Uses DATABASE_URL env var

    # Or with explicit URL
    db = Database("postgresql://user:pass@host:5432/dbname")

The Database class combines functionality through mixins:
- UserMixin: User CRUD operations
- StoreMixin: Store management
- OfferMixin: Offer management with expiry handling
- BookingMixin: Atomic booking operations
- OrderMixin: Order management
- RatingMixin: Ratings and reviews
- FavoritesMixin: User favorites
- SearchMixin: Full-text search with transliteration
- StatsMixin: Platform statistics
- PaymentMixin: Payment settings
- NotificationMixin: User notifications
"""
from __future__ import annotations

from .core import (
    DATABASE_URL,
    DatabaseCore,
    HybridRow,
    fix_railway_database_url,
    hybrid_row_factory,
)
from .database import Database
from .schema import SchemaMixin

__all__ = [
    "Database",
    "DatabaseCore",
    "SchemaMixin",
    "DATABASE_URL",
    "HybridRow",
    "hybrid_row_factory",
    "fix_railway_database_url",
]
