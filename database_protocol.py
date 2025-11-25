"""
Database Protocol - Interface contract for database implementations.

This protocol defines the interface that all database implementations must follow.
Uses flexible Any types for maximum compatibility with existing code.
"""
from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any, Protocol, runtime_checkable

# Type aliases for database results (flexible - can be dict, tuple, or HybridRow)
RowType = Any
RowList = list[Any]


@runtime_checkable
class DatabaseProtocol(Protocol):
    """
    Protocol describing database methods for type checking.

    All database implementations (PostgreSQL, etc.) must conform to this protocol.
    Uses flexible return types for compatibility with different row formats.
    """

    # ========== CONNECTION MANAGEMENT ==========
    @contextmanager
    def get_connection(self) -> Iterator[Any]:
        """Get a database connection from the pool."""
        ...

    def close(self) -> None:
        """Close all database connections."""
        ...

    # ========== USER METHODS ==========
    def add_user(
        self,
        user_id: int,
        username: str | None = None,
        first_name: str | None = None,
        phone: str | None = None,
        city: str = "Ташкент",
        language: str = "ru",
    ) -> None:
        ...

    def get_user(self, user_id: int) -> RowType | None:
        ...

    def get_user_model(self, user_id: int) -> Any | None:
        """Get user as a domain model object."""
        ...

    def update_user_phone(self, user_id: int, phone: str) -> None:
        ...

    def update_user_city(self, user_id: int, city: str) -> None:
        ...

    def update_user_language(self, user_id: int, language: str) -> None:
        ...

    def update_user_role(self, user_id: int, role: str) -> None:
        ...

    def get_user_language(self, user_id: int) -> str:
        ...

    def get_all_users(self) -> list[tuple[Any, ...]]:
        ...

    # ========== STORE METHODS ==========
    def add_store(
        self,
        owner_id: int,
        name: str,
        city: str,
        address: str | None = None,
        description: str | None = None,
        category: str = "Ресторан",
        phone: str | None = None,
        business_type: str = "supermarket",
    ) -> int:
        ...

    def get_user_stores(self, owner_id: int) -> RowList:
        ...

    def get_approved_stores(self, owner_id: int) -> RowList:
        ...

    def get_store(self, store_id: int) -> RowType | None:
        ...

    def get_stores_by_city(self, city: str) -> RowList:
        ...

    def get_stores_by_business_type(
        self, business_type: str, city: str | None = None
    ) -> list[tuple[Any, ...]]:
        ...

    def get_pending_stores(self) -> list[tuple[Any, ...]]:
        ...

    def approve_store(self, store_id: int) -> None:
        ...

    def reject_store(self, store_id: int, reason: str) -> None:
        ...

    def get_store_owner(self, store_id: int) -> int | None:
        ...

    # ========== OFFER METHODS ==========
    def add_offer(
        self,
        store_id: int,
        title: str,
        description: str,
        original_price: float,
        discount_price: float,
        quantity: int,
        available_from: str,
        available_until: str,
        photo: str | None = None,
        expiry_date: str | None = None,
        unit: str = "шт",
        category: str = "other",
    ) -> int:
        ...

    def get_active_offers(self, city: str | None = None, store_id: int | None = None) -> RowList:
        ...

    def get_hot_offers(
        self,
        city: str | None = None,
        limit: int = 20,
        offset: int = 0,
        business_type: str | None = None,
    ) -> list[tuple[Any, ...]]:
        ...

    def count_hot_offers(self, city: str | None = None, business_type: str | None = None) -> int:
        ...

    def get_offer(self, offer_id: int) -> tuple[Any, ...] | None:
        ...

    def get_store_offers(self, store_id: int) -> list[tuple[Any, ...]]:
        ...

    def update_offer_quantity(self, offer_id: int, new_quantity: int) -> None:
        ...

    def increment_offer_quantity(self, offer_id: int, amount: int = 1) -> None:
        ...

    def increment_offer_quantity_atomic(self, offer_id: int, amount: int = 1) -> int:
        ...

    def deactivate_offer(self, offer_id: int) -> None:
        ...

    def activate_offer(self, offer_id: int) -> None:
        ...

    def update_offer_expiry(self, offer_id: int, new_expiry: str) -> None:
        ...

    def delete_offer(self, offer_id: int) -> bool:
        ...

    def delete_expired_offers(self) -> None:
        ...

    # ========== BOOKING METHODS ==========
    def create_booking(
        self,
        offer_id: int,
        user_id: int,
        booking_code: str,
        quantity: int = 1,
        pickup_time: str | None = None,
        pickup_address: str | None = None,
    ) -> int:
        ...

    def create_booking_atomic(
        self,
        offer_id: int,
        user_id: int,
        quantity: int = 1,
        pickup_time: str | None = None,
        pickup_address: str | None = None,
    ) -> tuple[bool, int | None, str | None, str | None]:
        ...

    def get_user_bookings(self, user_id: int) -> list[tuple[Any, ...]]:
        ...

    def get_booking(self, booking_id: int) -> tuple[Any, ...] | None:
        ...

    def get_booking_by_code(self, booking_code: str) -> tuple[Any, ...] | None:
        ...

    def update_booking_status(self, booking_id: int, status: str) -> None:
        ...

    def complete_booking(self, booking_id: int) -> None:
        ...

    def cancel_booking(self, booking_id: int) -> None:
        ...

    def get_store_bookings(self, store_id: int) -> list[tuple[Any, ...]]:
        ...

    def get_booking_history(self, user_id: int, limit: int = 50) -> list[tuple[Any, ...]]:
        ...

    # ========== ADMIN METHODS ==========
    def set_admin(self, user_id: int) -> None:
        ...

    def is_admin(self, user_id: int) -> bool:
        ...

    def get_all_admins(self) -> list[int]:
        ...

    def get_statistics(self) -> dict[str, Any]:
        ...

    # ========== FAVORITES METHODS ==========
    def get_favorites(self, user_id: int) -> list[tuple[Any, ...]]:
        ...

    def add_to_favorites(self, user_id: int, store_id: int) -> None:
        ...

    def remove_from_favorites(self, user_id: int, store_id: int) -> None:
        ...

    def is_favorite(self, user_id: int, store_id: int) -> bool:
        ...

    # ========== NOTIFICATION METHODS ==========
    def add_notification(self, user_id: int, message: str) -> None:
        ...

    def toggle_notifications(self, user_id: int) -> bool:
        ...

    # ========== RATING METHODS ==========
    def add_rating(
        self,
        booking_id: int,
        user_id: int,
        store_id: int,
        rating: int,
        comment: str | None = None,
    ) -> None:
        ...

    def get_store_ratings(self, store_id: int) -> list[tuple[Any, ...]]:
        ...

    def get_store_rating_summary(self, store_id: int) -> tuple[float, int]:
        ...

    # ========== PAYMENT METHODS ==========
    def get_platform_payment_card(self) -> str | None:
        ...

    def set_platform_payment_card(self, card_number: str) -> None:
        ...

    # ======= BOOKING UTILITIES =======
    def set_booking_payment_proof(self, booking_id: int, file_id: str) -> bool:
        ...

    def mark_reminder_sent(self, booking_id: int) -> bool:
        ...

    # ======= ORDERS / DELIVERY =======
    def create_order(
        self,
        user_id: int,
        store_id: int,
        offer_id: int,
        quantity: int,
        order_type: str,
        delivery_address: str | None = None,
        delivery_price: int = 0,
        payment_method: str | None = None,
    ) -> int | None:
        ...

    def update_payment_status(
        self, order_id: int, status: str, photo_id: str | None = None
    ) -> bool:
        ...

    def get_order(self, order_id: int) -> tuple[Any, ...] | None:
        ...

    # ======= SEARCH =======
    def search_offers(self, query: str, city: str | None = None) -> RowList:
        ...

    def search_stores(self, query: str, city: str | None = None) -> RowList:
        ...
