"""
SQLAlchemy models for Alembic migrations.

These models define the database schema and are used by Alembic
to generate and apply migrations.
"""
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    """Base class for all models."""

    pass


class GeoRegion(Base):
    """Geo region model."""

    __tablename__ = "geo_regions"

    region_id = Column(Integer, primary_key=True, autoincrement=True)
    name_ru = Column(Text, nullable=False)
    name_uz = Column(Text, nullable=False)
    slug_ru = Column(Text, nullable=False, unique=True)
    slug_uz = Column(Text, nullable=False, unique=True)
    is_city = Column(Integer, default=0)

    districts = relationship("GeoDistrict", back_populates="region")


class GeoDistrict(Base):
    """Geo district model."""

    __tablename__ = "geo_districts"

    district_id = Column(Integer, primary_key=True, autoincrement=True)
    region_id = Column(Integer, ForeignKey("geo_regions.region_id"), nullable=False)
    name_ru = Column(Text, nullable=False)
    name_uz = Column(Text, nullable=False)
    slug_ru = Column(Text, nullable=False)
    slug_uz = Column(Text, nullable=False)

    region = relationship("GeoRegion", back_populates="districts")

    __table_args__ = (
        UniqueConstraint("region_id", "slug_ru"),
        UniqueConstraint("region_id", "slug_uz"),
        Index("ix_geo_districts_region_id", "region_id"),
    )


class User(Base):
    """User model."""

    __tablename__ = "users"

    user_id = Column(BigInteger, primary_key=True)
    username = Column(String(255), nullable=True)
    first_name = Column(String(255), nullable=True)
    phone = Column(String(50), nullable=True)
    city = Column(String(100), default="Ташкент")
    language = Column(String(10), default="ru")
    role = Column(String(20), default="customer")
    is_admin = Column(Integer, default=0)
    notifications_enabled = Column(Integer, default=1)
    created_at = Column(DateTime, default=datetime.utcnow)
    region_id = Column(Integer, ForeignKey("geo_regions.region_id"), nullable=True)
    district_id = Column(Integer, ForeignKey("geo_districts.district_id"), nullable=True)

    # Relationships
    stores = relationship("Store", back_populates="owner")
    bookings = relationship("Booking", back_populates="user")
    orders = relationship("Order", back_populates="user")
    favorites = relationship("Favorite", back_populates="user")
    notifications = relationship("Notification", back_populates="user")
    ratings = relationship("Rating", back_populates="user")

    # Indexes
    __table_args__ = (
        Index("ix_users_city", "city"),
        Index("ix_users_role", "role"),
        Index("ix_users_phone", "phone"),
        Index("ix_users_region_id", "region_id"),
        Index("ix_users_district_id", "district_id"),
    )


class Store(Base):
    """Store model."""

    __tablename__ = "stores"

    store_id = Column(Integer, primary_key=True, autoincrement=True)
    owner_id = Column(BigInteger, ForeignKey("users.user_id"), nullable=True)
    name = Column(String(255), nullable=False)
    city = Column(String(100), nullable=False)
    city_slug = Column(String(120), nullable=True)
    region = Column(String(100), nullable=True)
    region_slug = Column(String(120), nullable=True)
    district = Column(String(100), nullable=True)
    district_slug = Column(String(120), nullable=True)
    address = Column(Text, nullable=True)
    description = Column(Text, nullable=True)
    category = Column(String(100), default="Ресторан")
    phone = Column(String(50), nullable=True)
    status = Column(String(20), default="pending")
    rejection_reason = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    business_type = Column(String(50), default="supermarket")
    delivery_enabled = Column(Integer, default=1)
    delivery_price = Column(Integer, default=15000)
    min_order_amount = Column(Integer, default=30000)
    region_id = Column(Integer, ForeignKey("geo_regions.region_id"), nullable=True)
    district_id = Column(Integer, ForeignKey("geo_districts.district_id"), nullable=True)

    # Relationships
    owner = relationship("User", back_populates="stores")
    offers = relationship("Offer", back_populates="store")
    bookings = relationship("Booking", back_populates="store")
    orders = relationship("Order", back_populates="store")
    payment_settings = relationship("PaymentSettings", back_populates="store", uselist=False)
    ratings = relationship("Rating", back_populates="store")
    favorites = relationship("Favorite", back_populates="store")

    # Indexes
    __table_args__ = (
        Index("ix_stores_city", "city"),
        Index("ix_stores_status", "status"),
        Index("ix_stores_owner", "owner_id"),
        Index("ix_stores_region_id", "region_id"),
        Index("ix_stores_district_id", "district_id"),
    )


