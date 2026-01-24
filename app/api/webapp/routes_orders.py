from __future__ import annotations

import html
import json
from typing import Any

from aiogram import Bot
from aiogram.utils.keyboard import InlineKeyboardBuilder
from fastapi import APIRouter, Depends, HTTPException, Header
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.core.sanitize import sanitize_phone
from app.core.security import validator
from app.services.unified_order_service import (
    OrderItem,
    OrderStatus,
    PaymentStatus,
    get_unified_order_service,
)
from app.core.idempotency import (
    build_request_hash,
    check_or_reserve_key,
    normalize_idempotency_key,
    store_idempotency_response,
)

from .common import (
    CreateOrderRequest,
    OrderResponse,
    get_current_user,
    get_db,
    get_val,
    is_offer_active,
    logger,
    normalize_price,
    settings,
)

router = APIRouter()


class CancelOrderResponse(BaseModel):
    success: bool
    status: str


def _require_user_id(user: dict[str, Any]) -> int:
    user_id = int(user.get("id") or 0)
    if user_id == 0:
        raise HTTPException(status_code=401, detail="Authentication required")
    return user_id


def _normalize_phone(raw_phone: str | None) -> str:
    """Sanitize + validate phone; return empty string if invalid."""
    if not raw_phone:
        return ""
    sanitized = sanitize_phone(raw_phone)
    if not sanitized or not validator.validate_phone(sanitized):
        return ""
    return sanitized


def _update_phone_if_valid(db: Any, user_id: int, raw_phone: str | None) -> None:
    sanitized_phone = _normalize_phone(raw_phone)
    if not sanitized_phone:
        return
    try:
        if hasattr(db, "update_user_phone"):
            user_model = db.get_user_model(user_id)
            current_phone = get_val(user_model, "phone") if user_model else None
            if not current_phone or current_phone != sanitized_phone:
                db.update_user_phone(user_id, sanitized_phone)
    except Exception as e:  # pragma: no cover - defensive
        logger.warning(f"Could not update user phone for {user_id}: {e}")


def _resolve_required_phone(db: Any, user_id: int, raw_phone: str | None) -> str:
    """Return canonical phone: use DB if present, otherwise allow first-time set."""
    user_model = db.get_user_model(user_id) if hasattr(db, "get_user_model") else None
    stored_phone = _normalize_phone((get_val(user_model, "phone") if user_model else None))
    candidate = _normalize_phone(raw_phone)

    if stored_phone:
        if candidate and candidate != stored_phone:
            raise HTTPException(
                status_code=400,
                detail="Phone does not match registered number. Update it in the bot.",
            )
        return stored_phone

    if candidate:
        _update_phone_if_valid(db, user_id, candidate)
        return candidate

    raise HTTPException(status_code=400, detail="Phone is required")


def _status_for_creation_error(detail: str) -> int:
    """Map order creation error text to HTTP status code."""
    lower = detail.lower()
    if "insufficient stock" in lower or "unavailable" in lower:
        return 409
    return 400


def _load_offers_and_store(items: list[Any], db: Any) -> tuple[dict[int, Any], int]:
    if not items:
        raise HTTPException(status_code=400, detail="No items provided")
    offers_by_id: dict[int, Any] = {}
    store_ids: set[int] = set()
    for item in items:
        offer = db.get_offer(item.offer_id) if hasattr(db, "get_offer") else None
        if not offer or not is_offer_active(offer):
            raise HTTPException(status_code=400, detail=f"Offer not found: {item.offer_id}")
        offers_by_id[item.offer_id] = offer
        store_id = int(get_val(offer, "store_id") or 0)
        if store_id:
            store_ids.add(store_id)

    if len(store_ids) > 1:
        raise HTTPException(status_code=400, detail="Only one store per order is supported")
    if not store_ids:
        raise HTTPException(status_code=400, detail="Invalid store data")

    return offers_by_id, next(iter(store_ids))


