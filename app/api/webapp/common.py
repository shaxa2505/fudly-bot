from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
from datetime import date, datetime
from typing import Any
from urllib.parse import parse_qsl, unquote

from fastapi import Header, HTTPException
from pydantic import BaseModel

from app.core.config import load_settings

logger = logging.getLogger(__name__)

settings = load_settings()
# Default to sums; DB now stores prices in sums (major units).
PRICE_STORAGE_UNIT = os.getenv("PRICE_STORAGE_UNIT", "sums").lower()


def normalize_price(value: Any) -> float:
    """Normalize stored price to sums for API responses."""
    try:
        amount = float(value or 0)
    except (TypeError, ValueError):
        return 0.0
    if PRICE_STORAGE_UNIT == "kopeks":
        return amount / 100
    return amount


# =============================================================================
# Helper Functions
# =============================================================================


def get_val(obj: Any, key: str, default: Any = None) -> Any:
    """Universal getter for dict or object attributes."""
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


def _get_offer_quantity(offer: Any) -> int | None:
    raw_qty = get_val(offer, "stock_quantity")
    if raw_qty is None:
        raw_qty = get_val(offer, "quantity")
    if raw_qty is None:
        return None
    try:
        return int(raw_qty)
    except (TypeError, ValueError):
        return None


def is_offer_active(offer: Any) -> bool:
    if not offer:
        return False

    status = get_val(offer, "status")
    if status and str(status).lower() != "active":
        return False

    qty = _get_offer_quantity(offer)
    if qty is not None and qty <= 0:
        return False

    expiry_date = _parse_offer_expiry_date(get_val(offer, "expiry_date"))
    if expiry_date and expiry_date < date.today():
        return False

    return True


# =============================================================================
# Pydantic Models & Constants
# =============================================================================


class OfferResponse(BaseModel):
    id: int
    title: str
    description: str | None = None
    original_price: float
    discount_price: float
    discount_percent: float
    quantity: int
    unit: str = "шт"
    category: str
    store_id: int
    store_name: str
    store_address: str | None = None
    delivery_enabled: bool = False
    delivery_price: float | None = None
    min_order_amount: float | None = None
    photo: str | None = None
    expiry_date: str | None = None


class OfferListResponse(BaseModel):
    items: list[OfferResponse]
    total: int | None = None
    offset: int
    limit: int
    has_more: bool
    next_offset: int | None = None


class StoreResponse(BaseModel):
    id: int
    name: str
    address: str | None = None
    city: str | None = None
    region: str | None = None
    district: str | None = None
    business_type: str
    rating: float = 0.0
    offers_count: int = 0
    delivery_enabled: bool = False
    delivery_price: float | None = None
    min_order_amount: float | None = None
    photo_url: str | None = None


class CategoryResponse(BaseModel):
    id: str
    name: str
    emoji: str
    count: int = 0


class OrderItem(BaseModel):
    offer_id: int
    quantity: int


class CreateOrderRequest(BaseModel):
    items: list[OrderItem]
    user_id: int | None = None
    delivery_address: str | None = None
    phone: str | None = None
    comment: str | None = None
    payment_method: str | None = None


class OrderResponse(BaseModel):
    order_id: int
    status: str
    total: float
    items_count: int


class FavoriteRequest(BaseModel):
    offer_id: int | None = None
    store_id: int | None = None


class CartItem(BaseModel):
    offer_id: int
    quantity: int
    title: str
    price: float
    photo: str | None = None


class CartResponse(BaseModel):
    items: list[CartItem]
    total: float
    items_count: int


class FilterParams(BaseModel):
    min_price: float | None = None
    max_price: float | None = None
    min_discount: float | None = None
    max_distance: float | None = None  # km
    sort_by: str = "discount"  # discount, price_asc, price_desc, new


class LocationRequest(BaseModel):
    latitude: float
    longitude: float


CATEGORIES = [
    {"id": "all", "name": "Все", "emoji": "🔥"},
    {"id": "dairy", "name": "Молочные", "emoji": "🥛"},
    {"id": "bakery", "name": "Выпечка", "emoji": "🍞"},
    {"id": "meat", "name": "Мясо", "emoji": "🥩"},
    {"id": "fruits", "name": "Фрукты", "emoji": "🍎"},
    {"id": "vegetables", "name": "Овощи", "emoji": "🥕"},
    {"id": "drinks", "name": "Напитки", "emoji": "🥤"},
    {"id": "sweets", "name": "Сладости", "emoji": "🍰"},
    {"id": "frozen", "name": "Заморозка", "emoji": "🧊"},
    {"id": "other", "name": "Другое", "emoji": "📦"},
]


