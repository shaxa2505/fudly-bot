"""Typed structures for database entities to unify SQLite and PostgreSQL returns."""
from typing import TypedDict, Optional


class UserDict(TypedDict, total=False):
    """User record structure (unified dict format)."""
    user_id: int
    username: Optional[str]
    first_name: Optional[str]
    phone: Optional[str]
    city: str
    language: str
    role: str
    is_admin: int
    notifications_enabled: int
    created_at: str
    bonus_balance: float
    referral_code: Optional[str]


class StoreDict(TypedDict, total=False):
    """Store record structure."""
    store_id: int
    owner_id: int
    name: str
    city: str
    address: Optional[str]
    description: Optional[str]
    category: str
    phone: Optional[str]
    status: str
    rejection_reason: Optional[str]
    created_at: str
    business_type: Optional[str]
    delivery_enabled: int
    delivery_price: Optional[int]
    min_order_amount: Optional[int]


class OfferDict(TypedDict, total=False):
    """Offer record structure."""
    offer_id: int
    store_id: int
    title: str
    description: Optional[str]
    original_price: float
    discount_price: float
    quantity: int
    available_from: Optional[str]
    available_until: Optional[str]
    expiry_date: Optional[str]
    status: str
    photo: Optional[str]
    photo_id: Optional[str]
    created_at: str
    unit: Optional[str]
    category: Optional[str]


class BookingDict(TypedDict, total=False):
    """Booking record structure."""
    booking_id: int
    offer_id: int
    user_id: int
    store_id: Optional[int]
    status: str
    booking_code: Optional[str]
    pickup_time: Optional[str]
    quantity: int
    created_at: str
