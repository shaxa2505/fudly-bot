"""
Tests for caching module.

Tests:
- MemoryCacheBackend
- RedisCacheBackend (mocked)
- MultiLevelCache
- CacheService
- Cached decorators
- Tag-based invalidation
"""
import asyncio
import time
from unittest.mock import AsyncMock

import pytest

from app.core.caching import (
    CacheEntry,
    CacheService,
    CacheStats,
    CacheTags,
    MemoryCacheBackend,
    MultiLevelCache,
    RedisCacheBackend,
    cached,
    get_cache_service,
)

# ============= CacheEntry Tests =============


class TestCacheEntry:
    """Tests for CacheEntry dataclass."""

    def test_cache_entry_creation(self):
        """Test creating a cache entry."""
        entry = CacheEntry(
            key="test:key",
            value={"data": "value"},
            created_at=time.time(),
            ttl=300,
            tags={"tag1", "tag2"},
        )

        assert entry.key == "test:key"
        assert entry.value == {"data": "value"}
        assert entry.ttl == 300
        assert "tag1" in entry.tags
        assert entry.hits == 0

    def test_cache_entry_not_expired(self):
        """Test entry with TTL is not immediately expired."""
        entry = CacheEntry(key="test", value="data", created_at=time.time(), ttl=300)

        assert not entry.is_expired
        assert entry.ttl_remaining > 290  # Should have ~300 seconds left

    def test_cache_entry_expired(self):
        """Test entry is expired when TTL passed."""
        entry = CacheEntry(
            key="test",
            value="data",
            created_at=time.time() - 400,  # Created 400 seconds ago
            ttl=300,  # 5 minute TTL
        )

        assert entry.is_expired
        assert entry.ttl_remaining == 0

    def test_cache_entry_no_ttl(self):
        """Test entry without TTL never expires."""
        entry = CacheEntry(
            key="test",
            value="data",
            created_at=time.time() - 10000,  # Very old
            ttl=None,  # No TTL
        )

        assert not entry.is_expired
        assert entry.expires_at is None
        assert entry.ttl_remaining is None


class TestCacheStats:
    """Tests for CacheStats."""

    def test_stats_initial(self):
        """Test initial stats are zero."""
        stats = CacheStats()

        assert stats.hits == 0
        assert stats.misses == 0
        assert stats.hit_rate == 0.0

    def test_stats_hit_rate(self):
        """Test hit rate calculation."""
        stats = CacheStats(hits=80, misses=20)

        assert stats.hit_rate == 0.8

    def test_stats_to_dict(self):
        """Test stats conversion to dict."""
        stats = CacheStats(hits=100, misses=50, sets=150)
        result = stats.to_dict()

        assert result["hits"] == 100
        assert result["misses"] == 50
        assert result["hit_rate"] == 66.67  # 100/(100+50) * 100


# ============= MemoryCacheBackend Tests =============


