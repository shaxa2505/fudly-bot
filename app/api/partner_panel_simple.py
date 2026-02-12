"""
Partner Panel API endpoints for Telegram Mini App
Simplified version using Database class with raw SQL
"""
import csv
import hashlib
import hmac
import io
import os
import re
import urllib.parse
from datetime import datetime, timedelta, time as dt_time
import json
from typing import Optional

import pytz
from fastapi import (
    APIRouter,
    File,
    Form,
    Header,
    HTTPException,
    Query,
    Request,
    UploadFile,
    WebSocket,
    WebSocketDisconnect,
)

from app.core.async_db import AsyncDBProxy
from app.core.sanitize import sanitize_phone
from app.core.security import validator
from app.core.utils import normalize_city
from app.domain.offer_rules import MIN_OFFER_DISCOUNT_MESSAGE, validate_offer_prices
from database_pg_module.mixins.offers import canonicalize_geo_slug
from app.api.websocket_manager import get_connection_manager
from app.services.stats import PartnerTotals, Period, get_partner_stats
from aiogram import Bot

from app.services.unified_order_service import (
    OrderStatus,
    PaymentStatus,
    get_unified_order_service,
    init_unified_order_service,
)
from database_protocol import DatabaseProtocol
from app.api.rate_limit import limiter
from app.core.ws_tokens import issue_ws_token

router = APIRouter(tags=["partner-panel"])

# Global database instance (set by api_server.py)
_db: DatabaseProtocol | None = None
_bot_token: str | None = None
_legacy_bot_token: str | None = (
    os.getenv("LEGACY_TELEGRAM_BOT_TOKEN")
    or os.getenv("OLD_TELEGRAM_BOT_TOKEN")
    or os.getenv("PHOTO_FALLBACK_BOT_TOKEN")
)

# Get base URL for photo links
API_BASE_URL = os.getenv("RAILWAY_PUBLIC_DOMAIN") or os.getenv("PUBLIC_URL") or ""
if API_BASE_URL and not API_BASE_URL.startswith("http"):
    API_BASE_URL = f"https://{API_BASE_URL}"
elif not API_BASE_URL:
    # Fallback for local development
    API_BASE_URL = "http://localhost:8000"


def _is_dev_env() -> bool:
    return os.getenv("ENVIRONMENT", "production").lower() in ("development", "dev", "local", "test")


def set_partner_db(db: DatabaseProtocol, bot_token: str = None):
    """Set database instance and bot token for partner panel."""
    global _db, _bot_token
    if db is None:
        _db = None
    else:
        if not isinstance(db, AsyncDBProxy):
            db = AsyncDBProxy(db)
        _db = db
    if bot_token:
        _bot_token = bot_token
    elif not _bot_token:
        _bot_token = os.getenv("BOT_TOKEN")


def get_db() -> DatabaseProtocol:
    """Get database instance."""
    if _db is None:
        raise HTTPException(status_code=500, detail="Database not configured")
    return _db


def _ensure_unified_service(db: DatabaseProtocol):
    """Return initialized UnifiedOrderService if possible."""
    service = get_unified_order_service()
    if service is not None:
        return service
    if not _bot_token:
        return None
    try:
        sync_db = db.sync if hasattr(db, "sync") else db
        return init_unified_order_service(sync_db, Bot(_bot_token))
    except Exception:
        return None


async def get_partner_with_store(telegram_id: int) -> tuple[dict, dict]:
    """
    Get user and their store by telegram_id.
    A partner is defined by having a store (owned or admin access), not by role in users table.
    Returns (user, store) tuple.
    Raises HTTPException if user doesn't have a store.

    Note: In DB schema, users.user_id IS the telegram_id (Primary Key).
    stores.owner_id is FK to users.user_id, so it also contains telegram_id.
    """
    import logging

    db = get_db()
    if _is_dev_env():
        logging.debug(f"get_partner_with_store called for telegram_id={telegram_id}")

    user = await db.get_user(telegram_id)

    if not user:
        logging.error(f"❌ User not found: telegram_id={telegram_id}")
        raise HTTPException(status_code=403, detail="User not found")

    # users.user_id = telegram_id, stores.owner_id = users.user_id = telegram_id
    store = await db.get_store_by_owner(telegram_id)

    if not store and hasattr(db, "get_user_accessible_stores"):
        stores = await db.get_user_accessible_stores(telegram_id)
        if stores:
            store = next(
                (
                    s
                    for s in stores
                    if isinstance(s, dict) and s.get("status") in ("active", "approved")
                ),
                None,
            )
            if store is None:
                store = stores[0]

    if not store:
        logging.error(f"❌ No store found for telegram_id={telegram_id}")
        raise HTTPException(status_code=403, detail="Not a partner - no store found")

    if _is_dev_env():
        store_id_val = None
        if isinstance(store, dict):
            store_id_val = store.get("store_id")
        elif isinstance(store, (tuple, list)) and store:
            store_id_val = store[0]
        logging.debug(
            f"Partner resolved: user_id={user.get('user_id')}, store_id={store_id_val}"
        )
    return user, store


async def _load_json_payload(request: Request) -> dict:
    """Return JSON payload when content-type is application/json."""
    content_type = (request.headers.get("content-type") or "").lower()
    if "application/json" not in content_type:
        return {}
    try:
        payload = await request.json()
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid JSON body: {exc}") from exc
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Invalid JSON body: expected object")
    return payload


def _maybe_int(value: object, field: str) -> int | None:
    """Coerce numeric input to int with a useful error message."""
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=f"Invalid {field} value") from exc


def _to_kopeks(price_in_sums: int | float | None) -> int | None:
    """
    Normalize price from UI (sums) to DB storage (also sums).
    Returns None if input is None.
    """
    if price_in_sums is None:
        return None
    try:
        return int(round(float(price_in_sums)))
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail="Invalid price value") from exc


def _to_sums(price_in_kopeks: int | float | None) -> int:
    """Normalize price from DB to sums for API responses."""
    if price_in_kopeks is None:
        return 0
    try:
        return int(round(float(price_in_kopeks)))
    except (TypeError, ValueError):
        return 0


def _status_transition_error(unified_service: Any | None) -> str:
    if unified_service and hasattr(unified_service, "get_last_status_error"):
        reason = unified_service.get_last_status_error()
        if reason:
            return str(reason)
    return "Status transition not allowed"


DEFAULT_WORKING_HOURS = "08:00 - 23:00"

def _parse_time_value(value: object) -> dt_time | None:
    if not value:
        return None
    if isinstance(value, dt_time):
        return value
    if isinstance(value, datetime):
        return value.time()
    if isinstance(value, str):
        raw = value.strip()
        if not raw:
            return None
        if "T" in raw:
            raw = raw.split("T", 1)[1]
        raw = raw[:8]
        for fmt in ("%H:%M:%S", "%H:%M"):
            try:
                return datetime.strptime(raw, fmt).time()
            except ValueError:
                continue
    return None


def _parse_time_range(value: object) -> tuple[dt_time | None, dt_time | None]:
    if not value:
        return None, None
    match = re.search(r"(\d{1,2}:\d{2}).*(\d{1,2}:\d{2})", str(value))
    if not match:
        return None, None
    start = _parse_time_value(match.group(1))
    end = _parse_time_value(match.group(2))
    return start, end


def _format_time_value(value: object) -> str | None:
    parsed = _parse_time_value(value)
    if not parsed:
        return None
    return parsed.strftime("%H:%M")


def _normalize_working_hours(value: object) -> str | None:
    start, end = _parse_time_range(value)
    if not start or not end:
        return None
    return f"{start.strftime('%H:%M')} - {end.strftime('%H:%M')}"


