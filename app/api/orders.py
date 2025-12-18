"""
Order Tracking API for Telegram Mini App
Provides real-time order status, QR codes, and delivery tracking
"""
import base64
import io
from typing import Any

import qrcode
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.api.webapp.common import get_current_user

router = APIRouter(prefix="/api/v1/orders", tags=["orders"])

# Global database instance (set by api_server.py)
_db_instance = None


def get_db():
    """Dependency to get database instance."""
    if _db_instance is None:
        raise HTTPException(status_code=503, detail="Database not available")
    return _db_instance


def set_orders_db(db):
    """Set database instance for orders module."""
    global _db_instance
    _db_instance = db


# ==================== MODELS ====================


class OrderStatus(BaseModel):
    """Order status details."""

    booking_id: int
    booking_code: str
    status: str  # pending, confirmed, ready, completed, cancelled
    created_at: str
    updated_at: str | None

    # Offer details
    offer_title: str
    offer_photo: str | None
    quantity: int
    total_price: float

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

    user_id: int
    city: str
    address: str
    store_id: int


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


def calculate_delivery_cost(city: str, address: str, store_id: int, db) -> DeliveryResult:
    """Calculate delivery cost based on distance and city.

    Args:
        city: User city
        address: Delivery address
        store_id: Store ID
        db: Database instance

    Returns:
        DeliveryResult with cost and availability
    """
    # Get store info
    store = db.get_store(store_id)
    if not store:
        return DeliveryResult(
            can_deliver=False,
            delivery_cost=None,
            estimated_time=None,
            min_order_amount=None,
            message="Магазин не найден",
        )

    store_dict = dict(store) if not isinstance(store, dict) else store
    store_city = store_dict.get("city", "")

    # Check if same city
    if city.lower() != store_city.lower():
        return DeliveryResult(
            can_deliver=False,
            delivery_cost=None,
            estimated_time=None,
            min_order_amount=None,
            message=f"Доставка доступна только в городе {store_city}",
        )

    # Simple distance-based pricing (in production, use real geolocation)
    # For MVP: flat rate per city
    delivery_costs = {
        "Ташкент": 15000,  # 15k sum
        "Самарканд": 12000,
        "Бухара": 10000,
        "Андижан": 10000,
        "Фергана": 10000,
    }

    base_cost = delivery_costs.get(city, 15000)
    min_order = 50000  # 50k sum minimum

    return DeliveryResult(
        can_deliver=True,
        delivery_cost=float(base_cost),
        estimated_time="30-45 мин",
        min_order_amount=float(min_order),
        message=None,
    )


def format_booking_to_order_status(booking: Any, db) -> OrderStatus:
    """Convert database booking row to OrderStatus model.

    Args:
        booking: Database booking row
        db: Database instance

    Returns:
        OrderStatus model
    """
    import json

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

    status = booking_dict.get("order_status") or booking_dict.get("status") or "pending"

    # Best-effort order_type detection (unified table vs legacy booking)
    delivery_address = booking_dict.get("delivery_address")
    order_type = booking_dict.get("order_type") or ("delivery" if delivery_address else "pickup")

    booking_code = booking_dict.get("pickup_code") or booking_dict.get("booking_code") or ""

    # Store details: prefer explicit store_id on the row, fallback to offer.store_id
    store_id = int(booking_dict.get("store_id") or 0)

    # Cart order support (delivery cart = 1 row with cart_items)
    is_cart = int(booking_dict.get("is_cart_order") or booking_dict.get("is_cart_booking") or 0)
    cart_items_json = booking_dict.get("cart_items")
    cart_items: list[dict[str, Any]] = []
    if is_cart and cart_items_json:
        try:
            cart_items = (
                json.loads(cart_items_json) if isinstance(cart_items_json, str) else cart_items_json
            )
        except Exception:
            cart_items = []

    offer_id = booking_dict.get("offer_id")
    quantity = int(booking_dict.get("quantity") or 1)
    delivery_cost = booking_dict.get("delivery_cost", 0) or 0

    offer_dict: dict[str, Any] = {}
    store_dict: dict[str, Any] = {}

    if cart_items:
        # Use first cart item as representative
        first_item = cart_items[0]
        first_offer_id = first_item.get("offer_id")
        if not store_id:
            store_id = int(first_item.get("store_id") or 0)

        try:
            # Prefer total_price from DB row (includes delivery)
            total_price = float(booking_dict.get("total_price") or 0)
        except Exception:
            total_price = 0.0

        # Calculate delivery_cost if possible (total - items)
        items_total = 0
        qty_total = 0
        for item in cart_items:
            item_qty = int(item.get("quantity") or 1)
            item_price = int(item.get("price") or 0)
            qty_total += item_qty
            items_total += item_price * item_qty
        quantity = qty_total if qty_total > 0 else quantity

        if total_price and items_total and not delivery_cost:
            try:
                derived_delivery = float(total_price) - float(items_total)
                delivery_cost = derived_delivery if derived_delivery > 0 else 0
            except Exception:
                pass

        if first_offer_id:
            offer = db.get_offer(int(first_offer_id))
            offer_dict = dict(offer) if offer and not isinstance(offer, dict) else offer or {}
    else:
        # Single-item booking/order
        if offer_id:
            offer = db.get_offer(int(offer_id))
            offer_dict = dict(offer) if offer and not isinstance(offer, dict) else offer or {}

        # If total_price is stored on orders table, prefer it
        if booking_dict.get("total_price") is not None:
            try:
                total_price = float(booking_dict.get("total_price") or 0)
            except Exception:
                total_price = 0.0
        else:
            discount_price = int(offer_dict.get("discount_price") or 0)
            total_price = float((discount_price * quantity) + (delivery_cost or 0))

        if not store_id:
            store_id = int(offer_dict.get("store_id") or 0)

    if store_id:
        store = db.get_store(store_id)
        store_dict = dict(store) if store and not isinstance(store, dict) else store or {}

    # Generate QR code only for pickup orders when the code is available
    qr_code = None
    if order_type == "pickup" and status in ["preparing", "confirmed", "ready"] and booking_code:
        qr_code = generate_qr_code(booking_code)

    return OrderStatus(
        booking_id=int(booking_id),
        booking_code=booking_code,
        status=status,
        created_at=str(booking_dict.get("created_at", "")),
        updated_at=str(booking_dict.get("updated_at")) if booking_dict.get("updated_at") else None,
        offer_title=offer_dict.get("title", "Товар"),
        offer_photo=offer_dict.get("photo") or offer_dict.get("photo_id"),
        quantity=quantity,
        total_price=total_price,
        store_id=store_id,
        store_name=store_dict.get("name", "Магазин"),
        store_address=store_dict.get("address"),
        store_phone=store_dict.get("phone"),
        pickup_time=str(booking_dict.get("pickup_time"))
        if booking_dict.get("pickup_time")
        else None,
        pickup_address=booking_dict.get("pickup_address"),
        delivery_address=booking_dict.get("delivery_address"),
        delivery_cost=float(delivery_cost) if delivery_cost else None,
        qr_code=qr_code,
    )


