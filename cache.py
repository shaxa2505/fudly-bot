import os
import time
import pickle
import threading

try:
    import redis
except Exception:
    redis = None


class RedisCache:
    def __init__(self, url: str):
        self.client = redis.from_url(url)

    def get(self, key: str):
        v = self.client.get(key)
        if v is None:
            return None
        try:
            return pickle.loads(v)
        except Exception:
            return None

    def set(self, key: str, value, ex: int = 300):
        try:
            self.client.set(key, pickle.dumps(value), ex=ex)
        except Exception:
            pass

    def delete(self, key: str):
        try:
            self.client.delete(key)
        except Exception:
            pass


class InMemoryCache:
    def __init__(self):
        self._store = {}
        self._lock = threading.Lock()

    def get(self, key: str):
        with self._lock:
            entry = self._store.get(key)
            if not entry:
                return None
            value, expires = entry
            if expires and time.time() > expires:
                del self._store[key]
                return None
            return value

    def set(self, key: str, value, ex: int = 300):
        with self._lock:
            expires = time.time() + ex if ex else None
            self._store[key] = (value, expires)

    def delete(self, key: str):
        with self._lock:
            if key in self._store:
                del self._store[key]


# Factory
def get_cache():
    url = os.environ.get('REDIS_URL')
    if url and redis:
        try:
            return RedisCache(url)
        except Exception:
            return InMemoryCache()
    return InMemoryCache()


cache = get_cache()