class TestMemoryCacheBackend:
    """Tests for in-memory cache backend."""

    @pytest.fixture
    def cache(self):
        """Create memory cache backend."""
        return MemoryCacheBackend(max_size=100, default_ttl=60)

    @pytest.mark.asyncio
    async def test_set_and_get(self, cache):
        """Test basic set and get operations."""
        await cache.set("key1", "value1")

        result = await cache.get("key1")
        assert result == "value1"

    @pytest.mark.asyncio
    async def test_get_missing_key(self, cache):
        """Test getting non-existent key."""
        result = await cache.get("nonexistent")

        assert result is None

    @pytest.mark.asyncio
    async def test_get_expired_key(self, cache):
        """Test getting expired key returns None."""
        await cache.set("key1", "value1", ttl=1)

        # Wait for expiration
        await asyncio.sleep(1.5)

        result = await cache.get("key1")
        assert result is None

    @pytest.mark.asyncio
    async def test_delete(self, cache):
        """Test delete operation."""
        await cache.set("key1", "value1")

        deleted = await cache.delete("key1")
        assert deleted is True

        result = await cache.get("key1")
        assert result is None

    @pytest.mark.asyncio
    async def test_delete_nonexistent(self, cache):
        """Test deleting non-existent key."""
        deleted = await cache.delete("nonexistent")
        assert deleted is False

    @pytest.mark.asyncio
    async def test_exists(self, cache):
        """Test exists check."""
        await cache.set("key1", "value1")

        assert await cache.exists("key1") is True
        assert await cache.exists("nonexistent") is False

    @pytest.mark.asyncio
    async def test_clear(self, cache):
        """Test clearing all entries."""
        await cache.set("key1", "value1")
        await cache.set("key2", "value2")
        await cache.set("key3", "value3")

        count = await cache.clear()

        assert count == 3
        assert await cache.get("key1") is None
        assert await cache.get("key2") is None

    @pytest.mark.asyncio
    async def test_tags(self, cache):
        """Test setting values with tags."""
        await cache.set("offer:1", {"id": 1}, tags={"offers", "city:tashkent"})
        await cache.set("offer:2", {"id": 2}, tags={"offers", "city:tashkent"})
        await cache.set("store:1", {"id": 1}, tags={"stores", "city:tashkent"})

        # All should exist
        assert await cache.get("offer:1") is not None
        assert await cache.get("offer:2") is not None
        assert await cache.get("store:1") is not None

    @pytest.mark.asyncio
    async def test_delete_by_tag(self, cache):
        """Test deleting entries by tag."""
        await cache.set("offer:1", {"id": 1}, tags={"offers", "city:tashkent"})
        await cache.set("offer:2", {"id": 2}, tags={"offers", "city:samarkand"})
        await cache.set("store:1", {"id": 1}, tags={"stores", "city:tashkent"})

        # Delete all offers
        count = await cache.delete_by_tag("offers")

        assert count == 2
        assert await cache.get("offer:1") is None
        assert await cache.get("offer:2") is None
        assert await cache.get("store:1") is not None  # Store should remain

    @pytest.mark.asyncio
    async def test_lru_eviction(self):
        """Test LRU eviction when at max capacity."""
        cache = MemoryCacheBackend(max_size=3)

        await cache.set("key1", "value1")
        await cache.set("key2", "value2")
        await cache.set("key3", "value3")

        # Access key1 to make it recently used
        await cache.get("key1")

        # Add new key - should evict key2 (oldest not recently accessed)
        await cache.set("key4", "value4")

        assert await cache.get("key1") is not None  # Recently accessed
        assert await cache.get("key2") is None  # Evicted
        assert await cache.get("key3") is not None
        assert await cache.get("key4") is not None

    @pytest.mark.asyncio
    async def test_stats_tracking(self, cache):
        """Test that stats are tracked correctly."""
        await cache.set("key1", "value1")
        await cache.set("key2", "value2")

        await cache.get("key1")  # Hit
        await cache.get("key1")  # Hit
        await cache.get("nonexistent")  # Miss

        stats = await cache.get_stats()

        assert stats["sets"] == 2
        assert stats["hits"] == 2
        assert stats["misses"] == 1
        assert stats["memory_entries"] == 2


# ============= RedisCacheBackend Tests =============


class TestRedisCacheBackend:
    """Tests for Redis cache backend (mocked)."""

    @pytest.fixture
    def mock_redis(self):
        """Create mock Redis client."""
        redis = AsyncMock()
        redis.get = AsyncMock(return_value=None)
        redis.setex = AsyncMock(return_value=True)
        redis.set = AsyncMock(return_value=True)
        redis.delete = AsyncMock(return_value=1)
        redis.exists = AsyncMock(return_value=1)
        redis.sadd = AsyncMock()
        redis.expire = AsyncMock()
        redis.smembers = AsyncMock(return_value=set())
        redis.scan_iter = AsyncMock(return_value=iter([]))
        redis.info = AsyncMock(return_value={"db0": {"keys": 10}})
        redis.close = AsyncMock()
        return redis

    @pytest.mark.asyncio
    async def test_redis_set_with_ttl(self, mock_redis):
        """Test setting value with TTL in Redis."""

        # Test by directly injecting the mock redis client
        cache = RedisCacheBackend("redis://localhost")
        cache._redis = mock_redis

        result = await cache.set("key1", {"data": "value"}, ttl=300)

        assert result is True
        mock_redis.setex.assert_called_once()

    @pytest.mark.asyncio
    async def test_redis_get(self, mock_redis):
        """Test getting value from Redis."""
        import pickle

        test_value = {"data": "test"}
        mock_redis.get = AsyncMock(return_value=pickle.dumps(test_value))

        cache = RedisCacheBackend("redis://localhost")
        cache._redis = mock_redis

        result = await cache.get("key1")

        assert result == test_value

    @pytest.mark.asyncio
    async def test_redis_delete(self, mock_redis):
        """Test deleting from Redis."""
        cache = RedisCacheBackend("redis://localhost")
        cache._redis = mock_redis

        result = await cache.delete("key1")

        assert result is True
        mock_redis.delete.assert_called_once()


# ============= MultiLevelCache Tests =============


