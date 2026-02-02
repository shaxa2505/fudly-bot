"""
Telegram Mini App Authentication Endpoint
Validates initData from Telegram WebApp and returns user profile
"""
import hashlib
import hmac
import json
import logging
import os
import time
from typing import Any
from urllib.parse import parse_qsl

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel

from app.core.config import load_settings
from app.core.async_db import AsyncDBProxy

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["auth"])
settings = load_settings()

# Global database instance (set by api_server.py)
_db_instance = None


def get_db():
    """Dependency to get database instance."""
    if _db_instance is None:
        raise HTTPException(status_code=503, detail="Database not available")
    return _db_instance


def set_auth_db(db):
    """Set database instance for auth module."""
    global _db_instance
    if db is None:
        _db_instance = None
        return
    if not isinstance(db, AsyncDBProxy):
        db = AsyncDBProxy(db)
    _db_instance = db


def _get_user_id(user: Any) -> int | None:
    return getattr(user, "telegram_id", None) or getattr(user, "user_id", None) or getattr(
        user, "id", None
    )


class AuthRequest(BaseModel):
    """Telegram WebApp initData for validation."""

    init_data: str


class UserProfile(BaseModel):
    """User profile response."""

    user_id: int
    username: str | None
    first_name: str
    last_name: str | None
    phone: str | None
    city: str | None
    language: str
    registered: bool
    notifications_enabled: bool


class NotificationSettingsRequest(BaseModel):
    """Notification settings request."""

    enabled: bool


class NotificationSettingsResponse(BaseModel):
    """Notification settings response."""

    enabled: bool


def validate_telegram_webapp_data(init_data: str, bot_token: str) -> dict[str, Any] | None:
    """
    Validate Telegram WebApp initData signature.

    Based on: https://core.telegram.org/bots/webapps#validating-data-received-via-the-mini-app

    Args:
        init_data: Raw initData from window.Telegram.WebApp.initData
        bot_token: Telegram Bot Token

    Returns:
        Parsed data if valid, None otherwise
    """
    try:
        # Parse query string
        parsed_data = dict(parse_qsl(init_data))

        if "hash" not in parsed_data:
            return None

        received_hash = parsed_data.pop("hash")

        # Create data-check-string
        data_check_arr = [f"{k}={v}" for k, v in sorted(parsed_data.items())]
        data_check_string = "\n".join(data_check_arr)

        # Compute secret key
        secret_key = hmac.new(
            key=b"WebAppData", msg=bot_token.encode(), digestmod=hashlib.sha256
        ).digest()

        # Compute hash
        computed_hash = hmac.new(
            key=secret_key, msg=data_check_string.encode(), digestmod=hashlib.sha256
        ).hexdigest()

        # Verify hash
        if computed_hash != received_hash:
            return None

        # Parse user data
        if "user" in parsed_data:
            parsed_data["user"] = json.loads(parsed_data["user"])

        return parsed_data

    except Exception as e:
        print(f"Error validating initData: {e}")
        return None


def _validate_auth_date(parsed_data: dict[str, Any]) -> None:
    auth_date = parsed_data.get("auth_date")
    if not auth_date:
        raise HTTPException(status_code=401, detail="Invalid authentication data")
    try:
        auth_timestamp = int(auth_date)
    except (TypeError, ValueError):
        raise HTTPException(status_code=401, detail="Invalid authentication data")
    current_timestamp = int(time.time())
    if auth_timestamp > current_timestamp:
        raise HTTPException(status_code=401, detail="Invalid authentication data")

    max_auth_age_raw = os.getenv("WEBAPP_AUTH_MAX_AGE_SECONDS", "86400")
    try:
        max_auth_age = int(max_auth_age_raw)
    except ValueError:
        max_auth_age = 86400
    if max_auth_age < 0:
        max_auth_age = 0
    if max_auth_age and (current_timestamp - auth_timestamp) > max_auth_age:
        raise HTTPException(status_code=401, detail="Authentication expired")


def _require_valid_init_data(init_data: str | None) -> dict[str, Any]:
    if not init_data:
        raise HTTPException(status_code=401, detail="Authentication required")
    validated_data = validate_telegram_webapp_data(init_data, settings.telegram_bot_token)
    if not validated_data or "user" not in validated_data:
        raise HTTPException(status_code=401, detail="Invalid authentication data")
    _validate_auth_date(validated_data)
    return validated_data


def _ensure_self_access(authenticated_user_id: int, target_user_id: int, scope: str) -> None:
    if authenticated_user_id != target_user_id:
        logger.warning(
            "IDOR attempt: user %s tried to access %s of user %s",
            authenticated_user_id,
            scope,
            target_user_id,
        )
        raise HTTPException(status_code=403, detail="Access denied")


