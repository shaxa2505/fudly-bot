"""Helpers for webhook server API formatting and Telegram file resolution."""
from __future__ import annotations

import os
from datetime import date, datetime
from typing import Any

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError

from logging_config import logger


# =============================================================================
# Mini App API Helpers
# =============================================================================


def _delivery_cash_enabled() -> bool:
    return os.getenv("FUDLY_DELIVERY_CASH_ENABLED", "0").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def get_offer_value(obj: Any, key: str, default: Any = None) -> Any:
    """Get value from dict or object."""
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _parse_offer_expiry_date(value: Any) -> date | None:
    if not value:
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, str):
        raw = value.strip()
        if not raw:
            return None
        try:
            return datetime.fromisoformat(raw.replace("Z", "+00:00")).date()
        except ValueError:
            pass
        try:
            return datetime.strptime(raw[:10], "%Y-%m-%d").date()
        except ValueError:
            pass
        try:
            return datetime.strptime(raw[:10], "%d.%m.%Y").date()
        except ValueError:
            pass
    return None


def _get_offer_quantity(offer: Any) -> float | None:
    raw_qty = get_offer_value(offer, "stock_quantity")
    if raw_qty is None:
        raw_qty = get_offer_value(offer, "quantity")
    if raw_qty is None:
        return None
    try:
        return float(raw_qty)
    except (TypeError, ValueError):
        return None


def _is_offer_active(offer: Any) -> bool:
    if not offer:
        return False

    status = get_offer_value(offer, "status")
    if status and str(status).lower() != "active":
        return False

    qty = _get_offer_quantity(offer)
    if qty is not None and qty <= 0:
        return False

    expiry_date = _parse_offer_expiry_date(get_offer_value(offer, "expiry_date"))
    if expiry_date and expiry_date < date.today():
        return False

    return True


# Cache for photo URLs (file_id -> URL)
_photo_url_cache: dict[str, str] = {}
_LEGACY_BOT_TOKEN = (
    os.getenv("LEGACY_TELEGRAM_BOT_TOKEN")
    or os.getenv("OLD_TELEGRAM_BOT_TOKEN")
    or os.getenv("PHOTO_FALLBACK_BOT_TOKEN")
)


async def get_photo_url(bot: Bot, file_id: str | None) -> str | None:
    """Convert Telegram file_id to photo URL."""
    if not file_id:
        return None

    # Check cache
    if file_id in _photo_url_cache:
        return _photo_url_cache[file_id]

    async def _try_get_url(token: str) -> str | None:
        temp_bot = bot if token == bot.token else Bot(token=token)
        try:
            file = await temp_bot.get_file(file_id)
            if file and file.file_path:
                url = f"https://api.telegram.org/file/bot{token}/{file.file_path}"
                _photo_url_cache[file_id] = url
                if token != bot.token:
                    logger.info("Photo resolved using legacy bot token")
                return url
        finally:
            # Do not close shared bot session
            if temp_bot is not bot:
                await temp_bot.session.close()
        return None

    try:
        url = await _try_get_url(bot.token)
        if url:
            return url
    except TelegramAPIError:
        pass
    except Exception:
        logger.debug("Primary bot failed to fetch photo_id %s", file_id, exc_info=True)

    if _LEGACY_BOT_TOKEN and _LEGACY_BOT_TOKEN != bot.token:
        try:
            return await _try_get_url(_LEGACY_BOT_TOKEN)
        except TelegramAPIError:
            logger.warning("Legacy bot token could not fetch photo_id %s", file_id)
        except Exception:
            logger.debug("Legacy bot fallback failed for %s", file_id, exc_info=True)

    return None


def offer_to_dict(offer: Any, photo_url: str | None = None) -> dict:
    """Convert offer to API response dict."""
    # Try offer_id first (PostgreSQL), then id (SQLite)
    offer_id = get_offer_value(offer, "offer_id", 0) or get_offer_value(offer, "id", 0)

    # Use provided photo_url, or fallback to photo field
    photo = photo_url or get_offer_value(offer, "photo")

    price_unit = os.getenv("PRICE_STORAGE_UNIT", "sums").lower()
    convert = (lambda v: float(v or 0) / 100) if price_unit == "kopeks" else (lambda v: float(v or 0))

    return {
        "id": offer_id,
        "title": get_offer_value(offer, "title", ""),
        "description": get_offer_value(offer, "description"),
        "original_price": convert(get_offer_value(offer, "original_price", 0)),
        "discount_price": convert(get_offer_value(offer, "discount_price", 0)),
        "discount_percent": float(get_offer_value(offer, "discount_percent", 0) or 0),
        "quantity": float(get_offer_value(offer, "quantity", 0) or 0),
        "category": get_offer_value(offer, "category", "other") or "other",
        "store_id": int(get_offer_value(offer, "store_id", 0) or 0),
        "store_name": get_offer_value(offer, "store_name", "") or "",
        "store_address": get_offer_value(offer, "store_address")
        or get_offer_value(offer, "address"),
        "delivery_enabled": bool(get_offer_value(offer, "delivery_enabled", False)),
        "delivery_price": convert(get_offer_value(offer, "delivery_price", 0) or 0),
        "min_order_amount": convert(get_offer_value(offer, "min_order_amount", 0) or 0),
        "photo": photo,
        "expiry_date": str(get_offer_value(offer, "expiry_date", ""))
        if get_offer_value(offer, "expiry_date")
        else None,
    }


