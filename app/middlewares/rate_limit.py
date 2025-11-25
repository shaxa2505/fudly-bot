"""Rate limiting middleware to prevent API abuse."""
from __future__ import annotations

import logging
import time
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, User
from cachetools import TTLCache

logger = logging.getLogger(__name__)


class RateLimitMiddleware(BaseMiddleware):
    """Middleware for rate limiting user requests.

    Limits:
    - 100 requests per minute per user
    - 20 requests per 10 seconds per user (burst protection)
    """

    def __init__(
        self,
        rate_limit: int = 100,  # requests per minute
        burst_limit: int = 20,  # requests per 10 seconds
    ):
        """Initialize rate limiter with configurable limits.

        Args:
            rate_limit: Maximum requests per minute per user
            burst_limit: Maximum requests per 10 seconds per user
        """
        super().__init__()
        self.rate_limit = rate_limit
        self.burst_limit = burst_limit

        # Cache with 60 second TTL for per-minute tracking
        self.minute_cache: TTLCache = TTLCache(maxsize=10000, ttl=60)
        # Cache with 10 second TTL for burst protection
        self.burst_cache: TTLCache = TTLCache(maxsize=10000, ttl=10)

        # Track when users were last warned
        self.warning_cache: TTLCache = TTLCache(maxsize=10000, ttl=300)  # 5 minutes

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        """Check rate limit before processing update."""
        user: User | None = data.get("event_from_user")

        if not user:
            # No user info - allow (e.g., channel posts)
            return await handler(event, data)

        user_id = user.id

        # Check burst limit (10 seconds window)
        burst_count = self.burst_cache.get(f"burst_{user_id}", 0)
        if burst_count >= self.burst_limit:
            # Burst limit exceeded
            if user_id not in self.warning_cache:
                self.warning_cache[user_id] = time.time()
                logger.warning(
                    f"User {user_id} exceeded burst limit ({burst_count} requests in 10s)"
                )
                # Send warning only once per 5 minutes
                try:
                    await event.answer(
                        "⚠️ Слишком много запросов. Пожалуйста, подождите немного.\n"
                        "⚠️ Juda ko'p so'rovlar. Iltimos, biroz kuting."
                    )
                except Exception:
                    pass  # Ignore errors when sending warning
            return  # Block request

        # Check per-minute limit
        minute_count = self.minute_cache.get(f"minute_{user_id}", 0)
        if minute_count >= self.rate_limit:
            # Rate limit exceeded
            if user_id not in self.warning_cache:
                self.warning_cache[user_id] = time.time()
                logger.warning(
                    f"User {user_id} exceeded rate limit ({minute_count} requests per minute)"
                )
                try:
                    await event.answer(
                        "⚠️ Превышен лимит запросов (100 в минуту). Попробуйте через минуту.\n"
                        "⚠️ So'rovlar limiti oshib ketdi (daqiqada 100 ta). Bir daqiqadan keyin urinib ko'ring."
                    )
                except Exception:
                    pass
            return  # Block request

        # Update counters
        self.burst_cache[f"burst_{user_id}"] = burst_count + 1
        self.minute_cache[f"minute_{user_id}"] = minute_count + 1

        # Allow request
        return await handler(event, data)
