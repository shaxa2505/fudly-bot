"""
Advanced caching service with Redis and in-memory backends.

Features:
- Multi-level caching (L1: memory, L2: Redis)
- TTL support with automatic expiration
- Tag-based cache invalidation
- Cache warming and preloading
- Metrics and statistics
- Decorator for easy function caching
"""
import asyncio
import functools
import hashlib
import logging
import pickle
import time
from abc import ABC, abstractmethod
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


class CacheBackend(str, Enum):
    """Available cache backends."""

    MEMORY = "memory"
    REDIS = "redis"
    MULTI_LEVEL = "multi_level"


@dataclass
class CacheEntry:
    """Single cache entry with metadata."""

    key: str
    value: Any
    created_at: float
    ttl: int | None  # seconds
    tags: set[str] = field(default_factory=set)
    hits: int = 0

    @property
    def expires_at(self) -> float | None:
        """Get expiration timestamp."""
        if self.ttl is None:
            return None
        return self.created_at + self.ttl

    @property
    def is_expired(self) -> bool:
        """Check if entry is expired."""
        if self.ttl is None:
            return False
        return time.time() > self.expires_at

    @property
    def ttl_remaining(self) -> int | None:
        """Get remaining TTL in seconds."""
        if self.ttl is None:
            return None
        remaining = int(self.expires_at - time.time())
        return max(0, remaining)


@dataclass
class CacheStats:
    """Cache statistics."""

    hits: int = 0
    misses: int = 0
    sets: int = 0
    deletes: int = 0
    expirations: int = 0
    memory_entries: int = 0
    redis_entries: int = 0

    @property
    def hit_rate(self) -> float:
        """Calculate cache hit rate."""
        total = self.hits + self.misses
        if total == 0:
            return 0.0
        return self.hits / total

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "hits": self.hits,
            "misses": self.misses,
            "sets": self.sets,
            "deletes": self.deletes,
            "expirations": self.expirations,
            "hit_rate": round(self.hit_rate * 100, 2),
            "memory_entries": self.memory_entries,
            "redis_entries": self.redis_entries,
        }


class BaseCacheBackend(ABC):
    """Abstract cache backend."""

    @abstractmethod
    async def get(self, key: str) -> Any | None:
        """Get value from cache."""
        pass

    @abstractmethod
    async def set(
        self, key: str, value: Any, ttl: int | None = None, tags: set[str] | None = None
    ) -> bool:
        """Set value in cache."""
        pass

    @abstractmethod
    async def delete(self, key: str) -> bool:
        """Delete key from cache."""
        pass

    @abstractmethod
    async def exists(self, key: str) -> bool:
        """Check if key exists."""
        pass

    @abstractmethod
    async def clear(self) -> int:
        """Clear all entries."""
        pass

    @abstractmethod
    async def delete_by_tag(self, tag: str) -> int:
        """Delete all entries with tag."""
        pass

    @abstractmethod
    async def get_stats(self) -> dict[str, Any]:
        """Get backend statistics."""
        pass