def _resolve_store_hours(store: dict) -> tuple[dt_time, dt_time, str]:
    raw = store.get("working_hours")
    normalized = _normalize_working_hours(raw) if raw else None
    if not normalized:
        normalized = DEFAULT_WORKING_HOURS
    start, end = _parse_time_range(normalized)
    if not start or not end:
        start = _parse_time_value("08:00") or datetime.strptime("08:00", "%H:%M").time()
        end = _parse_time_value("23:00") or datetime.strptime("23:00", "%H:%M").time()
        normalized = DEFAULT_WORKING_HOURS
    return start, end, normalized


def verify_telegram_webapp(authorization: str) -> int:
    """
    Verify Telegram WebApp auth and return telegram_id.
    Only accepts signed initData (Telegram WebApp).
    """
    import logging

    if not authorization:
        logging.warning("Missing authorization header")
        raise HTTPException(status_code=401, detail="Missing authorization")

    if not authorization.startswith("tma "):
        raise HTTPException(status_code=401, detail="Invalid authorization format")

    init_data = authorization[4:]
    # Try injected token first, then BOT_TOKEN, fallback to TELEGRAM_BOT_TOKEN
    bot_token = _bot_token or os.getenv("BOT_TOKEN") or os.getenv("TELEGRAM_BOT_TOKEN")
    if not bot_token:
        raise HTTPException(status_code=500, detail="Bot token not configured")

    try:
        parsed = dict(urllib.parse.parse_qsl(init_data))

        if "hash" not in parsed:
            raise HTTPException(status_code=401, detail="Missing signature hash")

        # ✅ SECURITY: Verify auth_date is not too old (prevent replay attacks)
        auth_date = parsed.get("auth_date")
        if not auth_date:
            raise HTTPException(status_code=401, detail="Invalid auth_date format")
        try:
            auth_timestamp = int(auth_date)
            current_timestamp = int(datetime.now().timestamp())
            age_seconds = current_timestamp - auth_timestamp

            # Allow auth data up to a configurable age (default 24 hours; override via env).
            max_auth_age_raw = os.getenv("PARTNER_PANEL_AUTH_MAX_AGE_SECONDS", "86400")
            try:
                max_auth_age = int(max_auth_age_raw)
            except (TypeError, ValueError):
                max_auth_age = 86400
                logging.warning(
                    "⚠️ Invalid PARTNER_PANEL_AUTH_MAX_AGE_SECONDS value. "
                    "Falling back to 86400 seconds."
                )
            if max_auth_age < 0:
                max_auth_age = 0
            if 0 < max_auth_age < 86400:
                logging.warning(
                    "⚠️ PARTNER_PANEL_AUTH_MAX_AGE_SECONDS below minimum (24h). "
                    "Clamping to 86400 seconds."
                )
                max_auth_age = 86400
            if age_seconds > max_auth_age:
                logging.warning(
                    f"⚠️ Auth data too old: {age_seconds}s (max {max_auth_age}s)"
                )
                raise HTTPException(
                    status_code=401,
                    detail=f"Auth data expired (age: {age_seconds // 3600}h)",
                )
            elif age_seconds < 0:
                logging.warning(f"⚠️ Auth data from future: {age_seconds}s")
                raise HTTPException(status_code=401, detail="Invalid auth timestamp")

            logging.info(f"✅ Auth age valid: {age_seconds}s old")
        except ValueError:
            logging.error(f"❌ Invalid auth_date format: {auth_date}")
            raise HTTPException(status_code=401, detail="Invalid auth_date format")

        # ✅ SECURITY: Verify HMAC-SHA256 signature
        data_check_string_parts = []

        for key in sorted(parsed.keys()):
            if key != "hash":
                data_check_string_parts.append(f"{key}={parsed[key]}")

        data_check_string = "\n".join(data_check_string_parts)
        secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
        calculated_hash = hmac.new(
            secret_key, data_check_string.encode(), hashlib.sha256
        ).hexdigest()

        received_hash = parsed.get("hash", "")
        if not hmac.compare_digest(calculated_hash, str(received_hash)):
            logging.error(
                f"❌ Signature mismatch: calculated={calculated_hash[:16]}... received={received_hash[:16]}..."
            )
            raise HTTPException(status_code=401, detail="Invalid signature")

        logging.info("✅ Signature verified successfully")

        import json

        user_data = json.loads(parsed.get("user", "{}"))
        user_id = int(user_data.get("id", 0))

        if user_id <= 0:
            raise HTTPException(status_code=401, detail="Invalid user ID in token")

        return user_id
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"❌ Auth verification failed: {str(e)}")
        raise HTTPException(status_code=401, detail=f"Auth failed: {str(e)}")


# Profile endpoint
@router.get("/profile")
@limiter.limit("120/minute")
async def get_profile(request: Request, authorization: str = Header(None)):
    """Get partner profile"""
    import logging

    if _is_dev_env():
        logging.debug("Profile request")

    telegram_id = verify_telegram_webapp(authorization)
    logging.info(f"✅ Auth verified, telegram_id: {telegram_id}")

    user, store_info = await get_partner_with_store(telegram_id)
    logging.info(f"✅ Got partner with store: {store_info.get('name') if store_info else 'None'}")

    user_city = normalize_city(user.get("city") or "Toshkent")

    return {
        "name": user.get("first_name") or user.get("username") or "Partner",
        "city": user_city,
        "store": {
            "name": store_info.get("name"),
            "address": store_info.get("address"),
            "phone": store_info.get("phone"),
            "description": store_info.get("description"),
            "store_id": store_info.get("store_id"),
            "status": store_info.get("status"),
            "is_open": store_info.get("status") in ("approved", "active", "open"),
        }
        if store_info
        else None,
    }


@router.post("/ws-token")
@limiter.limit("60/minute")
async def create_ws_token(request: Request, authorization: str = Header(None)):
    """Issue short-lived WebSocket token for partner panel."""
    telegram_id = verify_telegram_webapp(authorization)
    token, ttl = await issue_ws_token(telegram_id)
    return {"token": token, "expires_in": ttl}


# ============================================
# WEBSOCKET - Real-time notifications
# ============================================


@router.websocket("/ws/partner/{store_id}")
async def websocket_partner(
    websocket: WebSocket, store_id: int, authorization: str | None = Query(None)
):
    """
    WebSocket endpoint for real-time partner notifications.

    Messages sent to partner:
    - {"type": "new_order", "data": {...}}
    - {"type": "order_status_changed", "data": {"order_id": 123, "status": "preparing"}}
    - {"type": "order_cancelled", "data": {"order_id": 123, "reason": "..."}}

    Usage (frontend):
        const ws = new WebSocket('wss://api.example.com/api/partner/ws/partner/123');
        ws.onmessage = (event) => {
            const data = JSON.parse(event.data);
            if (data.type === 'new_order') {
                // Show notification, reload orders
            }
        };
    """
    import logging

    logging.info(f"🔌 WebSocket connection attempt for store {store_id}")

    manager = get_connection_manager()
    try:
        if not authorization:
            await websocket.accept()
            await websocket.close(code=1008)
            return
        telegram_id = verify_telegram_webapp(authorization)
        _, store = await get_partner_with_store(telegram_id)
        if int(store.get("store_id", 0) or 0) != int(store_id):
            await websocket.accept()
            await websocket.close(code=1008)
            return
    except Exception as e:
        logging.warning(f"WebSocket auth failed for store {store_id}: {e}")
        try:
            await websocket.accept()
            await websocket.close(code=1008)
        finally:
            return

    try:
        await manager.connect(store_id, websocket)
        logging.info(f"✅ WebSocket connected: store_id={store_id}")

        # Send connection confirmation
        await websocket.send_json(
            {
                "type": "connected",
                "data": {"store_id": store_id, "timestamp": datetime.now().isoformat()},
            }
        )

        # Keep connection alive and handle ping/pong
        while True:
            try:
                # Wait for client messages (ping/pong)
                data = await websocket.receive_text()

                # Handle ping
                if data == "ping":
                    await websocket.send_json({"type": "pong"})

            except WebSocketDisconnect:
                logging.info(f"🔌 Client disconnected: store_id={store_id}")
                break
            except Exception as e:
                logging.error(f"❌ WebSocket error for store {store_id}: {e}")
                break

    finally:
        manager.disconnect(store_id, websocket)
        logging.info(f"🔌 WebSocket closed: store_id={store_id}")


