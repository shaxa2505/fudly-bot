"""
Order Tracking API for Telegram Mini App
Provides real-time order status, QR codes, and delivery tracking
"""
import base64
import io
import logging
import math
import os
from datetime import datetime, timedelta
from typing import Any

import qrcode
from aiogram import Bot
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel, Field, AliasChoices

from app.api.webapp.common import get_current_user
from app.core.async_db import AsyncDBProxy
from app.core.constants import DEFAULT_DELIVERY_RADIUS_KM, MAX_DELIVERY_RADIUS_KM
from app.core.order_math import (
    calc_delivery_fee,
    calc_items_total,
    calc_quantity,
    calc_total_price,
    parse_cart_items,
)
from app.core.utils import UZB_TZ, get_uzb_time, to_uzb_datetime
from app.services.unified_order_service import OrderStatus as UnifiedOrderStatus, PaymentStatus

router = APIRouter(prefix="/api/v1/orders", tags=["orders"])

logger = logging.getLogger(__name__)

# Global database instance (set by api_server.py)
_db_instance = None
_bot_instance: Bot | None = None


def get_db():
    """Dependency to get database instance."""
    if _db_instance is None:
        raise HTTPException(status_code=503, detail="Database not available")
    return _db_instance


def set_orders_db(db, bot_token: str | None = None):
    """Set database instance (and optional bot token) for orders module."""
    global _db_instance, _bot_instance
    if db is None:
        _db_instance = None
    else:
        if not isinstance(db, AsyncDBProxy):
            db = AsyncDBProxy(db)
        _db_instance = db
    if bot_token and _bot_instance is None:
        _bot_instance = Bot(bot_token)


def get_bot() -> Bot:
    """Dependency to get bot instance for Telegram operations."""
    global _bot_instance
    if _bot_instance is None:
        token = os.getenv("TELEGRAM_BOT_TOKEN")
        if token:
            _bot_instance = Bot(token)
        else:
            raise HTTPException(status_code=500, detail="Bot not configured")
    return _bot_instance


async def _bookings_archive_exists(db) -> bool:
    """Check if bookings_archive table exists (optional migration)."""
    try:
        if hasattr(db, "execute"):
            result = await db.execute("SELECT to_regclass('public.bookings_archive')")
            return bool(result and result[0] and result[0][0])
        if hasattr(db, "sync") and hasattr(db.sync, "get_connection"):
            def _check(sync_db) -> bool:
                with sync_db.get_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute("SELECT to_regclass('public.bookings_archive')")
                    row = cursor.fetchone()
                    return bool(row and row[0])

            return bool(await db.run(_check, db.sync))
    except Exception:
        return False
    return False


def _require_user_id(user: dict) -> int:
    user_id = int(user.get("id") or 0)
    if user_id <= 0:
        raise HTTPException(status_code=401, detail="Authentication required")
    return user_id


# ==================== MODELS ====================


class OrderStatus(BaseModel):
    """Order status details."""

    booking_id: int
    booking_code: str
    status: str  # pending, preparing, ready, delivering, completed, cancelled, rejected
    payment_status: str | None = None
    order_type: str | None = None
    created_at: str
    updated_at: str | None
    ready_until: str | None = None

    # Offer details
    offer_title: str
    offer_photo: str | None
    quantity: float
    total_price: float
    items_total: float | None = None
    total_with_delivery: float | None = None

    # Store details
    store_id: int
    store_name: str
    store_address: str | None
    store_phone: str | None

    # Pickup/Delivery
    pickup_time: str | None
    pickup_address: str | None
    delivery_address: str | None
    delivery_cost: float | None

    # QR code (base64 PNG)
    qr_code: str | None


class StatusUpdate(BaseModel):
    """Status update history item."""

    status: str
    timestamp: str
    message: str


class OrderTimeline(BaseModel):
    """Full order timeline with status history."""

    booking_id: int
    current_status: str
    timeline: list[StatusUpdate]
    estimated_ready_time: str | None


