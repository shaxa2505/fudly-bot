"""
Database module - PostgreSQL only.

SQLite support has been removed to simplify the codebase.
All database operations now use PostgreSQL via database_pg.py.

For local development:
1. Run: docker-compose -f docker-compose.dev.yml up -d postgres
2. Set DATABASE_URL=postgresql://fudly:fudly_dev_password@localhost:5432/fudly
"""
from __future__ import annotations

import os
import warnings

# Re-export PostgreSQL Database as Database for backward compatibility
from database_pg import Database

# Warn if someone imports this directly
if os.getenv("WARN_DEPRECATED_IMPORTS", "0") == "1":
    warnings.warn(
        "Importing from 'database' is deprecated. Use 'database_pg' directly.",
        DeprecationWarning,
        stacklevel=2,
    )

__all__ = ["Database"]
