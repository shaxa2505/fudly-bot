"""Order routes for webhook Mini App API."""
from __future__ import annotations

from typing import Any, Callable

from aiohttp import web
from fastapi import HTTPException
from pydantic import ValidationError

from app.api.orders import (
    calculate_delivery as fastapi_calculate_delivery,
    get_order_qr_code as fastapi_get_order_qr,
    get_order_status as fastapi_get_order_status,
    get_order_timeline as fastapi_get_order_timeline,
)
from app.api.webapp.common import (
    CreateOrderRequest,
    OrderResponse,
    get_offer_time_range_label,
    get_store_time_range_label,
    get_val,
    is_offer_active,
    is_offer_available_now,
    is_store_open_now,
    normalize_price,
)
from app.api.webapp.routes_orders import cancel_order as fastapi_cancel_order
from app.api.webapp.routes_orders import get_orders as fastapi_get_orders
from app.core.async_db import AsyncDBProxy
from app.core.idempotency import (
    build_request_hash,
    check_or_reserve_key,
    normalize_idempotency_key,
    store_idempotency_response,
)
from app.core.order_math import (
    calc_items_total,
)
from app.core.webhook_api_utils import add_cors_headers
from app.core.webhook_helpers import _delivery_cash_enabled
from app.core.sanitize import sanitize_phone
from app.core.security import validator
from app.services.unified_order_service import (
    OrderItem,
    PaymentStatus,
    get_unified_order_service,
    init_unified_order_service,
)
from logging_config import logger


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
            user_model = (
                db.get_user_model(user_id) if hasattr(db, "get_user_model") else db.get_user(user_id)
            )
            current_phone = get_val(user_model, "phone") if user_model else None
            if not current_phone or current_phone != sanitized_phone:
                db.update_user_phone(user_id, sanitized_phone)
    except Exception as e:  # pragma: no cover - defensive
        logger.warning(f"Could not update user phone for {user_id}: {e}")


def _resolve_required_phone(db: Any, user_id: int, raw_phone: str | None) -> str:
    """Return canonical phone: must exist in DB (bot-verified)."""
    user_model = (
        db.get_user_model(user_id) if hasattr(db, "get_user_model") else db.get_user(user_id)
    )
    stored_phone = _normalize_phone(get_val(user_model, "phone") if user_model else None)
    candidate = _normalize_phone(raw_phone)

    if not stored_phone:
        raise ValueError("Phone is required. Register in the bot and share your contact.")
    if candidate and candidate != stored_phone:
        raise ValueError("Phone does not match registered number. Update it in the bot.")
    return stored_phone


def _validate_store_open(store: Any) -> str | None:
    if not store:
        return None
    if not is_store_open_now(store):
        time_range = get_store_time_range_label(store)
        detail = "Do'kon hozir yopiq"
        if time_range:
            detail = f"{detail}. Ish vaqti: {time_range}"
        return detail
    return None