class MemoryCacheBackend(BaseCacheBackend):
    """
    In-memory LRU cache backend.

    Fast but not shared between processes.
    Best for single-instance deployments or as L1 cache.
    """

    def __init__(self, max_size: int = 10000, default_ttl: int = 300):
        self._cache: OrderedDict[str, CacheEntry] = OrderedDict()
        self._tags: dict[str, set[str]] = {}  # tag -> set of keys
        self._max_size = max_size
        self._default_ttl = default_ttl
        self._stats = CacheStats()
        self._lock = asyncio.Lock()

    async def get(self, key: str) -> Any | None:
        """Get value from memory cache."""
        async with self._lock:
            entry = self._cache.get(key)

            if entry is None:
                self._stats.misses += 1
                return None

            if entry.is_expired:
                await self._delete_entry(key)
                self._stats.misses += 1
                self._stats.expirations += 1
                return None

            # Move to end (LRU)
            self._cache.move_to_end(key)
            entry.hits += 1
            self._stats.hits += 1

            return entry.value

    async def set(
        self, key: str, value: Any, ttl: int | None = None, tags: set[str] | None = None
    ) -> bool:
        """Set value in memory cache."""
        async with self._lock:
            # Evict if at capacity
            while len(self._cache) >= self._max_size:
                await self._evict_oldest()

            ttl = ttl if ttl is not None else self._default_ttl
            tags = tags or set()

            entry = CacheEntry(key=key, value=value, created_at=time.time(), ttl=ttl, tags=tags)

            # Remove old entry if exists
            if key in self._cache:
                await self._delete_entry(key)

            self._cache[key] = entry

            # Update tag index
            for tag in tags:
                if tag not in self._tags:
                    self._tags[tag] = set()
                self._tags[tag].add(key)

            self._stats.sets += 1
            self._stats.memory_entries = len(self._cache)

            return True

    async def delete(self, key: str) -> bool:
        """Delete key from cache."""
        async with self._lock:
            if key in self._cache:
                await self._delete_entry(key)
                self._stats.deletes += 1
                return True
            return False

    async def _delete_entry(self, key: str) -> None:
        """Internal delete without lock."""
        entry = self._cache.pop(key, None)
        if entry:
            # Remove from tag index
            for tag in entry.tags:
                if tag in self._tags:
                    self._tags[tag].discard(key)
                    if not self._tags[tag]:
                        del self._tags[tag]
            self._stats.memory_entries = len(self._cache)

    async def _evict_oldest(self) -> None:
        """Evict oldest entry (LRU)."""
        if self._cache:
            oldest_key = next(iter(self._cache))
            await self._delete_entry(oldest_key)
            self._stats.expirations += 1

    async def exists(self, key: str) -> bool:
        """Check if key exists and not expired."""
        entry = self._cache.get(key)
        if entry is None:
            return False
        if entry.is_expired:
            await self.delete(key)
            return False
        return True

    async def clear(self) -> int:
        """Clear all entries."""
        async with self._lock:
            count = len(self._cache)
            self._cache.clear()
            self._tags.clear()
            self._stats.memory_entries = 0
            return count

    async def delete_by_tag(self, tag: str) -> int:
        """Delete all entries with tag."""
        async with self._lock:
            keys = self._tags.get(tag, set()).copy()
            count = 0
            for key in keys:
                if key in self._cache:
                    await self._delete_entry(key)
                    count += 1
            self._stats.deletes += count
            return count

    async def get_stats(self) -> dict[str, Any]:
        """Get cache statistics."""
        self._stats.memory_entries = len(self._cache)
        return self._stats.to_dict()


class RedisCacheBackend(BaseCacheBackend):
    """
    Redis cache backend.

    Shared across processes, best for multi-instance deployments.
    """

    def __init__(self, redis_url: str, prefix: str = "fudly:", default_ttl: int = 300):
        self._redis_url = redis_url
        self._prefix = prefix
        self._default_ttl = default_ttl
        self._redis = None
        self._stats = CacheStats()

    async def _ensure_connected(self) -> None:
        """Ensure Redis connection."""
        if self._redis is None:
            try:
                import redis.asyncio as aioredis

                self._redis = await aioredis.from_url(
                    self._redis_url, encoding="utf-8", decode_responses=False
                )
            except ImportError:
                raise RuntimeError("redis package not installed")

    def _make_key(self, key: str) -> str:
        """Add prefix to key."""
        return f"{self._prefix}{key}"

    def _tag_key(self, tag: str) -> str:
        """Get key for tag set."""
        return f"{self._prefix}tag:{tag}"

    async def get(self, key: str) -> Any | None:
        """Get value from Redis."""
        await self._ensure_connected()

        try:
            data = await self._redis.get(self._make_key(key))
            if data is None:
                self._stats.misses += 1
                return None

            self._stats.hits += 1
            return pickle.loads(data)
        except Exception as e:
            logger.error(f"Redis get error: {e}")
            self._stats.misses += 1
            return None

    async def set(
        self, key: str, value: Any, ttl: int | None = None, tags: set[str] | None = None
    ) -> bool:
        """Set value in Redis."""
        await self._ensure_connected()

        ttl = ttl if ttl is not None else self._default_ttl
        tags = tags or set()

        try:
            redis_key = self._make_key(key)
            data = pickle.dumps(value)

            # Set value with TTL
            if ttl:
                await self._redis.setex(redis_key, ttl, data)
            else:
                await self._redis.set(redis_key, data)

            # Update tag sets
            for tag in tags:
                await self._redis.sadd(self._tag_key(tag), key)
                if ttl:
                    await self._redis.expire(self._tag_key(tag), ttl + 60)

            self._stats.sets += 1
            return True
        except Exception as e:
            logger.error(f"Redis set error: {e}")
            return False

    async def delete(self, key: str) -> bool:
        """Delete key from Redis."""
        await self._ensure_connected()

        try:
            result = await self._redis.delete(self._make_key(key))
            if result:
                self._stats.deletes += 1
            return bool(result)
        except Exception as e:
            logger.error(f"Redis delete error: {e}")
            return False

    async def exists(self, key: str) -> bool:
        """Check if key exists in Redis."""
        await self._ensure_connected()

        try:
            return bool(await self._redis.exists(self._make_key(key)))
        except Exception as e:
            logger.error(f"Redis exists error: {e}")
            return False

    async def clear(self) -> int:
        """Clear all entries with prefix."""
        await self._ensure_connected()

        try:
            keys = []
            async for key in self._redis.scan_iter(f"{self._prefix}*"):
                keys.append(key)

            if keys:
                return await self._redis.delete(*keys)
            return 0
        except Exception as e:
            logger.error(f"Redis clear error: {e}")
            return 0

    async def delete_by_tag(self, tag: str) -> int:
        """Delete all entries with tag."""
        await self._ensure_connected()

        try:
            tag_key = self._tag_key(tag)
            keys = await self._redis.smembers(tag_key)

            count = 0
            for key in keys:
                key_str = key.decode() if isinstance(key, bytes) else key
                if await self.delete(key_str):
                    count += 1

            await self._redis.delete(tag_key)
            return count
        except Exception as e:
            logger.error(f"Redis delete_by_tag error: {e}")
            return 0

    async def get_stats(self) -> dict[str, Any]:
        """Get cache statistics."""
        await self._ensure_connected()

        try:
            info = await self._redis.info("keyspace")
            db_info = info.get("db0", {})
            self._stats.redis_entries = db_info.get("keys", 0)
        except Exception:
            pass

        return self._stats.to_dict()

    async def close(self) -> None:
        """Close Redis connection."""
        if self._redis:
            await self._redis.close()
            self._redis = None


