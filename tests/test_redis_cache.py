"""Tests for Redis cache implementation."""
from __future__ import annotations

from unittest.mock import MagicMock, Mock, patch

import pytest


class TestRedisCache:
    """Tests for RedisCache."""

    @patch('app.core.redis_cache.REDIS_AVAILABLE', True)
    @patch('app.core.redis_cache.redis.Redis')
    def test_init(self, mock_redis):
        """Test RedisCache initialization."""
        from app.core.redis_cache import RedisCache
        
        cache = RedisCache(host="localhost", port=6379)
        assert cache is not None
        mock_redis.assert_called_once()

    @patch('app.core.redis_cache.REDIS_AVAILABLE', False)
    def test_init_without_redis(self):
        """Test RedisCache initialization without redis package."""
        from app.core.redis_cache import RedisCache
        
        with pytest.raises(ImportError):
            RedisCache()

    @patch('app.core.redis_cache.REDIS_AVAILABLE', True)
    @patch('app.core.redis_cache.redis.Redis')
    def test_get_success(self, mock_redis):
        """Test successful get operation."""
        from app.core.redis_cache import RedisCache
        
        mock_client = Mock()
        mock_client.get.return_value = '{"key": "value"}'
        mock_redis.return_value = mock_client
        
        cache = RedisCache()
        result = cache.get("test_key")
        
        assert result == {"key": "value"}
        mock_client.get.assert_called_once_with("test_key")

    @patch('app.core.redis_cache.REDIS_AVAILABLE', True)
    @patch('app.core.redis_cache.redis.Redis')
    def test_get_not_found(self, mock_redis):
        """Test get operation when key not found."""
        from app.core.redis_cache import RedisCache
        
        mock_client = Mock()
        mock_client.get.return_value = None
        mock_redis.return_value = mock_client
        
        cache = RedisCache()
        result = cache.get("missing_key")
        
        assert result is None

    @patch('app.core.redis_cache.REDIS_AVAILABLE', True)
    @patch('app.core.redis_cache.redis.Redis')
    def test_set_success(self, mock_redis):
        """Test successful set operation."""
        from app.core.redis_cache import RedisCache
        
        mock_client = Mock()
        mock_client.setex.return_value = True
        mock_redis.return_value = mock_client
        
        cache = RedisCache()
        result = cache.set("test_key", {"data": "value"}, ttl=300)
        
        assert result is True
        mock_client.setex.assert_called_once()

    @patch('app.core.redis_cache.REDIS_AVAILABLE', True)
    @patch('app.core.redis_cache.redis.Redis')
    def test_delete_success(self, mock_redis):
        """Test successful delete operation."""
        from app.core.redis_cache import RedisCache
        
        mock_client = Mock()
        mock_client.delete.return_value = 1
        mock_redis.return_value = mock_client
        
        cache = RedisCache()
        result = cache.delete("test_key")
        
        assert result is True
        mock_client.delete.assert_called_once_with("test_key")

    @patch('app.core.redis_cache.REDIS_AVAILABLE', True)
    @patch('app.core.redis_cache.redis.Redis')
    def test_exists(self, mock_redis):
        """Test exists operation."""
        from app.core.redis_cache import RedisCache
        
        mock_client = Mock()
        mock_client.exists.return_value = 1
        mock_redis.return_value = mock_client
        
        cache = RedisCache()
        result = cache.exists("test_key")
        
        assert result is True

    @patch('app.core.redis_cache.REDIS_AVAILABLE', True)
    @patch('app.core.redis_cache.redis.Redis')
    def test_increment(self, mock_redis):
        """Test increment operation."""
        from app.core.redis_cache import RedisCache
        
        mock_client = Mock()
        mock_client.incrby.return_value = 5
        mock_redis.return_value = mock_client
        
        cache = RedisCache()
        result = cache.increment("counter", 2)
        
        assert result == 5
        mock_client.incrby.assert_called_once_with("counter", 2)

    @patch('app.core.redis_cache.REDIS_AVAILABLE', True)
    @patch('app.core.redis_cache.redis.Redis')
    def test_ping_success(self, mock_redis):
        """Test ping operation."""
        from app.core.redis_cache import RedisCache
        
        mock_client = Mock()
        mock_client.ping.return_value = True
        mock_redis.return_value = mock_client
        
        cache = RedisCache()
        result = cache.ping()
        
        assert result is True

    @patch('app.core.redis_cache.REDIS_AVAILABLE', True)
    @patch('app.core.redis_cache.redis.Redis')
    def test_get_error_handling(self, mock_redis):
        """Test error handling in get operation."""
        from app.core.redis_cache import RedisCache
        
        mock_client = Mock()
        mock_client.get.side_effect = Exception("Connection error")
        mock_redis.return_value = mock_client
        
        cache = RedisCache()
        result = cache.get("test_key")
        
        assert result is None

    @patch('app.core.redis_cache.REDIS_AVAILABLE', True)
    @patch('app.core.redis_cache.redis.Redis')
    def test_set_error_handling(self, mock_redis):
        """Test error handling in set operation."""
        from app.core.redis_cache import RedisCache
        
        mock_client = Mock()
        mock_client.setex.side_effect = Exception("Connection error")
        mock_redis.return_value = mock_client
        
        cache = RedisCache()
        result = cache.set("test_key", "value")
        
        assert result is False