class DeliveryCalculation(BaseModel):
    """Delivery cost calculation request."""

    city: str
    address: str
    store_id: int
    delivery_lat: float | None = Field(
        default=None,
        validation_alias=AliasChoices("delivery_lat", "lat", "latitude"),
    )
    delivery_lon: float | None = Field(
        default=None,
        validation_alias=AliasChoices("delivery_lon", "lon", "lng", "longitude"),
    )


class DeliveryResult(BaseModel):
    """Delivery cost calculation result."""

    can_deliver: bool
    delivery_cost: float | None
    estimated_time: str | None  # e.g. "30-40 min"
    min_order_amount: float | None
    message: str | None


# ==================== HELPERS ====================


def generate_qr_code(booking_code: str) -> str:
    """Generate QR code as base64 PNG.

    Args:
        booking_code: Booking code to encode

    Returns:
        Base64 encoded PNG image
    """
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=10,
        border=4,
    )
    qr.add_data(booking_code)
    qr.make(fit=True)

    img = qr.make_image(fill_color="black", back_color="white")

    # Convert to base64
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    img_bytes = buffer.getvalue()
    img_base64 = base64.b64encode(img_bytes).decode("utf-8")

    return f"data:image/png;base64,{img_base64}"


def _parse_coord(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    rad = math.pi / 180.0
    x = (lon2 - lon1) * rad * math.cos((lat1 + lat2) * rad / 2.0)
    y = (lat2 - lat1) * rad
    return math.hypot(x, y) * 6371.0


def _pickup_ready_expiry_hours() -> int:
    try:
        value = int(os.environ.get("PICKUP_READY_EXPIRY_HOURS", "2"))
    except Exception:
        value = 2
    return max(1, value)


def _format_ready_until(updated_at: Any) -> str | None:
    hours = _pickup_ready_expiry_hours()
    if hours <= 0:
        return None

    base_time = to_uzb_datetime(updated_at) or get_uzb_time()
    ready_until = base_time + timedelta(hours=hours)
    return ready_until.strftime("%H:%M")


async def calculate_delivery_cost(
    city: str,
    address: str,
    store_id: int,
    db,
    *,
    delivery_lat: float | None = None,
    delivery_lon: float | None = None,
) -> DeliveryResult:
    """Calculate delivery cost based on distance."""
    store = await db.get_store(store_id)
    if not store:
        return DeliveryResult(
            can_deliver=False,
            delivery_cost=None,
            estimated_time=None,
            min_order_amount=None,
            message="Store not found",
        )

    store_dict = dict(store) if not isinstance(store, dict) else store
    if not bool(store_dict.get("delivery_enabled", True)):
        return DeliveryResult(
            can_deliver=False,
            delivery_cost=None,
            estimated_time=None,
            min_order_amount=None,
            message="Yetkazib berish mavjud emas",
        )

    store_lat = _parse_coord(store_dict.get("latitude"))
    store_lon = _parse_coord(store_dict.get("longitude"))
    if store_lat is None or store_lon is None:
        return DeliveryResult(
            can_deliver=False,
            delivery_cost=None,
            estimated_time=None,
            min_order_amount=None,
            message="Do'kon geolokatsiyasi o'rnatilmagan",
        )

    delivery_lat_val = _parse_coord(delivery_lat)
    delivery_lon_val = _parse_coord(delivery_lon)
    if delivery_lat_val is None or delivery_lon_val is None:
        return DeliveryResult(
            can_deliver=False,
            delivery_cost=None,
            estimated_time=None,
            min_order_amount=None,
            message="Yetkazib berish manzilini xaritada belgilang",
        )

    radius_km = _parse_coord(store_dict.get("delivery_radius_km"))
    if radius_km is None or radius_km <= 0:
        radius_km = float(DEFAULT_DELIVERY_RADIUS_KM)
    radius_km = max(1.0, min(float(radius_km), float(MAX_DELIVERY_RADIUS_KM)))

    distance_km = _distance_km(store_lat, store_lon, delivery_lat_val, delivery_lon_val)
    if distance_km > radius_km:
        return DeliveryResult(
            can_deliver=False,
            delivery_cost=None,
            estimated_time=None,
            min_order_amount=None,
            message=(
                f"Yetkazib berish radiusi {radius_km:.0f} km. "
                f"Masofa: {distance_km:.1f} km"
            ),
        )

    delivery_cost = int(store_dict.get("delivery_price") or 0)
    min_order = int(store_dict.get("min_order_amount") or 0)

    return DeliveryResult(
        can_deliver=True,
        delivery_cost=float(delivery_cost),
        estimated_time="30-45 min",
        min_order_amount=float(min_order),
        message=None,
    )


async def format_booking_to_order_status(booking: Any, db) -> OrderStatus:
    """Convert database booking row to OrderStatus model.

    Args:
        booking: Database booking row
        db: Database instance

    Returns:
        OrderStatus model
    """
    # Convert to dict if needed
    booking_dict = dict(booking) if not isinstance(booking, dict) else booking

    # v24+: unified orders use `order_id`; legacy bookings use `booking_id` (or sometimes `id`)
    booking_id = (
        booking_dict.get("order_id")
        or booking_dict.get("booking_id")
        or booking_dict.get("id")
    )
    if booking_id is None:
        raise ValueError("Missing order_id/booking_id")

    raw_status = booking_dict.get("order_status") or booking_dict.get("status") or "pending"
    status = UnifiedOrderStatus.normalize(str(raw_status).strip().lower())

    # Best-effort order_type detection (unified table vs legacy booking)
    delivery_address = booking_dict.get("delivery_address")
    order_type = booking_dict.get("order_type") or ("delivery" if delivery_address else "pickup")

    ready_until = None
    if order_type == "pickup" and status == UnifiedOrderStatus.READY:
        ready_until = _format_ready_until(booking_dict.get("updated_at"))

    booking_code = booking_dict.get("pickup_code") or booking_dict.get("booking_code") or ""
    payment_status = PaymentStatus.normalize(
        booking_dict.get("payment_status"),
        payment_method=booking_dict.get("payment_method"),
        payment_proof_photo_id=booking_dict.get("payment_proof_photo_id"),
    )

    # Store details: prefer explicit store_id on the row, fallback to offer.store_id
    store_id = int(booking_dict.get("store_id") or 0)

    # Cart order support (delivery cart = 1 row with cart_items)
    is_cart = int(booking_dict.get("is_cart_order") or booking_dict.get("is_cart_booking") or 0)
    cart_items_json = booking_dict.get("cart_items")
    cart_items: list[dict[str, Any]] = parse_cart_items(cart_items_json) if is_cart else []

    offer_id = booking_dict.get("offer_id")
    quantity = float(booking_dict.get("quantity") or 1)
    delivery_cost = booking_dict.get("delivery_cost", 0) or 0
    items_total = 0
    total_price = 0.0

    offer_dict: dict[str, Any] = {}
    store_dict: dict[str, Any] = {}

    if cart_items:
        # Use first cart item as representative
        first_item = cart_items[0]
        first_offer_id = first_item.get("offer_id")
        if not store_id:
            store_id = int(first_item.get("store_id") or 0)

        # Calculate items_total from cart items
        items_total = calc_items_total(cart_items)
        try:
            # Prefer total_price from DB row when available
            total_price = float(booking_dict.get("total_price") or items_total)
        except Exception:
            total_price = float(items_total or 0)

        # Calculate delivery_cost if possible (total - items)
        qty_total = calc_quantity(cart_items)
        quantity = qty_total if qty_total > 0 else quantity

        if not delivery_cost:
            delivery_cost = calc_delivery_fee(
                total_price,
                items_total,
                delivery_price=booking_dict.get("delivery_price"),
                order_type=order_type,
            )

        if first_offer_id:
            offer = await db.get_offer(int(first_offer_id))
            offer_dict = dict(offer) if offer and not isinstance(offer, dict) else offer or {}
    else:
        # Single-item booking/order
        if offer_id:
            offer = await db.get_offer(int(offer_id))
            offer_dict = dict(offer) if offer and not isinstance(offer, dict) else offer or {}

        discount_price = int(offer_dict.get("discount_price") or 0)
        items_total = calc_items_total([{"price": discount_price, "quantity": quantity}])

        # If total_price is stored on orders table, prefer it
        if booking_dict.get("total_price") is not None:
            try:
                total_price = float(booking_dict.get("total_price") or 0)
            except Exception:
                total_price = float(items_total or 0)
        else:
            total_price = float(calc_total_price(items_total, delivery_cost or 0))

        if not delivery_cost:
            delivery_cost = calc_delivery_fee(
                total_price,
                items_total,
                delivery_price=booking_dict.get("delivery_price"),
                order_type=order_type,
            )

        if not store_id:
            store_id = int(offer_dict.get("store_id") or 0)

    if store_id:
        store = await db.get_store(store_id)
        store_dict = dict(store) if store and not isinstance(store, dict) else store or {}

    # Generate QR code only for pickup orders when the code is available
    qr_code = None
    if order_type == "pickup" and status in ["preparing", "confirmed", "ready"] and booking_code:
        qr_code = generate_qr_code(booking_code)

    items_total_value = float(items_total or 0)
    total_with_delivery = items_total_value + float(delivery_cost or 0)

    return OrderStatus(
        booking_id=int(booking_id),
        booking_code=booking_code,
        status=status,
        payment_status=payment_status,
        order_type=order_type,
        created_at=str(booking_dict.get("created_at", "")),
        updated_at=str(booking_dict.get("updated_at")) if booking_dict.get("updated_at") else None,
        ready_until=ready_until,
        offer_title=offer_dict.get("title", "Товар"),
        offer_photo=offer_dict.get("photo") or offer_dict.get("photo_id"),
        quantity=quantity,
        total_price=total_price,
        items_total=items_total_value,
        total_with_delivery=total_with_delivery,
        store_id=store_id,
        store_name=store_dict.get("name", "Магазин"),
        store_address=store_dict.get("address"),
        store_phone=booking_dict.get("store_phone") or store_dict.get("phone"),
        pickup_time=str(booking_dict.get("pickup_time"))
        if booking_dict.get("pickup_time")
        else None,
        pickup_address=booking_dict.get("pickup_address"),
        delivery_address=booking_dict.get("delivery_address"),
        delivery_cost=float(delivery_cost) if delivery_cost else None,
        qr_code=qr_code,
    )


# ==================== ENDPOINTS ====================


@router.get("")
async def get_user_orders(
    db=Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """Get user's orders from unified orders table (pickup + delivery)."""
    user_id = _require_user_id(user)

    orders: list[dict[str, Any]] = []
    raw_orders: list[Any] = []

    try:
        def _fetch_orders(sync_db, uid: int) -> list[Any]:
            with sync_db.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    SELECT
                        o.order_id,
                        o.order_status,
                        o.order_type,
                        o.pickup_code,
                        o.delivery_address,
                        o.delivery_price,
                        o.total_price,
                        o.quantity,
                        o.payment_method,
                        o.payment_status,
                        o.payment_proof_photo_id,
                        o.is_cart_order,
                        o.cart_items,
                        o.created_at,
                        o.updated_at,
                        o.store_id,
                        s.name AS store_name,
                        s.address AS store_address,
                        s.phone AS store_phone,
                        off.offer_id AS offer_id,
                        off.title AS offer_title,
                        off.discount_price AS offer_price,
                        off.photo_id AS offer_photo_id
                    FROM orders o
                    LEFT JOIN stores s ON o.store_id = s.store_id
                    LEFT JOIN offers off ON o.offer_id = off.offer_id
                    WHERE o.user_id = %s
                    ORDER BY o.created_at DESC
                    LIMIT 100
                    """,
                    (int(uid),),
                )
                return cursor.fetchall() or []

        sync_db = db.sync if hasattr(db, "sync") else db
        raw_orders = await db.run(_fetch_orders, sync_db, int(user_id))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e

    for r in raw_orders:
        if not hasattr(r, "get"):
            continue

        order_id = r.get("order_id")
        if not order_id:
            continue

        order_type = r.get("order_type") or (
            "delivery" if r.get("delivery_address") else "pickup"
        )
        raw_order_status = r.get("order_status") or "pending"
        order_status = UnifiedOrderStatus.normalize(str(raw_order_status).strip().lower())
        payment_status = PaymentStatus.normalize(
            r.get("payment_status"),
            payment_method=r.get("payment_method"),
            payment_proof_photo_id=r.get("payment_proof_photo_id"),
        )

        is_cart = int(r.get("is_cart_order") or 0) == 1
        cart_items_json = r.get("cart_items")

        items: list[dict[str, Any]] = []
        items_total = 0
        qty_total = 0

        if is_cart and cart_items_json:
            cart_items = parse_cart_items(cart_items_json)
            items_total = calc_items_total(cart_items)
            qty_total = calc_quantity(cart_items)

            for it in cart_items or []:
                title = it.get("title") or "Товар"
                qty = float(it.get("quantity") or 1)
                price = int(it.get("price") or 0)
                items.append(
                    {
                        "offer_id": it.get("offer_id"),
                        "store_id": r.get("store_id"),
                        "offer_title": title,
                        "title": title,
                        "price": price,
                        "quantity": qty,
                        "store_name": r.get("store_name"),
                        "photo": None,
                    }
                )
        else:
            qty = float(r.get("quantity") or 1)
            price = int(r.get("offer_price") or 0)
            title = r.get("offer_title") or "Товар"
            photo = r.get("offer_photo") or r.get("offer_photo_id")
            items_total = calc_items_total([{"price": price, "quantity": qty}])
            qty_total = qty
            items.append(
                {
                    "offer_id": r.get("offer_id"),
                    "store_id": r.get("store_id"),
                    "offer_title": title,
                    "title": title,
                    "price": price,
                    "quantity": qty,
                    "store_name": r.get("store_name"),
                    "photo": photo,
                }
            )

        total_price = float(r.get("total_price") or items_total)
        delivery_fee = calc_delivery_fee(
            total_price,
            items_total,
            delivery_price=r.get("delivery_price"),
            order_type=order_type,
        )
        total_with_delivery = items_total + delivery_fee

        orders.append(
            {
                "order_id": order_id,
                "order_type": order_type,
                "order_status": order_status,
                "status": order_status,
                "pickup_code": r.get("pickup_code"),
                "delivery_address": r.get("delivery_address"),
                "delivery_fee": delivery_fee,
                "total_price": total_price,
                "items_total": items_total,
                "total_with_delivery": total_with_delivery,
                "quantity": qty_total,
                "items_count": len(items),
                "items": items,
                "payment_method": r.get("payment_method"),
                "payment_status": payment_status,
                "payment_proof_photo_id": r.get("payment_proof_photo_id"),
                "created_at": str(r.get("created_at") or ""),
                "updated_at": str(r.get("updated_at") or ""),
                "store_id": r.get("store_id"),
                "store_name": r.get("store_name"),
                "store_address": r.get("store_address"),
            }
        )

    return orders


@router.post("/{order_id}/payment-proof")
async def upload_payment_proof(
    order_id: int,
    photo: UploadFile = File(...),
    db=Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """Upload payment proof for delivery orders (disabled; Click-only)."""
    raise HTTPException(
        status_code=410,
        detail="Payment proof uploads are disabled (Click-only payments)",
    )


@router.get("/{booking_id}/status", response_model=OrderStatus)
async def get_order_status(
    booking_id: int,
    db=Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """Get current order status with all details including QR code.

    Args:
        booking_id: Booking ID (v24+ order_id from unified orders table)

    Returns:
        OrderStatus with full order details and QR code (if applicable)

    Raises:
        404: Order not found
    """
    user_id = _require_user_id(user)

    # v24+: try unified orders table first
    order = await db.get_order(booking_id)
    if order:
        order_dict = dict(order) if not isinstance(order, dict) else order
        if int(order_dict.get("user_id") or 0) != user_id:
            raise HTTPException(status_code=403, detail="Access denied")
        # Convert order to booking format for compatibility
        return await format_booking_to_order_status(order, db)
    
    # Fallback: check archived bookings for old orders (optional table)
    if await _bookings_archive_exists(db):
        try:
            booking = await db.execute(
                "SELECT * FROM bookings_archive WHERE booking_id = %s",
                (booking_id,)
            )
            if booking:
                booking_dict = dict(booking[0]) if not isinstance(booking[0], dict) else booking[0]
                if int(booking_dict.get("user_id") or 0) != user_id:
                    raise HTTPException(status_code=403, detail="Access denied")
                return await format_booking_to_order_status(booking[0], db)
        except Exception as e:
            logger.warning(
                "Failed to fetch bookings_archive status for booking_id=%s: %s",
                booking_id,
                e,
            )
    
    raise HTTPException(status_code=404, detail="Заказ не найден")


@router.get("/{booking_id}/timeline", response_model=OrderTimeline)
async def get_order_timeline(
    booking_id: int,
    db=Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """Get order status timeline/history.

    Args:
        booking_id: Booking ID (v24+ order_id from unified orders table)

    Returns:
        OrderTimeline with status change history

    Raises:
        404: Order not found
    """
    user_id = _require_user_id(user)

    # v24+: try unified orders table first
    order = await db.get_order(booking_id)
    if not order and await _bookings_archive_exists(db):
        # Fallback: check archived bookings
        try:
            result = await db.execute(
                "SELECT * FROM bookings_archive WHERE booking_id = %s",
                (booking_id,)
            )
            if result:
                order = result[0]
        except Exception as e:
            logger.warning(
                "Failed to fetch bookings_archive timeline for booking_id=%s: %s",
                booking_id,
                e,
            )
    
    if not order:
        raise HTTPException(status_code=404, detail="Заказ не найден")

    order_dict = dict(order) if not isinstance(order, dict) else order
    if int(order_dict.get("user_id") or 0) != user_id:
        raise HTTPException(status_code=403, detail="Access denied")
    raw_status = order_dict.get("order_status", order_dict.get("status", "pending"))
    status = UnifiedOrderStatus.normalize(str(raw_status).strip().lower())
    created_at = str(order_dict.get("created_at", ""))
    order_type = order_dict.get("order_type") or (
        "delivery" if order_dict.get("delivery_address") else "pickup"
    )
    is_pickup = order_type == "pickup"

    # Build timeline based on status
    timeline: list[StatusUpdate] = []

    # Always have "created" status
    timeline.append(StatusUpdate(status="pending", timestamp=created_at, message="Заказ создан"))

    if is_pickup:
        if status in ["preparing", "ready", "completed", "cancelled", "rejected"]:
            timeline.append(
                StatusUpdate(
                    status="preparing",
                    timestamp=str(order_dict.get("updated_at", created_at)),
                    message="Заказ подтверждён и готовится",
                )
            )
        if status in ["ready", "completed"]:
            timeline.append(
                StatusUpdate(
                    status="ready",
                    timestamp=str(order_dict.get("updated_at", created_at)),
                    message="Заказ готов к выдаче",
                )
            )
        if status == "completed":
            timeline.append(
                StatusUpdate(
                    status="completed",
                    timestamp=str(order_dict.get("updated_at", created_at)),
                    message="Заказ выдан",
                )
            )
    else:
        if status in ["preparing", "ready", "delivering", "completed"]:
            timeline.append(
                StatusUpdate(
                    status="preparing",
                    timestamp=str(order_dict.get("updated_at", created_at)),
                    message="Заказ подтверждён и готовится",
                )
            )
        if status in ["delivering", "completed"]:
            timeline.append(
                StatusUpdate(
                    status="delivering",
                    timestamp=str(order_dict.get("updated_at", created_at)),
                    message="Заказ в пути",
                )
            )
        if status == "completed":
            timeline.append(
                StatusUpdate(
                    status="completed",
                    timestamp=str(order_dict.get("updated_at", created_at)),
                    message="Заказ доставлен",
                )
            )

    if status in ["rejected", "cancelled"]:
        timeline.append(
            StatusUpdate(
                status="cancelled",
                timestamp=str(order_dict.get("updated_at", created_at)),
                message="Заказ отменён",
            )
        )

    # Estimate ready time based on status
    estimated_ready = None
    if not is_pickup and status in ["preparing", "ready", "confirmed"]:
        # Calculate estimated time based on when order was confirmed
        from datetime import datetime, timedelta
        try:
            updated_at = order_dict.get("updated_at")
            if updated_at:
                if isinstance(updated_at, str):
                    confirmed_time = datetime.fromisoformat(updated_at.replace('Z', '+00:00'))
                else:
                    confirmed_time = updated_at
                
                # Estimate 25 minutes from confirmation time
                estimated_ready_dt = confirmed_time + timedelta(minutes=25)
                now = datetime.now(confirmed_time.tzinfo) if confirmed_time.tzinfo else datetime.now()
                
                # If still in future, show time
                if estimated_ready_dt > now:
                    minutes_left = int((estimated_ready_dt - now).total_seconds() / 60)
                    if minutes_left > 0:
                        estimated_ready = f"через {minutes_left} мин"
                    else:
                        estimated_ready = "скоро готов"
                else:
                    estimated_ready = "скоро готов"
            else:
                estimated_ready = "через 20-30 мин"
        except Exception:
            estimated_ready = "через 20-30 мин"

    return OrderTimeline(
        booking_id=booking_id,
        current_status=status,
        timeline=timeline,
        estimated_ready_time=estimated_ready,
    )


@router.post("/calculate-delivery", response_model=DeliveryResult)
async def calculate_delivery(
    request: DeliveryCalculation,
    db=Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """Calculate delivery cost for given address.

    Args:
        request: DeliveryCalculation with city, address, store_id

    Returns:
        DeliveryResult with cost and availability
    """
    return await calculate_delivery_cost(
        request.city,
        request.address,
        request.store_id,
        db,
        delivery_lat=request.delivery_lat,
        delivery_lon=request.delivery_lon,
    )


@router.get("/{booking_id}/qr")
async def get_order_qr_code(
    booking_id: int,
    db=Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """Get QR code for order pickup (standalone endpoint).

    Args:
        booking_id: Booking ID (v24+ order_id from unified orders table)

    Returns:
        JSON with base64 QR code

    Raises:
        404: Order not found
        400: QR code not available for this status
    """
    user_id = _require_user_id(user)

    # v24+: try unified orders table first
    order = await db.get_order(booking_id)
    if not order and await _bookings_archive_exists(db):
        # Fallback: check archived bookings
        try:
            result = await db.execute(
                "SELECT * FROM bookings_archive WHERE booking_id = %s",
                (booking_id,)
            )
            if result:
                order = result[0]
        except Exception as e:
            logger.warning(
                "Failed to fetch bookings_archive QR for booking_id=%s: %s",
                booking_id,
                e,
            )
    
    if not order:
        raise HTTPException(status_code=404, detail="Заказ не найден")

    order_dict = dict(order) if not isinstance(order, dict) else order
    if int(order_dict.get("user_id") or 0) != user_id:
        raise HTTPException(status_code=403, detail="Access denied")
    raw_status = order_dict.get("order_status", order_dict.get("status", "pending"))
    status = UnifiedOrderStatus.normalize(str(raw_status).strip().lower())
    pickup_code = order_dict.get("pickup_code", order_dict.get("booking_code", ""))

    # v23+ statuses: preparing, ready
    if status not in ["preparing", "confirmed", "ready"]:
        raise HTTPException(
            status_code=400, detail="QR код доступен только для подтвержденных заказов"
        )

    if not pickup_code:
        raise HTTPException(status_code=400, detail="Код заказа не найден")

    qr_code = generate_qr_code(pickup_code)

    return {
        "booking_id": booking_id,
        "booking_code": pickup_code,
        "qr_code": qr_code,
        "message": "Покажите этот QR код в магазине",
    }