class Offer(Base):
    """Offer model."""

    __tablename__ = "offers"

    offer_id = Column(Integer, primary_key=True, autoincrement=True)
    store_id = Column(Integer, ForeignKey("stores.store_id"), nullable=True)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    original_price = Column(Float, nullable=True)
    discount_price = Column(Float, nullable=True)
    quantity = Column(Integer, default=1)
    available_from = Column(String(50), nullable=True)
    available_until = Column(String(50), nullable=True)
    expiry_date = Column(String(50), nullable=True)
    photo_id = Column(String(255), nullable=True)
    status = Column(String(20), default="active")
    created_at = Column(DateTime, default=datetime.utcnow)
    unit = Column(String(20), default="шт")
    category = Column(String(50), default="other")

    # Relationships
    store = relationship("Store", back_populates="offers")
    bookings = relationship("Booking", back_populates="offer")
    orders = relationship("Order", back_populates="offer")

    # Indexes
    __table_args__ = (
        Index("ix_offers_store", "store_id"),
        Index("ix_offers_status", "status"),
        Index("ix_offers_category", "category"),
    )


class Booking(Base):
    """Booking model."""

    __tablename__ = "bookings"

    booking_id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, ForeignKey("users.user_id"), nullable=True)
    offer_id = Column(Integer, ForeignKey("offers.offer_id"), nullable=True)
    store_id = Column(Integer, ForeignKey("stores.store_id"), nullable=True)
    quantity = Column(Integer, default=1)
    booking_code = Column(String(50), nullable=True)
    pickup_time = Column(String(50), nullable=True)
    status = Column(String(20), default="active")
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    user = relationship("User", back_populates="bookings")
    offer = relationship("Offer", back_populates="bookings")
    store = relationship("Store", back_populates="bookings")
    rating = relationship("Rating", back_populates="booking", uselist=False)

    # Indexes
    __table_args__ = (
        Index("ix_bookings_user", "user_id"),
        Index("ix_bookings_store", "store_id"),
        Index("ix_bookings_status", "status"),
        Index("ix_bookings_code", "booking_code"),
    )


class Order(Base):
    """Order model (for delivery)."""

    __tablename__ = "orders"

    order_id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, ForeignKey("users.user_id"), nullable=True)
    offer_id = Column(Integer, ForeignKey("offers.offer_id"), nullable=True)
    store_id = Column(Integer, ForeignKey("stores.store_id"), nullable=True)
    delivery_address = Column(Text, nullable=True)
    payment_method = Column(String(50), default="card")
    payment_status = Column(String(20), default="pending")
    payment_proof_photo_id = Column(String(255), nullable=True)
    order_status = Column(String(20), default="pending")
    quantity = Column(Integer, default=1)
    total_price = Column(Float, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    user = relationship("User", back_populates="orders")
    offer = relationship("Offer", back_populates="orders")
    store = relationship("Store", back_populates="orders")
    rating = relationship("Rating", back_populates="order", uselist=False)
    promo_usages = relationship("PromoUsage", back_populates="order")

    # Indexes
    __table_args__ = (
        Index("ix_orders_user", "user_id"),
        Index("ix_orders_store", "store_id"),
        Index("ix_orders_status", "order_status"),
    )


class PaymentSettings(Base):
    """Payment settings for stores."""

    __tablename__ = "payment_settings"

    store_id = Column(Integer, ForeignKey("stores.store_id"), primary_key=True)
    card_number = Column(String(50), nullable=True)
    card_holder = Column(String(255), nullable=True)
    card_expiry = Column(String(10), nullable=True)
    payment_instructions = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    store = relationship("Store", back_populates="payment_settings")


class Notification(Base):
    """Notification model."""

    __tablename__ = "notifications"

    notification_id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, ForeignKey("users.user_id"), nullable=True)
    type = Column(String(50), nullable=True)
    title = Column(String(255), nullable=True)
    message = Column(Text, nullable=True)
    is_read = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    user = relationship("User", back_populates="notifications")

    # Indexes
    __table_args__ = (
        Index("ix_notifications_user", "user_id"),
        Index("ix_notifications_read", "is_read"),
    )