# Store info endpoint (для frontend storeAPI.getInfo())
@router.get("/store")
@limiter.limit("120/minute")
async def get_store_info(request: Request, authorization: str = Header(None)):
    """Get store information for partner panel"""
    telegram_id = verify_telegram_webapp(authorization)
    user, store = await get_partner_with_store(telegram_id)

    # Prices stored in sums (PRICE_STORAGE_UNIT = 'sums' by default)
    delivery_price = int(store.get("delivery_price") or 0)
    min_order_amount = int(store.get("min_order_amount") or 0)

    return {
        "store_id": store.get("store_id"),
        "name": store.get("name"),
        "address": store.get("address"),
        "region": store.get("region"),
        "district": store.get("district"),
        "phone": store.get("phone"),
        "description": store.get("description"),
        "status": store.get("status"),
        "is_open": store.get("status") in ("approved", "active", "open"),
        "working_hours": _normalize_working_hours(store.get("working_hours"))
        or DEFAULT_WORKING_HOURS,
        "delivery_enabled": bool(store.get("delivery_enabled")),
        "delivery_price": delivery_price,
        "min_order_amount": min_order_amount,
        "min_order": min_order_amount,
        "delivery_cost": delivery_price,
    }


# Products endpoints
@router.get("/products")
@limiter.limit("120/minute")
async def list_products(
    request: Request,
    authorization: str = Header(None),
    status: Optional[str] = None,
):
    """
    List partner's products with frontend-compatible field names.

    Returns prices in sums for display.
    Maps DB fields to frontend expectations: offer_id→id, title→name, quantity→stock, etc.
    """
    telegram_id = verify_telegram_webapp(authorization)
    user, store = await get_partner_with_store(telegram_id)
    db = get_db()

    # Partner panel: show ALL products (including out-of-stock and expired)
    offers = await db.get_offers_by_store(store["store_id"], include_all=True)

    # Filter by status if provided
    if status and status != "all":
        offers = [o for o in offers if o.get("status") == status]

    # Map to frontend-expected format
    products = []
    for o in offers:
        # Prices stored in sums; use as-is for UI
        discount_price = _to_sums(o.get("discount_price"))
        original_price = _to_sums(o.get("original_price")) if o.get("original_price") is not None else None

        stock_quantity = o.get("stock_quantity")
        if stock_quantity is None:
            stock_quantity = o["quantity"]

        status = o.get("status")
        if not status:
            status = "out_of_stock" if stock_quantity == 0 else "active"

        # Build photo URL if photo_id exists
        photo_url = None
        if o.get("photo_id"):
            photo_url = f"{API_BASE_URL}/api/partner/photo/{o['photo_id']}"

        available_from = _format_time_value(o.get("available_from"))
        available_until = _format_time_value(o.get("available_until"))

        product = {
            "id": o["offer_id"],  # Frontend expects 'id'
            "name": o["title"],  # Frontend expects 'name'
            "title": o["title"],  # Keep for compatibility
            "description": o.get("description") or "",
            "category": o.get("category") or "other",
            # Frontend expects 'price' as main price
            "price": discount_price,
            "discount_price": discount_price,  # Keep for compatibility
            "original_price": original_price,
            # Frontend expects 'stock'
            "stock": stock_quantity,
            "quantity": stock_quantity,  # Keep for compatibility
            "stock_quantity": stock_quantity,
            "unit": o.get("unit") or "шт",
            "expiry_date": str(o.get("expiry_date")) if o.get("expiry_date") else None,
            "photo_id": o.get("photo_id"),
            "photo_url": photo_url,
            "image": photo_url or "https://via.placeholder.com/120?text=No+Photo",
            "status": status,
            "is_active": status == "active",
            "available_from": available_from,
            "available_until": available_until,
        }
        products.append(product)

    return products


