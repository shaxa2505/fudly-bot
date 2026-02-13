"""Shared cart storage singleton used by bot handlers and WebApp API."""
from __future__ import annotations

from app.integrations.redis_cart import CartItem, RedisCartStorage


class CartStorage(RedisCartStorage):
    """Backward-compatible alias for Redis cart storage."""


cart_storage = CartStorage()

__all__ = ["CartItem", "CartStorage", "cart_storage"]
