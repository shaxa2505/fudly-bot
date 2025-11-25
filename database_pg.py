"""
PostgreSQL Database Module for Fudly Bot.

BACKWARDS COMPATIBILITY WRAPPER
================================
This file re-exports the Database class from the modular database package.
All imports from database_pg will continue to work as before.

The actual implementation is now in the `database_pg_module/` package with clean
separation into mixins:
- database_pg_module/core.py - Connection pool, HybridRow
- database_pg_module/schema.py - Schema initialization
- database_pg_module/mixins/users.py - User operations
- database_pg_module/mixins/stores.py - Store operations
- database_pg_module/mixins/offers.py - Offer operations
- database_pg_module/mixins/bookings.py - Booking operations (atomic)
- database_pg_module/mixins/orders.py - Order operations
- database_pg_module/mixins/ratings.py - Rating operations
- database_pg_module/mixins/favorites.py - Favorites operations
- database_pg_module/mixins/search.py - Search operations
- database_pg_module/mixins/stats.py - Statistics operations
- database_pg_module/mixins/payments.py - Payment operations
- database_pg_module/mixins/notifications.py - Notification operations
"""
from __future__ import annotations

# Re-export everything from the modular database package
from database_pg_module import (
    DATABASE_URL,
    Database,
    DatabaseCore,
    HybridRow,
    fix_railway_database_url,
    hybrid_row_factory,
)

# For backwards compatibility, also expose individual constants
from database_pg_module.core import (
    BOOKING_DURATION_HOURS,
    BOOKING_EXPIRY_CHECK_MINUTES,
    MAX_ACTIVE_BOOKINGS_PER_USER,
    MAX_CONNECTIONS,
    MIN_CONNECTIONS,
    POOL_WAIT_TIMEOUT,
)

__all__ = [
    "Database",
    "DatabaseCore",
    "DATABASE_URL",
    "HybridRow",
    "hybrid_row_factory",
    "fix_railway_database_url",
    "BOOKING_DURATION_HOURS",
    "MAX_ACTIVE_BOOKINGS_PER_USER",
    "BOOKING_EXPIRY_CHECK_MINUTES",
    "MIN_CONNECTIONS",
    "MAX_CONNECTIONS",
    "POOL_WAIT_TIMEOUT",
]