class MultiLevelCache(BaseCacheBackend):
    """
    Multi-level cache (L1: memory, L2: Redis).

    Provides fast memory access with Redis backup.
    """

    def __init__(self, memory_backend: MemoryCacheBackend, redis_backend: RedisCacheBackend):
        self._l1 = memory_backend
        self._l2 = redis_backend

    async def get(self, key: str) -> Any | None:
        """Get from L1, fallback to L2."""
        # Try L1 first
        value = await self._l1.get(key)
        if value is not None:
            return value

        # Try L2
        value = await self._l2.get(key)
        if value is not None:
            # Populate L1
            await self._l1.set(key, value)
            return value

        return None

    async def set(
        self, key: str, value: Any, ttl: int | None = None, tags: set[str] | None = None
    ) -> bool:
        """Set in both L1 and L2."""
        l1_ok = await self._l1.set(key, value, ttl, tags)
        l2_ok = await self._l2.set(key, value, ttl, tags)
        return l1_ok or l2_ok

    async def delete(self, key: str) -> bool:
        """Delete from both levels."""
        l1_ok = await self._l1.delete(key)
        l2_ok = await self._l2.delete(key)
        return l1_ok or l2_ok

    async def exists(self, key: str) -> bool:
        """Check if exists in either level."""
        return await self._l1.exists(key) or await self._l2.exists(key)

    async def clear(self) -> int:
        """Clear both levels."""
        l1_count = await self._l1.clear()
        l2_count = await self._l2.clear()
        return l1_count + l2_count

    async def delete_by_tag(self, tag: str) -> int:
        """Delete by tag from both levels."""
        l1_count = await self._l1.delete_by_tag(tag)
        l2_count = await self._l2.delete_by_tag(tag)
        return l1_count + l2_count

    async def get_stats(self) -> dict[str, Any]:
        """Get combined statistics."""
        l1_stats = await self._l1.get_stats()
        l2_stats = await self._l2.get_stats()

        return {
            "l1_memory": l1_stats,
            "l2_redis": l2_stats,
            "total_hits": l1_stats["hits"] + l2_stats["hits"],
            "total_misses": l1_stats["misses"] + l2_stats["misses"],
        }


