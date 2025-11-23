"""Protocol for database interface - ensures SQLite and PostgreSQL compatibility."""
from __future__ import annotations

from typing import Any, List, Optional, Protocol, Tuple

from database_types import OfferDict, StoreDict, UserDict


class DatabaseProtocol(Protocol):
    """
    Protocol describing database methods for type checking.
    
    Both SQLite (database.py) and PostgreSQL (database_pg.py) implementations
    must conform to this protocol.
    """

    # ========== USER METHODS ==========
    def add_user(
        self,
        user_id: int,
        username: Optional[str] = None,
        first_name: Optional[str] = None,
        role: str = "customer",
        city: Optional[str] = None,
    ) -> None: ...

    def get_user(self, user_id: int) -> Optional[UserDict]: ...

    def update_user_phone(self, user_id: int, phone: str) -> None: ...

    def update_user_city(self, user_id: int, city: str) -> None: ...

    def update_user_language(self, user_id: int, language: str) -> None: ...

    def update_user_role(self, user_id: int, role: str) -> None: ...

    def get_user_language(self, user_id: int) -> str: ...

    def get_all_users(self) -> List[Tuple[Any, ...]]: ...

    # ========== STORE METHODS ==========
    def add_store(
        self,
        owner_id: int,
        name: str,
        city: str,
        address: Optional[str] = None,
        description: Optional[str] = None,
        category: str = "Ресторан",
        phone: Optional[str] = None,
        business_type: str = "supermarket",
    ) -> int: ...

    def get_user_stores(self, owner_id: int) -> List[StoreDict]: ...

    def get_approved_stores(self, owner_id: int) -> List[StoreDict]: ...

    def get_store(self, store_id: int) -> Optional[StoreDict]: ...

    def get_stores_by_city(self, city: str) -> List[StoreDict]: ...

    def get_stores_by_business_type(
        self, business_type: str, city: Optional[str] = None
    ) -> List[Tuple[Any, ...]]: ...

    def get_pending_stores(self) -> List[Tuple[Any, ...]]: ...

    def approve_store(self, store_id: int) -> None: ...

    def reject_store(self, store_id: int, reason: str) -> None: ...

    def get_store_owner(self, store_id: int) -> Optional[int]: ...

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
        photo: Optional[str] = None,
        expiry_date: Optional[str] = None,
        unit: str = "шт",
        category: str = "other",
    ) -> int: ...

    def get_active_offers(
        self, city: Optional[str] = None, store_id: Optional[int] = None
    ) -> List[OfferDict]: ...

    def get_hot_offers(
        self,
        city: Optional[str] = None,
        limit: int = 20,
        offset: int = 0,
        business_type: Optional[str] = None,
    ) -> List[Tuple[Any, ...]]: ...

    def count_hot_offers(
        self, city: Optional[str] = None, business_type: Optional[str] = None
    ) -> int: ...

    def get_offer(self, offer_id: int) -> Optional[Tuple[Any, ...]]: ...

    def get_store_offers(self, store_id: int) -> List[Tuple[Any, ...]]: ...

    def update_offer_quantity(self, offer_id: int, new_quantity: int) -> None: ...

    def increment_offer_quantity(self, offer_id: int, amount: int = 1) -> None: ...

    def increment_offer_quantity_atomic(self, offer_id: int, amount: int = 1) -> int: ...

    def deactivate_offer(self, offer_id: int) -> None: ...

    def activate_offer(self, offer_id: int) -> None: ...

    def update_offer_expiry(self, offer_id: int, new_expiry: str) -> None: ...

    def delete_offer(self, offer_id: int) -> bool: ...

    def delete_expired_offers(self) -> None: ...

    # ========== BOOKING METHODS ==========
    def create_booking(
        self,
        offer_id: int,
        user_id: int,
        booking_code: str,
        quantity: int = 1,
        pickup_time: Optional[str] = None,
        pickup_address: Optional[str] = None,
    ) -> int: ...

    def create_booking_atomic(
        self,
        offer_id: int,
        user_id: int,
        quantity: int = 1,
        pickup_time: Optional[str] = None,
        pickup_address: Optional[str] = None,
    ) -> Tuple[bool, Optional[int], Optional[str]]: ...

    def get_user_bookings(self, user_id: int) -> List[Tuple[Any, ...]]: ...

    def get_booking(self, booking_id: int) -> Optional[Tuple[Any, ...]]: ...

    def get_booking_by_code(self, booking_code: str) -> Optional[Tuple[Any, ...]]: ...

    def update_booking_status(self, booking_id: int, status: str) -> None: ...

    def complete_booking(self, booking_id: int) -> None: ...

    def cancel_booking(self, booking_id: int) -> None: ...

    def get_store_bookings(self, store_id: int) -> List[Tuple[Any, ...]]: ...

    def get_booking_history(
        self, user_id: int, limit: int = 50
    ) -> List[Tuple[Any, ...]]: ...

    # ========== ADMIN METHODS ==========
    def set_admin(self, user_id: int) -> None: ...

    def is_admin(self, user_id: int) -> bool: ...

    def get_all_admins(self) -> List[int]: ...

    def get_statistics(self) -> dict[str, Any]: ...

    # ========== FAVORITES METHODS ==========
    def get_favorites(self, user_id: int) -> List[Tuple[Any, ...]]: ...

    def add_to_favorites(self, user_id: int, store_id: int) -> None: ...

    def remove_from_favorites(self, user_id: int, store_id: int) -> None: ...

    def is_favorite(self, user_id: int, store_id: int) -> bool: ...

    # ========== NOTIFICATION METHODS ==========
    def add_notification(self, user_id: int, message: str) -> None: ...

    def toggle_notifications(self, user_id: int) -> bool: ...

    # ========== RATING METHODS ==========
    def add_rating(
        self,
        booking_id: int,
        user_id: int,
        store_id: int,
        rating: int,
        comment: Optional[str] = None,
    ) -> None: ...

    def get_store_ratings(self, store_id: int) -> List[Tuple[Any, ...]]: ...

    def get_store_rating_summary(self, store_id: int) -> Tuple[float, int]: ...

    # ========== PAYMENT METHODS ==========
    def get_platform_payment_card(self) -> Optional[str]: ...

    def set_platform_payment_card(self, card_number: str) -> None: ...

    # ======= BOOKING UTILITIES =======
    def set_booking_payment_proof(self, booking_id: int, file_id: str) -> bool: ...

    def mark_reminder_sent(self, booking_id: int) -> bool: ...

    # ======= ORDERS / DELIVERY =======
    def create_order(
        self,
        user_id: int,
        store_id: int,
        offer_id: int,
        quantity: int,
        order_type: str,
        delivery_address: Optional[str] = None,
        delivery_price: int = 0,
        payment_method: Optional[str] = None,
    ) -> Optional[int]: ...

    def update_payment_status(self, order_id: int, status: str, photo_id: Optional[str] = None) -> bool: ...

    def get_order(self, order_id: int) -> Optional[Tuple[Any, ...]]: ...

    # ======= UTILITIES =======
    def get_user_model(self, user_id: int) -> Optional[Any]: ...

    def get_connection(self) -> Any: ...
