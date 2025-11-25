"""
Core database utilities - connection pool, helpers, configuration.
"""
from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Any

from psycopg_pool import ConnectionPool

# Logging
try:
    from logging_config import logger
except ImportError:
    import logging

    logger = logging.getLogger(__name__)

# Cache (optional)
try:
    from cache import cache  # type: ignore[import]
except ImportError:

    class SimpleCache:
        def get(self, key: str) -> Any:
            return None

        def set(self, key: str, value: Any, ex: int | None = None) -> None:
            pass

        def delete(self, key: str) -> None:
            pass

    cache = SimpleCache()


class HybridRow:
    """
    A row object that supports both index access (like a tuple) and key access (like a dict).
    This allows for a smooth transition from tuple-based code to dict-based code.
    """

    def __init__(self, cursor, values):
        self._data = dict(zip([d.name for d in cursor.description], values))
        self._values = values

    def __getitem__(self, key):
        if isinstance(key, int):
            return self._values[key]
        return self._data[key]

    def get(self, key, default=None):
        return self._data.get(key, default)

    def __iter__(self):
        return iter(self._values)

    def __repr__(self):
        return repr(self._data)

    def __len__(self):
        return len(self._values)

    def keys(self):
        return self._data.keys()

    def values(self):
        return self._data.values()

    def items(self):
        return self._data.items()


def hybrid_row_factory(cursor):
    """Row factory that returns HybridRow objects."""

    def make_row(values):
        return HybridRow(cursor, values)

    return make_row


# Database connection configuration
DATABASE_URL = os.environ.get("DATABASE_URL", "")
MIN_CONNECTIONS = int(os.environ.get("DB_MIN_CONN", "1"))
MAX_CONNECTIONS = int(os.environ.get("DB_MAX_CONN", "5"))
POOL_WAIT_TIMEOUT = int(os.environ.get("DB_POOL_WAIT_TIMEOUT", "60"))

# Booking configuration
BOOKING_DURATION_HOURS = int(os.environ.get("BOOKING_DURATION_HOURS", "2"))
MAX_ACTIVE_BOOKINGS_PER_USER = int(os.environ.get("MAX_ACTIVE_BOOKINGS_PER_USER", "3"))
BOOKING_EXPIRY_CHECK_MINUTES = int(os.environ.get("BOOKING_EXPIRY_CHECK_MINUTES", "30"))


def fix_railway_database_url(url: str) -> str:
    """
    Fix Railway internal hostname to use public URL.
    Railway sometimes provides internal hostnames that don't work across services.
    """
    if not url:
        return url

    if ".railway.internal" in url:
        pghost = os.environ.get("PGHOST", "")
        pgport = os.environ.get("PGPORT", "5432")
        pgdatabase = os.environ.get("PGDATABASE", "railway")
        pguser = os.environ.get("PGUSER", "postgres")
        pgpassword = os.environ.get("PGPASSWORD", "")

        if pghost and pgpassword and ".railway.internal" not in pghost:
            rebuilt_url = f"postgresql://{pguser}:{pgpassword}@{pghost}:{pgport}/{pgdatabase}"
            logger.info("🔧 Rebuilt DATABASE_URL from PGHOST components")
            return rebuilt_url
        else:
            logger.warning("⚠️ DATABASE_URL contains .railway.internal but no valid PGHOST found")

    return url


class DatabaseCore:
    """Core database functionality - connection pool and base operations."""

    def __init__(self, database_url: str | None = None):
        """Initialize PostgreSQL database connection."""
        raw_url = database_url or DATABASE_URL
        self.database_url = fix_railway_database_url(raw_url)
        self.db_name = "PostgreSQL"

        if not self.database_url:
            raise ValueError("DATABASE_URL environment variable is required for PostgreSQL")

        safe_url = (
            self.database_url.split("@")[1] if "@" in self.database_url else self.database_url
        )
        logger.info(f"🔌 Attempting to connect to: ...@{safe_url}")

        try:
            try:
                self.pool = ConnectionPool(
                    conninfo=self.database_url,
                    min_size=MIN_CONNECTIONS,
                    max_size=MAX_CONNECTIONS,
                    max_waiting=50,
                    max_waiting_timeout=POOL_WAIT_TIMEOUT,
                    kwargs={"row_factory": hybrid_row_factory},
                )
            except TypeError:
                self.pool = ConnectionPool(
                    conninfo=self.database_url,
                    min_size=MIN_CONNECTIONS,
                    max_size=MAX_CONNECTIONS,
                    kwargs={"row_factory": hybrid_row_factory},
                )
            logger.info(
                f"✅ PostgreSQL connection pool created (min={MIN_CONNECTIONS}, max={MAX_CONNECTIONS})"
            )
        except Exception as e:
            logger.error(f"❌ Failed to create PostgreSQL connection pool: {e}")
            raise

    @contextmanager
    def get_connection(self):
        """Context manager for database connections from pool."""
        with self.pool.connection() as conn:
            try:
                yield conn
                conn.commit()
            except Exception as e:
                conn.rollback()
                logger.error(f"Database error: {e}")
                raise

    def close(self):
        """Close all connections in the pool."""
        if hasattr(self, "pool") and self.pool:
            self.pool.close()
            logger.info("PostgreSQL connection pool closed")

    @staticmethod
    def get_time_remaining(expiry_date: str) -> str:
        """Return formatted time remaining until expiry."""
        if not expiry_date:
            return ""

        from datetime import datetime

        try:
            if isinstance(expiry_date, str):
                if " " in expiry_date:
                    try:
                        end_date = datetime.strptime(expiry_date, "%Y-%m-%d %H:%M:%S")
                    except ValueError:
                        try:
                            end_date = datetime.strptime(expiry_date, "%Y-%m-%d %H:%M")
                        except ValueError:
                            return ""
                elif "-" in expiry_date:
                    end_date = datetime.strptime(expiry_date, "%Y-%m-%d")
                elif "." in expiry_date:
                    end_date = datetime.strptime(expiry_date, "%d.%m.%Y")
                else:
                    return ""
            else:
                return ""

            now = datetime.now()
            delta = end_date - now

            if delta.days < 0:
                return "⏰ Срок годности истек"
            elif delta.days == 0:
                hours = delta.seconds // 3600
                if hours > 0:
                    return f"🕐 Годен: {hours} ч"
                else:
                    return "⏰ Срок истекает сегодня"
            elif delta.days == 1:
                return "🕐 Годен: 1 день"
            else:
                return (
                    f"🕐 Годен: {delta.days} дня"
                    if delta.days < 5
                    else f"🕐 Годен: {delta.days} дней"
                )
        except Exception:
            return ""