# ==================== ENDPOINTS ====================


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
    # v24+: try unified orders table first
    order = db.get_order(booking_id)
    if order:
        order_dict = dict(order) if not isinstance(order, dict) else order
        if order_dict.get("user_id") != user.get("id"):
            raise HTTPException(status_code=403, detail="Access denied")
        # Convert order to booking format for compatibility
        return format_booking_to_order_status(order, db)
    
    # Fallback: check archived bookings for old orders
    try:
        booking = db.execute(
            "SELECT * FROM bookings_archive WHERE booking_id = %s",
            (booking_id,)
        )
        if booking:
            booking_dict = dict(booking[0]) if not isinstance(booking[0], dict) else booking[0]
            if booking_dict.get("user_id") != user.get("id"):
                raise HTTPException(status_code=403, detail="Access denied")
            return format_booking_to_order_status(booking[0], db)
    except:
        pass
    
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
    # v24+: try unified orders table first
    order = db.get_order(booking_id)
    if not order:
        # Fallback: check archived bookings
        try:
            result = db.execute(
                "SELECT * FROM bookings_archive WHERE booking_id = %s",
                (booking_id,)
            )
            if result:
                order = result[0]
        except:
            pass
    
    if not order:
        raise HTTPException(status_code=404, detail="Заказ не найден")

    order_dict = dict(order) if not isinstance(order, dict) else order
    if order_dict.get("user_id") != user.get("id"):
        raise HTTPException(status_code=403, detail="Access denied")
    status = order_dict.get("order_status", order_dict.get("status", "pending"))
    created_at = str(order_dict.get("created_at", ""))

    # Build timeline based on status
    timeline = []

    # Always have "created" status
    timeline.append(StatusUpdate(status="pending", timestamp=created_at, message="Заказ создан"))

    # v23+ statuses: pending, preparing, ready, delivering, completed, rejected, cancelled
    if status in ["preparing", "confirmed", "ready", "completed"]:
        timeline.append(
            StatusUpdate(
                status="preparing",
                timestamp=str(order_dict.get("updated_at", created_at)),
                message="Заказ подтвержден магазином",
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
                message="Заказ завершен",
            )
        )

    if status == "cancelled":
        timeline.append(
            StatusUpdate(
                status="cancelled",
                timestamp=str(order_dict.get("updated_at", created_at)),
                message="Заказ отменен",
            )
        )

    # Estimate ready time based on status
    estimated_ready = None
    if status in ["preparing", "confirmed"]:
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
async def calculate_delivery(request: DeliveryCalculation, db=Depends(get_db)):
    """Calculate delivery cost for given address.

    Args:
        request: DeliveryCalculation with user_id, city, address, store_id

    Returns:
        DeliveryResult with cost and availability
    """
    return calculate_delivery_cost(request.city, request.address, request.store_id, db)


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
    # v24+: try unified orders table first
    order = db.get_order(booking_id)
    if not order:
        # Fallback: check archived bookings
        try:
            result = db.execute(
                "SELECT * FROM bookings_archive WHERE booking_id = %s",
                (booking_id,)
            )
            if result:
                order = result[0]
        except:
            pass
    
    if not order:
        raise HTTPException(status_code=404, detail="Заказ не найден")

    order_dict = dict(order) if not isinstance(order, dict) else order
    if order_dict.get("user_id") != user.get("id"):
        raise HTTPException(status_code=403, detail="Access denied")
    status = order_dict.get("order_status", order_dict.get("status", "pending"))
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
