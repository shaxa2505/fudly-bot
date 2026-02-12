"""Cart storage facade used by bot handlers.

The actual implementation is Redis-backed with 24h TTL and automatic
in-memory fallback when Redis is unavailable.
"""
from __future__ import annotations

from app.integrations.redis_cart import CartItem, RedisCartStorage


class CartStorage(RedisCartStorage):
    """Backward-compatible alias for the Redis-backed cart storage."""


# Global cart storage instance
cart_storage = CartStorage()

__all__ = ["CartItem", "CartStorage", "cart_storage"]
