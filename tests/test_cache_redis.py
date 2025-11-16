"""Tests for CacheManager with Redis integration."""
from __future__ import annotations

from typing import Any, List
from unittest.mock import MagicMock, Mock, patch

import pytest

from app.core.cache import CacheManager


class MockDatabase:
    """Mock database for testing."""

    def get_user(self, user_id: int) -> Any:
        if user_id == 123:
            return {"id": 123, "language": "en", "role": "seller", "city": "Moscow"}
        return None

    def get_hot_offers(self, city: str, limit: int, offset: int) -> List[Any]:
        return [{"id": 1, "title": "Offer 1"}, {"id": 2, "title": "Offer 2"}]

    def get_stores_by_business_type(self, city: str, business_type: str) -> List[Any]:
        return [{"id": 1, "name": "Store 1"}, {"id": 2, "name": "Store 2"}]


class TestCacheManagerWithoutRedis:
    """Test CacheManager without Redis (in-memory only)."""

    def test_init_without_redis(self) -> None:
        db = MockDatabase()
        cache = CacheManager(db)
        assert cache._redis is None

    def test_get_user_data_cache_miss(self) -> None:
        db = MockDatabase()
        cache = CacheManager(db)
        
        data = cache.get_user_data(123)
        
        assert data["lang"] == "en"
        assert data["role"] == "seller"
        assert data["city"] == "Moscow"
        assert data["user"]["id"] == 123

    def test_get_user_data_cache_hit(self) -> None:
        db = MockDatabase()
        cache = CacheManager(db)
        
        # First call - cache miss
        data1 = cache.get_user_data(123)
        # Second call - cache hit
        data2 = cache.get_user_data(123)
        
        assert data1 == data2
        assert data1["user"] is data2["user"]  # Same object

    def test_invalidate_user(self) -> None:
        db = MockDatabase()
        cache = CacheManager(db)
        
        # Cache user data
        cache.get_user_data(123)
        assert 123 in cache._user_cache
        
        # Invalidate
        cache.invalidate_user(123)
        assert 123 not in cache._user_cache

    def test_get_hot_offers(self) -> None:
        db = MockDatabase()
        cache = CacheManager(db)
        
        offers = cache.get_hot_offers("Moscow", limit=20, offset=0)
        
        assert len(offers) == 2
        assert offers[0]["id"] == 1

    def test_get_stores_by_type(self) -> None:
        db = MockDatabase()
        cache = CacheManager(db)
        
        stores = cache.get_stores_by_type("Moscow", "restaurant")
        
        assert len(stores) == 2
        assert stores[0]["id"] == 1


class TestCacheManagerWithRedis:
    """Test CacheManager with Redis integration."""

    @patch("app.core.cache.RedisCache")
    def test_init_with_redis_success(self, mock_redis_class: Mock) -> None:
        mock_redis_instance = MagicMock()
        mock_redis_instance.ping.return_value = True
        mock_redis_class.return_value = mock_redis_instance
        
        db = MockDatabase()
        cache = CacheManager(db, redis_host="localhost", redis_port=6379)
        
        assert cache._redis is not None
        mock_redis_class.assert_called_once_with(
            host="localhost", port=6379, db=0, password=None
        )

    @patch("app.core.cache.RedisCache")
    def test_init_with_redis_connection_fail(self, mock_redis_class: Mock) -> None:
        mock_redis_instance = MagicMock()
        mock_redis_instance.ping.return_value = False
        mock_redis_class.return_value = mock_redis_instance
        
        db = MockDatabase()
        cache = CacheManager(db, redis_host="localhost")
        
        # Should fall back to in-memory when ping fails
        assert cache._redis is None

    @patch("app.core.cache.RedisCache")
    def test_init_with_redis_exception(self, mock_redis_class: Mock) -> None:
        mock_redis_class.side_effect = Exception("Connection error")
        
        db = MockDatabase()
        cache = CacheManager(db, redis_host="localhost")
        
        # Should fall back to in-memory when exception occurs
        assert cache._redis is None

    @patch("app.core.cache.RedisCache")
    def test_get_user_data_with_redis_cache_hit(self, mock_redis_class: Mock) -> None:
        mock_redis_instance = MagicMock()
        mock_redis_instance.ping.return_value = True
        mock_redis_instance.get.return_value = {
            "lang": "en",
            "role": "seller",
            "city": "Moscow",
            "user": {"id": 123},
            "ts": 1234567890,
        }
        mock_redis_class.return_value = mock_redis_instance
        
        db = MockDatabase()
        cache = CacheManager(db, redis_host="localhost")
        
        data = cache.get_user_data(123)
        
        assert data["lang"] == "en"
        mock_redis_instance.get.assert_called_once_with("user:123")

    @patch("app.core.cache.RedisCache")
    def test_get_user_data_with_redis_cache_miss(self, mock_redis_class: Mock) -> None:
        mock_redis_instance = MagicMock()
        mock_redis_instance.ping.return_value = True
        mock_redis_instance.get.return_value = None
        mock_redis_class.return_value = mock_redis_instance
        
        db = MockDatabase()
        cache = CacheManager(db, redis_host="localhost")
        
        data = cache.get_user_data(123)
        
        assert data["lang"] == "en"
        assert data["role"] == "seller"
        # Should have stored in Redis
        mock_redis_instance.set.assert_called_once()

    @patch("app.core.cache.RedisCache")
    def test_invalidate_user_with_redis(self, mock_redis_class: Mock) -> None:
        mock_redis_instance = MagicMock()
        mock_redis_instance.ping.return_value = True
        mock_redis_class.return_value = mock_redis_instance
        
        db = MockDatabase()
        cache = CacheManager(db, redis_host="localhost")
        
        cache.invalidate_user(123)
        
        # Should delete from Redis
        mock_redis_instance.delete.assert_called_once_with("user:123")

    @patch("app.core.cache.RedisCache")
    def test_get_hot_offers_with_redis(self, mock_redis_class: Mock) -> None:
        mock_redis_instance = MagicMock()
        mock_redis_instance.ping.return_value = True
        mock_redis_instance.get.return_value = None
        mock_redis_class.return_value = mock_redis_instance
        
        db = MockDatabase()
        cache = CacheManager(db, redis_host="localhost")
        
        offers = cache.get_hot_offers("Moscow", limit=20, offset=0)
        
        assert len(offers) == 2
        # Should have stored in Redis
        mock_redis_instance.set.assert_called_once()

    @patch("app.core.cache.RedisCache")
    def test_get_stores_by_type_with_redis(self, mock_redis_class: Mock) -> None:
        mock_redis_instance = MagicMock()
        mock_redis_instance.ping.return_value = True
        mock_redis_instance.get.return_value = None
        mock_redis_class.return_value = mock_redis_instance
        
        db = MockDatabase()
        cache = CacheManager(db, redis_host="localhost")
        
        stores = cache.get_stores_by_type("Moscow", "restaurant")
        
        assert len(stores) == 2
        # Should have stored in Redis
        mock_redis_instance.set.assert_called_once()

    @patch("app.core.cache.RedisCache")
    def test_make_redis_key(self, mock_redis_class: Mock) -> None:
        mock_redis_instance = MagicMock()
        mock_redis_instance.ping.return_value = True
        mock_redis_class.return_value = mock_redis_instance
        
        db = MockDatabase()
        cache = CacheManager(db, redis_host="localhost")
        
        key = cache._make_redis_key("prefix", "part1", 123, "part3")
        assert key == "prefix:part1:123:part3"