def store_to_dict(store: Any, photo_url: str | None = None) -> dict:
    """Convert store to API response dict."""
    store_id = get_offer_value(store, "store_id", 0) or get_offer_value(store, "id", 0)

    # Get latitude/longitude safely
    lat = get_offer_value(store, "latitude")
    lng = get_offer_value(store, "longitude")

    return {
        "id": store_id,
        "name": get_offer_value(store, "name", ""),
        "address": get_offer_value(store, "address"),
        "city": get_offer_value(store, "city"),
        "business_type": get_offer_value(store, "business_type", "supermarket"),
        "rating": float(get_offer_value(store, "rating", 0) or 0),
        "offers_count": int(get_offer_value(store, "offers_count", 0) or 0),
        # Delivery settings
        "delivery_enabled": get_offer_value(store, "delivery_enabled", 1) == 1,
        "delivery_price": int(get_offer_value(store, "delivery_price", 0) or 0),
        "min_order_amount": int(get_offer_value(store, "min_order_amount", 0) or 0),
        # Photo
        "photo_url": photo_url,
        # Geolocation for map
        "latitude": float(lat) if lat else None,
        "longitude": float(lng) if lng else None,
    }


# Categories list
API_CATEGORIES = [
    {"id": "all", "name": "Все", "emoji": "🔥"},
    {"id": "dairy", "name": "Молочные", "emoji": "🥛"},
    {"id": "bakery", "name": "Выпечка", "emoji": "🍞"},
    {"id": "meat", "name": "Мясо", "emoji": "🥩"},
    {"id": "snacks", "name": "Снеки", "emoji": "🍿"},
    {"id": "drinks", "name": "Напитки", "emoji": "🥤"},
    {"id": "sweets", "name": "Сладости", "emoji": "🍰"},
    {"id": "frozen", "name": "Заморозка", "emoji": "🧊"},
    {"id": "other", "name": "Другое", "emoji": "📦"},
]

CATEGORY_ALIASES = {
    "sweets": ["sweets", "snacks"],
}

# Keep in sync with app/api/webapp/routes_offers.py
CATEGORY_SYNONYMS: dict[str, set[str]] = {
    "dairy": {
        "dairy",
        "sut",
        "sut mahsulotlari",
        "молочные",
        "молочные продукты",
    },
    "bakery": {
        "bakery",
        "non",
        "pishiriq",
        "выпечка",
        "хлеб",
    },
    "meat": {
        "meat",
        "go'sht",
        "go'sht mahsulotlari",
        "мясные",
        "мясо",
        "мясо и рыба",
        "рыба",
        "baliq",
    },
    "fruits": {
        "fruits",
        "meva",
        "mevalar",
        "фрукты",
    },
    "vegetables": {
        "vegetables",
        "sabzavot",
        "sabzavotlar",
        "овощи",
    },
    "drinks": {
        "drinks",
        "ichimlik",
        "ichimliklar",
        "напитки",
    },
    "sweets": {
        "sweets",
        "snacks",
        "сладости",
        "снеки",
        "shirinliklar",
        "gaz. ovqatlar",
        "gaz ovqatlar",
    },
    "frozen": {
        "frozen",
        "muzlatilgan",
        "замороженное",
        "заморозка",
    },
    "other": {
        "other",
        "boshqa",
        "другое",
        "ready_food",
        "tayyor ovqat",
        "готовая еда",
        "cheese",
        "pishloq",
        "сыры",
    },
}

_CATEGORY_CANONICAL: dict[str, str] = {}
for key, values in CATEGORY_SYNONYMS.items():
    for value in values:
        _CATEGORY_CANONICAL[value] = key
    _CATEGORY_CANONICAL[key] = key
for key, aliases in CATEGORY_ALIASES.items():
    for alias in aliases:
        _CATEGORY_CANONICAL.setdefault(alias, key)


def expand_category_filter(category: str | None) -> list[str] | None:
    if not category:
        return None
    normalized = str(category).strip().lower()
    if not normalized or normalized == "all":
        return None
    canonical = _CATEGORY_CANONICAL.get(normalized, normalized)
    values: set[str] = {canonical, normalized}
    values.update(CATEGORY_SYNONYMS.get(canonical, set()))
    for alias in CATEGORY_ALIASES.get(canonical, []):
        values.add(alias)
        values.update(CATEGORY_SYNONYMS.get(alias, set()))
    return sorted(values)