class TestMultiLevelCache:
    """Tests for multi-level cache."""

    @pytest.fixture
    def multi_cache(self):
        """Create multi-level cache with mock L2."""
        l1 = MemoryCacheBackend(max_size=100)
        l2 = AsyncMock(spec=RedisCacheBackend)
        l2.get = AsyncMock(return_value=None)
        l2.set = AsyncMock(return_value=True)
        l2.delete = AsyncMock(return_value=True)
        l2.exists = AsyncMock(return_value=False)
        l2.clear = AsyncMock(return_value=0)
        l2.delete_by_tag = AsyncMock(return_value=0)
        l2.get_stats = AsyncMock(return_value={"hits": 0, "misses": 0})

        return MultiLevelCache(l1, l2)

    @pytest.mark.asyncio
    async def test_get_from_l1(self, multi_cache):
        """Test getting from L1 cache."""
        # Set in L1
        await multi_cache._l1.set("key1", "value1")

        result = await multi_cache.get("key1")

        assert result == "value1"
        # L2 should not be called
        multi_cache._l2.get.assert_not_called()

    @pytest.mark.asyncio
    async def test_get_from_l2_populates_l1(self, multi_cache):
        """Test getting from L2 populates L1."""
        # Set up L2 to return value
        multi_cache._l2.get = AsyncMock(return_value="value_from_l2")

        result = await multi_cache.get("key1")

        assert result == "value_from_l2"

        # L1 should now have the value
        l1_value = await multi_cache._l1.get("key1")
        assert l1_value == "value_from_l2"

    @pytest.mark.asyncio
    async def test_set_both_levels(self, multi_cache):
        """Test setting in both cache levels."""
        result = await multi_cache.set("key1", "value1", ttl=300)

        assert result is True

        # Both should have been called
        l1_value = await multi_cache._l1.get("key1")
        assert l1_value == "value1"
        multi_cache._l2.set.assert_called_once()

    @pytest.mark.asyncio
    async def test_delete_both_levels(self, multi_cache):
        """Test deleting from both levels."""
        await multi_cache._l1.set("key1", "value1")

        result = await multi_cache.delete("key1")

        assert result is True
        multi_cache._l2.delete.assert_called_once()


# ============= CacheService Tests =============


class TestCacheService:
    """Tests for high-level CacheService."""

    @pytest.fixture
    def service(self):
        """Create cache service with memory backend."""
        backend = MemoryCacheBackend()
        return CacheService(backend)

    @pytest.mark.asyncio
    async def test_basic_operations(self, service):
        """Test basic set/get/delete operations."""
        await service.set("key1", {"data": "test"})

        result = await service.get("key1")
        assert result == {"data": "test"}

        await service.delete("key1")
        result = await service.get("key1")
        assert result is None

    @pytest.mark.asyncio
    async def test_get_or_set_cache_miss(self, service):
        """Test get_or_set computes on cache miss."""
        call_count = 0

        def factory():
            nonlocal call_count
            call_count += 1
            return {"computed": True}

        result = await service.get_or_set("key1", factory)

        assert result == {"computed": True}
        assert call_count == 1

    @pytest.mark.asyncio
    async def test_get_or_set_cache_hit(self, service):
        """Test get_or_set returns cached on hit."""
        await service.set("key1", {"cached": True})

        call_count = 0

        def factory():
            nonlocal call_count
            call_count += 1
            return {"computed": True}

        result = await service.get_or_set("key1", factory)

        assert result == {"cached": True}
        assert call_count == 0  # Factory not called

    @pytest.mark.asyncio
    async def test_get_or_set_async_factory(self, service):
        """Test get_or_set with async factory."""

        async def async_factory():
            await asyncio.sleep(0.01)
            return {"async": True}

        result = await service.get_or_set("key1", async_factory)

        assert result == {"async": True}

    @pytest.mark.asyncio
    async def test_invalidate_tag(self, service):
        """Test tag-based invalidation."""
        await service.set("offer:1", {"id": 1}, tags=["offers"])
        await service.set("offer:2", {"id": 2}, tags=["offers"])
        await service.set("store:1", {"id": 1}, tags=["stores"])

        count = await service.invalidate_tag("offers")

        assert count == 2
        assert await service.get("offer:1") is None
        assert await service.get("offer:2") is None
        assert await service.get("store:1") is not None

    @pytest.mark.asyncio
    async def test_invalidate_multiple_tags(self, service):
        """Test invalidating multiple tags."""
        await service.set("offer:1", {"id": 1}, tags=["offers", "city:tashkent"])
        await service.set("store:1", {"id": 1}, tags=["stores", "city:tashkent"])

        count = await service.invalidate_tags(["offers", "stores"])

        assert count >= 2
        assert await service.get("offer:1") is None
        assert await service.get("store:1") is None

    def test_make_key(self, service):
        """Test cache key generation."""
        key1 = service.make_key("offers", "tashkent", page=1)
        key2 = service.make_key("offers", "tashkent", page=1)
        key3 = service.make_key("offers", "samarkand", page=1)

        assert key1 == key2  # Same args = same key
        assert key1 != key3  # Different args = different key

    def test_make_key_long_input(self, service):
        """Test key generation with long input uses hash."""
        long_query = "a" * 300
        key = service.make_key("search", long_query)

        assert len(key) == 32  # MD5 hash length