def _validate_min_order(
    db: Any,
    store_id: int,
    items: list[Any],
    offers_by_id: dict[int, Any],
) -> None:
    total_check = 0.0
    for item in items:
        offer = offers_by_id.get(item.offer_id)
        if not offer:
            continue
        price = normalize_price(get_val(offer, "discount_price", 0))
        total_check += price * item.quantity

    store_check = db.get_store(store_id) if hasattr(db, "get_store") else None
    if not store_check:
        return
    min_order = normalize_price(get_val(store_check, "min_order_amount", 0))
    if min_order > 0 and total_check < min_order:
        raise HTTPException(
            status_code=400,
            detail=f"Minimum order amount: {min_order}. Your total: {total_check}",
        )


@router.post("/orders", response_model=OrderResponse)
async def create_order(
    order: CreateOrderRequest,
    db=Depends(get_db),
    user: dict = Depends(get_current_user),
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
    x_idempotency_key: str | None = Header(None, alias="X-Idempotency-Key"),
):
    """Create a new order from Mini App and notify partner."""

    try:
        user_id = _require_user_id(user)
        if order.user_id and order.user_id != user_id:
            logger.warning(
                "create_order user mismatch: initData=%s payload=%s", user_id, order.user_id
            )
            raise HTTPException(status_code=403, detail="User mismatch")

        for item in order.items:
            if int(item.quantity) <= 0:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid quantity for offer {item.offer_id}",
                )

        is_delivery = bool(order.delivery_address and order.delivery_address.strip())
        raw_payment_method = order.payment_method
        if not raw_payment_method:
            payment_method = "click" if is_delivery else "cash"
        else:
            payment_method = PaymentStatus.normalize_method(raw_payment_method)

        idem_key = normalize_idempotency_key(idempotency_key or x_idempotency_key)
        idem_hash = None
        if idem_key:
            items_payload = [
                {"offer_id": int(item.offer_id), "quantity": int(item.quantity)}
                for item in order.items
            ]
            items_payload.sort(key=lambda x: x["offer_id"])
            idem_payload = {
                "items": items_payload,
                "delivery_address": order.delivery_address or "",
                "delivery_lat": order.delivery_lat,
                "delivery_lon": order.delivery_lon,
                "phone": order.phone or "",
                "comment": order.comment or "",
                "payment_method": payment_method,
                "order_type": "delivery" if is_delivery else "pickup",
            }
            idem_hash = build_request_hash(idem_payload)
            idem_result = check_or_reserve_key(db, idem_key, user_id, idem_hash)
            if idem_result.get("status") in ("cached", "conflict", "in_progress"):
                return JSONResponse(
                    content=idem_result.get("payload", {}),
                    status_code=int(idem_result.get("status_code", 409)),
                )

        resolved_phone = _resolve_required_phone(db, user_id, order.phone)

        offers_by_id, store_id = _load_offers_and_store(order.items, db)

        if payment_method not in ("cash", "click"):
            raise HTTPException(status_code=400, detail="Unsupported payment method")

        if is_delivery and payment_method != "click":
            raise HTTPException(
                status_code=400,
                detail="Only Click is allowed for delivery orders",
            )

        if is_delivery:
            _validate_min_order(db, store_id, order.items, offers_by_id)

        created_items: list[dict[str, Any]] = []

        order_service = get_unified_order_service()

        # If unified service is available, use it as a single entry point
        if order_service and hasattr(db, "create_cart_order"):
            order_items: list[OrderItem] = []
            for item in order.items:
                offer = offers_by_id.get(item.offer_id)
                if not offer:
                    continue

                price = int(normalize_price(get_val(offer, "discount_price", 0)))
                offer_store_id = int(get_val(offer, "store_id"))
                offer_title = get_val(offer, "title", "Tovar")
                store = db.get_store(offer_store_id) if hasattr(db, "get_store") else None
                store_name = get_val(store, "name", "") if store else ""
                store_address = get_val(store, "address", "") if store else ""
                delivery_price = 0
                if is_delivery and store:
                    delivery_price = int(normalize_price(get_val(store, "delivery_price", 15000)))

                order_items.append(
                    OrderItem(
                        offer_id=item.offer_id,
                        store_id=offer_store_id,
                        title=offer_title,
                        price=price,
                        original_price=price,
                        quantity=item.quantity,
                        store_name=store_name,
                        store_address=store_address,
                        delivery_price=delivery_price,
                    )
                )

            try:
                from app.services.unified_order_service import OrderResult  # type: ignore

                result: OrderResult = await order_service.create_order(
                    user_id=user_id,
                    items=order_items,
                    order_type="delivery" if is_delivery else "pickup",
                    delivery_address=order.delivery_address if is_delivery else None,
                    delivery_lat=order.delivery_lat if is_delivery else None,
                    delivery_lon=order.delivery_lon if is_delivery else None,
                    comment=order.comment,
                    payment_method=payment_method,
                    notify_customer=True,
                    notify_sellers=True,
                    telegram_notify=True,
                )
            except Exception as e:  # pragma: no cover - defensive
                logger.error(f"Unified order service failed for webapp order: {e}")
                result = None

            if result and result.success:
                # Map unified result back to old created_items shape
                if is_delivery:
                    oid = result.order_ids[0] if result.order_ids else 0
                    delivery_price = int(order_items[0].delivery_price) if order_items else 0
                    for idx, item_obj in enumerate(order_items):
                        total = (item_obj.price * item_obj.quantity) + (
                            delivery_price if idx == 0 else 0
                        )
                        created_items.append(
                            {
                                "id": oid,
                                "type": "order",
                                "offer_id": item_obj.offer_id,
                                "quantity": item_obj.quantity,
                                "total": total,
                                "offer_title": item_obj.title,
                                "store_id": item_obj.store_id,
                            }
                        )
                        logger.info(f"✅ Created unified delivery ORDER {oid} for user {user_id}")
                else:
                    pickup_code = result.pickup_codes[0] if result.pickup_codes else None
                    oid = result.order_ids[0] if result.order_ids else 0
                    for item_obj in order_items:
                        total = item_obj.price * item_obj.quantity
                        created_items.append(
                            {
                                "id": oid,
                                "type": "order",
                                "offer_id": item_obj.offer_id,
                                "quantity": item_obj.quantity,
                                "total": total,
                                "offer_title": item_obj.title,
                                "store_id": item_obj.store_id,
                                "pickup_code": pickup_code,
                            }
                        )
                        logger.info(f"✅ Created unified pickup ORDER {oid} for user {user_id}")
            else:
                logger.error(
                    "Unified order service returned failure for webapp order: %s",
                    result.error_message if result else "no result",
                )
                detail = result.error_message if result else "Failed to create order"
                status_code = _status_for_creation_error(detail) if result else 500
                raise HTTPException(status_code=status_code, detail=detail)

        # UnifiedOrderService already notifies sellers (WebSocket + optional Telegram).

        order_id = created_items[0]["id"] if created_items else 0
        total_amount = sum(b["total"] for b in created_items)
        total_items = sum(b["quantity"] for b in created_items)
        logger.info(
            "ORDER_CREATED: id=%s, user=%s, type=%s, total=%s, items=%s, source=webapp_api",
            order_id,
            user_id,
            "delivery" if is_delivery else "pickup",
            int(total_amount),
            total_items,
        )

        response_payload = OrderResponse(
            order_id=order_id, status="pending", total=total_amount, items_count=total_items
        ).model_dump()
        if idem_key and idem_hash:
            store_idempotency_response(
                db,
                idem_key,
                user_id,
                idem_hash,
                response_payload,
                200,
            )
        return OrderResponse(**response_payload)

    except HTTPException as exc:
        if "idem_key" in locals() and idem_key and idem_hash:
            store_idempotency_response(
                db,
                idem_key,
                user_id,
                idem_hash,
                {"detail": exc.detail},
                exc.status_code,
            )
        raise
    except Exception as e:  # pragma: no cover - defensive
        logger.error(f"Error creating order: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e
    finally:
        pass


@router.get("/orders")
async def get_orders(db=Depends(get_db), user: dict = Depends(get_current_user)):
    """Get user's orders and bookings for WebApp."""
    user_id = _require_user_id(user)

    orders: list[dict[str, Any]] = []
    raw_orders: list[Any] = []

    try:
        if hasattr(db, "get_connection"):
            with db.get_connection() as conn:
                cursor = conn.cursor()
                orders_query = """
                    SELECT
                        o.order_id,
                        o.order_status,
                        o.order_type,
                        o.pickup_code,
                        o.delivery_address,
                        o.total_price,
                        o.delivery_price,
                        o.item_title,
                        o.item_price,
                        o.item_original_price,
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
                """
                fallback_query = """
                    SELECT
                        o.order_id,
                        o.order_status,
                        NULL AS order_type,
                        o.pickup_code,
                        o.delivery_address,
                        o.total_price,
                        NULL AS delivery_price,
                        o.item_title,
                        o.item_price,
                        o.item_original_price,
                        o.quantity,
                        o.payment_method,
                        o.payment_status,
                        o.payment_proof_photo_id,
                        o.is_cart_order,
                        o.cart_items,
                        o.created_at,
                        NULL AS updated_at,
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
                """
                try:
                    cursor.execute(orders_query, (int(user_id),))
                except Exception as e:
                    message = str(e)
                    if "delivery_price" in message or "order_type" in message or "updated_at" in message:
                        logger.warning(
                            "Orders query fallback (missing columns): %s", message
                        )
                        cursor.execute(fallback_query, (int(user_id),))
                    else:
                        raise
                raw_orders = cursor.fetchall() or []
                if raw_orders and not hasattr(raw_orders[0], "get"):
                    columns = [col[0] for col in cursor.description or []]
                    raw_orders = [dict(zip(columns, row)) for row in raw_orders]
                logger.info(
                    f"📦 Fetched {len(raw_orders)} raw orders from database for user {user_id}"
                )
    except Exception as e:
        logger.warning(f"Webapp get_orders failed to fetch orders: {e}")
        raw_orders = []

    for r in raw_orders:
        if not hasattr(r, "get"):
            continue

        order_id = r.get("order_id")
        if not order_id:
            continue

        order_type = r.get("order_type") or ("delivery" if r.get("delivery_address") else "pickup")
        order_status = OrderStatus.normalize(str(r.get("order_status") or "pending").lower())

        raw_payment_method = r.get("payment_method")
        if raw_payment_method:
            payment_method = PaymentStatus.normalize_method(raw_payment_method)
        else:
            payment_method = "click" if order_type == "delivery" else "cash"
        payment_status = PaymentStatus.normalize(
            r.get("payment_status"),
            payment_method=payment_method,
            payment_proof_photo_id=r.get("payment_proof_photo_id"),
        )

        is_cart = int(r.get("is_cart_order") or 0) == 1
        cart_items_json = r.get("cart_items")

        items: list[dict[str, Any]] = []
        items_total = 0
        qty_total = 0

        if is_cart and cart_items_json:
            try:
                cart_items = (
                    json.loads(cart_items_json)
                    if isinstance(cart_items_json, str)
                    else cart_items_json
                )
            except Exception:
                cart_items = []

            for it in cart_items or []:
                title = it.get("title") or "Tovar"
                qty = int(it.get("quantity") or 1)
                price = int(it.get("price") or 0)
                items_total += price * qty
                qty_total += qty
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
            price = int(r.get("item_price") or r.get("offer_price") or 0)
            title = r.get("item_title") or r.get("offer_title") or "Tovar"
            photo = r.get("offer_photo") or r.get("offer_photo_id")
            items_total = price * qty
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

        total_price = int(r.get("total_price") or 0)
        delivery_fee = 0
        if order_type == "delivery":
            delivery_fee_raw = r.get("delivery_price")
            if delivery_fee_raw is not None:
                try:
                    delivery_fee = int(delivery_fee_raw)
                except Exception:
                    delivery_fee = 0
            else:
                delivery_fee = max(0, total_price - items_total)

        primary_item = items[0] if items else {}
        offer_title = primary_item.get("title") or primary_item.get("offer_title")
        offer_photo = primary_item.get("photo")

        orders.append(
            {
                "id": order_id,
                "order_id": order_id,
                "booking_id": order_id,
                "offer_id": primary_item.get("offer_id"),
                "offer_title": offer_title,
                "offer_photo": offer_photo,
                "status": order_status,
                "order_status": order_status,
                "order_type": order_type,
                "pickup_code": r.get("pickup_code"),
                "booking_code": r.get("pickup_code"),
                "payment_method": payment_method,
                "payment_status": payment_status,
                "payment_proof_photo_id": r.get("payment_proof_photo_id"),
                "delivery_address": r.get("delivery_address"),
                "delivery_fee": delivery_fee,
                "total_price": total_price,
                "quantity": qty_total,
                "created_at": str(r.get("created_at") or ""),
                "updated_at": str(r.get("updated_at") or "") if r.get("updated_at") else None,
                "store_id": r.get("store_id"),
                "store_name": r.get("store_name"),
                "store_address": r.get("store_address"),
                "store_phone": r.get("store_phone"),
                "items": items,
            }
        )

    bookings = []
    if hasattr(db, "get_user_bookings"):
        try:
            raw_bookings = db.get_user_bookings(int(user_id)) or []
            for b in raw_bookings:
                if isinstance(b, tuple):
                    offer_photo = None
                    if len(b) > 1 and b[1] and hasattr(db, "get_offer"):
                        try:
                            offer = db.get_offer(b[1])
                            if offer:
                                offer_photo = get_val(offer, "photo") or get_val(offer, "photo_id")
                        except Exception:
                            pass

                    bookings.append(
                        {
                            "booking_id": b[0] if len(b) > 0 else None,
                            "offer_id": b[1] if len(b) > 1 else None,
                            "user_id": b[2] if len(b) > 2 else None,
                            "status": OrderStatus.normalize(
                                str(b[3] if len(b) > 3 else "pending").lower()
                            ),
                            "booking_code": b[4] if len(b) > 4 else None,
                            "pickup_time": str(b[5]) if len(b) > 5 and b[5] else None,
                            "quantity": b[6] if len(b) > 6 else 1,
                            "created_at": str(b[7]) if len(b) > 7 and b[7] else None,
                            "offer_title": b[8] if len(b) > 8 else None,
                            "total_price": (b[9] or 0) * (b[6] or 1) if len(b) > 9 else 0,
                            "store_name": b[11] if len(b) > 11 else None,
                            "store_address": b[12] if len(b) > 12 else None,
                            "offer_photo": offer_photo,
                        }
                    )
                elif isinstance(b, dict):
                    booking = {}
                    for key, value in b.items():
                        if hasattr(value, "isoformat"):
                            booking[key] = value.isoformat()
                        else:
                            booking[key] = value
                    booking["status"] = OrderStatus.normalize(
                        str(booking.get("status") or "pending").lower()
                    )
                    bookings.append(booking)
        except Exception as e:
            logger.warning(f"Webapp get_orders failed to fetch bookings: {e}")
            raw_bookings = []

    if not bookings and hasattr(db, "get_connection"):
        try:
            with db.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    SELECT
                        b.booking_id,
                        b.offer_id,
                        b.user_id,
                        b.status,
                        b.booking_code,
                        b.pickup_time,
                        COALESCE(b.quantity, 1) as quantity,
                        b.created_at,
                        COALESCE(o.title, 'Tovar') as title,
                        COALESCE(o.discount_price, 0) as discount_price,
                        o.available_until,
                        COALESCE(s.name, 'Dokon') as name,
                        COALESCE(s.address, '') as address,
                        s.city
                    FROM bookings_archive b
                    LEFT JOIN offers o ON b.offer_id = o.offer_id
                    LEFT JOIN stores s ON o.store_id = s.store_id
                    WHERE b.user_id = %s
                    ORDER BY b.created_at DESC
                    """,
                    (int(user_id),),
                )
                raw_bookings = cursor.fetchall() or []
        except Exception as e:
            # bookings_archive is optional (only exists after v24 migration)
            logger.debug(f"Webapp get_orders fallback bookings_archive skipped: {e}")
            raw_bookings = []

        for b in raw_bookings:
            if isinstance(b, tuple):
                offer_photo = None
                if len(b) > 1 and b[1] and hasattr(db, "get_offer"):
                    try:
                        offer = db.get_offer(b[1])
                        if offer:
                            offer_photo = get_val(offer, "photo") or get_val(offer, "photo_id")
                    except Exception:
                        pass

                bookings.append(
                    {
                        "booking_id": b[0] if len(b) > 0 else None,
                        "offer_id": b[1] if len(b) > 1 else None,
                        "user_id": b[2] if len(b) > 2 else None,
                        "status": OrderStatus.normalize(
                            str(b[3] if len(b) > 3 else "pending").lower()
                        ),
                        "booking_code": b[4] if len(b) > 4 else None,
                        "pickup_time": str(b[5]) if len(b) > 5 and b[5] else None,
                        "quantity": b[6] if len(b) > 6 else 1,
                        "created_at": str(b[7]) if len(b) > 7 and b[7] else None,
                        "offer_title": b[8] if len(b) > 8 else None,
                        "total_price": (b[9] or 0) * (b[6] or 1) if len(b) > 9 else 0,
                        "store_name": b[11] if len(b) > 11 else None,
                        "store_address": b[12] if len(b) > 12 else None,
                        "offer_photo": offer_photo,
                    }
                )
            elif isinstance(b, dict):
                booking = {}
                for key, value in b.items():
                    if hasattr(value, "isoformat"):
                        booking[key] = value.isoformat()
                    else:
                        booking[key] = value
                booking["status"] = OrderStatus.normalize(
                    str(booking.get("status") or "pending").lower()
                )
                bookings.append(booking)

    logger.info(
        f"📊 get_orders result for user {user_id}: {len(orders)} orders, {len(bookings)} bookings"
    )
    return {"bookings": bookings, "orders": orders}


@router.post("/orders/{order_id}/cancel", response_model=CancelOrderResponse)
async def cancel_order(
    order_id: int,
    db=Depends(get_db),
    user: dict = Depends(get_current_user),
) -> CancelOrderResponse:
    """Cancel order/booking from Mini App (customer)."""
    user_id = _require_user_id(user)

    entity = None
    entity_type = "order"

    if hasattr(db, "get_order"):
        entity = db.get_order(order_id)
        if entity and int(get_val(entity, "user_id", 0)) != user_id:
            raise HTTPException(status_code=403, detail="Access denied")

    if entity is None and hasattr(db, "get_booking"):
        entity_type = "booking"
        entity = db.get_booking(order_id)
        if entity and int(get_val(entity, "user_id", 0)) != user_id:
            raise HTTPException(status_code=403, detail="Access denied")

    if entity is None:
        raise HTTPException(status_code=404, detail="Order not found")

    current_status_raw = get_val(entity, "order_status") or get_val(entity, "status") or "pending"
    current_status = OrderStatus.normalize(str(current_status_raw).lower())
    if current_status in ("completed", "cancelled", "rejected"):
        return CancelOrderResponse(success=True, status=str(current_status))
    if current_status != "pending":
        raise HTTPException(
            status_code=400,
            detail="Order can only be cancelled while pending",
        )

    order_service = get_unified_order_service()
    if not order_service:
        raise HTTPException(status_code=500, detail="Order service unavailable")

    ok = await order_service.cancel_order(order_id, entity_type)
    if not ok:
        raise HTTPException(status_code=500, detail="Failed to cancel order")

    return CancelOrderResponse(success=True, status="cancelled")


async def notify_partner_webapp_order(
    bot: Bot,
    db: Any,
    owner_id: int,
    entity_id: int,
    offer_title: str,
    quantity: int,
    total: float,
    user_id: int,
    delivery_address: str | None,
    phone: str | None,
    photo: str | None,
    is_delivery: bool = False,
) -> None:
    """Send notification to partner about new webapp order."""

    partner_lang = db.get_user_language(owner_id) if hasattr(db, "get_user_language") else "uz"
    user = db.get_user(user_id) if hasattr(db, "get_user") else None

    def get_user_val(obj: Any, key: str, default: Any | None = None) -> Any | None:
        if isinstance(obj, dict):
            return obj.get(key, default)
        return getattr(obj, key, default) if obj else default

    customer_name = get_user_val(user, "first_name", "Клиент")
    customer_phone = phone or get_user_val(user, "phone", "Не указан")

    def _esc(val: Any) -> str:
        return html.escape(str(val)) if val is not None else ""

    currency = "so'm" if partner_lang == "uz" else "сум"
    unit_label = "dona" if partner_lang == "uz" else "шт"

    if partner_lang == "uz":
        text = (
            f"🔔 <b>YANGI BUYURTMA (Mini App)!</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n\n"
            f"🛒 <b>{_esc(offer_title)}</b>\n"
            f"📦 Miqdor: <b>{quantity}</b> {unit_label}\n"
            f"💰 Jami: <b>{int(total):,}</b> {currency}\n\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"👤 <b>Xaridor:</b>\n"
            f"   Ism: {_esc(customer_name)}\n"
            f"   📱 <code>{_esc(customer_phone)}</code>\n"
        )
        if is_delivery:
            text += "\n🚚 <b>Yetkazib berish</b>\n"
            if delivery_address:
                text += f"   📍 {_esc(delivery_address)}\n"
        else:
            text += "\n🏪 <b>O'zi olib ketadi</b>\n"
        text += "━━━━━━━━━━━━━━━━━━━━"
        confirm_text = "✅ Tasdiqlash"
        reject_text = "❌ Rad etish"
    else:
        text = (
            f"🔔 <b>НОВЫЙ ЗАКАЗ (Mini App)!</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n\n"
            f"🛒 <b>{_esc(offer_title)}</b>\n"
            f"📦 Количество: <b>{quantity}</b> {unit_label}\n"
            f"💰 Итого: <b>{int(total):,}</b> {currency}\n\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"👤 <b>Покупатель:</b>\n"
            f"   Имя: {_esc(customer_name)}\n"
            f"   📱 <code>{_esc(customer_phone)}</code>\n"
        )
        if is_delivery:
            text += "\n🚚 <b>Доставка</b>\n"
            if delivery_address:
                text += f"   📍 {_esc(delivery_address)}\n"
        else:
            text += "\n🏪 <b>Самовывоз</b>\n"
        text += "━━━━━━━━━━━━━━━━━━━━"
        confirm_text = "✅ Подтвердить"
        reject_text = "❌ Отклонить"

    kb = InlineKeyboardBuilder()
    kb.button(text=confirm_text, callback_data=f"order_confirm_{entity_id}")
    kb.button(text=reject_text, callback_data=f"order_reject_{entity_id}")
    kb.adjust(2)

    try:
        sent_msg = None
        if photo:
            try:
                sent_msg = await bot.send_photo(
                    owner_id,
                    photo=photo,
                    caption=text,
                    parse_mode="HTML",
                    reply_markup=kb.as_markup(),
                )
            except Exception:  # pragma: no cover - fallback to text
                sent_msg = None

        if not sent_msg:
            sent_msg = await bot.send_message(
                owner_id, text, parse_mode="HTML", reply_markup=kb.as_markup()
            )

        if sent_msg and hasattr(db, "set_order_seller_message_id"):
            try:
                db.set_order_seller_message_id(entity_id, sent_msg.message_id)
                logger.info(
                    "Saved seller_message_id=%s for order#%s",
                    sent_msg.message_id,
                    entity_id,
                )
            except Exception as save_err:  # pragma: no cover - defensive
                logger.error(f"Failed to save seller_message_id: {save_err}")
    except Exception as e:  # pragma: no cover - defensive
        logger.error(f"Failed to notify partner {owner_id}: {e}")
