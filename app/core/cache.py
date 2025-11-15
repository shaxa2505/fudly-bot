"""Cache helpers for users, offers, and stores with Redis support."""
from __future__ import annotations

import time
from typing import Any, Dict, List, Optional, Protocol, Tuple

from .redis_cache import RedisCache
from .utils import get_user_field

CACHE_TTL = 180  # 3 minutes
OFFERS_CACHE_TTL = 60  # 1 minute


class CacheDatabaseProto(Protocol):
    """Subset of database API required by the cache manager."""

    def get_user(self, user_id: int) -> Any: ...

    def get_hot_offers(self, city: str, limit: int, offset: int) -> List[Any]: ...

    def get_stores_by_business_type(self, city: str, business_type: str) -> List[Any]: ...


class CacheManager:
    """Encapsulates frequently used cache lookups with TTL invalidation.
    
    Supports both in-memory and Redis caching. If Redis is available and configured,
    it will be used for distributed caching. Otherwise, falls back to in-memory cache.
    """

    def __init__(
        self,
        db: CacheDatabaseProto,
        redis_host: Optional[str] = None,
        redis_port: int = 6379,
        redis_db: int = 0,
        redis_password: Optional[str] = None,
    ):
        self._db = db
        self._user_cache: Dict[int, Dict[str, Any]] = {}
        self._offers_cache: Dict[Tuple[str, str, int], Dict[str, Any]] = {}
        self._stores_cache: Dict[Tuple[str, str], Dict[str, Any]] = {}
        
        # Try to initialize Redis cache if connection details provided
        self._redis: Optional[RedisCache] = None
        if redis_host:
            try:
                self._redis = RedisCache(
                    host=redis_host,
                    port=redis_port,
                    db=redis_db,
                    password=redis_password,
                )
                # Test connection
                if not self._redis.ping():
                    self._redis = None
            except Exception:
                # Fall back to in-memory cache
                self._redis = None

    def _make_redis_key(self, prefix: str, *parts: Any) -> str:
        """Generate Redis key from prefix and parts."""
        return f"{prefix}:{':'.join(str(p) for p in parts)}"

    def get_user_data(self, user_id: int) -> Dict[str, Any]:
        now = time.time()
        
        # Try Redis first if available
        if self._redis:
            redis_key = self._make_redis_key("user", user_id)
            cached = self._redis.get(redis_key)
            if cached:
                return cached
        
        # Check in-memory cache
        cached = self._user_cache.get(user_id)
        if cached and (now - cached["ts"]) < CACHE_TTL:
            return cached
        
        # Fetch from database
        user = self._db.get_user(user_id)
        if user:
            data = {
                "lang": get_user_field(user, "language", "ru"),
                "role": get_user_field(user, "role", "customer"),
                "city": get_user_field(user, "city", "Ташкент"),
                "user": user,
                "ts": now,
            }
            self._user_cache[user_id] = data
            
            # Store in Redis if available
            if self._redis:
                redis_key = self._make_redis_key("user", user_id)
                self._redis.set(redis_key, data, ttl=CACHE_TTL)
            
            return data
        
        return {"lang": "ru", "role": "customer", "city": "Ташкент", "user": None, "ts": now}

    def invalidate_user(self, user_id: int) -> None:
        self._user_cache.pop(user_id, None)
        if self._redis:
            redis_key = self._make_redis_key("user", user_id)
            self._redis.delete(redis_key)

    def get_user_language(self, user_id: int) -> str:
        return self.get_user_data(user_id)["lang"]

    def get_hot_offers(self, city: str, limit: int = 20, offset: int = 0) -> List[Any]:
        now = time.time()
        cache_key = (city, "hot", offset)
        
        # Try Redis first if available
        if self._redis:
            redis_key = self._make_redis_key("offers", city, "hot", offset)
            cached = self._redis.get(redis_key)
            if cached:
                return cached
        
        # Check in-memory cache
        cached_dict = self._offers_cache.get(cache_key)
        if cached_dict and (now - cached_dict["ts"]) < OFFERS_CACHE_TTL:
            return cached_dict["offers"]
        
        # Fetch from database
        offers = self._db.get_hot_offers(city, limit, offset)
        self._offers_cache[cache_key] = {"offers": offers, "ts": now}
        
        # Store in Redis if available
        if self._redis:
            redis_key = self._make_redis_key("offers", city, "hot", offset)
            self._redis.set(redis_key, offers, ttl=OFFERS_CACHE_TTL)
        
        return offers

    def invalidate_offers(self) -> None:
        self._offers_cache.clear()
        # Clear Redis offers cache if available
        if self._redis:
            # Note: This is a simple implementation. For production, 
            # you might want to track keys or use Redis SCAN
            pass

    def get_stores_by_type(self, city: str, business_type: str) -> List[Any]:
        now = time.time()
        cache_key = (city, business_type)
        
        # Try Redis first if available
        if self._redis:
            redis_key = self._make_redis_key("stores", city, business_type)
            cached = self._redis.get(redis_key)
            if cached:
                return cached
        
        # Check in-memory cache
        cached_dict = self._stores_cache.get(cache_key)
        if cached_dict and (now - cached_dict["ts"]) < OFFERS_CACHE_TTL:
            return cached_dict["stores"]
        
        # Fetch from database
        stores = self._db.get_stores_by_business_type(city, business_type)
        self._stores_cache[cache_key] = {"stores": stores, "ts": now}
        
        # Store in Redis if available
        if self._redis:
            redis_key = self._make_redis_key("stores", city, business_type)
            self._redis.set(redis_key, stores, ttl=OFFERS_CACHE_TTL)
        
        return stores

    def invalidate_stores(self) -> None:
        self._stores_cache.clear()
        # Clear Redis stores cache if available
        if self._redis:
            # Note: This is a simple implementation. For production,
            # you might want to track keys or use Redis SCAN
            pass