# ============= Cached Decorator Tests =============


class TestCachedDecorator:
    """Tests for caching decorators."""

    @pytest.fixture(autouse=True)
    def reset_singleton(self):
        """Reset CacheService singleton before each test."""
        CacheService._instance = None
        yield
        CacheService._instance = None

    @pytest.mark.asyncio
    async def test_cached_decorator(self):
        """Test @cached decorator caches results."""
        call_count = 0

        @cached(ttl=60, tags=["test"])
        async def expensive_operation(x: int) -> int:
            nonlocal call_count
            call_count += 1
            return x * 2

        # First call - computes
        result1 = await expensive_operation(5)
        assert result1 == 10
        assert call_count == 1

        # Second call - cached
        result2 = await expensive_operation(5)
        assert result2 == 10
        assert call_count == 1  # Not called again

        # Different argument - computes
        result3 = await expensive_operation(10)
        assert result3 == 20
        assert call_count == 2

    @pytest.mark.asyncio
    async def test_service_cached_decorator(self):
        """Test CacheService.cached() decorator."""
        backend = MemoryCacheBackend()
        service = CacheService(backend)

        call_count = 0

        @service.cached(ttl=60, tags=["test"])
        async def get_data(id: int) -> dict:
            nonlocal call_count
            call_count += 1
            return {"id": id, "name": f"Item {id}"}

        result1 = await get_data(1)
        assert result1 == {"id": 1, "name": "Item 1"}
        assert call_count == 1

        result2 = await get_data(1)
        assert result2 == {"id": 1, "name": "Item 1"}
        assert call_count == 1  # Cached


# ============= CacheTags Tests =============


class TestCacheTags:
    """Tests for CacheTags helper."""

    def test_predefined_tags(self):
        """Test predefined tag constants."""
        assert CacheTags.OFFERS == "offers"
        assert CacheTags.STORES == "stores"
        assert CacheTags.USERS == "users"

    def test_dynamic_tags(self):
        """Test dynamic tag generation."""
        assert CacheTags.offer(123) == "offer:123"
        assert CacheTags.store(456) == "store:456"
        assert CacheTags.user(789) == "user:789"
        assert CacheTags.city("Tashkent") == "city:Tashkent"


# ============= Integration Tests =============


class TestCacheIntegration:
    """Integration tests for caching system."""

    @pytest.fixture(autouse=True)
    def reset_singleton(self):
        """Reset singleton before each test."""
        CacheService._instance = None
        yield
        CacheService._instance = None

    @pytest.mark.asyncio
    async def test_full_workflow(self):
        """Test complete caching workflow."""
        cache = get_cache_service()

        # Simulate offer caching
        offers = [
            {"id": 1, "title": "Pizza", "price": 50000},
            {"id": 2, "title": "Burger", "price": 30000},
        ]

        await cache.set(
            "offers:tashkent", offers, ttl=60, tags=[CacheTags.OFFERS, CacheTags.city("tashkent")]
        )

        # Retrieve
        cached_offers = await cache.get("offers:tashkent")
        assert len(cached_offers) == 2

        # Invalidate by city
        await cache.invalidate_tag(CacheTags.city("tashkent"))

        # Should be gone
        assert await cache.get("offers:tashkent") is None

    @pytest.mark.asyncio
    async def test_concurrent_access(self):
        """Test cache under concurrent access."""
        cache = get_cache_service()

        async def writer(key: str, value: str):
            for i in range(10):
                await cache.set(f"{key}:{i}", f"{value}:{i}")
                await asyncio.sleep(0.001)

        async def reader(key: str):
            results = []
            for i in range(10):
                result = await cache.get(f"{key}:{i}")
                if result:
                    results.append(result)
                await asyncio.sleep(0.001)
            return results

        # Run concurrent operations
        await asyncio.gather(
            writer("test", "value"),
            reader("test"),
            writer("other", "data"),
        )

        # Verify some values were cached
        stats = await cache.stats()
        assert stats["sets"] > 0