class CacheService:
    """
    High-level caching service.

    Provides convenient API for caching with:
    - Automatic key generation
    - Tag-based invalidation
    - Decorator support
    - Metrics
    """

    _instance: Optional["CacheService"] = None

    def __init__(self, backend: BaseCacheBackend):
        self._backend = backend
        self._default_ttl = 300  # 5 minutes

    @classmethod
    def get_instance(cls, redis_url: str | None = None, use_memory: bool = True) -> "CacheService":
        """Get or create singleton instance."""
        if cls._instance is None:
            if redis_url:
                try:
                    redis_backend = RedisCacheBackend(redis_url)
                    if use_memory:
                        memory_backend = MemoryCacheBackend()
                        backend = MultiLevelCache(memory_backend, redis_backend)
                    else:
                        backend = redis_backend
                except Exception as e:
                    logger.warning(f"Redis unavailable, using memory: {e}")
                    backend = MemoryCacheBackend()
            else:
                backend = MemoryCacheBackend()

            cls._instance = cls(backend)
        return cls._instance

    @staticmethod
    def make_key(*args, **kwargs) -> str:
        """Generate cache key from arguments."""
        key_parts = [str(a) for a in args]
        key_parts.extend(f"{k}={v}" for k, v in sorted(kwargs.items()))
        key_str = ":".join(key_parts)

        # Hash if too long
        if len(key_str) > 200:
            return hashlib.md5(key_str.encode()).hexdigest()
        return key_str

    async def get(self, key: str) -> Any | None:
        """Get cached value."""
        return await self._backend.get(key)

    async def set(
        self, key: str, value: Any, ttl: int | None = None, tags: list[str] | None = None
    ) -> bool:
        """Set cached value."""
        tag_set = set(tags) if tags else None
        return await self._backend.set(key, value, ttl or self._default_ttl, tag_set)

    async def delete(self, key: str) -> bool:
        """Delete cached value."""
        return await self._backend.delete(key)

    async def invalidate_tag(self, tag: str) -> int:
        """Invalidate all entries with tag."""
        count = await self._backend.delete_by_tag(tag)
        logger.info(f"Invalidated {count} entries with tag '{tag}'")
        return count

    async def invalidate_tags(self, tags: list[str]) -> int:
        """Invalidate multiple tags."""
        total = 0
        for tag in tags:
            total += await self.invalidate_tag(tag)
        return total

    async def get_or_set(
        self,
        key: str,
        factory: Callable[[], Any],
        ttl: int | None = None,
        tags: list[str] | None = None,
    ) -> Any:
        """Get cached value or compute and cache it."""
        value = await self.get(key)
        if value is not None:
            return value

        # Compute value
        if asyncio.iscoroutinefunction(factory):
            value = await factory()
        else:
            value = factory()

        await self.set(key, value, ttl, tags)
        return value

    async def clear(self) -> int:
        """Clear all cache."""
        return await self._backend.clear()

    async def stats(self) -> dict[str, Any]:
        """Get cache statistics."""
        return await self._backend.get_stats()

    def cached(self, ttl: int | None = None, tags: list[str] | None = None, key_prefix: str = ""):
        """
        Decorator for caching function results.

        Usage:
            @cache.cached(ttl=60, tags=["offers"])
            async def get_offers(city: str):
                ...
        """

        def decorator(func: Callable) -> Callable:
            @functools.wraps(func)
            async def wrapper(*args, **kwargs):
                # Generate cache key
                key = f"{key_prefix}{func.__name__}:{self.make_key(*args, **kwargs)}"

                # Try to get from cache
                cached_value = await self.get(key)
                if cached_value is not None:
                    return cached_value

                # Call function
                if asyncio.iscoroutinefunction(func):
                    result = await func(*args, **kwargs)
                else:
                    result = func(*args, **kwargs)

                # Cache result
                await self.set(key, result, ttl, tags)

                return result

            return wrapper

        return decorator


# Predefined cache tags
class CacheTags:
    """Standard cache tags for invalidation."""

    OFFERS = "offers"
    STORES = "stores"
    USERS = "users"
    BOOKINGS = "bookings"
    SEARCH = "search"
    STATS = "stats"

    @staticmethod
    def offer(offer_id: int) -> str:
        return f"offer:{offer_id}"

    @staticmethod
    def store(store_id: int) -> str:
        return f"store:{store_id}"

    @staticmethod
    def user(user_id: int) -> str:
        return f"user:{user_id}"

    @staticmethod
    def city(city: str) -> str:
        return f"city:{city}"


# Convenience functions
def get_cache_service(redis_url: str | None = None, use_memory: bool = True) -> CacheService:
    """Get cache service singleton."""
    return CacheService.get_instance(redis_url, use_memory)


def cached(ttl: int = 300, tags: list[str] | None = None, key_prefix: str = ""):
    """
    Standalone caching decorator.

    Usage:
        @cached(ttl=60, tags=["offers"])
        async def get_offers():
            ...
    """

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            cache = get_cache_service()
            key = f"{key_prefix}{func.__name__}:{CacheService.make_key(*args, **kwargs)}"

            cached_value = await cache.get(key)
            if cached_value is not None:
                return cached_value

            if asyncio.iscoroutinefunction(func):
                result = await func(*args, **kwargs)
            else:
                result = func(*args, **kwargs)

            await cache.set(key, result, ttl, tags)
            return result

        return wrapper

    return decorator