@router.post("/products")
@limiter.limit("5/minute")
async def create_product(
    request: Request,
    authorization: str = Header(None),
    title: Optional[str] = Form(None),
    category: Optional[str] = Form(None),
    original_price: Optional[int] = Form(None),  # In SUMS
    discount_price: Optional[int] = Form(None),  # In SUMS
    quantity: Optional[int] = Form(None),
    stock_quantity: Optional[int] = Form(None),  # NEW: Stock quantity (v22.0)
    unit: Optional[str] = Form(None),
    available_from: Optional[str] = Form(None),
    available_until: Optional[str] = Form(None),
    expiry_date: Optional[str] = Form(None),
    description: Optional[str] = Form(None),
    photo_id: Optional[str] = Form(None),
):
    """
    Create new product with unified schema.

    Prices are accepted in sums (user-friendly) and stored as-is.
    Times default to store working hours unless overridden.
    Validation happens via Pydantic models.

    v22.0: Added stock_quantity support.
    """
    import logging
    from datetime import datetime, timedelta

    from app.domain.models import OfferCreate

    logger = logging.getLogger(__name__)
    logger.info(f"📦 Create product - received prices: original={original_price}, discount={discount_price}")

    telegram_id = verify_telegram_webapp(authorization)
    user, store = await get_partner_with_store(telegram_id)
    db = get_db()

    payload = await _load_json_payload(request)
    title = title or payload.get("title") or payload.get("name")
    category = category or payload.get("category") or "other"
    original_price = _maybe_int(
        original_price if original_price is not None else payload.get("original_price")
        or payload.get("price"),
        "original_price",
    )
    discount_price = _maybe_int(
        discount_price if discount_price is not None else payload.get("discount_price"),
        "discount_price",
    )
    payload_quantity = payload.get("quantity")
    if payload_quantity is None:
        payload_quantity = payload.get("stock")
    quantity = _maybe_int(quantity if quantity is not None else payload_quantity, "quantity")
    stock_quantity = _maybe_int(
        stock_quantity if stock_quantity is not None else payload.get("stock_quantity"),
        "stock_quantity",
    )
    unit = unit or payload.get("unit") or "шт"
    available_from = available_from or payload.get("available_from")
    available_until = available_until or payload.get("available_until")
    expiry_date = expiry_date or payload.get("expiry_date")
    description = description or payload.get("description")
    photo_id = photo_id or payload.get("photo_id")

    if not title or original_price is None or quantity is None:
        raise HTTPException(
            status_code=400,
            detail="Missing required fields: title, original_price, quantity",
        )

    if discount_price is None:
        raise HTTPException(status_code=400, detail="discount_price is required")

    try:
        validate_offer_prices(original_price, discount_price, require_both=True)
    except ValueError as exc:
        message = str(exc)
        if "Минимальная скидка" in message:
            message = MIN_OFFER_DISCOUNT_MESSAGE
        raise HTTPException(status_code=400, detail=message) from exc

    # Normalize prices from UI input
    original_price = _to_kopeks(original_price)
    discount_price = _to_kopeks(discount_price)

    # Use stock_quantity if provided, otherwise use quantity
    actual_stock = stock_quantity if stock_quantity is not None else quantity

    # Prepare times (default from store working hours)
    now = datetime.now()
    parsed_from = _parse_time_value(available_from)
    parsed_until = _parse_time_value(available_until)
    if not parsed_from or not parsed_until:
        parsed_from, parsed_until, _ = _resolve_store_hours(store)

    # Parse expiry date (Pydantic will validate format)
    if expiry_date:
        try:
            expiry_dt = datetime.fromisoformat(expiry_date)
            expiry = expiry_dt.date()
        except ValueError:
            # Try alternative formats
            try:
                expiry_dt = datetime.strptime(expiry_date, "%d.%m.%Y")
                expiry = expiry_dt.date()
            except ValueError:
                raise HTTPException(
                    status_code=400, detail=f"Invalid expiry_date format: {expiry_date}"
                )
    else:
        # Default: 7 days from now
        expiry = (now + timedelta(days=7)).date()

    try:
        # Validate with Pydantic model (prices in sums, normalize_price handles conversion)
        offer_data = OfferCreate(
            store_id=store["store_id"],
            title=title,
            description=description or title,
            original_price=original_price,
            discount_price=discount_price,
            quantity=quantity,
            available_from=parsed_from,
            available_until=parsed_until,
            expiry_date=expiry,
            unit=unit,
            category=category,
            photo_id=photo_id,
        )

        # Save to database (Pydantic ensures correct types)
        offer_id = await db.add_offer(
            store_id=offer_data.store_id,
            title=offer_data.title,
            description=offer_data.description,
            original_price=offer_data.original_price,
            discount_price=offer_data.discount_price,
            quantity=offer_data.quantity,
            stock_quantity=actual_stock,  # NEW: v22.0 field
            available_from=offer_data.available_from.isoformat(),
            available_until=offer_data.available_until.isoformat(),
            expiry_date=offer_data.expiry_date.isoformat(),
            unit=offer_data.unit,
            category=offer_data.category,
            photo_id=offer_data.photo_id,
        )

        return {"offer_id": offer_id, "status": "created"}

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.put("/products/{product_id}")
@router.patch("/products/{product_id}")  # Add PATCH support for frontend compatibility
@limiter.limit("10/minute")
async def update_product(
    product_id: int,
    request: Request,
    authorization: str = Header(None),
    title: Optional[str] = Form(None),
    category: Optional[str] = Form(None),
    original_price: Optional[int] = Form(None),  # In SUMS
    discount_price: Optional[int] = Form(None),  # In SUMS
    quantity: Optional[int] = Form(None),
    stock_quantity: Optional[int] = Form(None),  # NEW: v22.0
    unit: Optional[str] = Form(None),
    available_from: Optional[str] = Form(None),
    available_until: Optional[str] = Form(None),
    expiry_date: Optional[str] = Form(None),
    description: Optional[str] = Form(None),
    photo_id: Optional[str] = Form(None),
    status: Optional[str] = Form(None),
):
    """
    Update product (supports partial updates for quick actions).
    Accepts both PUT and PATCH methods.

    Prices accepted in sums and stored as-is.

    v22.0: Added stock_quantity support.
    """
    import logging

    logging.info(
        f"📦 Update product {product_id}: quantity={quantity}, title={title}, status={status}"
    )

    telegram_id = verify_telegram_webapp(authorization)
    user, store = await get_partner_with_store(telegram_id)
    db = get_db()

    # Verify ownership
    offer = await db.get_offer(product_id)
    if not offer or offer.get("store_id") != store["store_id"]:
        raise HTTPException(status_code=404, detail="Product not found")

    payload = await _load_json_payload(request)
    if title is None:
        title = payload.get("title") or payload.get("name")
    if category is None:
        category = payload.get("category")
    if original_price is None:
        original_price = _maybe_int(payload.get("original_price"), "original_price")
    if discount_price is None:
        discount_price = _maybe_int(payload.get("discount_price"), "discount_price")
    if quantity is None:
        payload_quantity = payload.get("quantity")
        if payload_quantity is None:
            payload_quantity = payload.get("stock")
        quantity = _maybe_int(payload_quantity, "quantity")
    if stock_quantity is None:
        stock_quantity = _maybe_int(payload.get("stock_quantity"), "stock_quantity")
    if unit is None:
        unit = payload.get("unit")
    if available_from is None:
        available_from = payload.get("available_from")
    if available_until is None:
        available_until = payload.get("available_until")
    if expiry_date is None:
        expiry_date = payload.get("expiry_date")
    if description is None:
        description = payload.get("description")
    if photo_id is None:
        photo_id = payload.get("photo_id")
    if status is None:
        status = payload.get("status")

    if original_price is not None or discount_price is not None:
        current_original = (
            original_price if original_price is not None else offer.get("original_price")
        )
        current_discount = (
            discount_price if discount_price is not None else offer.get("discount_price")
        )
        try:
            validate_offer_prices(current_original, current_discount, require_both=True)
        except ValueError as exc:
            message = str(exc)
            if "Минимальная скидка" in message:
                message = MIN_OFFER_DISCOUNT_MESSAGE
            raise HTTPException(status_code=400, detail=message) from exc

    # Normalize prices from UI input
    if original_price is not None:
        original_price = _to_kopeks(original_price)
    if discount_price is not None:
        discount_price = _to_kopeks(discount_price)

    parsed_from_iso: str | None = None
    parsed_until_iso: str | None = None

    if available_from is not None or available_until is not None:
        current_from = available_from if available_from is not None else offer.get("available_from")
        current_until = available_until if available_until is not None else offer.get("available_until")
        parsed_from = _parse_time_value(current_from)
        parsed_until = _parse_time_value(current_until)
        if not parsed_from or not parsed_until:
            raise HTTPException(
                status_code=400, detail="Invalid available_from/available_until values"
            )
        parsed_from_iso = parsed_from.isoformat()
        parsed_until_iso = parsed_until.isoformat()

    if quantity is not None:
        # Auto-update status based on quantity (sync with frontend)
        if quantity <= 0 and status is None:
            status = "out_of_stock"
        elif quantity > 0 and status is None:
            # Restore to active if was out_of_stock
            current_offer = await db.get_offer(product_id)
            if current_offer and current_offer.get("status") == "out_of_stock":
                status = "active"

    expiry_iso: str | None = None
    if expiry_date is not None:
        if expiry_date:
            try:
                expiry_iso = datetime.fromisoformat(expiry_date).date().isoformat()
            except ValueError:
                raise HTTPException(status_code=400, detail="Invalid expiry_date format")

    has_updates = any(
        value is not None
        for value in (
            title,
            category,
            original_price,
            discount_price,
            quantity,
            stock_quantity,
            unit,
            description,
            photo_id,
            status,
            parsed_from_iso,
            parsed_until_iso,
            expiry_date,
        )
    )
    if not has_updates:
        raise HTTPException(status_code=400, detail="No fields to update")

    try:
        updated = await db.update_offer(
            offer_id=product_id,
            title=title,
            description=description,
            original_price=original_price,
            discount_price=discount_price,
            quantity=quantity,
            available_from=parsed_from_iso,
            available_until=parsed_until_iso,
            expiry_date=expiry_iso if expiry_date is not None else None,
            unit=unit,
            category=category,
            stock_quantity=stock_quantity,
            status=status,
            photo_id=photo_id,
        )
    except ValueError as exc:
        message = str(exc)
        if "Минимальная скидка" in message:
            message = MIN_OFFER_DISCOUNT_MESSAGE
        raise HTTPException(status_code=400, detail=message) from exc

    if not updated:
        raise HTTPException(status_code=400, detail="No fields to update")

    return {"offer_id": product_id, "status": "updated"}


@router.patch("/products/{product_id}/status")
@limiter.limit("120/minute")
async def update_product_status(
    product_id: int, request: Request, authorization: str = Header(None)
):
    """Update product status (toggle active/hidden)"""
    telegram_id = verify_telegram_webapp(authorization)
    user, store = await get_partner_with_store(telegram_id)
    db = get_db()

    # Parse request body
    try:
        body = await request.json()
        new_status = body.get("status")
        if not new_status:
            raise HTTPException(status_code=400, detail="Missing 'status' field")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid request body: {e}")

    # Verify ownership
    offer = await db.get_offer(product_id)
    if not offer or offer.get("store_id") != store["store_id"]:
        raise HTTPException(status_code=404, detail="Product not found")

    # Update status
    await db.execute(
        "UPDATE offers SET status = %s WHERE offer_id = %s", (new_status, product_id)
    )

    return {"offer_id": product_id, "status": new_status}


