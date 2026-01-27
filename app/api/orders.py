"""
Order Tracking API for Telegram Mini App
Provides real-time order status, QR codes, and delivery tracking
"""
import base64
import io
import os
from typing import Any

import qrcode
from aiogram import Bot
from aiogram.types import BufferedInputFile
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel

from app.api.webapp.common import get_current_user, get_optional_user
from app.core.order_math import (
    calc_delivery_fee,
    calc_items_total,
    calc_quantity,
    calc_total_price,
    parse_cart_items,
)
from app.core.utils import normalize_city
from app.application.orders.submit_payment_proof import submit_payment_proof
from app.domain.order import PaymentStatus as DomainPaymentStatus
from app.infra.db.orders_repo import OrdersRepository
from app.interfaces.bot.presenters.payment_proof_messages import (
    build_admin_payment_proof_caption,
    build_admin_payment_proof_keyboard,
)
from app.services.unified_order_service import OrderStatus as UnifiedOrderStatus, PaymentStatus

router = APIRouter(prefix="/api/v1/orders", tags=["orders"])

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


def _bookings_archive_exists(db) -> bool:
    """Check if bookings_archive table exists (optional migration)."""
    try:
        if hasattr(db, "get_connection"):
            with db.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT to_regclass('public.bookings_archive')")
                row = cursor.fetchone()
                return bool(row and row[0])
        if hasattr(db, "execute"):
            result = db.execute("SELECT to_regclass('public.bookings_archive')")
            return bool(result and result[0] and result[0][0])
    except Exception:
        return False
    return False


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
    """Calculate delivery cost based on distance and city."""
    store = db.get_store(store_id)
    if not store:
        return DeliveryResult(
            can_deliver=False,
            delivery_cost=None,
            estimated_time=None,
            min_order_amount=None,
            message="Store not found",
        )

    store_dict = dict(store) if not isinstance(store, dict) else store
    store_city_raw = store_dict.get("city", "") or ""
    normalized_city = normalize_city(city or "")
    normalized_store_city = normalize_city(store_city_raw)

    # Check if same city using normalized values to align Uzbek/Russian inputs
    if normalized_city.lower() != normalized_store_city.lower():
        return DeliveryResult(
            can_deliver=False,
            delivery_cost=None,
            estimated_time=None,
            min_order_amount=None,
            message=f"Delivery available only in {store_city_raw or 'store city'}",
        )

    delivery_costs = {
        "???????": 15000,  # 15k sum
        "?????????": 12000,
        "??????": 10000,
        "????????": 10000,
        "???????": 10000,
        "Tashkent": 15000,
        "Samarqand": 12000,
        "Bukhara": 10000,
        "Namangan": 10000,
        "Fergana": 10000,
    }

    base_cost = delivery_costs.get(normalized_store_city or normalized_city, 15000)
    min_order = 50000  # 50k sum minimum

    return DeliveryResult(
        can_deliver=True,
        delivery_cost=float(base_cost),
        estimated_time="30-45 min",
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
        items_total = calc_items_total(cart_items)
        qty_total = calc_quantity(cart_items)
        quantity = qty_total if qty_total > 0 else quantity

        if total_price and not delivery_cost:
            delivery_cost = calc_delivery_fee(
                total_price,
                items_total,
                delivery_price=booking_dict.get("delivery_price"),
                order_type=order_type,
            )

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
            items_total = calc_items_total([{"price": discount_price, "quantity": quantity}])
            total_price = float(calc_total_price(items_total, delivery_cost or 0))

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
        payment_status=payment_status,
        order_type=order_type,
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


@router.get("")
async def get_user_orders(
    db=Depends(get_db),
    user: dict | None = Depends(get_optional_user),
):
    """Get user's orders from unified orders table (pickup + delivery)."""
    user_id = int(user.get("id") or 0) if isinstance(user, dict) else 0
    if user_id <= 0:
        return []

    orders: list[dict[str, Any]] = []
    raw_orders: list[Any] = []

    try:
        with db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT
                    o.order_id,
                    o.order_status,
                    o.order_type,
                    o.pickup_code,
                    o.delivery_address,
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
                (int(user_id),),
            )
            raw_orders = cursor.fetchall() or []
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
                qty = int(it.get("quantity") or 1)
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
            qty = int(r.get("quantity") or 1)
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

        orders.append(
            {
                "order_id": order_id,
                "order_type": order_type,
                "order_status": order_status,
                "status": order_status,
                "pickup_code": r.get("pickup_code"),
                "delivery_address": r.get("delivery_address"),
                "total_price": total_price,
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
                "store_phone": r.get("store_phone"),
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
    """Upload payment proof for delivery orders (admin verification flow)."""
    bot = get_bot()
    user_id = int(user.get("id") or 0)
    if user_id <= 0:
        raise HTTPException(status_code=401, detail="Authentication required")

    photo_data = await photo.read()
    if not photo_data:
        raise HTTPException(status_code=400, detail="No photo provided")

    order = db.get_order(order_id) if hasattr(db, "get_order") else None
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    if isinstance(order, dict):
        order_type = order.get("order_type")
        order_user_id = order.get("user_id")
        delivery_address = order.get("delivery_address")
        cart_items_json = order.get("cart_items")
        store_name = order.get("store_name", "")
        total_price = order.get("total_price", 0)
        delivery_fee = order.get("delivery_fee") or order.get("delivery_price") or 0
        payment_method = order.get("payment_method")
        payment_status_raw = order.get("payment_status")
        payment_proof_photo_id = order.get("payment_proof_photo_id")
    else:
        order_type = getattr(order, "order_type", None)
        order_user_id = getattr(order, "user_id", None)
        delivery_address = getattr(order, "delivery_address", None)
        cart_items_json = getattr(order, "cart_items", None)
        store_name = getattr(order, "store_name", "")
        total_price = getattr(order, "total_price", 0)
        delivery_fee = getattr(order, "delivery_fee", 0)
        payment_method = getattr(order, "payment_method", None)
        payment_status_raw = getattr(order, "payment_status", None)
        payment_proof_photo_id = getattr(order, "payment_proof_photo_id", None)

    try:
        order_user_id_int = int(order_user_id) if order_user_id is not None else None
    except Exception:
        order_user_id_int = None

    if order_user_id_int != user_id:
        raise HTTPException(status_code=403, detail="Access denied")

    if order_type != "delivery":
        raise HTTPException(
            status_code=400, detail=f"Order type is '{order_type}', not 'delivery'"
        )

    payment_status = DomainPaymentStatus.normalize(
        payment_status_raw,
        payment_method=payment_method,
        payment_proof_photo_id=payment_proof_photo_id,
    )
    if payment_status == DomainPaymentStatus.PROOF_SUBMITTED:
        raise HTTPException(status_code=409, detail="Payment proof already submitted")
    if payment_status == DomainPaymentStatus.CONFIRMED:
        raise HTTPException(status_code=409, detail="Payment already confirmed")
    if payment_status == DomainPaymentStatus.NOT_REQUIRED:
        raise HTTPException(status_code=400, detail="Payment proof not required")
    if payment_status not in (DomainPaymentStatus.AWAITING_PROOF, DomainPaymentStatus.REJECTED):
        raise HTTPException(status_code=400, detail="Payment proof not allowed")

    photo_file = BufferedInputFile(photo_data, filename=photo.filename or "payment_proof.jpg")

    customer = db.get_user(order_user_id) if hasattr(db, "get_user") else None
    customer_name = ""
    customer_phone = ""
    if customer:
        if isinstance(customer, dict):
            customer_name = customer.get("first_name", "")
            customer_phone = customer.get("phone", "")
        else:
            customer_name = getattr(customer, "first_name", "")
            customer_phone = getattr(customer, "phone", "")

    cart_items = parse_cart_items(cart_items_json)

    admin_msg = build_admin_payment_proof_caption(
        order_id=order_id,
        customer_name=customer_name,
        customer_phone=customer_phone,
        store_name=store_name,
        delivery_address=delivery_address,
        cart_items=cart_items,
        total_price=total_price,
        delivery_fee=delivery_fee,
        lang="ru",
    )

    admin_keyboard = build_admin_payment_proof_keyboard(order_id)

    admin_ids: list[int] = []
    if hasattr(db, "get_all_users"):
        all_users = db.get_all_users()
        for u in all_users:
            role = u.get("role") if isinstance(u, dict) else getattr(u, "role", None)
            u_id = u.get("user_id") if isinstance(u, dict) else getattr(u, "user_id", None)
            if role == "admin" and u_id:
                admin_ids.append(u_id)

    if not admin_ids:
        admin_id_env = int(os.getenv("ADMIN_ID", "0"))
        if admin_id_env:
            admin_ids.append(admin_id_env)

    if not admin_ids:
        raise HTTPException(status_code=500, detail="No admin configured")

    sent_count = 0
    file_id = None
    for admin_id in admin_ids:
        try:
            sent_msg = await bot.send_photo(
                chat_id=admin_id,
                photo=photo_file,
                caption=admin_msg,
                parse_mode="HTML",
                reply_markup=admin_keyboard,
            )
            if not file_id and sent_msg.photo:
                file_id = sent_msg.photo[-1].file_id
            sent_count += 1
        except Exception:
            continue

    if sent_count == 0:
        raise HTTPException(status_code=500, detail="Failed to send to admins")

    if not file_id:
        raise HTTPException(status_code=500, detail="Failed to persist payment proof")

    repo = OrdersRepository(db)
    result = await submit_payment_proof(
        order_id,
        actor_user_id=user_id,
        proof_file_id=file_id,
        repo=repo,
    )
    if not result.ok:
        raise HTTPException(status_code=500, detail="Failed to persist payment proof")

    return {
        "success": True,
        "message": f"Payment proof sent to {sent_count} admin(s) for verification",
    }


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
    
    # Fallback: check archived bookings for old orders (optional table)
    if _bookings_archive_exists(db):
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
        except Exception:
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
    if not order and _bookings_archive_exists(db):
        # Fallback: check archived bookings
        try:
            result = db.execute(
                "SELECT * FROM bookings_archive WHERE booking_id = %s",
                (booking_id,)
            )
            if result:
                order = result[0]
        except Exception:
            pass
    
    if not order:
        raise HTTPException(status_code=404, detail="Заказ не найден")

    order_dict = dict(order) if not isinstance(order, dict) else order
    if order_dict.get("user_id") != user.get("id"):
        raise HTTPException(status_code=403, detail="Access denied")
    raw_status = order_dict.get("order_status", order_dict.get("status", "pending"))
    status = UnifiedOrderStatus.normalize(str(raw_status).strip().lower())
    created_at = str(order_dict.get("created_at", ""))

    # Build timeline based on status
    timeline = []

    # Always have "created" status
    timeline.append(StatusUpdate(status="pending", timestamp=created_at, message="Заказ создан"))

    # v23+ statuses: pending, preparing, ready, delivering, completed, rejected, cancelled
    if status in ["preparing", "confirmed", "ready", "delivering", "completed"]:
        timeline.append(
            StatusUpdate(
                status="preparing",
                timestamp=str(order_dict.get("updated_at", created_at)),
                message="Заказ подтвержден магазином",
            )
        )

    if status in ["ready", "delivering", "completed"]:
        timeline.append(
            StatusUpdate(
                status="ready",
                timestamp=str(order_dict.get("updated_at", created_at)),
                message="Заказ готов к выдаче",
            )
        )

    if status == "delivering":
        timeline.append(
            StatusUpdate(
                status="delivering",
                timestamp=str(order_dict.get("updated_at", created_at)),
                message="Buyurtma yetkazib berilmoqda",
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

    if status == "rejected":
        timeline.append(
            StatusUpdate(
                status="rejected",
                timestamp=str(order_dict.get("updated_at", created_at)),
                message="Buyurtma rad etildi",
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
    if not order and _bookings_archive_exists(db):
        # Fallback: check archived bookings
        try:
            result = db.execute(
                "SELECT * FROM bookings_archive WHERE booking_id = %s",
                (booking_id,)
            )
            if result:
                order = result[0]
        except Exception:
            pass
    
    if not order:
        raise HTTPException(status_code=404, detail="Заказ не найден")

    order_dict = dict(order) if not isinstance(order, dict) else order
    if order_dict.get("user_id") != user.get("id"):
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