def _get_authenticated_user_id(x_telegram_init_data: str | None) -> int:
    validated_data = _require_valid_init_data(x_telegram_init_data)
    user = validated_data.get("user") or {}
    user_id = user.get("id")
    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication required")
    return int(user_id)


async def _get_notifications_enabled(db, user_id: int) -> bool:
    user = None
    if hasattr(db, "get_user_model"):
        user = await db.get_user_model(user_id)
    elif hasattr(db, "get_user"):
        user = await db.get_user(user_id)
    if not user:
        return True
    if isinstance(user, dict):
        return bool(user.get("notifications_enabled", True))
    return bool(getattr(user, "notifications_enabled", True))


@router.post("/auth/validate", response_model=UserProfile)
async def validate_auth(request: AuthRequest, db=Depends(get_db)) -> UserProfile:
    """
    Validate Telegram WebApp authentication and return user profile.

    Usage from Mini App:
    ```javascript
    const initData = window.Telegram.WebApp.initData
    const response = await fetch('/api/v1/auth/validate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ init_data: initData })
    })
    ```
    """
    # Validate initData signature
    validated_data = validate_telegram_webapp_data(request.init_data, settings.telegram_bot_token)

    if not validated_data or "user" not in validated_data:
        raise HTTPException(status_code=401, detail="Invalid authentication data")
    _validate_auth_date(validated_data)

    telegram_user = validated_data["user"]
    user_id = telegram_user["id"]

    # Check if user exists in database
    user = await db.get_user_model(user_id)

    if not user:
        # User not registered yet
        return UserProfile(
            user_id=user_id,
            username=telegram_user.get("username"),
            first_name=telegram_user.get("first_name", ""),
            last_name=telegram_user.get("last_name"),
            phone=None,
            city=None,
            language=telegram_user.get("language_code", "ru"),
            registered=False,
            notifications_enabled=True,
        )

    # Return existing user profile
    return UserProfile(
        user_id=_get_user_id(user) or user_id,
        username=user.username,
        first_name=user.first_name or telegram_user.get("first_name", ""),
        last_name=getattr(user, "last_name", None) or telegram_user.get("last_name"),
        phone=user.phone,
        city=user.city,
        language=user.language or "ru",
        registered=bool(user.phone),  # Считаем зарегистрированным если есть телефон
        notifications_enabled=getattr(user, "notifications_enabled", True),
    )


@router.get("/user/profile", response_model=UserProfile)
async def get_profile(
    user_id: int | None = None,
    x_telegram_init_data: str = Header(None, alias="X-Telegram-Init-Data"),
    db=Depends(get_db),
) -> UserProfile:
    """Get user profile by ID. Requires authentication - user can only access their own profile."""
    authenticated_user_id = _get_authenticated_user_id(x_telegram_init_data)
    effective_user_id = user_id or authenticated_user_id
    if user_id is not None:
        _ensure_self_access(authenticated_user_id, user_id, "profile")

    user = await db.get_user_model(effective_user_id)

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    return UserProfile(
        user_id=_get_user_id(user) or effective_user_id,
        username=user.username,
        first_name=user.first_name or "",
        last_name=getattr(user, "last_name", None),
        phone=user.phone,
        city=user.city,
        language=user.language or "ru",
        registered=bool(user.phone),
        notifications_enabled=getattr(user, "notifications_enabled", True),
    )


@router.get("/user/notifications", response_model=NotificationSettingsResponse)
async def get_notifications(
    user_id: int | None = None,
    x_telegram_init_data: str = Header(None, alias="X-Telegram-Init-Data"),
    db=Depends(get_db),
) -> NotificationSettingsResponse:
    """Get notification settings for the authenticated user."""
    authenticated_user_id = _get_authenticated_user_id(x_telegram_init_data)
    effective_user_id = user_id or authenticated_user_id
    if user_id is not None:
        _ensure_self_access(authenticated_user_id, user_id, "notifications")
    return NotificationSettingsResponse(
        enabled=await _get_notifications_enabled(db, effective_user_id)
    )


@router.post("/user/notifications", response_model=NotificationSettingsResponse)
async def set_notifications(
    request: NotificationSettingsRequest,
    user_id: int | None = None,
    x_telegram_init_data: str = Header(None, alias="X-Telegram-Init-Data"),
    db=Depends(get_db),
) -> NotificationSettingsResponse:
    """Update notification settings for the authenticated user."""
    authenticated_user_id = _get_authenticated_user_id(x_telegram_init_data)
    effective_user_id = user_id or authenticated_user_id
    if user_id is not None:
        _ensure_self_access(authenticated_user_id, user_id, "notifications")
    current = await _get_notifications_enabled(db, effective_user_id)
    target = bool(request.enabled)
    if current != target and hasattr(db, "toggle_notifications"):
        await db.toggle_notifications(effective_user_id)
    return NotificationSettingsResponse(enabled=target)


