from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from app.integrations.redis_cart import RedisCartStorage


@dataclass
class FakeRedisClient:
    data: dict[str, str] = field(default_factory=dict)
    expiry: dict[str, int] = field(default_factory=dict)
    setex_calls: list[tuple[str, int]] = field(default_factory=list)

    def ping(self) -> bool:
        return True

    def get(self, key: str):
        return self.data.get(key)

    def setex(self, key: str, ttl: int, value: str) -> bool:
        self.data[key] = value
        self.expiry[key] = ttl
        self.setex_calls.append((key, ttl))
        return True

    def delete(self, key: str) -> int:
        existed = 1 if key in self.data else 0
        self.data.pop(key, None)
        self.expiry.pop(key, None)
        return existed

    def set(self, key: str, value: str, nx: bool = False, ex: int | None = None):
        if nx and key in self.data:
            return False
        self.data[key] = value
        if ex is not None:
            self.expiry[key] = ex
        return True

    def eval(self, _script: str, _keys_count: int, key: str, token: str) -> int:
        if self.data.get(key) == token:
            self.delete(key)
            return 1
        return 0


@pytest.fixture
def fake_redis(monkeypatch):
    import app.integrations.redis_cart as redis_cart_module

    client = FakeRedisClient()
    monkeypatch.setattr(redis_cart_module, "REDIS_AVAILABLE", True)
    monkeypatch.setattr(redis_cart_module.redis, "from_url", lambda *args, **kwargs: client, raising=False)
    return client


def test_redis_cart_is_shared_between_instances(fake_redis) -> None:
    storage_a = RedisCartStorage(redis_url="redis://fake")
    storage_b = RedisCartStorage(redis_url="redis://fake")

    added = storage_a.add_item(
        user_id=42,
        offer_id=10,
        store_id=7,
        title="Bread",
        price=8000,
        quantity=1,
        original_price=10000,
    )

    assert added is not None
    items = storage_b.get_cart(42)
    assert len(items) == 1
    assert items[0].offer_id == 10
    assert items[0].store_id == 7


def test_redis_cart_enforces_single_store_rule(fake_redis) -> None:
    storage = RedisCartStorage(redis_url="redis://fake")
    storage.add_item(
        user_id=99,
        offer_id=1,
        store_id=11,
        title="Milk",
        price=5000,
    )

    rejected = storage.add_item(
        user_id=99,
        offer_id=2,
        store_id=12,
        title="Fish",
        price=9000,
    )

    assert rejected is None
    assert len(storage.get_cart(99)) == 1


def test_redis_cart_refreshes_ttl_on_changes(fake_redis) -> None:
    storage = RedisCartStorage(redis_url="redis://fake")
    user_id = 777

    storage.add_item(
        user_id=user_id,
        offer_id=4,
        store_id=3,
        title="Apple",
        price=4000,
        quantity=1,
    )
    calls_before = len(fake_redis.setex_calls)
    assert calls_before >= 1
    assert fake_redis.expiry["cart:777"] == RedisCartStorage.CART_EXPIRY_SECONDS

    assert storage.update_quantity(user_id, 4, 2)
    assert len(fake_redis.setex_calls) == calls_before + 1
    assert fake_redis.expiry["cart:777"] == RedisCartStorage.CART_EXPIRY_SECONDS

