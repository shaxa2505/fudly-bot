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
    "Toshkent": "Ташкент",
    "tashkent": "Ташкент",
    "samarqand": "Самарканд",
    "Samarqand": "Самарканд",
    "samarkand": "Самарканд",
    "buxoro": "Бухара",
    "Buxoro": "Бухара",
    "bukhara": "Бухара",
    "andijon": "Андижан",
    "Andijon": "Андижан",
    "namangan": "Наманган",
    "Namangan": "Наманган",
    "farg'ona": "Фергана",
    "fargona": "Фергана",
    "fergana": "Фергана",
    "xiva": "Хива",
    "khiva": "Хива",
    "nukus": "Нукус",
    "qarshi": "Карши",
    "qoqon": "Коканд",
    "kokand": "Коканд",
    "ташкент": "Ташкент",
    "самарканд": "Самарканд",
    "бухара": "Бухара",
    "андижан": "Андижан",
    "наманган": "Наманган",
    "фергана": "Фергана",
    "хива": "Хива",
    "нукус": "Нукус",
    "карши": "Карши",
    "коканд": "Коканд",
    "kattaqo'rg'on": "Каттакурган",
    "kattakurgan": "Каттакурган",
    "kattaqurgan": "Каттакурган",
    "каттакурган": "Каттакурган",
    "qashqadaryo": "Кашкадарья",
    "sirdaryo": "Сырдарья",
    "surxondaryo": "Сурхандарья",
    "xorazm": "Хорезм",
    "qoraqalpogiston": "Каракалпакстан",
    "qoraqalpog'iston": "Каракалпакстан",
    "кашкадарьинская": "Кашкадарья",
    "сурхандарьинская": "Сурхандарья",
    "сырдарьинская": "Сырдарья",
    "хорезмская": "Хорезм",
    "каракалпакская": "Каракалпакстан",
    "каракалпакстан": "Каракалпакстан",
    "самаркандская": "Самарканд",
    "бухарская": "Бухара",
    "ферганская": "Фергана",
    "андижанская": "Андижан",
    "наманганская": "Наманган",
    "навоийская": "Навои",
    "джизакская": "Джизак",
    "ташкентская": "Ташкент",
}

_CITY_MOJIBAKE_FIXES = {
    "\u0420\u045e\u0420\u00b0\u0421\u20ac\u0420\u0454\u0420\u00b5\u0420\u0405\u0421\u201a": "Ташкент",
    "\u0420\u040e\u0420\u00b0\u0420\u0458\u0420\u00b0\u0421\u0402\u0420\u0454\u0420\u00b0\u0420\u0405\u0420\u0491": "Самарканд",
    "\u0420\u2018\u0421\u0453\u0421\u2026\u0420\u00b0\u0421\u0402\u0420\u00b0": "Бухара",
    "\u0420\u0452\u0420\u0405\u0420\u0491\u0420\u0451\u0420\u00b6\u0420\u00b0\u0420\u0405": "Андижан",
    "\u0420\u045c\u0420\u00b0\u0420\u0458\u0420\u00b0\u0420\u0405\u0420\u0456\u0420\u00b0\u0420\u0405": "Наманган",
    "\u0420\u00a4\u0420\u00b5\u0421\u0402\u0420\u0456\u0420\u00b0\u0420\u0405\u0420\u00b0": "Фергана",
    "\u0420\u0490\u0420\u0451\u0420\u0406\u0420\u00b0": "Хива",
    "\u0420\u045c\u0421\u0453\u0420\u0454\u0421\u0453\u0421\u0403": "Нукус",
    "\u0420\u0459\u0420\u00b0\u0421\u0402\u0421\u20ac\u0420\u0451": "Карши",
    "\u0420\u0459\u0420\u0455\u0420\u0454\u0420\u00b0\u0420\u0405\u0420\u0491": "Коканд",
}

_CITY_SUFFIX_RE = re.compile(
    r"\s+(?:shahri|shahar|shahr|tumani|tuman|viloyati|viloyat|region|district|province|oblast|oblasti"
    r"|город|г\.|район|районы|область|области|обл\.|шахри|шахар|тумани|туман|вилояти|вилоят)\b",
    re.IGNORECASE,
)
_APOSTROPHE_RE = re.compile(r"[\u2018\u2019\u02BB\u02BC\u2032\u2035\u00B4\u0060]")


def _contains_cyrillic(text: str) -> bool:
    return any("\u0400" <= ch <= "\u04FF" for ch in text)


def _fix_mojibake_city(city: str) -> str:
    fixed = _CITY_MOJIBAKE_FIXES.get(city)
    if fixed:
        return fixed
    for encoding in ("cp1251", "latin1", "cp866"):
        try:
            candidate = city.encode(encoding).decode("utf-8")
        except UnicodeError:
            continue
        if _contains_cyrillic(candidate):
            return candidate
    return city


def get_uzb_time() -> datetime:
    """Return current datetime in Uzbek timezone."""
    return datetime.now(UZB_TZ)


def to_uzb_datetime(value: Any) -> datetime | None:
    """Normalize a datetime/string to UZB timezone, assuming naive values are UTC."""
    if not value:
        return None
    base_time: datetime | None = None
    if isinstance(value, datetime):
        base_time = value
    elif isinstance(value, str):
        raw = value.strip()
        if not raw:
            return None
        try:
            base_time = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except Exception:
            base_time = None
    if base_time is None:
        return None
    if base_time.tzinfo is None:
        base_time = base_time.replace(tzinfo=timezone.utc)
    return base_time.astimezone(UZB_TZ)


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
    if field_name in {"region", "district", "latitude", "longitude", "region_id", "district_id"}:
        if isinstance(user, (tuple, list)):
            if len(user) >= 17:
                tail_map = {
                    "region": -6,
                    "district": -5,
                    "latitude": -4,
                    "longitude": -3,
                    "region_id": -2,
                    "district_id": -1,
                }
                return user[tail_map[field_name]]
            if len(user) >= 15:
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
    if not isinstance(city, str):
        city = str(city)
    city_clean = " ".join(city.strip().split())
    city_clean = _APOSTROPHE_RE.sub("'", city_clean)
    city_clean = city_clean.split(",")[0]
    city_clean = re.sub(r"\s*\([^)]*\)", "", city_clean)
    city_clean = _CITY_SUFFIX_RE.sub("", city_clean).strip(" ,")
    city_clean = _fix_mojibake_city(city_clean)
    return CITY_UZ_TO_RU.get(city_clean.lower(), city_clean)


def calc_discount_percent(original_price: float, discount_price: float) -> int:
    """Calculate discount percent, avoiding float artifacts on integer boundaries."""
    if not original_price or original_price <= 0:
        return 0
    percent = ((original_price - discount_price) * 100) / original_price
    if percent <= 0:
        return 0
    # Guard against float rounding turning 20.0 into 19.999999...
    return int(percent + 1e-9)


