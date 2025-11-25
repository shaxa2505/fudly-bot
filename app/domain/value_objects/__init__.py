"""Value Objects for domain model."""
from __future__ import annotations

from enum import Enum
from typing import Literal


class Language(str, Enum):
    """Supported languages."""

    RUSSIAN = "ru"
    UZBEK = "uz"


class City(str, Enum):
    """Cities in Uzbekistan."""

    TASHKENT_RU = "Ташкент"
    SAMARKAND_RU = "Самарканд"
    BUKHARA_RU = "Бухара"
    ANDIJAN_RU = "Андижан"
    NAMANGAN_RU = "Наманган"
    FERGANA_RU = "Фергана"
    KHIVA_RU = "Хива"
    NUKUS_RU = "Нукус"

    TASHKENT_UZ = "Toshkent"
    SAMARKAND_UZ = "Samarqand"
    BUKHARA_UZ = "Buxoro"
    ANDIJAN_UZ = "Andijon"
    NAMANGAN_UZ = "Namangan"
    FERGANA_UZ = "Farg'ona"
    KHIVA_UZ = "Xiva"
    NUKUS_UZ = "Nukus"

    @classmethod
    def normalize(cls, city: str) -> str:
        """Normalize city name to standard form."""
        city_clean = city.replace("📍 ", "").strip()
        # Try to find matching enum value
        for item in cls:
            if item.value == city_clean:
                return item.value
        return city_clean


class UserRole(str, Enum):
    """User roles."""

    CUSTOMER = "customer"
    SELLER = "seller"
    ADMIN = "admin"


class StoreStatus(str, Enum):
    """Store approval status."""

    PENDING = "pending"
    ACTIVE = "active"
    REJECTED = "rejected"


class BookingStatus(str, Enum):
    """Booking status."""

    PENDING = "pending"
    CONFIRMED = "confirmed"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class OrderStatus(str, Enum):
    """Order status."""

    PENDING = "pending"
    PAID = "paid"
    CONFIRMED = "confirmed"
    DELIVERING = "delivering"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class BusinessCategory(str, Enum):
    """Business categories."""

    RESTAURANT = "restaurant"
    CAFE = "cafe"
    BAKERY = "bakery"
    SUPERMARKET = "supermarket"
    CONFECTIONERY = "confectionery"
    FASTFOOD = "fastfood"
    PHARMACY = "pharmacy"


ProductUnit = Literal["шт", "кг", "г", "л", "мл", "упак", "м", "см"]
