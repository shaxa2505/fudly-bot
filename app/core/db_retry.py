"""Database retry logic with exponential backoff."""
from __future__ import annotations

import functools
import logging
import time
from collections.abc import Callable
from typing import Any, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


def db_retry(
    max_attempts: int = 3,
    initial_delay: float = 0.1,
    max_delay: float = 5.0,
    exponential_base: float = 2.0,
    exceptions: tuple = (Exception,),
):
    """Retry decorator with exponential backoff for database operations.

    Args:
        max_attempts: Maximum number of retry attempts
        initial_delay: Initial delay in seconds
        max_delay: Maximum delay between retries
        exponential_base: Base for exponential backoff calculation
        exceptions: Tuple of exceptions to catch and retry

    Example:
        @db_retry(max_attempts=3, exceptions=(psycopg.OperationalError,))
        def get_user(user_id):
            return db.get_user(user_id)
    """

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> T:
            delay = initial_delay
            last_exception = None

            for attempt in range(max_attempts):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e

                    if attempt < max_attempts - 1:
                        # Log retry attempt
                        logger.warning(
                            f"DB operation {func.__name__} failed (attempt {attempt + 1}/{max_attempts}): {e}. "
                            f"Retrying in {delay:.2f}s..."
                        )
                        time.sleep(delay)
                        # Exponential backoff with max delay cap
                        delay = min(delay * exponential_base, max_delay)
                    else:
                        # Last attempt failed
                        logger.error(
                            f"DB operation {func.__name__} failed after {max_attempts} attempts: {e}"
                        )

            # All attempts exhausted
            raise last_exception

        return wrapper

    return decorator


def is_connection_error(error: Exception) -> bool:
    """Check if error is a connection-related error.

    Args:
        error: Exception to check

    Returns:
        True if error is connection-related
    """
    error_msg = str(error).lower()
    connection_keywords = [
        "connection",
        "timeout",
        "lost connection",
        "server closed",
        "network",
        "broken pipe",
        "connection refused",
        "no route to host",
    ]
    return any(keyword in error_msg for keyword in connection_keywords)


class DBHealthCheck:
    """Database health check utility."""

    def __init__(self, db: Any):
        """Initialize health checker.

        Args:
            db: Database instance
        """
        self.db = db
        self._last_check_time = 0.0
        self._last_check_result = False
        self._check_interval = 30.0  # Check every 30 seconds

    def is_healthy(self, force: bool = False) -> bool:
        """Check if database connection is healthy.

        Args:
            force: Force check even if cached result is available

        Returns:
            True if database is healthy
        """
        current_time = time.time()

        # Use cached result if available and recent
        if not force and (current_time - self._last_check_time) < self._check_interval:
            return self._last_check_result

        # Perform health check
        try:
            with self.db.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT 1")
                result = cursor.fetchone()
                self._last_check_result = result is not None
        except Exception as e:
            logger.error(f"Database health check failed: {e}")
            self._last_check_result = False

        self._last_check_time = current_time
        return self._last_check_result

    def get_status(self) -> dict[str, Any]:
        """Get detailed database status.

        Returns:
            Dictionary with status information
        """
        is_healthy = self.is_healthy(force=True)

        status = {
            "healthy": is_healthy,
            "timestamp": time.time(),
        }

        if is_healthy:
            try:
                # Get connection pool stats if available
                if hasattr(self.db, "pool"):
                    pool = self.db.pool
                    status["pool"] = {
                        "size": pool.size if hasattr(pool, "size") else "unknown",
                        "available": getattr(pool, "available", "unknown"),
                    }
            except Exception as e:
                logger.warning(f"Failed to get pool stats: {e}")

        return status
