"""Redis cache implementation for distributed caching."""
from __future__ import annotations

import importlib.util
import json
from typing import Any

from app.core.constants import CACHE_TTL_LONG

# Determine availability once to avoid reassigning constants
REDIS_AVAILABLE: bool = importlib.util.find_spec("redis") is not None

# Expose a patchable `redis` symbol whether or not the package is installed
if REDIS_AVAILABLE:
    import redis as redis  # type: ignore
else:

    class _DummyRedisModule:  # minimal stub so tests can patch `redis.Redis`
        class Redis:  # type: ignore
            pass

    redis = _DummyRedisModule()  # type: ignore


class RedisCache:
    """Redis-based cache implementation."""

    def __init__(
        self, host: str = "localhost", port: int = 6379, db: int = 0, password: str | None = None
    ):
        """Initialize Redis connection.

        Args:
            host: Redis host
            port: Redis port
            db: Redis database number
            password: Redis password (if required)
        """
        # If redis package explicitly marked unavailable, fail fast
        if not REDIS_AVAILABLE:
            raise ImportError("redis package not installed. Install with: pip install redis")

        # Require a usable `redis.Redis` constructor (tests may patch this)
        if not hasattr(redis, "Redis"):
            raise ImportError("redis package not installed. Install with: pip install redis")

        # Use Any for client type to avoid runtime/type issues if redis is patched in tests
        self._client: Any = redis.Redis(
            host=host,
            port=port,
            db=db,
            password=password,
            decode_responses=True,
            socket_connect_timeout=5,
            socket_timeout=5,
        )
        self._default_ttl = CACHE_TTL_LONG  # 1 hour

    def get(self, key: str) -> Any:
        """Get value from cache.

        Args:
            key: Cache key

        Returns:
            Cached value or None if not found
        """
        try:
            value = self._client.get(key)
            if value is None:
                return None
            return json.loads(value)
        except Exception:
            return None

    def set(self, key: str, value: Any, ttl: int | None = None) -> bool:
        """Set value in cache.

        Args:
            key: Cache key
            value: Value to cache
            ttl: Time to live in seconds (default: 1 hour)

        Returns:
            True if successful
        """
        try:
            ttl = ttl or self._default_ttl
            serialized = json.dumps(value)
            return bool(self._client.setex(key, ttl, serialized))
        except Exception:
            return False

    def delete(self, key: str) -> bool:
        """Delete key from cache.

        Args:
            key: Cache key

        Returns:
            True if key was deleted
        """
        try:
            return bool(self._client.delete(key))
        except Exception:
            return False

    def clear(self) -> bool:
        """Clear all keys in current database.

        Returns:
            True if successful
        """
        try:
            self._client.flushdb()
            return True
        except Exception:
            return False

    def exists(self, key: str) -> bool:
        """Check if key exists.

        Args:
            key: Cache key

        Returns:
            True if key exists
        """
        try:
            return bool(self._client.exists(key))
        except Exception:
            return False

    def increment(self, key: str, amount: int = 1) -> int | None:
        """Increment counter.

        Args:
            key: Cache key
            amount: Amount to increment

        Returns:
            New value or None on error
        """
        try:
            return self._client.incrby(key, amount)
        except Exception:
            return None

    def get_many(self, keys: list[str]) -> dict[str, Any]:
        """Get multiple values at once.

        Args:
            keys: List of cache keys

        Returns:
            Dictionary of key-value pairs
        """
        try:
            values = self._client.mget(keys)
            result = {}
            for key, value in zip(keys, values):
                if value is not None:
                    result[key] = json.loads(value)
            return result
        except Exception:
            return {}

    def set_many(self, mapping: dict[str, Any], ttl: int | None = None) -> bool:
        """Set multiple values at once.

        Args:
            mapping: Dictionary of key-value pairs
            ttl: Time to live in seconds

        Returns:
            True if successful
        """
        try:
            ttl = ttl or self._default_ttl
            pipeline = self._client.pipeline()
            for key, value in mapping.items():
                serialized = json.dumps(value)
                pipeline.setex(key, ttl, serialized)
            pipeline.execute()
            return True
        except Exception:
            return False

    def ping(self) -> bool:
        """Check if Redis is available.

        Returns:
            True if Redis responds to PING
        """
        try:
            return self._client.ping()
        except Exception:
            return False
