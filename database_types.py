"""Typed structures for database entities to unify SQLite and PostgreSQL returns."""
from typing import TypedDict


class UserDict(TypedDict, total=False):
    """User record structure (unified dict format)."""

    user_id: int
    username: str | None
    first_name: str | None
    phone: str | None
    city: str
    language: str
    role: str
    is_admin: int
    notifications_enabled: int
    created_at: str
    bonus_balance: float
    referral_code: str | None


class StoreDict(TypedDict, total=False):
    """Store record structure."""

    store_id: int
    owner_id: int
    name: str
    city: str
    address: str | None
    description: str | None
    category: str
    phone: str | None
    status: str
    rejection_reason: str | None
    created_at: str
    business_type: str | None
    delivery_enabled: int
    delivery_price: int | None
    min_order_amount: int | None


class OfferDict(TypedDict, total=False):
    """Offer record structure."""

    offer_id: int
    store_id: int
    title: str
    description: str | None
    original_price: float
    discount_price: float
    quantity: int
    available_from: str | None
    available_until: str | None
    expiry_date: str | None
    status: str
    photo: str | None
    photo_id: str | None
    created_at: str
    unit: str | None
    category: str | None


class BookingDict(TypedDict, total=False):
    """Booking record structure."""

    booking_id: int
    offer_id: int
    user_id: int
    store_id: int | None
    status: str
    booking_code: str | None
    pickup_time: str | None
    quantity: int
    created_at: str
