"""Redis-backed cart storage with TTL and single-store guard."""
from __future__ import annotations

import json
import os
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Iterator

from app.core.redis_cache import REDIS_AVAILABLE, redis

try:
    from logging_config import logger
except ImportError:
    import logging

    logger = logging.getLogger(__name__)


@dataclass
class CartItem:
    """Single item in cart."""

    offer_id: int
    store_id: int
    title: str
    price: int
    original_price: int
    quantity: float
    max_quantity: float
    store_name: str
    store_address: str
    photo: str | None
    unit: str
    expiry_date: str
    delivery_enabled: bool
    delivery_price: int
    added_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "offer_id": int(self.offer_id),
            "store_id": int(self.store_id),
            "title": self.title,
            "price": int(self.price),
            "original_price": int(self.original_price),
            "quantity": float(self.quantity),
            "max_quantity": float(self.max_quantity),
            "store_name": self.store_name,
            "store_address": self.store_address,
            "photo": self.photo,
            "unit": self.unit,
            "expiry_date": self.expiry_date,
            "delivery_enabled": bool(self.delivery_enabled),
            "delivery_price": int(self.delivery_price),
            "added_at": float(self.added_at),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CartItem:
        return cls(
            offer_id=int(data.get("offer_id", 0)),
            store_id=int(data.get("store_id", 0)),
            title=str(data.get("title", "")),
            price=int(data.get("price", 0)),
            original_price=int(data.get("original_price", data.get("price", 0) or 0)),
            quantity=float(data.get("quantity", 0)),
            max_quantity=float(data.get("max_quantity", 99)),
            store_name=str(data.get("store_name", "")),
            store_address=str(data.get("store_address", "")),
            photo=data.get("photo"),
            unit=str(data.get("unit", "piece")),
            expiry_date=str(data.get("expiry_date", "")),
            delivery_enabled=bool(data.get("delivery_enabled", False)),
            delivery_price=int(data.get("delivery_price", 0)),
            added_at=float(data.get("added_at", time.time())),
        )


