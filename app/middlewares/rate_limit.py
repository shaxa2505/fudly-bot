"""Rate limiting middleware to prevent API abuse."""
from __future__ import annotations

import logging
import os
import time
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, User
from cachetools import TTLCache

logger = logging.getLogger(__name__)

# Try to import Redis
try:
    import redis

    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False
    redis = None  # type: ignore


class RedisRateLimiter:
    """Redis-based rate limiter for distributed deployments."""

    def __init__(self, redis_url: str | None = None):
        """Initialize Redis connection for rate limiting.

        Args:
            redis_url: Redis URL (defaults to REDIS_URL env var)
        """
        self.redis_url = redis_url or os.getenv("REDIS_URL", "redis://localhost:6379/0")
        self._client: Any = None
        self._connect()

    def _connect(self) -> None:
        """Establish Redis connection."""
        if not REDIS_AVAILABLE:
            raise ImportError("redis package not installed")
        try:
            self._client = redis.from_url(
                self.redis_url,
                decode_responses=True,
                socket_connect_timeout=2,
                socket_timeout=2,
            )
            self._client.ping()
            logger.info("✅ Redis rate limiter connected")
        except Exception as e:
            logger.warning(f"⚠️ Redis connection failed: {e}")
            self._client = None

    def is_available(self) -> bool:
        """Check if Redis is available."""
        if not self._client:
            return False
        try:
            return self._client.ping()
        except Exception:
            return False

    def check_and_increment(
        self, user_id: int, limit: int, window_seconds: int, key_prefix: str
    ) -> tuple[bool, int]:
        """Check rate limit and increment counter atomically.

        Args:
            user_id: User ID to check
            limit: Maximum requests allowed
            window_seconds: Time window in seconds
            key_prefix: Prefix for the Redis key

        Returns:
            Tuple of (is_allowed, current_count)
        """
        if not self._client:
            return True, 0  # Allow if Redis not available

        key = f"ratelimit:{key_prefix}:{user_id}"

        try:
            pipe = self._client.pipeline()
            pipe.incr(key)
            pipe.expire(key, window_seconds)
            results = pipe.execute()

            current_count = results[0]
            is_allowed = current_count <= limit

            return is_allowed, current_count
        except Exception as e:
            logger.error(f"Redis rate limit error: {e}")
            return True, 0  # Allow on error


class RateLimitMiddleware(BaseMiddleware):
    """Middleware for rate limiting user requests.

    Limits:
    - 100 requests per minute per user
    - 20 requests per 10 seconds per user (burst protection)

    Supports both in-memory (single instance) and Redis (distributed) modes.
    """

    def __init__(
        self,
        rate_limit: int = 100,  # requests per minute
        burst_limit: int = 20,  # requests per 10 seconds
        use_redis: bool = True,  # Try to use Redis if available
    ):
        """Initialize rate limiter with configurable limits.

        Args:
            rate_limit: Maximum requests per minute per user
            burst_limit: Maximum requests per 10 seconds per user
            use_redis: Whether to try using Redis (falls back to in-memory)
        """
        super().__init__()
        self.rate_limit = rate_limit
        self.burst_limit = burst_limit

        # Try Redis first if enabled
        self.redis_limiter: RedisRateLimiter | None = None
        if use_redis and REDIS_AVAILABLE:
            try:
                self.redis_limiter = RedisRateLimiter()
                if not self.redis_limiter.is_available():
                    self.redis_limiter = None
                    logger.info("📝 Falling back to in-memory rate limiting")
            except Exception:
                logger.info("📝 Falling back to in-memory rate limiting")

        # In-memory fallback caches
        # Cache with 60 second TTL for per-minute tracking
        self.minute_cache: TTLCache = TTLCache(maxsize=10000, ttl=60)
        # Cache with 10 second TTL for burst protection
        self.burst_cache: TTLCache = TTLCache(maxsize=10000, ttl=10)

        # Track when users were last warned
        self.warning_cache: TTLCache = TTLCache(maxsize=10000, ttl=300)  # 5 minutes

    def _check_limit_memory(self, user_id: int) -> tuple[bool, str | None]:
        """Check rate limit using in-memory cache.

        Returns:
            Tuple of (is_allowed, error_message)
        """
        # Check burst limit (10 seconds window)
        burst_key = f"burst_{user_id}"
        burst_count = self.burst_cache.get(burst_key, 0)
        if burst_count >= self.burst_limit:
            return False, "burst"

        # Check per-minute limit
        minute_key = f"minute_{user_id}"
        minute_count = self.minute_cache.get(minute_key, 0)
        if minute_count >= self.rate_limit:
            return False, "minute"

        # Update counters
        self.burst_cache[burst_key] = burst_count + 1
        self.minute_cache[minute_key] = minute_count + 1

        return True, None

    def _check_limit_redis(self, user_id: int) -> tuple[bool, str | None]:
        """Check rate limit using Redis.

        Returns:
            Tuple of (is_allowed, error_message)
        """
        if not self.redis_limiter:
            return self._check_limit_memory(user_id)

        # Check burst limit
        burst_allowed, burst_count = self.redis_limiter.check_and_increment(
            user_id, self.burst_limit, 10, "burst"
        )
        if not burst_allowed:
            return False, "burst"

        # Check minute limit
        minute_allowed, minute_count = self.redis_limiter.check_and_increment(
            user_id, self.rate_limit, 60, "minute"
        )
        if not minute_allowed:
            return False, "minute"

        return True, None

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

        # Check rate limit (Redis or in-memory)
        if self.redis_limiter and self.redis_limiter.is_available():
            is_allowed, limit_type = self._check_limit_redis(user_id)
        else:
            is_allowed, limit_type = self._check_limit_memory(user_id)

        if not is_allowed:
            # Rate limit exceeded - send warning once per 5 minutes
            if user_id not in self.warning_cache:
                self.warning_cache[user_id] = time.time()

                if limit_type == "burst":
                    logger.warning(f"User {user_id} exceeded burst limit")
                    msg = (
                        "⚠️ Слишком много запросов. Пожалуйста, подождите немного.\n"
                        "⚠️ Juda ko'p so'rovlar. Iltimos, biroz kuting."
                    )
                else:
                    logger.warning(f"User {user_id} exceeded rate limit")
                    msg = (
                        "⚠️ Превышен лимит запросов (100 в минуту). Попробуйте через минуту.\n"
                        "⚠️ So'rovlar limiti oshib ketdi (daqiqada 100 ta). Bir daqiqadan keyin urinib ko'ring."
                    )

                try:
                    await event.answer(msg)
                except Exception:
                    pass  # Ignore errors when sending warning

            return  # Block request

        # Allow request
        return await handler(event, data)
