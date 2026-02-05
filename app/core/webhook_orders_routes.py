"""Order routes for webhook Mini App API."""
from __future__ import annotations

import os
from datetime import datetime, timedelta
from typing import Any, Callable

from aiohttp import web

from app.core.idempotency import (
    build_request_hash,
    check_or_reserve_key,
    normalize_idempotency_key,
    store_idempotency_response,
)
from app.core.order_math import (
    calc_delivery_fee,
    calc_items_total,
    calc_quantity,
    parse_cart_items,
)
from app.core.webhook_api_utils import add_cors_headers
from app.core.webhook_helpers import _delivery_cash_enabled, _is_offer_active, get_offer_value
from app.interfaces.bot.presenters.payment_proof_messages import (
    build_admin_payment_proof_caption,
    build_admin_payment_proof_keyboard,
)
from logging_config import logger


def build_order_handlers(
    bot: Any,
    db: Any,
    get_authenticated_user_id: Callable[[web.Request], int | None],
):
    _get_authenticated_user_id = get_authenticated_user_id

    async def api_create_order(request: web.Request) -> web.Response:
        """POST /api/v1/orders - Create order from Mini App cart."""
        try:
            from app.services.unified_order_service import (
                OrderItem as UnifiedOrderItem,
            )
            from app.services.unified_order_service import (
                OrderResult,
                PaymentStatus,
                get_unified_order_service,
            )

            data = await request.json()
            logger.info(f"API /orders request: {data}")

            # Extract order data
            items = data.get("items", [])
            authenticated_user_id = _get_authenticated_user_id(request)
            if not authenticated_user_id:
                return add_cors_headers(
                    web.json_response({"error": "Authentication required"}, status=401)
                )

            user_id = authenticated_user_id
            # Support both order_type and delivery_type field names
            delivery_type = data.get("order_type") or data.get("delivery_type", "pickup")
            phone = data.get("phone", "")
            # Support both address and delivery_address field names
            address = data.get("delivery_address") or data.get("address", "")
            notes = data.get("notes") or data.get("comment", "")
            payment_proof = (
                data.get("payment_proof")
                or data.get("payment_proof_photo_id")
                or data.get("payment_screenshot")
            )
            if payment_proof:
                logger.info("Ignoring payment_proof in create_order payload (disabled)")
            payment_proof = None

            if not items:
                return add_cors_headers(
                    web.json_response({"error": "No items in order"}, status=400)
                )

            is_delivery = delivery_type == "delivery"
            payment_method = data.get("payment_method")
            if not payment_method:
                payment_method = "click" if is_delivery else "cash"
            payment_method = PaymentStatus.normalize_method(payment_method)
            if payment_method not in ("cash", "click"):
                return add_cors_headers(
                    web.json_response({"error": "Unsupported payment method"}, status=400)
                )
            if is_delivery and payment_method == "cash" and not _delivery_cash_enabled():
                return add_cors_headers(
                    web.json_response(
                        {"error": "Cash is not allowed for delivery orders"}, status=400
                    )
                )

            idempotency_key = normalize_idempotency_key(
                request.headers.get("Idempotency-Key")
                or request.headers.get("X-Idempotency-Key")
            )
            idem_hash = None
            if idempotency_key:
                items_payload = []
                for item in items:
                    offer_id = item.get("offer_id") or item.get("id")
                    if offer_id is None:
                        continue
                    try:
                        offer_id_val = int(offer_id)
                    except (TypeError, ValueError):
                        continue
                    try:
                        quantity_val = int(item.get("quantity", 1))
                    except (TypeError, ValueError):
                        quantity_val = 0
                    items_payload.append(
                        {"offer_id": offer_id_val, "quantity": quantity_val}
                    )
                items_payload.sort(key=lambda x: x["offer_id"])
                idem_payload = {
                    "items": items_payload,
                    "delivery_address": address or "",
                    "phone": phone or "",
                    "comment": notes or "",
                    "payment_method": payment_method,
                    "order_type": delivery_type or ("delivery" if is_delivery else "pickup"),
                }
                idem_hash = build_request_hash(idem_payload)
                idem_result = check_or_reserve_key(db, idempotency_key, user_id, idem_hash)
                if idem_result.get("status") in ("cached", "conflict", "in_progress"):
                    return add_cors_headers(
                        web.json_response(
                            idem_result.get("payload", {}),
                            status=int(idem_result.get("status_code", 409)),
                        )
                    )

            def _respond(payload: dict[str, Any], status_code: int) -> web.Response:
                if idempotency_key and idem_hash:
                    store_idempotency_response(
                        db,
                        idempotency_key,
                        user_id,
                        idem_hash,
                        payload,
                        status_code,
                    )
                return add_cors_headers(web.json_response(payload, status=status_code))

            if is_delivery and (not address or not str(address).strip()):
                return _respond({"error": "Delivery address required"}, 400)
            if is_delivery and payment_method == "cash" and not _delivery_cash_enabled():
                return _respond(
                    {"error": "Cash is not allowed for delivery orders"},
                    400,
                )

            # Try unified order service first
            created_bookings: list[dict[str, Any]] = []
            failed_items: list[dict[str, Any]] = []

            order_service = get_unified_order_service()
            if order_service and hasattr(db, "create_cart_order"):
                order_items: list[UnifiedOrderItem] = []

                for item in items:
                    offer_id = item.get("id") or item.get("offer_id")
                    try:
                        quantity = int(item.get("quantity", 1))
                    except (TypeError, ValueError):
                        return _respond({"error": "Invalid quantity"}, 400)
                    if quantity <= 0:
                        return _respond(
                            {"error": f"Invalid quantity for offer {offer_id}"},
                            400,
                        )

                    if not offer_id:
                        failed_items.append({"item": item, "error": "Missing offer_id"})
                        continue

                    offer = db.get_offer(int(offer_id)) if hasattr(db, "get_offer") else None
                    if not offer:
                        failed_items.append({"offer_id": offer_id, "error": "Offer not found"})
                        continue
                    if not _is_offer_active(offer):
                        failed_items.append({"offer_id": offer_id, "error": "Offer not available"})
                        continue

                    price = int(get_offer_value(offer, "discount_price", 0) or 0)
                    store_id = int(get_offer_value(offer, "store_id"))
                    title = get_offer_value(offer, "title", "Товар")

                    store = db.get_store(store_id) if hasattr(db, "get_store") else None
                    store_name = get_offer_value(store, "name", "") if store else ""
                    store_address = get_offer_value(store, "address", "") if store else ""
                    delivery_price = 0
                    if is_delivery and store:
                        delivery_price = int(
                            get_offer_value(store, "delivery_price", 15000) or 15000
                        )

                    order_items.append(
                        UnifiedOrderItem(
                            offer_id=int(offer_id),
                            store_id=store_id,
                            title=title,
                            price=price,
                            original_price=price,
                            quantity=quantity,
                            store_name=store_name,
                            store_address=store_address,
                            delivery_price=delivery_price,
                        )
                    )
                if not order_items:
                    return _respond(
                        {
                            "success": False,
                            "error": "No valid items in order",
                            "failed": failed_items,
                        },
                        400,
                    )

                try:
                    result: OrderResult = await order_service.create_order(
                        user_id=int(user_id),
                        items=order_items,
                        order_type="delivery" if is_delivery else "pickup",
                        delivery_address=address if is_delivery else None,
                        payment_method=payment_method,
                        notify_customer=True,
                        notify_sellers=True,
                        telegram_notify=True,
                    )

                    logger.info(
                        f"Mini App order created via unified_order_service: "
                        f"user={user_id}, type={delivery_type}, "
                        f"items={len(order_items)}, success={result.success if result else False}"
                    )
                except Exception as e:  # pragma: no cover - defensive
                    logger.error(f"Unified order service failed for mini app order: {e}")
                    result = None

                if result and result.success:
                    order_id = result.order_ids[0] if result.order_ids else None
                    pickup_code = result.pickup_codes[0] if result.pickup_codes else None
                    total_qty = sum(int(getattr(i, "quantity", 1) or 1) for i in order_items)
                    first_offer_id = order_items[0].offer_id if order_items else None

                    if order_id:
                        created_bookings.append(
                            {
                                "booking_id": order_id,
                                "booking_code": pickup_code if not is_delivery else None,
                                "offer_id": first_offer_id,
                                "quantity": total_qty,
                                "items_count": len(order_items),
                            }
                        )

                    resolved_payment_status = PaymentStatus.initial_for_method(payment_method)

                    awaiting_payment = resolved_payment_status in (
                        PaymentStatus.AWAITING_PAYMENT,
                        PaymentStatus.AWAITING_PROOF,
                        PaymentStatus.PROOF_SUBMITTED,
                    )

                    response = {
                        "success": True,
                        "order_id": order_id,
                        "order_ids": result.order_ids,
                        "pickup_code": pickup_code,
                        "pickup_codes": result.pickup_codes,
                        "payment_method": payment_method,
                        "payment_status": resolved_payment_status,
                        "awaiting_payment": awaiting_payment,
                        "bookings": created_bookings,
                        "failed": failed_items,
                        "message": result.error_message or "OK",
                    }
                    return _respond(response, 201)
                elif result and not result.success:
                    detail = result.error_message or "Failed to create order"
                    status_code = (
                        409 if ("insufficient stock" in detail.lower() or "unavailable" in detail.lower()) else 400
                    )
                    return _respond(
                        {
                            "success": False,
                            "error": detail,
                            "failed": getattr(result, "failed_items", []) or failed_items,
                        },
                        status_code,
                    )

            # Fallback: create an order row directly (no new bookings for Mini App)
            if (
                not created_bookings
                and not failed_items
                and order_items
                and hasattr(db, "create_cart_order")
            ):
                db_items = [
                    {
                        "offer_id": int(i.offer_id),
                        "store_id": int(i.store_id),
                        "quantity": int(i.quantity),
                        "price": int(i.price),
                        "delivery_price": int(i.delivery_price) if is_delivery else 0,
                        "title": i.title,
                        "store_name": i.store_name,
                        "store_address": i.store_address,
                    }
                    for i in order_items
                ]

                try:
                    # Use UnifiedOrderService for consistent order creation and notifications
                    order_service = get_unified_order_service()
                    if not order_service:
                        logger.error("UnifiedOrderService not available in webhook_server")
                        failed_items.append({"error": "Order service not available"})
                        return _respond(
                            {"success": False, "error": "Order service not available"},
                            500,
                        )

                    # Convert db_items to OrderItem format
                    order_items_list = [
                        OrderItem(
                            offer_id=int(item["offer_id"]),
                            store_id=int(item["store_id"]),
                            title=item.get("title", ""),
                            price=int(item.get("price", 0)),
                            original_price=int(item.get("price", 0)),
                            quantity=int(item.get("quantity", 1)),
                            store_name=item.get("store_name", ""),
                            store_address=item.get("store_address", ""),
                            delivery_price=int(item.get("delivery_price", 0)) if is_delivery else 0,
                        )
                        for item in db_items
                    ]

                    result = await order_service.create_order(
                        user_id=int(user_id),
                        items=order_items_list,
                        order_type="delivery" if is_delivery else "pickup",
                        delivery_address=address if is_delivery else None,
                        payment_method=payment_method,
                        notify_customer=True,
                        notify_sellers=True,
                        telegram_notify=True,
                    )

                    if result.success and result.order_ids:
                        # Map result to expected format
                        for idx, order_id in enumerate(result.order_ids):
                            created_bookings.append(
                                {
                                    "booking_id": order_id,
                                    "booking_code": result.pickup_codes[idx]
                                    if result.pickup_codes and idx < len(result.pickup_codes)
                                    else None,
                                    "offer_id": order_items_list[0].offer_id
                                    if order_items_list
                                    else None,
                                    "quantity": result.total_items,
                                    "items_count": len(order_items_list),
                                }
                            )
                    else:
                        failed_items.append(
                            {"error": result.error_message or "Failed to create order"}
                        )

                except Exception as e:
                    logger.error(
                        f"Error creating order via UnifiedOrderService: {e}", exc_info=True
                    )
                    failed_items.append({"error": str(e)})

            # Return result
            response = {
                "success": len(created_bookings) > 0,
                "bookings": created_bookings,
                "failed": failed_items,
                "message": f"Создано {len(created_bookings)} бронирований"
                if created_bookings
                else "Не удалось создать заказ",
            }

            status_code = 201 if created_bookings else 400
            return _respond(response, status_code)

        except Exception as e:
            logger.error(f"API create order error: {e}", exc_info=True)
            if (
                "idempotency_key" in locals()
                and "idem_hash" in locals()
                and "user_id" in locals()
                and idempotency_key
                and idem_hash
                and user_id
            ):
                try:
                    store_idempotency_response(
                        db,
                        idempotency_key,
                        user_id,
                        idem_hash,
                        {"error": str(e), "success": False},
                        500,
                    )
                except Exception:
                    pass
            return add_cors_headers(
                web.json_response({"error": str(e), "success": False}, status=500)
            )


    async def api_user_orders(request: web.Request) -> web.Response:
        """GET /api/v1/orders - Get user's orders/bookings and delivery orders."""
        try:
            from app.services.unified_order_service import OrderStatus, PaymentStatus

            authenticated_user_id = _get_authenticated_user_id(request)
            if not authenticated_user_id:
                return add_cors_headers(
                    web.json_response({"error": "Authentication required"}, status=401)
                )

            user_id = authenticated_user_id

            # Unified orders list (pickup + delivery) from orders table
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
                logger.warning(f"API user orders: failed to fetch orders: {e}")
                raw_orders = []

            for r in raw_orders:
                if not hasattr(r, "get"):
                    continue

                order_id = r.get("order_id")
                if not order_id:
                    continue

                order_type = r.get("order_type") or (
                    "delivery" if r.get("delivery_address") else "pickup"
                )
                order_status_raw = r.get("order_status") or "pending"
                order_status = OrderStatus.normalize(str(order_status_raw).strip().lower())

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
                    cart_items = parse_cart_items(cart_items_json)
                    items_total = calc_items_total(cart_items)
                    qty_total = calc_quantity(cart_items)

                    for it in cart_items:
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

                total_price = int(r.get("total_price") or 0)
                delivery_fee = calc_delivery_fee(
                    total_price,
                    items_total,
                    order_type=order_type,
                )

                primary_item = items[0] if items else {}
                offer_title = primary_item.get("title") or primary_item.get("offer_title")
                offer_photo = primary_item.get("photo")

                orders.append(
                    {
                        "id": order_id,
                        "order_id": order_id,
                        "booking_id": order_id,  # legacy field used by UI
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
                        "updated_at": str(r.get("updated_at") or "")
                        if r.get("updated_at")
                        else None,
                        "store_id": r.get("store_id"),
                        "store_name": r.get("store_name"),
                        "store_address": r.get("store_address"),
                        "store_phone": r.get("store_phone"),
                        "items": items,
                    }
                )

            # Get bookings (old system)
            bookings = []
            if hasattr(db, "get_user_bookings"):
                raw_bookings = db.get_user_bookings(int(user_id)) or []
                for b in raw_bookings:
                    # Convert tuple to dict
                    # SQL: booking_id(0), offer_id(1), user_id(2), status(3), booking_code(4),
                    #      pickup_time(5), quantity(6), created_at(7), title(8), discount_price(9),
                    #      available_until(10), store_name(11), store_address(12), store_city(13)
                    if isinstance(b, tuple):
                        # Get photo for offer
                        offer_photo = None
                        if len(b) > 1 and b[1] and hasattr(db, "get_offer"):
                            try:
                                offer = db.get_offer(b[1])
                                if offer:
                                    # Try photo or photo_id field
                                    photo_file_id = get_offer_value(
                                        offer, "photo"
                                    ) or get_offer_value(offer, "photo_id")
                                    if photo_file_id:
                                        try:
                                            file = await bot.get_file(photo_file_id)
                                            if file and file.file_path:
                                                offer_photo = f"https://api.telegram.org/file/bot{bot.token}/{file.file_path}"
                                        except Exception:
                                            pass
                            except Exception:
                                pass

                        bookings.append(
                            {
                                "booking_id": b[0] if len(b) > 0 else None,
                                "offer_id": b[1] if len(b) > 1 else None,
                                "user_id": b[2] if len(b) > 2 else None,
                                "status": b[3] if len(b) > 3 else "pending",
                                "booking_code": b[4] if len(b) > 4 else None,
                                "pickup_time": str(b[5]) if len(b) > 5 and b[5] else None,
                                "quantity": b[6] if len(b) > 6 else 1,
                                "created_at": str(b[7]) if len(b) > 7 and b[7] else None,
                                "offer_title": b[8] if len(b) > 8 else None,
                                "total_price": calc_items_total(
                                    [{"price": b[9] or 0, "quantity": b[6] or 1}]
                                )
                                if len(b) > 9
                                else 0,
                                "store_name": b[11] if len(b) > 11 else None,
                                "store_address": b[12] if len(b) > 12 else None,
                                "offer_photo": offer_photo,
                            }
                        )
                    elif isinstance(b, dict):
                        # Serialize datetime fields
                        booking = {}
                        for key, value in b.items():
                            if hasattr(value, "isoformat"):
                                booking[key] = value.isoformat()
                            else:
                                booking[key] = value
                        bookings.append(booking)

            response_payload = {"bookings": bookings, "orders": orders}
            if request.path.endswith("/user/orders"):
                combined = []
                combined.extend(orders)
                combined.extend(bookings)
                active_count = sum(
                    1
                    for item in combined
                    if item.get("status") in ("pending", "confirmed", "ready", "preparing")
                )
                completed_count = sum(
                    1 for item in combined if item.get("status") in ("completed", "cancelled")
                )
                response_payload = {
                    "orders": combined,
                    "total_count": len(combined),
                    "active_count": active_count,
                    "completed_count": completed_count,
                }

            return add_cors_headers(web.json_response(response_payload))

        except Exception as e:
            logger.error(f"API user orders error: {e}")
            return add_cors_headers(web.json_response({"error": str(e)}, status=500))


    async def api_order_status(request: web.Request) -> web.Response:
        """GET /api/v1/orders/{order_id}/status - Order tracking status payload."""
        try:
            authenticated_user_id = _get_authenticated_user_id(request)
            if not authenticated_user_id:
                return add_cors_headers(
                    web.json_response({"error": "Authentication required"}, status=401)
                )

            order_id_str = request.match_info.get("order_id")
            if not order_id_str:
                return add_cors_headers(
                    web.json_response({"error": "order_id required"}, status=400)
                )

            order_id = int(order_id_str)

            order = db.get_order(order_id) if hasattr(db, "get_order") else None
            if not order and hasattr(db, "get_booking"):
                booking = db.get_booking(order_id)
                if booking:
                    if int(booking.get("user_id") or 0) != int(authenticated_user_id):
                        return add_cors_headers(
                            web.json_response({"error": "Access denied"}, status=403)
                        )

                    from urllib.parse import quote

                    status = booking.get("status") or "pending"
                    status = "ready" if status == "confirmed" else status
                    booking_code = booking.get("booking_code") or ""
                    quantity = int(booking.get("quantity") or 1)

                    offer = (
                        db.get_offer(int(booking.get("offer_id")))
                        if booking.get("offer_id") and hasattr(db, "get_offer")
                        else None
                    )
                    offer_title = get_offer_value(offer, "title", "Товар") if offer else "Товар"
                    price = int(get_offer_value(offer, "discount_price", 0) or 0) if offer else 0
                    total_price = calc_items_total([{"price": price, "quantity": quantity}])
                    photo_id = (
                        get_offer_value(offer, "photo") or get_offer_value(offer, "photo_id")
                        if offer
                        else None
                    )
                    offer_photo = (
                        f"/api/v1/photo/{quote(str(photo_id), safe='')}" if photo_id else None
                    )

                    store_id = int(
                        booking.get("store_id") or get_offer_value(offer, "store_id", 0) or 0
                    )
                    store = (
                        db.get_store(store_id) if store_id and hasattr(db, "get_store") else None
                    )

                    qr_code = None
                    if booking_code and status in ("ready", "preparing", "confirmed"):
                        try:
                            from app.api.orders import generate_qr_code

                            qr_code = generate_qr_code(booking_code)
                        except Exception:
                            qr_code = None

                    return add_cors_headers(
                        web.json_response(
                            {
                                "booking_id": int(order_id),
                                "booking_code": booking_code or str(order_id),
                                "status": status,
                                "created_at": str(booking.get("created_at") or ""),
                                "updated_at": None,
                                "offer_title": offer_title,
                                "offer_photo": offer_photo,
                                "quantity": quantity,
                                "total_price": float(total_price),
                                "store_id": store_id,
                                "store_name": get_offer_value(store, "name", "Магазин")
                                if store
                                else "Магазин",
                                "store_address": get_offer_value(store, "address")
                                if store
                                else None,
                                "store_phone": get_offer_value(store, "phone") if store else None,
                                "pickup_time": str(booking.get("pickup_time"))
                                if booking.get("pickup_time")
                                else None,
                                "pickup_address": get_offer_value(store, "address")
                                if store
                                else None,
                                "delivery_address": None,
                                "delivery_cost": None,
                                "qr_code": qr_code,
                            }
                        )
                    )

            if not order:
                return add_cors_headers(web.json_response({"error": "Order not found"}, status=404))

            order_dict = dict(order) if not isinstance(order, dict) else order
            if int(order_dict.get("user_id") or 0) != int(authenticated_user_id):
                return add_cors_headers(web.json_response({"error": "Access denied"}, status=403))

            order_status = order_dict.get("order_status") or "pending"
            order_type = order_dict.get("order_type") or (
                "delivery" if order_dict.get("delivery_address") else "pickup"
            )

            store_id = int(order_dict.get("store_id") or 0)
            store = db.get_store(store_id) if store_id and hasattr(db, "get_store") else None
            store_name = get_offer_value(store, "name", "Магазин") if store else "Магазин"
            store_address = get_offer_value(store, "address") if store else None
            store_phone = get_offer_value(store, "phone") if store else None

            is_cart = int(order_dict.get("is_cart_order") or 0) == 1
            cart_items_json = order_dict.get("cart_items")

            from urllib.parse import quote

            items_total = 0
            qty_total = 0
            offer_title = "Заказ"
            offer_photo = None

            if is_cart and cart_items_json:
                cart_items = parse_cart_items(cart_items_json)

                if cart_items:
                    offer_title = cart_items[0].get("title") or "Заказ"
                    qty_total = calc_quantity(cart_items)
                    items_total = calc_items_total(cart_items)

                    first_offer_id = cart_items[0].get("offer_id")
                    if first_offer_id and hasattr(db, "get_offer"):
                        offer = db.get_offer(int(first_offer_id))
                        photo_id = (
                            get_offer_value(offer, "photo") or get_offer_value(offer, "photo_id")
                            if offer
                            else None
                        )
                        if photo_id:
                            offer_photo = f"/api/v1/photo/{quote(str(photo_id), safe='')}"
            else:
                offer_id = order_dict.get("offer_id")
                qty_total = int(order_dict.get("quantity") or 1)
                if offer_id and hasattr(db, "get_offer"):
                    offer = db.get_offer(int(offer_id))
                    offer_title = get_offer_value(offer, "title", "Товар") if offer else "Товар"
                    price = int(get_offer_value(offer, "discount_price", 0) or 0) if offer else 0
                    items_total = calc_items_total([{"price": price, "quantity": qty_total}])
                    photo_id = (
                        get_offer_value(offer, "photo") or get_offer_value(offer, "photo_id")
                        if offer
                        else None
                    )
                    if photo_id:
                        offer_photo = f"/api/v1/photo/{quote(str(photo_id), safe='')}"

            total_price = int(order_dict.get("total_price") or 0)
            delivery_cost = None
            if order_type == "delivery":
                delivery_cost = float(
                    calc_delivery_fee(
                        total_price,
                        items_total,
                        order_type=order_type,
                    )
                )

            pickup_code = order_dict.get("pickup_code") or ""
            qr_code = None
            if (
                order_type == "pickup"
                and pickup_code
                and order_status in ("preparing", "confirmed", "ready")
            ):
                try:
                    from app.api.orders import generate_qr_code

                    qr_code = generate_qr_code(pickup_code)
                except Exception:
                    qr_code = None

            result = {
                "booking_id": int(order_id),
                "booking_code": pickup_code or str(order_id),
                "status": order_status,
                "created_at": str(order_dict.get("created_at") or ""),
                "updated_at": str(order_dict.get("updated_at") or "")
                if order_dict.get("updated_at")
                else None,
                "offer_title": offer_title,
                "offer_photo": offer_photo,
                "quantity": qty_total or 1,
                "total_price": float(total_price),
                "store_id": store_id,
                "store_name": store_name,
                "store_address": store_address,
                "store_phone": store_phone,
                "pickup_time": None,
                "pickup_address": store_address if order_type == "pickup" else None,
                "delivery_address": order_dict.get("delivery_address"),
                "delivery_cost": delivery_cost,
                "qr_code": qr_code,
            }
            return add_cors_headers(web.json_response(result))
        except Exception as e:
            logger.error(f"API order status error: {e}")
            return add_cors_headers(web.json_response({"error": str(e)}, status=500))


    async def api_order_timeline(request: web.Request) -> web.Response:
        """GET /api/v1/orders/{order_id}/timeline - Order tracking timeline payload."""
        try:
            authenticated_user_id = _get_authenticated_user_id(request)
            if not authenticated_user_id:
                return add_cors_headers(
                    web.json_response({"error": "Authentication required"}, status=401)
                )

            order_id_str = request.match_info.get("order_id")
            if not order_id_str:
                return add_cors_headers(
                    web.json_response({"error": "order_id required"}, status=400)
                )

            order_id = int(order_id_str)
            order = db.get_order(order_id) if hasattr(db, "get_order") else None
            if not order and hasattr(db, "get_booking"):
                booking = db.get_booking(order_id)
                if booking:
                    if int(booking.get("user_id") or 0) != int(authenticated_user_id):
                        return add_cors_headers(
                            web.json_response({"error": "Access denied"}, status=403)
                        )

                    status = booking.get("status") or "pending"
                    status = "ready" if status == "confirmed" else status
                    created_at = str(booking.get("created_at") or "")
                    updated_at = created_at

                    timeline = [
                        {"status": "pending", "timestamp": created_at, "message": "Заказ создан"}
                    ]
                    if status in ("ready", "completed"):
                        timeline.append(
                            {"status": "ready", "timestamp": updated_at, "message": "Заказ готов"}
                        )
                    if status == "completed":
                        timeline.append(
                            {
                                "status": "completed",
                                "timestamp": updated_at,
                                "message": "Заказ завершен",
                            }
                        )
                    if status == "cancelled":
                        timeline.append(
                            {
                                "status": "cancelled",
                                "timestamp": updated_at,
                                "message": "Заказ отменен",
                            }
                        )
                    if status == "rejected":
                        timeline.append(
                            {
                                "status": "rejected",
                                "timestamp": updated_at,
                                "message": "Заказ отклонен",
                            }
                        )

                    return add_cors_headers(
                        web.json_response(
                            {
                                "booking_id": int(order_id),
                                "current_status": status,
                                "timeline": timeline,
                                "estimated_ready_time": None,
                            }
                        )
                    )

            if not order:
                return add_cors_headers(web.json_response({"error": "Order not found"}, status=404))

            order_dict = dict(order) if not isinstance(order, dict) else order
            if int(order_dict.get("user_id") or 0) != int(authenticated_user_id):
                return add_cors_headers(web.json_response({"error": "Access denied"}, status=403))

            status = order_dict.get("order_status") or "pending"
            created_at = str(order_dict.get("created_at") or "")
            updated_at = str(order_dict.get("updated_at") or created_at)
            order_type = order_dict.get("order_type") or (
                "delivery" if order_dict.get("delivery_address") else "pickup"
            )
            is_pickup = order_type == "pickup"

            timeline = [{"status": "pending", "timestamp": created_at, "message": "Заказ создан"}]

            if not is_pickup:
                if status in ("preparing", "confirmed", "ready", "delivering", "completed"):
                    timeline.append(
                        {
                            "status": "preparing",
                            "timestamp": updated_at,
                            "message": "Заказ принят и готовится",
                        }
                    )
            else:
                if status in ("preparing", "confirmed", "ready", "completed"):
                    timeline.append(
                        {"status": "ready", "timestamp": updated_at, "message": "Заказ готов"}
                    )

            if not is_pickup and status in ("ready", "delivering", "completed"):
                timeline.append(
                    {"status": "ready", "timestamp": updated_at, "message": "Заказ готов"}
                )

            if not is_pickup and status in ("delivering", "completed"):
                timeline.append(
                    {
                        "status": "delivering",
                        "timestamp": updated_at,
                        "message": "Заказ передан курьеру",
                    }
                )

            if status == "completed":
                timeline.append(
                    {
                        "status": "completed",
                        "timestamp": updated_at,
                        "message": "Заказ завершен",
                    }
                )

            if status == "cancelled":
                timeline.append(
                    {
                        "status": "cancelled",
                        "timestamp": updated_at,
                        "message": "Заказ отменен",
                    }
                )

            if status == "rejected":
                timeline.append(
                    {
                        "status": "rejected",
                        "timestamp": updated_at,
                        "message": "Заказ отклонен",
                    }
                )

            estimated_ready = None
            if not is_pickup and status in ("preparing", "confirmed"):
                try:
                    from datetime import datetime, timedelta

                    updated_dt = order_dict.get("updated_at")
                    if hasattr(updated_dt, "isoformat"):
                        confirmed_time = updated_dt
                    else:
                        confirmed_time = datetime.fromisoformat(
                            str(updated_at).replace("Z", "+00:00")
                        )

                    estimated_ready_dt = confirmed_time + timedelta(minutes=25)
                    now = (
                        datetime.now(confirmed_time.tzinfo)
                        if confirmed_time.tzinfo
                        else datetime.now()
                    )
                    if estimated_ready_dt > now:
                        minutes_left = int((estimated_ready_dt - now).total_seconds() / 60)
                        estimated_ready = (
                            f"через {minutes_left} мин" if minutes_left > 0 else "скоро готов"
                        )
                    else:
                        estimated_ready = "скоро готов"
                except Exception:
                    estimated_ready = "через 20-30 мин"

            return add_cors_headers(
                web.json_response(
                    {
                        "booking_id": int(order_id),
                        "current_status": status,
                        "timeline": timeline,
                        "estimated_ready_time": estimated_ready,
                    }
                )
            )
        except Exception as e:
            logger.error(f"API order timeline error: {e}")
            return add_cors_headers(web.json_response({"error": str(e)}, status=500))


    async def api_order_qr(request: web.Request) -> web.Response:
        """GET /api/v1/orders/{order_id}/qr - Standalone QR endpoint."""
        try:
            authenticated_user_id = _get_authenticated_user_id(request)
            if not authenticated_user_id:
                return add_cors_headers(
                    web.json_response({"error": "Authentication required"}, status=401)
                )

            order_id_str = request.match_info.get("order_id")
            if not order_id_str:
                return add_cors_headers(
                    web.json_response({"error": "order_id required"}, status=400)
                )

            order_id = int(order_id_str)
            order = db.get_order(order_id) if hasattr(db, "get_order") else None
            if not order and hasattr(db, "get_booking"):
                booking = db.get_booking(order_id)
                if booking:
                    if int(booking.get("user_id") or 0) != int(authenticated_user_id):
                        return add_cors_headers(
                            web.json_response({"error": "Access denied"}, status=403)
                        )

                    status = booking.get("status") or "pending"
                    status = "ready" if status == "confirmed" else status
                    booking_code = booking.get("booking_code") or ""

                    if status not in ("ready", "preparing", "confirmed"):
                        return add_cors_headers(
                            web.json_response(
                                {"error": "QR not available for this status"}, status=400
                            )
                        )
                    if not booking_code:
                        return add_cors_headers(
                            web.json_response({"error": "booking_code missing"}, status=400)
                        )

                    from app.api.orders import generate_qr_code

                    qr_code = generate_qr_code(booking_code)
                    return add_cors_headers(
                        web.json_response(
                            {
                                "booking_id": int(order_id),
                                "booking_code": booking_code,
                                "qr_code": qr_code,
                                "message": "Покажите этот QR код в магазине",
                            }
                        )
                    )

            if not order:
                return add_cors_headers(web.json_response({"error": "Order not found"}, status=404))

            order_dict = dict(order) if not isinstance(order, dict) else order
            if int(order_dict.get("user_id") or 0) != int(authenticated_user_id):
                return add_cors_headers(web.json_response({"error": "Access denied"}, status=403))

            status = order_dict.get("order_status") or "pending"
            pickup_code = order_dict.get("pickup_code") or ""
            order_type = order_dict.get("order_type") or (
                "delivery" if order_dict.get("delivery_address") else "pickup"
            )

            if order_type != "pickup":
                return add_cors_headers(
                    web.json_response(
                        {"error": "QR is only available for pickup orders"}, status=400
                    )
                )

            if status not in ("preparing", "confirmed", "ready"):
                return add_cors_headers(
                    web.json_response({"error": "QR not available for this status"}, status=400)
                )

            if not pickup_code:
                return add_cors_headers(
                    web.json_response({"error": "pickup_code missing"}, status=400)
                )

            from app.api.orders import generate_qr_code

            qr_code = generate_qr_code(pickup_code)
            return add_cors_headers(
                web.json_response(
                    {
                        "booking_id": int(order_id),
                        "booking_code": pickup_code,
                        "qr_code": qr_code,
                        "message": "Покажите этот QR код в магазине",
                    }
                )
            )
        except Exception as e:
            logger.error(f"API order qr error: {e}")
            return add_cors_headers(web.json_response({"error": str(e)}, status=500))


    async def api_upload_payment_proof(request: web.Request) -> web.Response:
        """POST /api/v1/orders/{order_id}/payment-proof - Upload payment screenshot.

        Payment proof uploads are disabled (Click-only payments).
        """
        return add_cors_headers(
            web.json_response(
                {"error": "Payment proof uploads are disabled"}, status=410
            )
        )
        order_id_str = request.match_info.get("order_id")
        try:
            authenticated_user_id = _get_authenticated_user_id(request)
            if not authenticated_user_id:
                return add_cors_headers(
                    web.json_response({"error": "Authentication required"}, status=401)
                )

            order_id = int(order_id_str)

            # Parse multipart form data
            reader = await request.multipart()
            photo_data = None
            filename = None

            async for part in reader:
                if part.name == "photo":
                    photo_data = await part.read()
                    filename = part.filename or "payment_proof.jpg"

            if not photo_data:
                return add_cors_headers(
                    web.json_response({"error": "No photo provided"}, status=400)
                )

            # Upload photo to Telegram
            from aiogram.types import BufferedInputFile

            photo_file = BufferedInputFile(photo_data, filename=filename)

            # Check if this is a DELIVERY ORDER (not booking)
            order = None
            if hasattr(db, "get_order"):
                order = db.get_order(order_id)
                logger.info(f"📦 Order lookup for #{order_id}: found={order is not None}")
            else:
                logger.warning("⚠️ Database doesn't have get_order method!")

            if order:
                # 🔴 DELIVERY ORDER - Send to ADMIN for confirmation
                order_type = (
                    order.get("order_type")
                    if isinstance(order, dict)
                    else getattr(order, "order_type", None)
                )
                user_id = (
                    order.get("user_id")
                    if isinstance(order, dict)
                    else getattr(order, "user_id", None)
                )
                delivery_address = (
                    order.get("delivery_address")
                    if isinstance(order, dict)
                    else getattr(order, "delivery_address", None)
                )

                logger.info(
                    f"📋 Order #{order_id} details: type={order_type}, user_id={user_id}, delivery={delivery_address is not None}"
                )

                if order_type == "delivery":
                    logger.info(
                        f"📸 Payment proof uploaded for delivery order #{order_id} by user {authenticated_user_id}"
                    )

                    # SECURITY: user can only upload proof for their own order
                    try:
                        order_user_id_int = int(user_id) if user_id is not None else None
                    except Exception:
                        order_user_id_int = None

                    if order_user_id_int != authenticated_user_id:
                        logger.warning(
                            "🚨 IDOR attempt: user %s tried to upload payment proof for order #%s (owner=%s)",
                            authenticated_user_id,
                            order_id,
                            order_user_id_int,
                        )
                        return add_cors_headers(
                            web.json_response({"error": "Access denied"}, status=403)
                        )

                    # Get user info
                    user = db.get_user(user_id) if hasattr(db, "get_user") else None
                    customer_name = ""
                    customer_phone = ""
                    if user:
                        if isinstance(user, dict):
                            customer_name = user.get("first_name", "")
                            customer_phone = user.get("phone", "")
                        else:
                            customer_name = getattr(user, "first_name", "")
                            customer_phone = getattr(user, "phone", "")

                    # Get order details (items, store, total)
                    cart_items = []
                    store_name = ""
                    total_price = 0
                    delivery_fee = 0

                    if isinstance(order, dict):
                        cart_items_json = order.get("cart_items")
                        store_name = order.get("store_name", "")
                        total_price = order.get("total_price", 0)
                        delivery_fee = order.get("delivery_fee", 0)
                    else:
                        cart_items_json = getattr(order, "cart_items", None)
                        store_name = getattr(order, "store_name", "")
                        total_price = getattr(order, "total_price", 0)
                        delivery_fee = getattr(order, "delivery_fee", 0)

                    if cart_items_json:
                        cart_items = parse_cart_items(cart_items_json)

                    items_total = calc_items_total(cart_items)
                    if not delivery_fee and delivery_address:
                        delivery_fee = calc_delivery_fee(
                            total_price,
                            items_total,
                            order_type="delivery",
                        )

                    # Build admin message with progress bar
                    admin_msg = "💳 <b>НОВАЯ ДОСТАВКА - ЧЕК НА ПРОВЕРКЕ</b>\n\n"

                    # Progress bar: ● ● ● ○ ○
                    admin_msg += "🔄 <b>Статус:</b> ● ● ● ○ ○\n"
                    admin_msg += "   <i>Ожидает подтверждения оплаты</i>\n\n"

                    admin_msg += f"📦 <b>Заказ #{order_id}</b>\n"
                    admin_msg += f"👤 {customer_name or 'Клиент'}\n"

                    if customer_phone:
                        phone_display = customer_phone if customer_phone else "не указан"
                        admin_msg += f"📱 <code>{phone_display}</code>\n"

                    if store_name:
                        admin_msg += f"🏪 {store_name}\n"

                    if delivery_address:
                        admin_msg += f"📍 {delivery_address}\n"

                    # Items list
                    if cart_items:
                        admin_msg += f"\n📋 <b>Товары ({len(cart_items)}):</b>\n"
                        for idx, item in enumerate(cart_items[:5], 1):  # Max 5 items to show
                            title = item.get("title", "Товар")
                            qty = item.get("quantity", 1)
                            price = item.get("price", 0)
                            item_total = calc_items_total([{"price": price, "quantity": qty}])
                            admin_msg += f"{idx}. {title} × {qty} = {int(item_total):,} сум\n"

                        if len(cart_items) > 5:
                            admin_msg += f"   ... и ещё {len(cart_items) - 5}\n"

                    # Total
                    subtotal = items_total or max(0, int(total_price) - int(delivery_fee or 0))
                    admin_msg += "\n💰 <b>Итого:</b>\n"
                    admin_msg += f"   Товары: {int(subtotal):,} сум\n"
                    if delivery_fee:
                        admin_msg += f"   Доставка: {int(delivery_fee):,} сум\n"
                    admin_msg += f"   <b>Всего: {int(total_price):,} сум</b>\n"

                    admin_msg += "\n⚠️ <b>ПРОВЕРЬТЕ ЧЕК И ПОДТВЕРДИТЕ ОПЛАТУ</b>"

                    # Buttons for admin
                    admin_keyboard = InlineKeyboardMarkup(
                        inline_keyboard=[
                            [
                                InlineKeyboardButton(
                                    text="✅ Оплата подтверждена",
                                    callback_data=f"admin_confirm_payment_{order_id}",
                                ),
                            ],
                            [
                                InlineKeyboardButton(
                                    text="❌ Отклонить заказ",
                                    callback_data=f"admin_reject_payment_{order_id}",
                                ),
                            ],
                        ]
                    )

                    # Get all admins from database (like in bot handler)
                    admin_ids = []
                    if hasattr(db, "get_all_users"):
                        all_users = db.get_all_users()
                        for u in all_users:
                            role = (
                                u.get("role") if isinstance(u, dict) else getattr(u, "role", None)
                            )
                            u_id = (
                                u.get("user_id")
                                if isinstance(u, dict)
                                else getattr(u, "user_id", None)
                            )
                            if role == "admin" and u_id:
                                admin_ids.append(u_id)

                    # Fallback to ADMIN_ID from env
                    if not admin_ids:
                        admin_id_env = int(os.getenv("ADMIN_ID", "0"))
                        if admin_id_env:
                            admin_ids.append(admin_id_env)
                            logger.info(f"Using ADMIN_ID from env: {admin_id_env}")

                    if not admin_ids:
                        logger.error("❌ No admin users found - cannot send payment proof!")
                        return add_cors_headers(
                            web.json_response({"error": "No admin configured"}, status=500)
                        )

                    logger.info(
                        f"📤 Sending payment proof to {len(admin_ids)} admin(s): {admin_ids}"
                    )

                    # Send to all admins
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
                            if not file_id:
                                file_id = sent_msg.photo[-1].file_id
                            sent_count += 1
                            logger.info(f"✅ Payment proof sent to admin {admin_id}")
                        except Exception as e:
                            logger.error(
                                f"❌ Failed to send payment proof to admin {admin_id}: {e}"
                            )

                    if sent_count > 0:
                        logger.info(
                            f"✅ Payment proof for order #{order_id} sent to {sent_count}/{len(admin_ids)} admins"
                        )

                        # Persist payment proof in DB for audit trail and later access
                        if file_id:
                            if hasattr(db, "update_payment_status"):
                                db.update_payment_status(order_id, "proof_submitted", file_id)
                            elif hasattr(db, "update_order_payment_proof"):
                                db.update_order_payment_proof(order_id, file_id)

                        return add_cors_headers(
                            web.json_response(
                                {
                                    "success": True,
                                    "message": f"Payment proof sent to {sent_count} admin(s) for verification",
                                }
                            )
                        )
                    else:
                        logger.error("❌ Failed to send payment proof to any admin!")
                        return add_cors_headers(
                            web.json_response({"error": "Failed to send to admins"}, status=500)
                        )
                else:
                    logger.warning(f"⚠️ Order #{order_id} is not delivery type: {order_type}")
                    return add_cors_headers(
                        web.json_response(
                            {"error": f"Order type is '{order_type}', not 'delivery'"}, status=400
                        )
                    )
            else:
                logger.error(f"❌ Order #{order_id} not found in database!")
                return add_cors_headers(web.json_response({"error": "Order not found"}, status=404))

        except Exception as e:
            logger.error(f"API upload payment proof error: {e}")
            return add_cors_headers(web.json_response({"error": str(e)}, status=500))


    return (
        api_create_order,
        api_user_orders,
        api_order_status,
        api_order_timeline,
        api_order_qr,
        api_upload_payment_proof,
    )