def _model_to_payload(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump()
    if hasattr(value, "dict"):
        return value.dict()
    return value


def _detail_response(detail: Any, status_code: int) -> web.Response:
    if isinstance(detail, str):
        payload = {"detail": detail, "error": detail}
    else:
        payload = {"detail": detail, "error": "Validation error"}
    return add_cors_headers(web.json_response(payload, status=status_code))


def _format_validation_errors(errors: list[dict[str, Any]]) -> list[dict[str, Any]]:
    formatted: list[dict[str, Any]] = []
    for err in errors:
        entry = dict(err)
        loc = entry.get("loc", ())
        if isinstance(loc, (list, tuple)):
            if not loc or loc[0] != "body":
                entry["loc"] = ("body", *loc)
        else:
            entry["loc"] = ("body",)
        formatted.append(entry)
    return formatted


def _ensure_unified_service(db: Any, bot: Any):
    service = get_unified_order_service()
    if service is not None:
        return service
    try:
        return init_unified_order_service(db, bot)
    except Exception:
        return None


def _status_for_creation_error(detail: str) -> int:
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
        if not is_offer_available_now(offer):
            time_range = get_offer_time_range_label(offer)
            detail = "Mahsulot hozir buyurtma uchun mavjud emas"
            if time_range:
                detail = f"{detail}. Buyurtma vaqti: {time_range}"
            raise HTTPException(status_code=409, detail=detail)
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
    calc_items: list[dict[str, int | float]] = []
    for item in items:
        offer = offers_by_id.get(item.offer_id)
        if not offer:
            continue
        price = normalize_price(get_val(offer, "discount_price", 0))
        calc_items.append({"price": price, "quantity": item.quantity})

    total_check = calc_items_total(calc_items)

    store_check = db.get_store(store_id) if hasattr(db, "get_store") else None
    if not store_check:
        return
    min_order = normalize_price(get_val(store_check, "min_order_amount", 0))
    if min_order > 0 and total_check < min_order:
        raise HTTPException(
            status_code=400,
            detail=f"Minimum order amount: {min_order}. Your total: {total_check}",
        )


def _validate_store_open_for_order(db: Any, store_id: int) -> None:
    store_check = db.get_store(store_id) if hasattr(db, "get_store") else None
    if not store_check:
        return
    if not is_store_open_now(store_check):
        time_range = get_store_time_range_label(store_check)
        detail = "Do'kon hozir yopiq"
        if time_range:
            detail = f"{detail}. Ish vaqti: {time_range}"
        raise HTTPException(status_code=409, detail=detail)


def build_order_handlers(
    bot: Any,
    db: Any,
    get_authenticated_user_id: Callable[[web.Request], int | None],
):
    _get_authenticated_user_id = get_authenticated_user_id
    async_db = AsyncDBProxy(db)

    async def api_create_order(request: web.Request) -> web.Response:
        """POST /api/v1/orders - Create order from Mini App cart."""
        try:
            try:
                data = await request.json()
            except Exception:
                return _detail_response("Invalid JSON", 400)

            authenticated_user_id = _get_authenticated_user_id(request)
            if not authenticated_user_id:
                return _detail_response("Authentication required", 401)

            user_id = authenticated_user_id

            try:
                order = CreateOrderRequest.model_validate(data)
            except ValidationError as exc:
                return _detail_response(_format_validation_errors(exc.errors()), 422)

            if order.user_id and int(order.user_id) != int(user_id):
                logger.warning(
                    "create_order user mismatch: initData=%s payload=%s", user_id, order.user_id
                )
                return _detail_response("User mismatch", 403)

            for item in order.items:
                if float(item.quantity) <= 0:
                    return _detail_response(
                        f"Invalid quantity for offer {item.offer_id}",
                        400,
                    )

            delivery_address = order.delivery_address or ""
            is_delivery = bool(str(delivery_address).strip())
            raw_payment_method = order.payment_method
            if not raw_payment_method:
                payment_method = "click" if is_delivery else "cash"
            else:
                payment_method = PaymentStatus.normalize_method(raw_payment_method)

            idempotency_key = normalize_idempotency_key(
                request.headers.get("Idempotency-Key")
                or request.headers.get("X-Idempotency-Key")
            )
            idem_hash = None
            if idempotency_key:
                items_payload = [
                    {"offer_id": int(item.offer_id), "quantity": float(item.quantity)}
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
                idem_result = check_or_reserve_key(db, idempotency_key, user_id, idem_hash)
                if idem_result.get("status") in ("cached", "conflict", "in_progress"):
                    payload = idem_result.get("payload", {}) or {}
                    if isinstance(payload, dict) and "error" in payload and "detail" not in payload:
                        payload = {**payload, "detail": payload.get("error")}
                    return add_cors_headers(
                        web.json_response(
                            payload,
                            status=int(idem_result.get("status_code", 409)),
                        )
                    )

            def _store_idempotency(payload: dict[str, Any], status_code: int) -> None:
                if idempotency_key and idem_hash:
                    store_idempotency_response(
                        db,
                        idempotency_key,
                        user_id,
                        idem_hash,
                        payload,
                        status_code,
                    )

            try:
                _resolve_required_phone(db, user_id, order.phone)
                offers_by_id, store_id = _load_offers_and_store(order.items, db)
                _validate_store_open_for_order(db, store_id)

                if payment_method not in ("cash", "click"):
                    raise HTTPException(status_code=400, detail="Unsupported payment method")

                if is_delivery and payment_method == "cash" and not _delivery_cash_enabled():
                    raise HTTPException(
                        status_code=400,
                        detail="Cash is not allowed for delivery orders",
                    )

                if is_delivery:
                    _validate_min_order(db, store_id, order.items, offers_by_id)

            except HTTPException as exc:
                _store_idempotency({"detail": exc.detail}, exc.status_code)
                return _detail_response(exc.detail, exc.status_code)

            order_service = get_unified_order_service()
            if not order_service:
                order_service = _ensure_unified_service(db, bot)
            if not order_service:
                _store_idempotency({"detail": "Order service unavailable"}, 503)
                return _detail_response("Order service unavailable", 503)

            order_items: list[OrderItem] = []
            for item in order.items:
                offer = offers_by_id.get(item.offer_id)
                if not offer:
                    continue

                price = int(normalize_price(get_val(offer, "discount_price", 0)))
                original_price = int(
                    normalize_price(get_val(offer, "original_price", price) or price)
                )
                offer_store_id = int(get_val(offer, "store_id"))
                offer_title = get_val(offer, "title", "Tovar")
                store = db.get_store(offer_store_id) if hasattr(db, "get_store") else None
                store_name = get_val(store, "name", "") if store else ""
                store_address = get_val(store, "address", "") if store else ""
                delivery_price = 0
                if is_delivery and store:
                    delivery_price = int(normalize_price(get_val(store, "delivery_price", 0)))

                order_items.append(
                    OrderItem(
                        offer_id=item.offer_id,
                        store_id=offer_store_id,
                        title=offer_title,
                        price=price,
                        original_price=original_price,
                        quantity=item.quantity,
                        store_name=store_name,
                        store_address=store_address,
                        delivery_price=delivery_price,
                    )
                )

            if not order_items:
                _store_idempotency({"detail": "No valid items provided"}, 400)
                return _detail_response("No valid items provided", 400)

            try:
                result = await order_service.create_order(
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

            if not result or not result.success:
                detail = result.error_message if result else "Failed to create order"
                status_code = _status_for_creation_error(detail) if result else 500
                _store_idempotency({"detail": detail}, status_code)
                return _detail_response(detail, status_code)

            created_items: list[dict[str, Any]] = []
            if is_delivery:
                oid = result.order_ids[0] if result.order_ids else 0
                for item_obj in order_items:
                    item_total = calc_items_total(
                        [{"price": item_obj.price, "quantity": item_obj.quantity}]
                    )
                    created_items.append(
                        {
                            "id": oid,
                            "type": "order",
                            "offer_id": item_obj.offer_id,
                            "quantity": item_obj.quantity,
                            "total": item_total,
                            "offer_title": item_obj.title,
                            "store_id": item_obj.store_id,
                        }
                    )
            else:
                pickup_code = result.pickup_codes[0] if result.pickup_codes else None
                oid = result.order_ids[0] if result.order_ids else 0
                for item_obj in order_items:
                    item_total = calc_items_total(
                        [{"price": item_obj.price, "quantity": item_obj.quantity}]
                    )
                    created_items.append(
                        {
                            "id": oid,
                            "type": "order",
                            "offer_id": item_obj.offer_id,
                            "quantity": item_obj.quantity,
                            "total": item_total,
                            "offer_title": item_obj.title,
                            "store_id": item_obj.store_id,
                            "pickup_code": pickup_code,
                        }
                    )

            order_id = created_items[0]["id"] if created_items else 0
            total_amount = sum(item["total"] for item in created_items)
            total_items = sum(item["quantity"] for item in created_items)

            response_payload = OrderResponse(
                order_id=order_id,
                status="pending",
                total=total_amount,
                items_count=total_items,
            ).model_dump()

            _store_idempotency(response_payload, 201)
            return add_cors_headers(web.json_response(response_payload, status=201))

        except Exception as e:
            logger.error(f"API create order error: {e}", exc_info=True)
            return _detail_response(str(e), 500)


    async def api_user_orders(request: web.Request) -> web.Response:
        """GET /api/v1/orders - Get user's orders and bookings for WebApp."""
        authenticated_user_id = _get_authenticated_user_id(request)
        if not authenticated_user_id:
            return _detail_response("Authentication required", 401)
        try:
            payload = await fastapi_get_orders(db=async_db, user={"id": authenticated_user_id})
        except HTTPException as exc:
            return _detail_response(exc.detail, exc.status_code)
        payload = _model_to_payload(payload)
        return add_cors_headers(web.json_response(payload))


    async def api_user_orders_history(request: web.Request) -> web.Response:
        """GET /api/v1/user/orders - User order history (legacy bookings)."""
        authenticated_user_id = _get_authenticated_user_id(request)
        if not authenticated_user_id:
            return _detail_response("Authentication required", 401)

        query = request.query
        user_id_raw = query.get("user_id")
        status = query.get("status")
        limit_raw = query.get("limit")

        try:
            limit = int(limit_raw) if limit_raw else 50
        except (TypeError, ValueError):
            limit = 50
        if limit <= 0:
            limit = 50

        effective_user_id = authenticated_user_id
        if user_id_raw:
            try:
                requested_id = int(user_id_raw)
            except (TypeError, ValueError):
                return _detail_response("Invalid user_id", 400)
            if requested_id != authenticated_user_id:
                return _detail_response("Access denied", 403)
            effective_user_id = requested_id

        try:
            if status and hasattr(db, "get_user_bookings_by_status"):
                bookings = db.get_user_bookings_by_status(effective_user_id, status)
            else:
                bookings = db.get_user_bookings(effective_user_id) if hasattr(db, "get_user_bookings") else []

            bookings = bookings or []
            if not bookings:
                payload = {
                    "orders": [],
                    "total_count": 0,
                    "active_count": 0,
                    "completed_count": 0,
                }
                return add_cors_headers(web.json_response(payload))

            orders_list = []
            active_count = 0
            completed_count = 0

            for booking in bookings[:limit]:
                if isinstance(booking, dict):
                    booking_id = booking.get("booking_id")
                    offer_id = booking.get("offer_id")
                    quantity = float(booking.get("quantity", 1) or 1)
                    total_price = booking.get("total_price", 0)
                    booking_status = booking.get("status", "pending")
                    booking_code = booking.get("booking_code")
                    created_at = booking.get("created_at")
                else:
                    booking_id = booking[0]
                    offer_id = booking[2]
                    booking_status = booking[3]
                    quantity = float(booking[4]) if len(booking) > 4 and booking[4] is not None else 1.0
                    total_price = booking[5]
                    booking_code = booking[6] if len(booking) > 6 else None
                    created_at = booking[7] if len(booking) > 7 else None

                if not offer_id:
                    continue

                offer = db.get_offer(offer_id) if hasattr(db, "get_offer") else None
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

                store = db.get_store(store_id) if store_id and hasattr(db, "get_store") else None
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

                if booking_status in ("pending", "confirmed"):
                    active_count += 1
                elif booking_status == "completed":
                    completed_count += 1

                created_at_str = str(created_at) if created_at else None

                orders_list.append(
                    {
                        "booking_id": booking_id,
                        "offer_id": offer_id,
                        "offer_title": offer_title,
                        "offer_photo": offer_photo,
                        "quantity": quantity,
                        "total_price": int(total_price),
                        "status": booking_status,
                        "store_name": store_name,
                        "store_address": store_address,
                        "booking_code": booking_code,
                        "created_at": created_at_str,
                        "pickup_time": None,
                    }
                )

            payload = {
                "orders": orders_list,
                "total_count": len(bookings),
                "active_count": active_count,
                "completed_count": completed_count,
            }
            return add_cors_headers(web.json_response(payload))
        except Exception as e:
            logger.error(f"Error getting user orders: {e}")
            return _detail_response(f"Failed to get orders: {str(e)}", 500)


    async def api_user_bookings_history(request: web.Request) -> web.Response:
        """GET /api/v1/user/bookings - Alias for order history."""
        return await api_user_orders_history(request)


    async def api_order_status(request: web.Request) -> web.Response:
        """GET /api/v1/orders/{order_id}/status - Order tracking status payload."""
        authenticated_user_id = _get_authenticated_user_id(request)
        if not authenticated_user_id:
            return _detail_response("Authentication required", 401)

        order_id_str = request.match_info.get("order_id")
        if not order_id_str:
            return _detail_response("order_id required", 400)

        try:
            order_id = int(order_id_str)
        except (TypeError, ValueError):
            return _detail_response("order_id required", 400)

        try:
            result = await fastapi_get_order_status(order_id, db=async_db, user={"id": authenticated_user_id})
        except HTTPException as exc:
            return _detail_response(exc.detail, exc.status_code)

        payload = _model_to_payload(result)
        return add_cors_headers(web.json_response(payload))


    async def api_order_timeline(request: web.Request) -> web.Response:
        """GET /api/v1/orders/{order_id}/timeline - Order tracking timeline payload."""
        authenticated_user_id = _get_authenticated_user_id(request)
        if not authenticated_user_id:
            return _detail_response("Authentication required", 401)

        order_id_str = request.match_info.get("order_id")
        if not order_id_str:
            return _detail_response("order_id required", 400)

        try:
            order_id = int(order_id_str)
        except (TypeError, ValueError):
            return _detail_response("order_id required", 400)

        try:
            result = await fastapi_get_order_timeline(order_id, db=async_db, user={"id": authenticated_user_id})
        except HTTPException as exc:
            return _detail_response(exc.detail, exc.status_code)

        payload = _model_to_payload(result)
        return add_cors_headers(web.json_response(payload))


    async def api_order_qr(request: web.Request) -> web.Response:
        """GET /api/v1/orders/{order_id}/qr - Standalone QR endpoint."""
        authenticated_user_id = _get_authenticated_user_id(request)
        if not authenticated_user_id:
            return _detail_response("Authentication required", 401)

        order_id_str = request.match_info.get("order_id")
        if not order_id_str:
            return _detail_response("order_id required", 400)

        try:
            order_id = int(order_id_str)
        except (TypeError, ValueError):
            return _detail_response("order_id required", 400)

        try:
            result = await fastapi_get_order_qr(order_id, db=async_db, user={"id": authenticated_user_id})
        except HTTPException as exc:
            return _detail_response(exc.detail, exc.status_code)

        payload = _model_to_payload(result)
        return add_cors_headers(web.json_response(payload))


    async def api_upload_payment_proof(request: web.Request) -> web.Response:
        """POST /api/v1/orders/{order_id}/payment-proof - Upload payment screenshot.

        Payment proof uploads are disabled (Click-only payments).
        """
        return _detail_response("Payment proof uploads are disabled (Click-only payments)", 410)


    async def api_cancel_order(request: web.Request) -> web.Response:
        """POST /api/v1/orders/{order_id}/cancel - Cancel an order (customer)."""
        authenticated_user_id = _get_authenticated_user_id(request)
        if not authenticated_user_id:
            return _detail_response("Authentication required", 401)

        order_id_str = request.match_info.get("order_id")
        if not order_id_str:
            return _detail_response("order_id required", 400)

        try:
            order_id = int(order_id_str)
        except (TypeError, ValueError):
            return _detail_response("order_id required", 400)

        try:
            result = await fastapi_cancel_order(order_id, db=async_db, user={"id": authenticated_user_id})
        except HTTPException as exc:
            return _detail_response(exc.detail, exc.status_code)

        payload = _model_to_payload(result)
        return add_cors_headers(web.json_response(payload))


    async def api_calculate_delivery(request: web.Request) -> web.Response:
        """POST /api/v1/orders/calculate-delivery - Calculate delivery cost."""
        authenticated_user_id = _get_authenticated_user_id(request)
        if not authenticated_user_id:
            return _detail_response("Authentication required", 401)

        try:
            data = await request.json()
        except Exception:
            return _detail_response("Invalid JSON", 400)

        try:
            from app.api.orders import DeliveryCalculation

            payload_model = DeliveryCalculation.model_validate(data)
        except ValidationError as exc:
            return _detail_response(_format_validation_errors(exc.errors()), 422)

        try:
            result = await fastapi_calculate_delivery(
                payload_model,
                db=async_db,
                user={"id": authenticated_user_id},
            )
        except HTTPException as exc:
            return _detail_response(exc.detail, exc.status_code)

        payload = _model_to_payload(result)
        return add_cors_headers(web.json_response(payload))


    return (
        api_create_order,
        api_user_orders,
        api_user_orders_history,
        api_user_bookings_history,
        api_order_status,
        api_order_timeline,
        api_order_qr,
        api_upload_payment_proof,
        api_cancel_order,
        api_calculate_delivery,
    )