class Rating(Base):
    """Rating model."""

    __tablename__ = "ratings"

    rating_id = Column(Integer, primary_key=True, autoincrement=True)
    booking_id = Column(Integer, ForeignKey("bookings.booking_id"), nullable=True)
    user_id = Column(BigInteger, ForeignKey("users.user_id"), nullable=True)
    store_id = Column(Integer, ForeignKey("stores.store_id"), nullable=True)
    order_id = Column(Integer, ForeignKey("orders.order_id"), nullable=True)
    rating = Column(Integer, nullable=True)
    comment = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    booking = relationship("Booking", back_populates="rating")
    user = relationship("User", back_populates="ratings")
    store = relationship("Store", back_populates="ratings")
    order = relationship("Order", back_populates="rating")

    # Constraints and indexes
    __table_args__ = (
        CheckConstraint("rating >= 1 AND rating <= 5", name="check_rating_range"),
        Index("ix_ratings_store", "store_id"),
        Index("ix_ratings_user", "user_id"),
    )


class Favorite(Base):
    """Favorites model."""

    __tablename__ = "favorites"

    favorite_id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, ForeignKey("users.user_id"), nullable=True)
    store_id = Column(Integer, ForeignKey("stores.store_id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    user = relationship("User", back_populates="favorites")
    store = relationship("Store", back_populates="favorites")

    # Constraints
    __table_args__ = (UniqueConstraint("user_id", "store_id", name="uq_favorites_user_store"),)


class Promocode(Base):
    """Promocode model."""

    __tablename__ = "promocodes"

    promo_id = Column(Integer, primary_key=True, autoincrement=True)
    code = Column(String(50), unique=True, nullable=False)
    discount_percent = Column(Integer, nullable=True)
    discount_amount = Column(Float, nullable=True)
    max_uses = Column(Integer, default=0)
    current_uses = Column(Integer, default=0)
    valid_from = Column(DateTime, nullable=True)
    valid_until = Column(DateTime, nullable=True)
    is_active = Column(Integer, default=1)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    usages = relationship("PromoUsage", back_populates="promocode")

    # Indexes
    __table_args__ = (
        Index("ix_promocodes_code", "code"),
        Index("ix_promocodes_active", "is_active"),
    )


class PromoUsage(Base):
    """Promo usage tracking."""

    __tablename__ = "promo_usage"

    usage_id = Column(Integer, primary_key=True, autoincrement=True)
    promo_id = Column(Integer, ForeignKey("promocodes.promo_id"), nullable=True)
    user_id = Column(BigInteger, ForeignKey("users.user_id"), nullable=True)
    order_id = Column(Integer, ForeignKey("orders.order_id"), nullable=True)
    used_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    promocode = relationship("Promocode", back_populates="usages")
    order = relationship("Order", back_populates="promo_usages")


class Referral(Base):
    """Referral model."""

    __tablename__ = "referrals"

    referral_id = Column(Integer, primary_key=True, autoincrement=True)
    referrer_user_id = Column(BigInteger, ForeignKey("users.user_id"), nullable=True)
    referred_user_id = Column(BigInteger, ForeignKey("users.user_id"), nullable=True)
    bonus_amount = Column(Float, default=0)
    status = Column(String(20), default="pending")
    created_at = Column(DateTime, default=datetime.utcnow)

    # Indexes
    __table_args__ = (
        Index("ix_referrals_referrer", "referrer_user_id"),
        Index("ix_referrals_referred", "referred_user_id"),
    )


class FSMState(Base):
    """FSM state storage."""

    __tablename__ = "fsm_states"

    user_id = Column(BigInteger, primary_key=True)
    state = Column(String(255), nullable=True)
    data = Column(JSONB, nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow)


class PlatformSettings(Base):
    """Platform-wide settings."""

    __tablename__ = "platform_settings"

    key = Column(String(100), primary_key=True)
    value = Column(Text, nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow)


class PickupSlot(Base):
    """Pickup time slots."""

    __tablename__ = "pickup_slots"

    slot_id = Column(Integer, primary_key=True, autoincrement=True)
    store_id = Column(Integer, ForeignKey("stores.store_id"), nullable=True)
    day_of_week = Column(Integer, nullable=True)  # 0=Monday, 6=Sunday
    start_time = Column(String(10), nullable=True)
    end_time = Column(String(10), nullable=True)
    max_bookings = Column(Integer, default=10)
    is_active = Column(Integer, default=1)

    # Indexes
    __table_args__ = (Index("ix_pickup_slots_store", "store_id"),)