@router.delete("/products/{product_id}")
@limiter.limit("120/minute")
async def delete_product(product_id: int, request: Request, authorization: str = Header(None)):
    """Delete product (soft delete)"""
    telegram_id = verify_telegram_webapp(authorization)
    user, store = await get_partner_with_store(telegram_id)
    db = get_db()

    # Verify ownership
    offer = await db.get_offer(product_id)
    if not offer or offer["store_id"] != store["store_id"]:
        raise HTTPException(status_code=404, detail="Product not found")

    # Soft delete
    await db.deactivate_offer(product_id)

    return {"offer_id": product_id, "status": "deleted"}


@router.post("/orders/{order_id}/cancel")
@limiter.limit("10/minute")
async def cancel_order(
    order_id: int,
    request: Request,
    authorization: str = Header(None),
):
    """
    Cancel order with reason (v22.0).

    Valid reasons:
    - out_of_stock: Товар закончился
    - cant_fulfill: Не могу выполнить
    - customer_request: По просьбе клиента
    - technical_issue: Технические проблемы
    - other: Другая причина
    """
    telegram_id = verify_telegram_webapp(authorization)
    user, store = await get_partner_with_store(telegram_id)
    db = get_db()

    # Parse request body
    try:
        body = await request.json()
        cancel_reason = body.get("reason")
        cancel_comment = body.get("comment", "")

        if not cancel_reason:
            raise HTTPException(status_code=400, detail="Missing 'reason' field")

        # Validate reason
        valid_reasons = [
            "out_of_stock",
            "cant_fulfill",
            "customer_request",
            "technical_issue",
            "other",
        ]
        if cancel_reason not in valid_reasons:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid reason. Must be one of: {', '.join(valid_reasons)}",
            )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid request body: {e}")

    # Get order and verify ownership
    order_rows = await db.execute(
        """
        SELECT o.order_id, o.user_id, o.order_status, o.store_id,
               o.payment_method, o.payment_status, o.payment_proof_photo_id
        FROM orders o
        WHERE o.order_id = %s
        """,
        (order_id,),
    )
    order = order_rows[0] if order_rows else None

    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    store_id_val = order.get("store_id") if hasattr(order, "get") else order[3]
    status_val = order.get("order_status") if hasattr(order, "get") else order[2]
    payment_method = order.get("payment_method") if hasattr(order, "get") else order[4]
    payment_status = order.get("payment_status") if hasattr(order, "get") else order[5]
    payment_proof_photo_id = (
        order.get("payment_proof_photo_id") if hasattr(order, "get") else order[6]
    )

    # Verify store ownership
    if store_id_val != store["store_id"]:
        raise HTTPException(status_code=403, detail="Not your order")

    # Check if already cancelled
    if status_val == "cancelled":
        raise HTTPException(status_code=400, detail="Order already cancelled")

    method_norm = PaymentStatus.normalize_method(payment_method)
    status_norm = PaymentStatus.normalize(
        payment_status,
        payment_method=payment_method,
        payment_proof_photo_id=payment_proof_photo_id,
    )
    if method_norm in ("click", "payme") and status_norm == PaymentStatus.CONFIRMED:
        raise HTTPException(
            status_code=409,
            detail="Paid Click/Payme orders cannot be cancelled by partner",
        )

    unified_service = _ensure_unified_service(db)
    if not unified_service:
        raise HTTPException(status_code=500, detail="Order service unavailable")

    ok = await unified_service.cancel_order(order_id, "order")
    if not ok:
        raise HTTPException(status_code=400, detail=_status_transition_error(unified_service))

    await db.execute(
        """
        UPDATE orders
        SET cancel_reason = %s,
            cancel_comment = %s
        WHERE order_id = %s
        """,
        (cancel_reason, cancel_comment, order_id),
    )

    return {
        "order_id": order_id,
        "status": "cancelled",
        "reason": cancel_reason,
        "comment": cancel_comment,
    }


@router.post("/products/import")
@limiter.limit("2/minute")
async def import_csv(
    request: Request, file: UploadFile = File(...), authorization: str = Header(None)
):
    """Import products from CSV"""
    telegram_id = verify_telegram_webapp(authorization)
    user, store = await get_partner_with_store(telegram_id)
    db = get_db()

    if not file.filename.endswith(".csv"):
        raise HTTPException(status_code=400, detail="File must be CSV")

    store_id = store["store_id"]
    store_from, store_until, _ = _resolve_store_hours(store)
    available_from_default = store_from.isoformat()
    available_until_default = store_until.isoformat()

    # Read CSV
    content = await file.read()
    text = content.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))

    imported = 0
    errors = []

    for row_num, row in enumerate(reader, start=2):
        try:
            expiry = None
            if row.get("expiry_date"):
                try:
                    expiry = datetime.fromisoformat(row["expiry_date"])
                except ValueError:
                    pass

            await db.add_offer(
                store_id=store_id,
                title=row["title"],
                description=row.get("description", row["title"]),
                original_price=_to_kopeks(row.get("original_price", 0)) or None,
                discount_price=_to_kopeks(row.get("discount_price", 0)),
                quantity=int(row.get("quantity", 1)),
                available_from=available_from_default,
                available_until=available_until_default,
                expiry_date=expiry.isoformat() if expiry else None,
                unit=row.get("unit", "шт"),
                category=row.get("category", "other"),
            )
            imported += 1
        except Exception as e:
            errors.append(f"Row {row_num}: {str(e)}")

    return {"imported": imported, "errors": errors if errors else None}


# Orders endpoints
@router.get("/orders")
@limiter.limit("120/minute")
async def list_orders(
    request: Request,
    authorization: str = Header(None),
    status: Optional[str] = None,
):
    """
    List partner's orders (unified from orders table).
    After v24 migration, all orders (pickup + delivery) are in orders table.
    """
    telegram_id = verify_telegram_webapp(authorization)
    user, store = await get_partner_with_store(telegram_id)
    db = get_db()

    # Get all orders from unified orders table
    orders = await db.get_store_orders(store["store_id"])

    result = []

    # Process all orders from unified table
    for order in orders:
        # Handle both dict and tuple formats
        if isinstance(order, dict):
            order_id = order.get("order_id")
            offer_id = order.get("offer_id")
            user_id = order.get("user_id")
            order_status = order.get("order_status") or order.get("status")
            order_type = order.get("order_type") or ("delivery" if order.get("delivery_address") else "pickup")
            quantity = order.get("quantity", 1)
            total_price = order.get("total_price", 0)
            delivery_address = order.get("delivery_address")
            created_at = order.get("created_at")
            payment_method = order.get("payment_method")
            payment_status = order.get("payment_status")
            payment_proof_photo_id = order.get("payment_proof_photo_id")
            pickup_code = order.get("pickup_code") or order.get("booking_code")
            cart_items_raw = order.get("cart_items")

            # Customer info from JOIN
            first_name = order.get("first_name", "")
            customer_name = first_name or "Unknown"
            customer_phone = order.get("phone")

            # Offer info from JOIN
            offer_title = order.get("offer_title", "Unknown")
            offer_photo_id = order.get("offer_photo_id")
            offer_photo_url = (
                f"{API_BASE_URL}/api/partner/photo/{offer_photo_id}" if offer_photo_id else None
            )

            # Build items list (cart orders or single item)
            items = []
            if cart_items_raw:
                try:
                    cart_items = (
                        json.loads(cart_items_raw)
                        if isinstance(cart_items_raw, str)
                        else cart_items_raw
                    )
                    if isinstance(cart_items, list):
                        for it in cart_items:
                            items.append(
                                {
                                    "title": it.get("title") or it.get("offer_title") or offer_title,
                                    "quantity": int(it.get("quantity") or 1),
                                    "price": it.get("price") or it.get("discount_price") or 0,
                                }
                            )
                except Exception:
                    items = []

            if not items:
                items = [
                    {
                        "title": offer_title,
                        "quantity": int(quantity or 1),
                        "price": int(total_price or 0),
                    }
                ]

            items_count = sum(int(it.get("quantity") or 1) for it in items) if items else 0

            # Keep unpaid orders visible for partner actions/updates
        else:
            # Tuple format varies, try to extract what we can
            order_id = order[0]
            user_id = order[1]
            store_id = order[2]
            offer_id = order[3]
            quantity = order[4]
            order_type = order[5] if len(order) > 5 else "delivery"
            order_status = order[6] if len(order) > 6 else "pending"
            total_price = order[7] if len(order) > 7 else 0
            delivery_address = order[8] if len(order) > 8 else None
            created_at = order[11] if len(order) > 11 else None
            customer_name = order[-2] if len(order) > 14 else "Unknown"
            customer_phone = order[-1] if len(order) > 15 else None
            offer_title = "Unknown"
            offer_photo_url = None
            pickup_code = None
            payment_method = None
            payment_status = None
            items = [
                {
                    "title": offer_title,
                    "quantity": int(quantity or 1),
                    "price": int(total_price or 0),
                }
            ]
            items_count = int(quantity or 1)

        # Filter by status if requested
        if status and status != "all" and order_status != status:
            continue

        # Determine entity type for API - 'booking' for pickup, 'order' for delivery
        entity_type = "booking" if order_type == "pickup" else "order"
        result.append(
            {
                "order_id": order_id,
                "type": entity_type,  # 'booking' for pickup, 'order' for delivery
                "offer_title": offer_title,
                "offer_photo_url": offer_photo_url,
                "photo_url": offer_photo_url,
                "quantity": quantity,
                "price": total_price,
                "total_price": total_price,
                "items": items,
                "items_count": items_count,
                "order_type": order_type,  # 'pickup' or 'delivery'
                "status": order_status,
                "order_status": order_status,
                "payment_status": payment_status,
                "payment_method": payment_method,
                "payment_proof_photo_id": payment_proof_photo_id,
                "payment_proof_url": (
                    f"{API_BASE_URL}/api/partner/photo/{payment_proof_photo_id}"
                    if payment_proof_photo_id
                    else None
                ),
                "pickup_code": pickup_code,
                "booking_code": pickup_code,
                "delivery_address": delivery_address,
                "created_at": str(created_at) if created_at else None,
                "customer_name": customer_name,
                "customer_phone": customer_phone,
            }
        )


    # Sort by created_at descending
    result.sort(key=lambda x: x.get("created_at") or "", reverse=True)

    return result


