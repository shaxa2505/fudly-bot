"""Middleware that pre-fetches and caches user data for each request.

This eliminates redundant database queries when handlers call both
get_user_language() and get_user_model() separately.
"""
from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject

if TYPE_CHECKING:
    from app.core.cache import CacheManager


class UserCacheMiddleware(BaseMiddleware):
    """Middleware that caches user data per-request to avoid duplicate DB calls.

    Many handlers call both db.get_user_language() and db.get_user_model(),
    which results in 2 identical database queries. This middleware pre-fetches
    user data once and injects it into the handler data dict.

    Usage in handlers:
        async def handler(message: Message, user_data: dict, ...):
            lang = user_data.get("lang", "ru")
            user = user_data.get("user")  # Already a model
            city = user_data.get("city", "Ташкент")
    """

    def __init__(self, cache_manager: CacheManager) -> None:
        """Initialize with CacheManager instance.

        Args:
            cache_manager: Instance of app.core.cache.CacheManager
        """
        self.cache = cache_manager

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        # Extract user_id from event
        user_id = self._get_user_id(event)

        if user_id:
            # Pre-fetch user data (uses cache internally)
            user_data = self.cache.get_user_data(user_id)
            data["user_data"] = user_data
            # Also inject commonly used values for convenience
            data["user_lang"] = user_data.get("lang", "ru")
            data["user_city"] = user_data.get("city", "Ташкент")
            data["cached_user"] = user_data.get("user")
        else:
            data["user_data"] = {"lang": "ru", "city": "Ташкент", "user": None}
            data["user_lang"] = "ru"
            data["user_city"] = "Ташкент"
            data["cached_user"] = None

        return await handler(event, data)

    def _get_user_id(self, event: TelegramObject) -> int | None:
        """Extract user_id from various event types."""
        if isinstance(event, Message) and event.from_user:
            return int(event.from_user.id)
        if isinstance(event, CallbackQuery) and event.from_user:
            return int(event.from_user.id)
        # Handle other event types if needed
        from_user = getattr(event, "from_user", None)
        if from_user:
            user_id = getattr(from_user, "id", None)
            return int(user_id) if user_id is not None else None
        return None
