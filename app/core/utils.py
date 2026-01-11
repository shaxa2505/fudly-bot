"""Shared helper utilities reused across handlers and services."""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime, timedelta, timezone
import re
from typing import Any

# Узбекская временная зона (UTC+5)
UZB_TZ = timezone(timedelta(hours=5))

# Словарь для преобразования узбекских названий городов в русские
CITY_UZ_TO_RU = {
    "toshkent": "Ташкент",
    "tashkent": "Ташкент",
    "samarqand": "Самарканд",
    "samarkand": "Самарканд",
    "buxoro": "Бухара",
    "bukhara": "Бухара",
    "andijon": "Андижан",
    "namangan": "Наманган",
    "farg'ona": "Фергана",
    "fargona": "Фергана",
    "fergana": "Фергана",
    "xiva": "Хива",
    "khiva": "Хива",
    "nukus": "Нукус",
    "qarshi": "Карши",
    "qoqon": "Коканд",
    "kokand": "Коканд",
}

_CITY_SUFFIX_RE = re.compile(
    r"\s+(?:shahri|shahar|shahr|tumani|tuman|viloyati|viloyat|region|district|province|oblast|oblasti"
    r"|город|район|область|шахри|шахар|тумани|туман|вилояти)\b",
    re.IGNORECASE,
)


def get_uzb_time() -> datetime:
    """Return current datetime in Uzbek timezone."""
    return datetime.now(UZB_TZ)


def get_user_field(user: Any, field_name: str, default: Any = None) -> Any:
    """Safely extract field from user (dict or tuple)."""
    if not user:
        return default

    # Try dict-like access first (works for dict and HybridRow)
    try:
        return user[field_name]
    except (KeyError, TypeError, IndexError):
        pass

    if isinstance(user, Mapping):
        return user.get(field_name, default)

    # Tuple indexing: 0=id, 1=lang, 2=name, 3=phone, 4=city, 5=created_at, 6=role, 7=store_id, 8=notif
    field_map = {
        "id": 0,
        "language": 1,
        "name": 2,
        "phone": 3,
        "city": 4,
        "created_at": 5,
        "role": 6,
        "store_id": 7,
        "notifications_enabled": 8,
    }
    idx = field_map.get(field_name)
    if idx is not None and isinstance(user, (tuple, list)) and len(user) > idx:
        return user[idx]
    if field_name in {"region", "district", "latitude", "longitude"}:
        if isinstance(user, (tuple, list)) and len(user) >= 15:
            tail_map = {"region": -4, "district": -3, "latitude": -2, "longitude": -1}
            return user[tail_map[field_name]]
    return default


def get_field(obj: Any, field_name_or_index: Any, default: Any = None) -> Any:
    """Universal helper: safely get field from dict or tuple by name or index."""
    if not obj:
        return default
    if isinstance(obj, Mapping):
        if isinstance(field_name_or_index, int):
            values = list(obj.values())
            return values[field_name_or_index] if field_name_or_index < len(values) else default
        return obj.get(field_name_or_index, default)
    try:
        if isinstance(field_name_or_index, int):
            return obj[field_name_or_index] if len(obj) > field_name_or_index else default
        return default
    except (IndexError, TypeError, KeyError):
        return default


def db_get(data: Any, key: str, index: int | None = None) -> Any:
    """Universal accessor for dict (PostgreSQL) or tuple (SQLite)."""
    if data is None:
        return None
    if isinstance(data, Mapping):
        return data.get(key)
    if isinstance(data, Sequence) and index is not None:
        return data[index] if len(data) > index else None
    return None


def get_store_field(store: Any, field_name: str, default: Any = None) -> Any:
    """Safely extract field from store (dict or tuple)."""
    if not store:
        return default
    if isinstance(store, Mapping):
        return store.get(field_name, default)
    field_map = {
        "store_id": 0,
        "owner_id": 1,
        "name": 2,
        "city": 3,
        "address": 4,
        "description": 5,
        "category": 6,
        "phone": 7,
        "status": 8,
        "rejection_reason": 9,
        "created_at": 10,
        "business_type": 11,
        "delivery_enabled": 12,
        "delivery_price": 13,
        "min_order_amount": 14,
    }
    idx = field_map.get(field_name)
    if idx is not None and len(store) > idx:
        return store[idx]
    return default


def get_offer_field(offer: Any, field_name: str, default: Any = None) -> Any:
    """Safely extract field from offer (dict or tuple)."""
    if not offer:
        return default
    if isinstance(offer, Mapping):
        return offer.get(field_name, default)
    field_map = {
        "offer_id": 0,
        "store_id": 1,
        "title": 2,
        "description": 3,
        "original_price": 4,
        "discount_price": 5,
        "quantity": 6,
        "available_from": 7,
        "available_until": 8,
        "expiry_date": 9,
        "status": 10,
        "photo": 11,
        "created_at": 12,
        "unit": 13,
        "category": 14,
    }
    idx = field_map.get(field_name)
    if idx is not None and len(offer) > idx:
        return offer[idx]
    return default


def get_booking_field(booking: Any, field_name: str, default: Any = None) -> Any:
    """Safely extract field from booking (dict or tuple)."""
    if not booking:
        return default

    # Try dict-like access first
    try:
        return booking[field_name]
    except (KeyError, TypeError, IndexError):
        pass

    if isinstance(booking, Mapping):
        return booking.get(field_name, default)

    field_map = {
        "booking_id": 0,
        "offer_id": 1,
        "user_id": 2,
        "store_id": 3,
        "pickup_address": 4,
        "status": 5,
        "quantity": 6,
        "total_price": 7,
        "code": 8,
        "booking_code": 8,
        "created_at": 9,
        "completed_at": 10,
        "cancelled_at": 11,
    }
    idx = field_map.get(field_name)
    if idx is not None and isinstance(booking, (tuple, list)) and len(booking) > idx:
        return booking[idx]
    return default


def get_order_field(order: Any, field_name: str, default: Any = None) -> Any:
    """Safely extract field from order (dict or tuple)."""
    if not order:
        return default

    # Try dict-like access first
    try:
        return order[field_name]
    except (KeyError, TypeError, IndexError):
        pass

    if isinstance(order, Mapping):
        return order.get(field_name, default)

    field_map = {
        "order_id": 0,
        "user_id": 1,
        "store_id": 2,
        "offer_id": 3,
        "quantity": 4,
        "total_price": 5,
        "order_type": 6,
        "delivery_address": 7,
        "delivery_price": 8,
        "payment_method": 9,
        "order_status": 10,
        "payment_status": 11,
        "created_at": 12,
    }
    idx = field_map.get(field_name)
    if idx is not None and isinstance(order, (tuple, list)) and len(order) > idx:
        return order[idx]
    return default


def normalize_city(city: str) -> str:
    """Convert Uzbek/English city names to the Russian form used in DB."""
    if not city:
        return city
    city_clean = " ".join(city.strip().split())
    city_clean = city_clean.split(",")[0]
    city_clean = re.sub(r"\s*\([^)]*\)", "", city_clean)
    city_clean = _CITY_SUFFIX_RE.sub("", city_clean).strip(" ,")
    return CITY_UZ_TO_RU.get(city_clean.lower(), city_clean)