class RedisCartStorage:
    """Cart storage persisted in Redis with per-user lock and 24h TTL."""

    CART_EXPIRY_SECONDS = 24 * 60 * 60
    LOCK_TTL_SECONDS = 5
    LOCK_WAIT_SECONDS = 2.0

    def __init__(self, redis_url: str | None = None):
        self._redis_url = redis_url or os.getenv("REDIS_URL")
        self._client = self._init_client()
        self._memory_carts: dict[int, dict[str, Any]] = {}
        self._memory_last_access: dict[int, float] = {}

    def _switch_to_memory_fallback(self, reason: Exception | str) -> None:
        logger.warning("Redis cart fallback to memory mode: %s", reason)
        self._client = None

    def _init_client(self):
        if not REDIS_AVAILABLE:
            logger.warning("redis package is unavailable; cart uses in-memory fallback")
            return None

        if not self._redis_url:
            logger.warning("REDIS_URL is not set; cart uses in-memory fallback")
            return None

        try:
            if hasattr(redis, "from_url"):
                client = redis.from_url(
                    self._redis_url,
                    decode_responses=True,
                    socket_connect_timeout=5,
                    socket_timeout=5,
                )
            else:
                return None
            client.ping()
            logger.info("Redis cart storage enabled")
            return client
        except Exception as exc:
            logger.warning("Redis cart init failed, fallback to in-memory: %s", exc)
            return None

    @staticmethod
    def _cart_key(user_id: int) -> str:
        return f"cart:{int(user_id)}"

    @staticmethod
    def _lock_key(user_id: int) -> str:
        return f"cart_lock:{int(user_id)}"

    @staticmethod
    def _empty_payload() -> dict[str, Any]:
        return {"store_id": None, "items": [], "updated_at": int(time.time())}

    def _cleanup_memory_expired(self) -> None:
        now = time.time()
        expired = [
            user_id
            for user_id, last_access in self._memory_last_access.items()
            if now - last_access > self.CART_EXPIRY_SECONDS
        ]
        for user_id in expired:
            self._memory_carts.pop(user_id, None)
            self._memory_last_access.pop(user_id, None)

    def _memory_touch(self, user_id: int) -> None:
        self._memory_last_access[user_id] = time.time()

    def _memory_load(self, user_id: int) -> dict[str, Any]:
        self._cleanup_memory_expired()
        self._memory_touch(user_id)
        payload = self._memory_carts.get(user_id)
        if not payload:
            return self._empty_payload()
        return payload

    def _memory_save(self, user_id: int, payload: dict[str, Any]) -> None:
        if not payload.get("items"):
            self._memory_carts.pop(user_id, None)
            self._memory_last_access.pop(user_id, None)
            return
        payload["updated_at"] = int(time.time())
        self._memory_carts[user_id] = payload
        self._memory_touch(user_id)

    def _load_payload(self, user_id: int) -> dict[str, Any]:
        if not self._client:
            return self._memory_load(user_id)

        try:
            raw = self._client.get(self._cart_key(user_id))
        except Exception as exc:
            self._switch_to_memory_fallback(exc)
            return self._memory_load(user_id)
        if not raw:
            return self._empty_payload()
        try:
            payload = json.loads(raw)
            if not isinstance(payload, dict):
                return self._empty_payload()
            if not isinstance(payload.get("items"), list):
                payload["items"] = []
            if "store_id" not in payload:
                payload["store_id"] = None
            return payload
        except Exception:
            return self._empty_payload()

    def _save_payload(self, user_id: int, payload: dict[str, Any]) -> None:
        payload["updated_at"] = int(time.time())
        if not payload.get("items"):
            if self._client:
                try:
                    self._client.delete(self._cart_key(user_id))
                except Exception as exc:
                    self._switch_to_memory_fallback(exc)
                    self._memory_save(user_id, payload)
            else:
                self._memory_save(user_id, payload)
            return

        if self._client:
            serialized = json.dumps(payload, ensure_ascii=False)
            try:
                self._client.setex(self._cart_key(user_id), self.CART_EXPIRY_SECONDS, serialized)
                return
            except Exception as exc:
                self._switch_to_memory_fallback(exc)
        self._memory_save(user_id, payload)

    @contextmanager
    def _user_lock(self, user_id: int) -> Iterator[None]:
        if not self._client:
            yield
            return

        lock_key = self._lock_key(user_id)
        token = str(uuid.uuid4())
        deadline = time.monotonic() + self.LOCK_WAIT_SECONDS
        acquired = False

        while time.monotonic() < deadline:
            try:
                acquired = bool(
                    self._client.set(lock_key, token, nx=True, ex=self.LOCK_TTL_SECONDS)
                )
            except Exception as exc:
                self._switch_to_memory_fallback(exc)
                break
            if acquired:
                break
            time.sleep(0.05)

        if not acquired:
            logger.warning("Cart lock timeout for user %s; proceeding without lock", user_id)
            yield
            return

        try:
            yield
        finally:
            try:
                unlock_lua = (
                    "if redis.call('get', KEYS[1]) == ARGV[1] "
                    "then return redis.call('del', KEYS[1]) else return 0 end"
                )
                self._client.eval(unlock_lua, 1, lock_key, token)
            except Exception:
                pass

    def get_cart(self, user_id: int) -> list[CartItem]:
        payload = self._load_payload(user_id)
        return [CartItem.from_dict(item) for item in payload.get("items", [])]

    def replace_cart(self, user_id: int, items: list[CartItem]) -> None:
        with self._user_lock(user_id):
            if not items:
                self._save_payload(user_id, self._empty_payload())
                return
            store_id = int(items[0].store_id)
            payload = {
                "store_id": store_id,
                "items": [item.to_dict() for item in items],
            }
            self._save_payload(user_id, payload)

    def add_item(
        self,
        user_id: int,
        offer_id: int,
        store_id: int,
        title: str,
        price: int,
        quantity: float = 1,
        original_price: int = 0,
        max_quantity: float = 99,
        store_name: str = "",
        store_address: str = "",
        photo: str | None = None,
        unit: str = "piece",
        expiry_date: str = "",
        delivery_enabled: bool = False,
        delivery_price: int = 0,
    ) -> CartItem | None:
        with self._user_lock(user_id):
            payload = self._load_payload(user_id)
            existing_store_id = payload.get("store_id")
            if existing_store_id is not None and int(existing_store_id) != int(store_id):
                logger.info(
                    "Rejected add_item: mixed stores not allowed (existing=%s, new=%s, user=%s)",
                    existing_store_id,
                    store_id,
                    user_id,
                )
                return None

            items = [CartItem.from_dict(raw) for raw in payload.get("items", [])]
            for item in items:
                if int(item.offer_id) == int(offer_id):
                    item.quantity = min(float(item.quantity) + float(quantity), float(item.max_quantity))
                    payload["store_id"] = int(store_id)
                    payload["items"] = [cart_item.to_dict() for cart_item in items]
                    self._save_payload(user_id, payload)
                    return item

            item = CartItem(
                offer_id=int(offer_id),
                store_id=int(store_id),
                title=title,
                price=int(price),
                original_price=int(original_price or price),
                quantity=float(quantity),
                max_quantity=float(max_quantity),
                store_name=store_name,
                store_address=store_address,
                photo=photo,
                unit=unit,
                expiry_date=expiry_date,
                delivery_enabled=delivery_enabled,
                delivery_price=int(delivery_price),
            )
            items.append(item)
            payload["store_id"] = int(store_id)
            payload["items"] = [cart_item.to_dict() for cart_item in items]
            self._save_payload(user_id, payload)
            return item

    def update_quantity(self, user_id: int, offer_id: int, quantity: float) -> bool:
        with self._user_lock(user_id):
            payload = self._load_payload(user_id)
            items = [CartItem.from_dict(raw) for raw in payload.get("items", [])]
            updated = False
            for idx, item in enumerate(items):
                if int(item.offer_id) != int(offer_id):
                    continue
                if quantity <= 0:
                    del items[idx]
                else:
                    item.quantity = min(float(quantity), float(item.max_quantity))
                updated = True
                break

            if not updated:
                return False

            payload["items"] = [cart_item.to_dict() for cart_item in items]
            payload["store_id"] = int(items[0].store_id) if items else None
            self._save_payload(user_id, payload)
            return True

    def update_item(self, user_id: int, offer_id: int, **changes: Any) -> bool:
        with self._user_lock(user_id):
            payload = self._load_payload(user_id)
            items = [CartItem.from_dict(raw) for raw in payload.get("items", [])]
            changed = False
            for item in items:
                if int(item.offer_id) != int(offer_id):
                    continue
                for field_name, value in changes.items():
                    if hasattr(item, field_name):
                        setattr(item, field_name, value)
                        changed = True
                break

            if not changed:
                return False

            payload["items"] = [cart_item.to_dict() for cart_item in items]
            payload["store_id"] = int(items[0].store_id) if items else None
            self._save_payload(user_id, payload)
            return True

    def remove_item(self, user_id: int, offer_id: int) -> bool:
        with self._user_lock(user_id):
            payload = self._load_payload(user_id)
            items = [CartItem.from_dict(raw) for raw in payload.get("items", [])]
            before = len(items)
            items = [item for item in items if int(item.offer_id) != int(offer_id)]
            if len(items) == before:
                return False
            payload["items"] = [cart_item.to_dict() for cart_item in items]
            payload["store_id"] = int(items[0].store_id) if items else None
            self._save_payload(user_id, payload)
            return True

    def clear_cart(self, user_id: int) -> None:
        with self._user_lock(user_id):
            if self._client:
                try:
                    self._client.delete(self._cart_key(user_id))
                except Exception as exc:
                    self._switch_to_memory_fallback(exc)
                    self._memory_carts.pop(user_id, None)
                    self._memory_last_access.pop(user_id, None)
            else:
                self._memory_carts.pop(user_id, None)
                self._memory_last_access.pop(user_id, None)

    def get_cart_total(self, user_id: int) -> float:
        return sum(item.price * item.quantity for item in self.get_cart(user_id))

    def get_cart_count(self, user_id: int) -> float:
        return sum(item.quantity for item in self.get_cart(user_id))

    def get_cart_stores(self, user_id: int) -> set[int]:
        items = self.get_cart(user_id)
        return {int(item.store_id) for item in items}

    def is_empty(self, user_id: int) -> bool:
        return len(self.get_cart(user_id)) == 0
