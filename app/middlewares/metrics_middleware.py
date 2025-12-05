"""
Metrics Middleware for aiogram.

Automatically tracks:
- Request count per handler
- Request duration
- Error rates
- Active users
"""
import time
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject

from app.core.constants import SECONDS_PER_HOUR
from app.core.metrics import metrics

try:
    from logging_config import logger
except ImportError:
    import logging

    logger = logging.getLogger(__name__)


class MetricsMiddleware(BaseMiddleware):
    """Middleware to collect metrics for all handlers."""

    def __init__(self):
        self._active_users: dict[int, float] = {}  # user_id -> last_seen timestamp
        self._active_users_window = SECONDS_PER_HOUR  # 1 hour window for "active" users

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        # Extract handler name
        handler_name = self._get_handler_name(handler, data)

        # Extract user info
        user_id = self._get_user_id(event)
        city = self._get_user_city(event, data)

        # Track active user
        if user_id:
            self._track_active_user(user_id, city)

        # Track request timing
        start_time = time.time()
        status = "success"

        try:
            result = await handler(event, data)
            return result
        except Exception as e:
            status = "error"
            metrics.errors_total.inc(handler=handler_name, error_type=type(e).__name__)
            raise
        finally:
            duration = time.time() - start_time

            # Record metrics
            metrics.requests_total.inc(handler=handler_name, status=status)
            metrics.request_duration.observe(duration, handler=handler_name)

            # Log slow requests
            if duration > 1.0:
                logger.warning(
                    f"Slow request: handler={handler_name}, "
                    f"duration={duration:.2f}s, user_id={user_id}"
                )

    def _get_handler_name(self, handler: Callable, data: dict[str, Any]) -> str:
        """Extract handler name from function or data."""
        # Try to get from handler function
        if hasattr(handler, "__name__"):
            return handler.__name__

        # Try to get from wrapped function
        if hasattr(handler, "__wrapped__"):
            return handler.__wrapped__.__name__

        # Fallback
        return "unknown"

    def _get_user_id(self, event: TelegramObject) -> int | None:
        """Extract user ID from event."""
        if isinstance(event, Message):
            return event.from_user.id if event.from_user else None
        elif isinstance(event, CallbackQuery):
            return event.from_user.id if event.from_user else None
        return None

    def _get_user_city(self, event: TelegramObject, data: dict[str, Any]) -> str:
        """Try to get user's city from context."""
        # Try to get from data (if middleware chain has db data)
        db = data.get("db")
        user_id = self._get_user_id(event)

        if db and user_id:
            try:
                user = db.get_user_model(user_id)
                if user and user.city:
                    return user.city
            except Exception:
                pass

        return "unknown"

    def _track_active_user(self, user_id: int, city: str = "unknown"):
        """Track user as active."""
        current_time = time.time()
        self._active_users[user_id] = current_time

        # Clean up old entries and update gauge
        self._cleanup_inactive_users()

        # Update active users gauge by city
        city_counts: dict[str, int] = {}
        for uid, last_seen in self._active_users.items():
            # We don't have city per user here, so just count total
            city_counts["all"] = city_counts.get("all", 0) + 1

        for c, count in city_counts.items():
            metrics.active_users.set(count, city=c)

    def _cleanup_inactive_users(self):
        """Remove users who haven't been active in the window."""
        current_time = time.time()
        cutoff = current_time - self._active_users_window

        self._active_users = {uid: ts for uid, ts in self._active_users.items() if ts > cutoff}


class BusinessMetricsMiddleware(BaseMiddleware):
    """Middleware to track business-specific metrics."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        # Store metrics instance in data for handlers to use
        data["metrics"] = metrics

        result = await handler(event, data)
        return result
