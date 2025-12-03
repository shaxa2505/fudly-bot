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
    # Convert to dict if needed
    booking_dict = dict(booking) if not isinstance(booking, dict) else booking

    booking_id = booking_dict["id"]
    offer_id = booking_dict["offer_id"]

    # Get offer details
    offer = db.get_offer(offer_id)
    offer_dict = dict(offer) if offer and not isinstance(offer, dict) else offer or {}

    # Get store details
    store_id = offer_dict.get("store_id", 0)
    store = db.get_store(store_id)
    store_dict = dict(store) if store and not isinstance(store, dict) else store or {}

    # Calculate total price
    quantity = booking_dict.get("quantity", 1)
    discount_price = offer_dict.get("discount_price", 0)
    delivery_cost = booking_dict.get("delivery_cost", 0) or 0
    total_price = (discount_price * quantity) + delivery_cost

    # Generate QR code for pickup orders
    booking_code = booking_dict.get("booking_code", "")
    status = booking_dict.get("status", "pending")
    qr_code = None
    if status in ["confirmed", "ready"] and booking_code:
        qr_code = generate_qr_code(booking_code)

    return OrderStatus(
        booking_id=booking_id,
        booking_code=booking_code,
        status=status,
        created_at=str(booking_dict.get("created_at", "")),
        updated_at=str(booking_dict.get("updated_at")) if booking_dict.get("updated_at") else None,
        offer_title=offer_dict.get("title", "Товар"),
        offer_photo=offer_dict.get("photo"),
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
async def get_order_status(booking_id: int, db=Depends(get_db)):
    """Get current order status with all details including QR code.

    Args:
        booking_id: Booking ID

    Returns:
        OrderStatus with full order details and QR code (if applicable)

    Raises:
        404: Booking not found
    """
    booking = db.get_booking(booking_id)
    if not booking:
        raise HTTPException(status_code=404, detail="Заказ не найден")

    return format_booking_to_order_status(booking, db)


@router.get("/{booking_id}/timeline", response_model=OrderTimeline)
async def get_order_timeline(booking_id: int, db=Depends(get_db)):
    """Get order status timeline/history.

    Args:
        booking_id: Booking ID

    Returns:
        OrderTimeline with status change history

    Raises:
        404: Booking not found
    """
    booking = db.get_booking(booking_id)
    if not booking:
        raise HTTPException(status_code=404, detail="Заказ не найден")

    booking_dict = dict(booking) if not isinstance(booking, dict) else booking
    status = booking_dict.get("status", "pending")
    created_at = str(booking_dict.get("created_at", ""))

    # Build timeline based on status
    timeline = []

    # Always have "created" status
    timeline.append(StatusUpdate(status="pending", timestamp=created_at, message="Заказ создан"))

    if status in ["confirmed", "ready", "completed"]:
        timeline.append(
            StatusUpdate(
                status="confirmed",
                timestamp=str(booking_dict.get("updated_at", created_at)),
                message="Заказ подтвержден магазином",
            )
        )

    if status in ["ready", "completed"]:
        timeline.append(
            StatusUpdate(
                status="ready",
                timestamp=str(booking_dict.get("updated_at", created_at)),
                message="Заказ готов к выдаче",
            )
        )

    if status == "completed":
        timeline.append(
            StatusUpdate(
                status="completed",
                timestamp=str(booking_dict.get("updated_at", created_at)),
                message="Заказ завершен",
            )
        )

    if status == "cancelled":
        timeline.append(
            StatusUpdate(
                status="cancelled",
                timestamp=str(booking_dict.get("updated_at", created_at)),
                message="Заказ отменен",
            )
        )

    # Estimate ready time (30 min from now for MVP)
    estimated_ready = None
    if status == "confirmed":
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
async def get_order_qr_code(booking_id: int, db=Depends(get_db)):
    """Get QR code for order pickup (standalone endpoint).

    Args:
        booking_id: Booking ID

    Returns:
        JSON with base64 QR code

    Raises:
        404: Booking not found
        400: QR code not available for this status
    """
    booking = db.get_booking(booking_id)
    if not booking:
        raise HTTPException(status_code=404, detail="Заказ не найден")

    booking_dict = dict(booking) if not isinstance(booking, dict) else booking
    status = booking_dict.get("status", "pending")
    booking_code = booking_dict.get("booking_code", "")

    if status not in ["confirmed", "ready"]:
        raise HTTPException(
            status_code=400, detail="QR код доступен только для подтвержденных заказов"
        )

    if not booking_code:
        raise HTTPException(status_code=400, detail="Код заказа не найден")

    qr_code = generate_qr_code(booking_code)

    return {
        "booking_id": booking_id,
        "booking_code": booking_code,
        "qr_code": qr_code,
        "message": "Покажите этот QR код в магазине",
    }
