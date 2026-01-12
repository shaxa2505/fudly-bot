"""Cart storage - in-memory cart storage for users.

Uses dictionary with user_id as key and list of cart items.
For production, consider using Redis or database table.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

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
    quantity: int
    max_quantity: int
    store_name: str
    store_address: str
    photo: str | None
    unit: str
    expiry_date: str
    delivery_enabled: bool
    delivery_price: int
    added_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "offer_id": self.offer_id,
            "store_id": self.store_id,
            "title": self.title,
            "price": self.price,
            "original_price": self.original_price,
            "quantity": self.quantity,
            "max_quantity": self.max_quantity,
            "store_name": self.store_name,
            "store_address": self.store_address,
            "photo": self.photo,
            "unit": self.unit,
            "expiry_date": self.expiry_date,
            "delivery_enabled": self.delivery_enabled,
            "delivery_price": self.delivery_price,
            "added_at": self.added_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CartItem:
        """Create from dictionary."""
        return cls(
            offer_id=data["offer_id"],
            store_id=data["store_id"],
            title=data["title"],
            price=data["price"],
            original_price=data.get("original_price", data["price"]),
            quantity=data["quantity"],
            max_quantity=data.get("max_quantity", 99),
            store_name=data["store_name"],
            store_address=data.get("store_address", ""),
            photo=data.get("photo"),
            unit=data.get("unit", "шт"),
            expiry_date=data.get("expiry_date", ""),
            delivery_enabled=data.get("delivery_enabled", False),
            delivery_price=data.get("delivery_price", 0),
            added_at=data.get("added_at", time.time()),
        )


class CartStorage:
    """In-memory cart storage.

    Thread-safe storage for user carts.
    Carts expire after 24 hours of inactivity.
    """

    CART_EXPIRY_SECONDS = 86400  # 24 hours

    _instance: CartStorage | None = None
    _carts: dict[int, list[CartItem]]
    _last_access: dict[int, float]

    def __new__(cls) -> CartStorage:
        """Singleton pattern."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._carts = {}
            cls._instance._last_access = {}
        return cls._instance

    def _cleanup_expired(self) -> None:
        """Remove expired carts."""
        current_time = time.time()
        expired_users = [
            user_id
            for user_id, last_access in self._last_access.items()
            if current_time - last_access > self.CART_EXPIRY_SECONDS
        ]
        for user_id in expired_users:
            del self._carts[user_id]
            del self._last_access[user_id]
            logger.debug(f"Expired cart for user {user_id}")

    def _touch(self, user_id: int) -> None:
        """Update last access time for user."""
        self._last_access[user_id] = time.time()

    def get_cart(self, user_id: int) -> list[CartItem]:
        """Get cart for user."""
        self._cleanup_expired()
        self._touch(user_id)
        return self._carts.get(user_id, [])

    def add_item(
        self,
        user_id: int,
        offer_id: int,
        store_id: int,
        title: str,
        price: int,
        quantity: int = 1,
        original_price: int = 0,
        max_quantity: int = 99,
        store_name: str = "",
        store_address: str = "",
        photo: str | None = None,
        unit: str = "шт",
        expiry_date: str = "",
        delivery_enabled: bool = False,
        delivery_price: int = 0,
    ) -> CartItem | None:
        """
        Add item to cart or update quantity if exists.

        Returns None if cart already contains items from a different store
        to enforce single-store carts.
        """
        self._touch(user_id)

        if user_id not in self._carts:
            self._carts[user_id] = []

        # Enforce single-store cart: reject items from another store
        existing_stores = {item.store_id for item in self._carts[user_id]}
        if existing_stores and store_id not in existing_stores:
            logger.info(
                "Rejected add_item: mixed stores not allowed (existing=%s, new=%s, user=%s)",
                existing_stores,
                store_id,
                user_id,
            )
            return None

        # Check if item already in cart
        for item in self._carts[user_id]:
            if item.offer_id == offer_id:
                # Update quantity (max = max_quantity)
                new_qty = min(item.quantity + quantity, item.max_quantity)
                item.quantity = new_qty
                logger.info(f"Updated cart item {offer_id} qty={new_qty} for user {user_id}")
                return item

        # Add new item
        item = CartItem(
            offer_id=offer_id,
            store_id=store_id,
            title=title,
            price=price,
            original_price=original_price or price,
            quantity=quantity,
            max_quantity=max_quantity,
            store_name=store_name,
            store_address=store_address,
            photo=photo,
            unit=unit,
            expiry_date=expiry_date,
            delivery_enabled=delivery_enabled,
            delivery_price=delivery_price,
        )
        self._carts[user_id].append(item)
        logger.info(f"Added item {offer_id} to cart for user {user_id}")
        return item

    def update_quantity(self, user_id: int, offer_id: int, quantity: int) -> bool:
        """Update item quantity. Returns True if found and updated."""
        self._touch(user_id)
        cart = self._carts.get(user_id, [])
        for item in cart:
            if item.offer_id == offer_id:
                if quantity <= 0:
                    return self.remove_item(user_id, offer_id)
                item.quantity = min(quantity, item.max_quantity)
                return True
        return False

    def remove_item(self, user_id: int, offer_id: int) -> bool:
        """Remove item from cart. Returns True if found and removed."""
        self._touch(user_id)
        cart = self._carts.get(user_id, [])
        for i, item in enumerate(cart):
            if item.offer_id == offer_id:
                del cart[i]
                logger.info(f"Removed item {offer_id} from cart for user {user_id}")
                return True
        return False

    def clear_cart(self, user_id: int) -> None:
        """Clear entire cart for user."""
        if user_id in self._carts:
            del self._carts[user_id]
        if user_id in self._last_access:
            del self._last_access[user_id]
        logger.info(f"Cleared cart for user {user_id}")

    def get_cart_total(self, user_id: int) -> int:
        """Get total price of cart."""
        cart = self.get_cart(user_id)
        return sum(item.price * item.quantity for item in cart)

    def get_cart_count(self, user_id: int) -> int:
        """Get total number of items in cart."""
        cart = self.get_cart(user_id)
        return sum(item.quantity for item in cart)

    def get_cart_stores(self, user_id: int) -> set[int]:
        """Get set of store IDs in cart."""
        cart = self.get_cart(user_id)
        return {item.store_id for item in cart}

    def is_empty(self, user_id: int) -> bool:
        """Check if cart is empty."""
        return len(self.get_cart(user_id)) == 0


# Global cart storage instance
cart_storage = CartStorage()