# =============================================================================
# USER ORDERS / BOOKINGS
# =============================================================================


class BookingItem(BaseModel):
    """Single booking/order item."""

    booking_id: int
    offer_id: int
    offer_title: str
    offer_photo: str | None
    quantity: int
    total_price: int
    status: str
    store_name: str
    store_address: str | None
    booking_code: str | None
    created_at: str
    pickup_time: str | None


class OrdersHistoryResponse(BaseModel):
    """User's orders history."""

    orders: list[BookingItem]
    total_count: int
    active_count: int
    completed_count: int


@router.get("/user/orders", response_model=OrdersHistoryResponse)
async def get_user_orders(
    user_id: int | None = None,
    status: str | None = None,
    limit: int = 50,
    x_telegram_init_data: str = Header(None, alias="X-Telegram-Init-Data"),
    db=Depends(get_db),
) -> OrdersHistoryResponse:
    """
    Get user's order history. Requires authentication - user can only access their own orders.

    Args:
        user_id: Telegram user ID
        status: Filter by status (pending, confirmed, completed, cancelled)
        limit: Maximum number of orders to return
    """
    authenticated_user_id = _get_authenticated_user_id(x_telegram_init_data)
    effective_user_id = user_id or authenticated_user_id
    if user_id is not None:
        _ensure_self_access(authenticated_user_id, user_id, "orders")
    try:
        # Get all bookings
        if status:
            bookings = await db.get_user_bookings_by_status(effective_user_id, status)
        else:
            bookings = await db.get_user_bookings(effective_user_id)

        if not bookings:
            return OrdersHistoryResponse(
                orders=[], total_count=0, active_count=0, completed_count=0
            )

        # Convert to response format
        orders_list = []
        active_count = 0
        completed_count = 0

        for booking in bookings[:limit]:
            # Handle both dict and tuple formats
            if isinstance(booking, dict):
                booking_id = booking.get("booking_id")
                offer_id = booking.get("offer_id")
                quantity = booking.get("quantity", 1)
                total_price = booking.get("total_price", 0)
                booking_status = booking.get("status", "pending")
                booking_code = booking.get("booking_code")
                created_at = booking.get("created_at")
            else:
                # Tuple format: (booking_id, user_id, offer_id, status, quantity, total_price, code, created_at, ...)
                booking_id = booking[0]
                offer_id = booking[2]
                booking_status = booking[3]
                quantity = booking[4]
                total_price = booking[5]
                booking_code = booking[6] if len(booking) > 6 else None
                created_at = booking[7] if len(booking) > 7 else None

            # Get offer details
            offer = await db.get_offer(offer_id)
            if not offer:
                continue

            if isinstance(offer, dict):
                offer_title = offer.get("title", "Товар")
                offer_photo = offer.get("photo")
                store_id = offer.get("store_id")
            else:
                offer_title = offer[1] if len(offer) > 1 else "Товар"
                offer_photo = offer[7] if len(offer) > 7 else None
                store_id = offer[10] if len(offer) > 10 else None

            # Get store details
            store = await db.get_store(store_id) if store_id else None
            if store:
                if isinstance(store, dict):
                    store_name = store.get("name", "Магазин")
                    store_address = store.get("address")
                else:
                    store_name = store[1] if len(store) > 1 else "Магазин"
                    store_address = store[2] if len(store) > 2 else None
            else:
                store_name = "Магазин"
                store_address = None

            # Count statuses
            if booking_status in ("pending", "confirmed"):
                active_count += 1
            elif booking_status == "completed":
                completed_count += 1

            # Format created_at
            created_at_str = str(created_at) if created_at else None

            orders_list.append(
                BookingItem(
                    booking_id=booking_id,
                    offer_id=offer_id,
                    offer_title=offer_title,
                    offer_photo=offer_photo,
                    quantity=quantity,
                    total_price=int(total_price),
                    status=booking_status,
                    store_name=store_name,
                    store_address=store_address,
                    booking_code=booking_code,
                    created_at=created_at_str,
                    pickup_time=None,  # TODO: Add pickup time if needed
                )
            )

        return OrdersHistoryResponse(
            orders=orders_list,
            total_count=len(bookings),
            active_count=active_count,
            completed_count=completed_count,
        )

    except Exception as e:
        logger.error(f"Error getting user orders: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get orders: {str(e)}")


@router.get("/user/bookings", response_model=OrdersHistoryResponse)
async def get_user_bookings(
    user_id: int | None = None,
    status: str | None = None,
    limit: int = 50,
    x_telegram_init_data: str = Header(None, alias="X-Telegram-Init-Data"),
    db=Depends(get_db),
) -> OrdersHistoryResponse:
    """Alias for bookings history (compatibility)."""
    return await get_user_orders(user_id, status, limit, x_telegram_init_data, db)