# =============================================================================
# Telegram Init Data Validation
# =============================================================================


def validate_init_data(init_data: str, bot_token: str) -> dict[str, Any] | None:
    """Validate Telegram WebApp initData.

    https://core.telegram.org/bots/webapps#validating-data-received-via-the-mini-app
    """
    try:
        parsed = dict(parse_qsl(init_data, keep_blank_values=True))

        if "hash" not in parsed:
            return None

        received_hash = parsed.pop("hash")

        data_check_arr = sorted([f"{k}={v}" for k, v in parsed.items()])
        data_check_string = "\n".join(data_check_arr)

        secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()

        calculated_hash = hmac.new(
            secret_key, data_check_string.encode(), hashlib.sha256
        ).hexdigest()

        if calculated_hash != received_hash:
            logger.warning("Invalid initData hash")
            return None

        if "user" in parsed:
            parsed["user"] = json.loads(unquote(parsed["user"]))

        return parsed

    except Exception as e:  # pragma: no cover - defensive logging
        logger.error(f"Error validating initData: {e}")
        return None


async def get_current_user(
    x_telegram_init_data: str = Header(None, alias="X-Telegram-Init-Data"),
) -> dict[str, Any] | None:
    """Dependency to validate Telegram initData and extract user.

    Guest access only allowed in development mode.
    """
    if not x_telegram_init_data:
        if os.getenv("ALLOW_GUEST_ACCESS", "false").lower() in ("true", "1", "yes"):
            logger.warning("Guest access allowed - DEVELOPMENT MODE ONLY")
            return {"id": 0, "first_name": "Guest"}
        raise HTTPException(status_code=401, detail="Authentication required")

    bot_token = settings.bot_token
    validated = validate_init_data(x_telegram_init_data, bot_token)

    if not validated:
        raise HTTPException(status_code=401, detail="Invalid Telegram initData")

    return validated.get("user")


# =============================================================================
# Database dependency (will be injected from main app)
# =============================================================================

_db_instance: Any | None = None
_offer_service: Any | None = None

# Photo URL cache (file_id -> url)
_photo_cache: dict[str, str] = {}


def set_db_instance(db: Any, offer_service: Any | None = None) -> None:
    """Set database (and optional offer service) instance for API routes."""
    global _db_instance, _offer_service
    _db_instance = db
    _offer_service = offer_service


def get_db() -> Any:
    """Get database instance."""
    if _db_instance is None:
        raise HTTPException(status_code=500, detail="Database not initialized")
    return _db_instance


def get_offer_service() -> Any | None:
    """Get offer service instance if available."""
    return _offer_service


def get_photo_url_sync(file_id: str | None) -> str | None:
    """Convert Telegram file_id to photo URL (sync version for API).

    Telegram file_ids start with 'AgAC' for photos.
    If it's already a URL (http/https), return as-is.
    """
    if not file_id:
        return None

    if file_id.startswith(("http://", "https://")):
        return file_id

    if file_id in _photo_cache:
        return _photo_cache[file_id]

    try:
        bot_token = settings.bot_token
        if bot_token and file_id.startswith("AgAC"):
            # NOTE: Real Telegram URLs require getFile call; return None to let frontend fallback
            return None
    except Exception:  # pragma: no cover - defensive
        pass

    return None


__all__ = [
    "logger",
    "settings",
    "get_val",
    "is_offer_active",
    "OfferResponse",
    "OfferListResponse",
    "StoreResponse",
    "CategoryResponse",
    "OrderItem",
    "CreateOrderRequest",
    "OrderResponse",
    "FavoriteRequest",
    "CartItem",
    "CartResponse",
    "FilterParams",
    "LocationRequest",
    "CATEGORIES",
    "validate_init_data",
    "get_current_user",
    "set_db_instance",
    "get_db",
    "get_offer_service",
    "get_photo_url_sync",
    "_photo_cache",
]
