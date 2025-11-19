"""Shared helper utilities reused across handlers and services."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Mapping, MutableMapping, Sequence

# Узбекская временная зона (UTC+5)
UZB_TZ = timezone(timedelta(hours=5))

# Словарь для преобразования узбекских названий городов в русские
CITY_UZ_TO_RU = {
    "Toshkent": "Ташкент",
    "Samarqand": "Самарканд",
    "Buxoro": "Бухара",
    "Andijon": "Андижан",
    "Namangan": "Наманган",
    "Farg'ona": "Фергана",
    "Xiva": "Хива",
    "Nukus": "Нукус",
}


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



def normalize_city(city: str) -> str:
    """Convert Uzbek city name to Russian representation used in DB."""
    return CITY_UZ_TO_RU.get(city, city)