@router.post("/orders/{order_id}/confirm")
@limiter.limit("20/minute")
async def confirm_order(
    request: Request,
    order_id: int,
    authorization: str = Header(None),
):
    """
    Confirm order with notifications (v24+ unified orders).
    Works for both pickup and delivery orders.
    """
    telegram_id = verify_telegram_webapp(authorization)
    user, store = await get_partner_with_store(telegram_id)
    db = get_db()
    unified_service = _ensure_unified_service(db)

    # Get order from unified orders table
    order = await db.get_order(order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    # Verify it's partner's order
    order_store_id = order.get("store_id") if isinstance(order, dict) else order[2]
    if order_store_id != store["store_id"]:
        raise HTTPException(status_code=403, detail="Not your order")

    payment_method = order.get("payment_method") if isinstance(order, dict) else order[4]
    payment_status = order.get("payment_status") if isinstance(order, dict) else order[5]
    payment_proof_photo_id = (
        order.get("payment_proof_photo_id") if isinstance(order, dict) else order[6]
    )
    method_norm = PaymentStatus.normalize_method(payment_method)
    status_norm = PaymentStatus.normalize(
        payment_status,
        payment_method=payment_method,
        payment_proof_photo_id=payment_proof_photo_id,
    )
    if method_norm in ("click", "payme") and status_norm != PaymentStatus.CONFIRMED:
        raise HTTPException(status_code=409, detail="Payment not confirmed")

    # Use unified service if available; fall back to direct status update.
    if unified_service:
        ok = await unified_service.confirm_order(order_id, "order")
        if not ok:
            raise HTTPException(status_code=400, detail=_status_transition_error(unified_service))
    else:
        if hasattr(db, "update_order_status"):
            if isinstance(order, dict):
                order_type = order.get("order_type") or (
                    "delivery" if order.get("delivery_address") else "pickup"
                )
            else:
                order_type = order[5] if len(order) > 5 else "delivery"
            target_status = OrderStatus.READY if order_type == "pickup" else OrderStatus.PREPARING
            try:
                await db.update_order_status(order_id, target_status)
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc

    # Return type based on order_type for frontend
    db_order_type = (
        order.get("order_type")
        if isinstance(order, dict)
        else (order[5] if len(order) > 5 else "delivery")
    )
    frontend_type = "booking" if db_order_type == "pickup" else "order"

    response_status = (
        OrderStatus.READY if db_order_type == "pickup" else OrderStatus.PREPARING
    )

    return {"order_id": order_id, "status": response_status, "type": frontend_type}


# REMOVED: Duplicate cancel endpoint without reason - use v22.0 endpoint above with cancel_reason


@router.post("/orders/{order_id}/status")
@limiter.limit("120/minute")
async def update_order_status(
    order_id: int,
    request: Request,
    authorization: str = Header(None),
    status: str = Query(...),
):
    """
    Update order status (ready, delivering, etc) with notifications (v24+ unified orders).
    Works for both pickup and delivery orders.
    """
    telegram_id = verify_telegram_webapp(authorization)
    user, store = await get_partner_with_store(telegram_id)
    db = get_db()
    unified_service = _ensure_unified_service(db)

    # Get order from unified orders table
    order = await db.get_order(order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    # Verify it's partner's order
    order_store_id = order.get("store_id") if isinstance(order, dict) else order[2]
    if order_store_id != store["store_id"]:
        raise HTTPException(status_code=403, detail="Not your order")

    payment_method = order.get("payment_method") if isinstance(order, dict) else order[4]
    payment_status = order.get("payment_status") if isinstance(order, dict) else order[5]
    payment_proof_photo_id = (
        order.get("payment_proof_photo_id") if isinstance(order, dict) else order[6]
    )
    method_norm = PaymentStatus.normalize_method(payment_method)
    status_norm = PaymentStatus.normalize(
        payment_status,
        payment_method=payment_method,
        payment_proof_photo_id=payment_proof_photo_id,
    )
    if method_norm in ("click", "payme") and status_norm != PaymentStatus.CONFIRMED:
        raise HTTPException(status_code=409, detail="Payment not confirmed")

    courier_phone: str | None = None
    if status == "delivering":
        try:
            payload = await request.json()
        except Exception:
            payload = {}
        courier_phone = (payload or {}).get("courier_phone")
        if not courier_phone:
            raise HTTPException(status_code=400, detail="Courier phone required")
        phone_digits = "".join(filter(str.isdigit, str(courier_phone)))
        if len(phone_digits) < 9:
            raise HTTPException(status_code=400, detail="Invalid courier phone")

    # Use unified service based on status
    if unified_service:
        if status == "ready":
            ok = await unified_service.mark_ready(order_id, "order")
        elif status == "delivering":
            ok = await unified_service.start_delivery(order_id, courier_phone=courier_phone)
        elif status == "completed":
            ok = await unified_service.complete_order(order_id, "order")
        else:
            raise HTTPException(status_code=400, detail="Unsupported status transition")
    else:
        if not hasattr(db, "update_order_status"):
            raise HTTPException(status_code=500, detail="Order service unavailable")
        try:
            if status == "ready":
                await db.update_order_status(order_id, OrderStatus.READY)
            elif status == "delivering":
                await db.update_order_status(order_id, OrderStatus.DELIVERING)
            elif status == "completed":
                await db.update_order_status(order_id, OrderStatus.COMPLETED)
            else:
                raise HTTPException(status_code=400, detail="Unsupported status transition")
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        ok = True

    if not ok:
        raise HTTPException(status_code=400, detail=_status_transition_error(unified_service))

    # Return type based on order_type for frontend
    db_order_type = (
        order.get("order_type")
        if isinstance(order, dict)
        else (order[5] if len(order) > 5 else "delivery")
    )
    frontend_type = "booking" if db_order_type == "pickup" else "order"

    return {"order_id": order_id, "status": status, "type": frontend_type}


# Stats endpoint
@router.get("/stats")
@limiter.limit("120/minute")
async def get_stats(
    request: Request,
    authorization: str = Header(None),
    period: str = "today",
):
    """Get partner statistics with daily breakdown for charts."""
    telegram_id = verify_telegram_webapp(authorization)
    user, store = await get_partner_with_store(telegram_id)
    db = get_db()

    store_id = store["store_id"]

    # Calculate period
    tz = pytz.timezone("Asia/Tashkent")
    now = datetime.now(tz)

    if period == "today":
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end = now
    elif period == "yesterday":
        start = (now - timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        end = start.replace(hour=23, minute=59, second=59)
    elif period == "week":
        start = (now - timedelta(days=7)).replace(hour=0, minute=0, second=0, microsecond=0)
        end = now
    elif period == "month":
        start = (now - timedelta(days=30)).replace(hour=0, minute=0, second=0, microsecond=0)
        end = now
    else:
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end = now

    period_obj = Period(start=start, end=end, tz="Asia/Tashkent")

    sync_db = db.sync if hasattr(db, "sync") else db
    stats = await db.run(
        get_partner_stats,
        sync_db,
        partner_id=user["user_id"],
        period=period_obj,
        tz="Asia/Tashkent",
        store_id=store_id,
    )

    # Count active products
    active_products = 0
    if store_id:
        offers = await db.get_offers_by_store(store_id)
        active_products = len([o for o in offers if o.get("status") == "active"])

    # Get daily breakdown for charts (last 7 days)
    revenue_by_day = []
    orders_by_day = []
    top_products = []

    try:
        def _fetch_breakdown(sync_db, store_id_val, now_val):
            revenue = []
            orders = []
            top = []
            with sync_db.get_connection() as conn:
                cursor = conn.cursor()

                # Revenue and orders by day (last 7 days)
                for i in range(6, -1, -1):
                    day_start = (now_val - timedelta(days=i)).replace(
                        hour=0, minute=0, second=0, microsecond=0
                    )
                    day_end = day_start.replace(hour=23, minute=59, second=59)

                    cursor.execute(
                        """
                        SELECT
                            COALESCE(SUM(o.discount_price * b.quantity), 0) AS revenue,
                            COUNT(DISTINCT b.booking_id) AS orders
                        FROM bookings b
                        JOIN offers o ON b.offer_id = o.offer_id
                        WHERE o.store_id = %s
                        AND b.status IN ('completed', 'confirmed')
                        AND b.created_at >= %s AND b.created_at < %s
                        """,
                        (store_id_val, day_start, day_end),
                    )
                    row = cursor.fetchone() or (0, 0)
                    bookings_revenue = float(row[0] or 0)
                    bookings_orders = int(row[1] or 0)

                    cursor.execute(
                        """
                        SELECT
                            COALESCE(SUM(o.total_price), 0) AS revenue,
                            COUNT(DISTINCT o.order_id) AS orders
                        FROM orders o
                        WHERE o.store_id = %s
                        AND o.order_status = 'completed'
                        AND o.created_at >= %s AND o.created_at < %s
                        """,
                        (store_id_val, day_start, day_end),
                    )
                    row = cursor.fetchone() or (0, 0)
                    orders_revenue = float(row[0] or 0)
                    orders_count = int(row[1] or 0)

                    revenue.append(bookings_revenue + orders_revenue)
                    orders.append(bookings_orders + orders_count)

                # Top products (last 30 days)
                top_map: dict[str, dict[str, float | int | str]] = {}
                cursor.execute(
                    """
                    SELECT o.title, SUM(b.quantity) as qty, SUM(o.discount_price * b.quantity) as revenue
                    FROM bookings b
                    JOIN offers o ON b.offer_id = o.offer_id
                    WHERE o.store_id = %s
                    AND b.status IN ('completed', 'confirmed')
                    AND b.created_at >= %s
                    GROUP BY o.offer_id, o.title
                    ORDER BY qty DESC
                    LIMIT 20
                    """,
                    (store_id_val, now_val - timedelta(days=30)),
                )
                for row in cursor.fetchall():
                    name = row[0] or "Unknown"
                    qty = int(row[1] or 0)
                    rev = float(row[2] or 0)
                    top_map[name] = {"name": name, "qty": qty, "revenue": rev}

                cursor.execute(
                    """
                    SELECT COALESCE(off.title, o.item_title, 'Unknown') as title,
                           COALESCE(SUM(o.quantity), 0) as qty,
                           COALESCE(SUM(o.total_price), 0) as revenue
                    FROM orders o
                    LEFT JOIN offers off ON o.offer_id = off.offer_id
                    WHERE o.store_id = %s
                    AND o.order_status = 'completed'
                    AND COALESCE(o.is_cart_order, 0) = 0
                    AND o.created_at >= %s
                    GROUP BY COALESCE(off.title, o.item_title, 'Unknown')
                    ORDER BY qty DESC
                    LIMIT 20
                    """,
                    (store_id_val, now_val - timedelta(days=30)),
                )
                for row in cursor.fetchall():
                    name = row[0] or "Unknown"
                    qty = int(row[1] or 0)
                    rev = float(row[2] or 0)
                    entry = top_map.get(name)
                    if not entry:
                        top_map[name] = {"name": name, "qty": qty, "revenue": rev}
                    else:
                        entry["qty"] = int(entry.get("qty", 0)) + qty
                        entry["revenue"] = float(entry.get("revenue", 0)) + rev

                top = sorted(
                    top_map.values(), key=lambda item: int(item.get("qty", 0)), reverse=True
                )[:5]
            return revenue, orders, top

        sync_db = db.sync if hasattr(db, "sync") else db
        revenue_by_day, orders_by_day, top_products = await db.run(
            _fetch_breakdown, sync_db, store_id, now
        )
    except Exception as e:
        import logging

        logging.warning(f"Failed to get daily breakdown: {e}")
        # Fallback to zeros
        revenue_by_day = [0] * 7
        orders_by_day = [0] * 7

    return {
        "period": period,
        "start": start.isoformat(),
        "end": end.isoformat(),
        "revenue": float(stats.totals.revenue),
        "orders": stats.totals.orders,
        "items_sold": stats.totals.items_sold,
        "avg_ticket": float(stats.totals.avg_ticket) if stats.totals.avg_ticket else 0,
        "active_products": active_products,
        # Daily breakdown for charts
        "revenue_by_day": revenue_by_day,
        "orders_by_day": orders_by_day,
        "top_products": top_products,
    }


# Store settings
@router.put("/store")
@limiter.limit("120/minute")
async def update_store(
    settings: dict,
    request: Request,
    authorization: str = Header(None),
):
    """Update store settings"""
    import logging

    logger = logging.getLogger(__name__)
    telegram_id = verify_telegram_webapp(authorization)
    user, store = await get_partner_with_store(telegram_id)
    db = get_db()

    def _parse_bool(value, fallback=False):
        if isinstance(value, bool):
            return value
        if isinstance(value, int):
            return value != 0
        if isinstance(value, str):
            return value.strip().lower() in {"1", "true", "yes", "on"}
        return fallback

    def _parse_int(value, fallback=0):
        try:
            return int(float(value))
        except (TypeError, ValueError):
            return fallback

    delivery_enabled = _parse_bool(
        settings.get("delivery_enabled", store.get("delivery_enabled", 0)),
        bool(store.get("delivery_enabled", 0)),
    )
    delivery_price_input = settings.get("delivery_price", settings.get("delivery_cost"))
    min_order_input = settings.get("min_order_amount", settings.get("min_order"))

    delivery_price = (
        _parse_int(delivery_price_input, int(store.get("delivery_price") or 0))
        if delivery_price_input is not None
        else int(store.get("delivery_price") or 0)
    )
    min_order_amount = (
        _parse_int(min_order_input, int(store.get("min_order_amount") or 0))
        if min_order_input is not None
        else int(store.get("min_order_amount") or 0)
    )

    delivery_price_value = max(0, int(delivery_price))
    min_order_value = max(0, int(min_order_amount))

    phone_value = sanitize_phone(settings.get("phone", store.get("phone")))
    if not phone_value or not validator.validate_phone(phone_value):
        raise HTTPException(status_code=400, detail="Invalid store phone")

    working_hours_value = store.get("working_hours")
    if "working_hours" in settings:
        normalized_hours = _normalize_working_hours(settings.get("working_hours"))
        if not normalized_hours:
            raise HTTPException(
                status_code=400,
                detail="Invalid working_hours format. Use HH:MM - HH:MM",
            )
        working_hours_value = normalized_hours
    # Normalize hours for syncing offer availability with store hours.
    old_hours_norm = _normalize_working_hours(store.get("working_hours")) or DEFAULT_WORKING_HOURS
    new_hours_norm = _normalize_working_hours(working_hours_value) or old_hours_norm

    region_value = settings.get("region", store.get("region"))
    district_value = settings.get("district", store.get("district"))
    region_id_value = store.get("region_id")
    district_id_value = store.get("district_id")

    sync_db = db.sync if hasattr(db, "sync") else db
    resolver = getattr(sync_db, "resolve_geo_location", None)
    if resolver and (region_value is not None or district_value is not None):
        try:
            resolved = await db.run(resolver, region=region_value, district=district_value)
        except Exception as exc:
            logger.warning("Geo resolve failed in partner settings: %s", exc)
            resolved = None
        if resolved:
            if region_value is not None and resolved.get("region_name_ru"):
                region_value = resolved["region_name_ru"]
            if district_value is not None and resolved.get("district_name_ru"):
                district_value = resolved["district_name_ru"]
            if region_value is None and district_value is not None and resolved.get("region_name_ru"):
                region_value = resolved["region_name_ru"]
            region_id_value = resolved.get("region_id") or region_id_value
            district_id_value = resolved.get("district_id") or district_id_value

    region_slug = canonicalize_geo_slug(region_value) if region_value else None
    district_slug = canonicalize_geo_slug(district_value) if district_value else None

    async def _sync_offer_hours(from_norm: str, to_norm: str) -> None:
        if from_norm == to_norm:
            return
        old_start, old_end = _parse_time_range(from_norm)
        new_start, new_end = _parse_time_range(to_norm)
        if not (old_start and old_end and new_start and new_end):
            return
        await db.execute(
            """
            UPDATE offers
            SET available_from = %s,
                available_until = %s
            WHERE store_id = %s
              AND available_from = %s
              AND available_until = %s
            """,
            (
                new_start.isoformat(),
                new_end.isoformat(),
                store["store_id"],
                old_start.isoformat(),
                old_end.isoformat(),
            ),
        )

    # If store working hours are updated, keep offers that used store defaults in sync.
    if "working_hours" in settings:
        if new_hours_norm != old_hours_norm:
            await _sync_offer_hours(old_hours_norm, new_hours_norm)
        elif new_hours_norm != DEFAULT_WORKING_HOURS:
            await _sync_offer_hours(DEFAULT_WORKING_HOURS, new_hours_norm)

    # Update existing store via SQL
    await db.execute(
        """
        UPDATE stores
        SET name = %s,
            address = %s,
            region = %s,
            region_slug = %s,
            district = %s,
            district_slug = %s,
            region_id = %s,
            district_id = %s,
            phone = %s,
            description = %s,
            working_hours = %s,
            delivery_enabled = %s,
            delivery_price = %s,
            min_order_amount = %s
        WHERE store_id = %s
        """,
        (
            settings.get("name", store.get("name")),
            settings.get("address", store.get("address")),
            region_value,
            region_slug,
            district_value,
            district_slug,
            region_id_value,
            district_id_value,
            phone_value,
            settings.get("description", store.get("description")),
            working_hours_value,
            int(delivery_enabled),
            delivery_price_value,
            min_order_value,
            store["store_id"],
        ),
    )

    return {"status": "updated"}


@router.patch("/store/status")
@limiter.limit("120/minute")
async def toggle_store_status(
    request: Request,
    is_open: bool = Form(...),
    authorization: str = Header(None),
):
    """Toggle store open/closed status"""
    telegram_id = verify_telegram_webapp(authorization)
    user, store = await get_partner_with_store(telegram_id)
    db = get_db()

    new_status = "approved" if is_open else "closed"

    await db.execute(
        "UPDATE stores SET status = %s WHERE store_id = %s", (new_status, store["store_id"])
    )

    return {"status": new_status, "is_open": is_open}


# Photo upload endpoint
@router.post("/upload-photo")
@limiter.limit("120/minute")
async def upload_photo(
    request: Request,
    photo: UploadFile = File(...),
    authorization: str = Header(None),
):
    """
    Upload photo and get Telegram file_id.
    Sends photo to a special channel/chat via bot to get file_id.
    """
    import aiohttp

    telegram_id = verify_telegram_webapp(authorization)
    user, store = await get_partner_with_store(telegram_id)

    # Read photo content
    content = await photo.read()

    # Check file size (max 10MB)
    if len(content) > 10 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Photo too large (max 10MB)")

    # Check file type
    if not photo.content_type or not photo.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="File must be an image")

    if not _bot_token:
        raise HTTPException(status_code=500, detail="Bot token not configured")

    # Send photo to user's chat to get file_id
    # We use the partner's own chat_id (telegram_id)
    try:
        async with aiohttp.ClientSession() as session:
            form_data = aiohttp.FormData()
            form_data.add_field("chat_id", str(telegram_id))
            form_data.add_field(
                "photo", content, filename=photo.filename, content_type=photo.content_type
            )
            # No caption - send photo silently without text

            async with session.post(
                f"https://api.telegram.org/bot{_bot_token}/sendPhoto", data=form_data
            ) as resp:
                result = await resp.json()

                if not result.get("ok"):
                    raise HTTPException(
                        status_code=500,
                        detail=f"Failed to upload: {result.get('description', 'Unknown error')}",
                    )

                # Get the largest photo size (last in array)
                photos = result["result"].get("photo", [])
                if not photos:
                    raise HTTPException(status_code=500, detail="No photo in response")

                file_id = photos[-1]["file_id"]

                return {"file_id": file_id, "message": "Photo uploaded successfully"}
    except aiohttp.ClientError as e:
        raise HTTPException(status_code=500, detail=f"Network error: {str(e)}")


# Get photo URL endpoint
@router.get("/photo/{file_id}")
@limiter.limit("120/minute")
async def get_photo_url(
    file_id: str,
    request: Request,
    authorization: str = Header(None),
):
    """Redirect to Telegram photo URL"""
    import aiohttp
    from fastapi.responses import RedirectResponse

    telegram_id = verify_telegram_webapp(authorization)
    await get_partner_with_store(telegram_id)

    tokens = [_bot_token] if _bot_token else []
    if _legacy_bot_token and _legacy_bot_token not in tokens:
        tokens.append(_legacy_bot_token)

    if not tokens:
        raise HTTPException(status_code=500, detail="Bot token not configured")

    try:
        async with aiohttp.ClientSession() as session:
            for token in tokens:
                async with session.get(
                    f"https://api.telegram.org/bot{token}/getFile?file_id={file_id}"
                ) as resp:
                    result = await resp.json()

                    if not result.get("ok"):
                        continue

                    file_path = result["result"]["file_path"]
                    photo_url = f"https://api.telegram.org/file/bot{token}/{file_path}"

                    if _bot_token and token != _bot_token:
                        import logging

                        logging.info("Photo served via legacy bot token (partner panel)")

                    # Redirect to actual photo URL
                    return RedirectResponse(url=photo_url)
    except aiohttp.ClientError as e:
        raise HTTPException(status_code=500, detail=f"Network error: {str(e)}")

    raise HTTPException(status_code=404, detail="File not found")
