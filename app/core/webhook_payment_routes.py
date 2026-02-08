"""Payment routes for webhook Mini App API."""
from __future__ import annotations

import json
from typing import Any, Callable

from aiohttp import web

from app.core.webhook_api_utils import add_cors_headers
from app.integrations.payment_service import get_payment_service
from logging_config import logger


def build_payment_handlers(
    db: Any,
    get_authenticated_user_id: Callable[[web.Request], int | None],
    get_cached_payment_link: Callable[[int, str], str | None],
    set_cached_payment_link: Callable[[int, str, str], None],
):
    async def api_get_payment_providers(request: web.Request) -> web.Response:
        """GET /api/v1/payment/providers - Get available payment providers."""
        try:
            payment_service = get_payment_service()
            store_id = request.query.get("store_id")
            store_id_int = int(store_id) if store_id and store_id.isdigit() else None
            providers = payment_service.get_available_providers(store_id_int)

            # Return provider info
            result = []
            for provider in providers:
                if provider == "click":
                    result.append(
                        {"id": "click", "name": "Click", "icon": "\U0001F4B3", "enabled": True}
                    )

            return add_cors_headers(web.json_response({"providers": result}))
        except Exception as e:
            logger.error(f"API get payment providers error: {e}")
            return add_cors_headers(web.json_response({"error": str(e)}, status=500))

    async def api_create_payment(request: web.Request) -> web.Response:
        """POST /api/v1/payment/create - Create payment URL for order."""
        try:
            data = await request.json()
            authenticated_user_id = get_authenticated_user_id(request)
            if not authenticated_user_id:
                return add_cors_headers(
                    web.json_response({"error": "Authentication required"}, status=401)
                )
            payload_user_id = data.get("user_id")
            if payload_user_id is not None:
                try:
                    payload_user_id_int = int(payload_user_id)
                except Exception:
                    payload_user_id_int = None
                if payload_user_id_int is None or payload_user_id_int != authenticated_user_id:
                    return add_cors_headers(web.json_response({"error": "Access denied"}, status=403))
            order_id = data.get("order_id")
            amount = data.get("amount")
            provider = str(data.get("provider", "click")).lower()
            user_id = authenticated_user_id
            return_url = data.get("return_url")
            store_id = data.get("store_id")  # For per-store credentials

            if not order_id:
                return add_cors_headers(web.json_response({"error": "order_id required"}, status=400))

            payment_service = get_payment_service()
            if hasattr(payment_service, "set_database"):
                payment_service.set_database(db)

            order = None
            if hasattr(db, "get_order"):
                order = db.get_order(int(order_id))
            if not order:
                return add_cors_headers(web.json_response({"error": "Order not found"}, status=404))

            order_user_id = (
                order.get("user_id") if isinstance(order, dict) else getattr(order, "user_id", None)
            )
            try:
                order_user_id_int = int(order_user_id) if order_user_id is not None else None
            except Exception:
                order_user_id_int = None
            if order_user_id_int is None:
                return add_cors_headers(web.json_response({"error": "Access denied"}, status=403))
            if order_user_id_int != authenticated_user_id:
                return add_cors_headers(web.json_response({"error": "Access denied"}, status=403))

            order_store_id = order.get("store_id")
            if store_id:
                try:
                    store_id_int = int(store_id)
                except Exception:
                    store_id_int = None
                if store_id_int is None or (
                    order_store_id is not None and store_id_int != int(order_store_id)
                ):
                    return add_cors_headers(
                        web.json_response({"error": "Invalid store_id for order"}, status=400)
                    )
            store_id = order_store_id

            if not amount:
                amount = order.get("total_price")
            else:
                order_total = order.get("total_price")
                if order_total is not None and int(amount) != int(order_total):
                    amount = order_total

            order_type = order.get("order_type") if isinstance(order, dict) else None
            if not order_type:
                order_type = "delivery" if order.get("delivery_address") else "pickup"
            is_delivery = str(order_type).lower() in ("delivery", "taxi")

            if is_delivery:
                items_total = 0
                cart_items = order.get("cart_items")
                if cart_items:
                    if isinstance(cart_items, str):
                        try:
                            cart_items = json.loads(cart_items)
                        except Exception:
                            cart_items = None
                    if isinstance(cart_items, list):
                        for item in cart_items:
                            try:
                                price = int(item.get("price") or 0)
                                qty = int(item.get("quantity") or 1)
                            except Exception:
                                price = 0
                                qty = 1
                            items_total += price * qty
                if not items_total:
                    try:
                        qty = int(order.get("quantity") or 1)
                    except Exception:
                        qty = 1
                    try:
                        price = int(order.get("item_price") or 0)
                    except Exception:
                        price = 0
                    items_total = max(0, price * qty)
                if items_total:
                    amount = items_total

            order_status = str(order.get("order_status") or order.get("status") or "").lower()
            payment_status = str(order.get("payment_status") or "").lower()
            payment_method = str(order.get("payment_method") or "").lower()

            if order_status in ("completed", "cancelled", "rejected"):
                return add_cors_headers(
                    web.json_response({"error": "Order already finalized"}, status=400)
                )

            if provider != "click":
                return add_cors_headers(
                    web.json_response({"error": "Payment provider not supported"}, status=400)
                )
            if payment_method and payment_method != "click":
                return add_cors_headers(web.json_response({"error": "Payment method mismatch"}, status=400))
            if payment_status not in ("awaiting_payment", ""):
                return add_cors_headers(
                    web.json_response({"error": "Payment not awaiting online payment"}, status=400)
                )

            available = payment_service.get_available_providers(int(store_id) if store_id else None)
            if provider not in available:
                return add_cors_headers(
                    web.json_response({"error": "Payment provider not available"}, status=400)
                )

            cached_url = get_cached_payment_link(int(order_id), provider)
            if cached_url:
                return add_cors_headers(
                    web.json_response({"payment_url": cached_url, "provider": provider})
                )

            # Check for store-specific or platform-wide Click credentials
            credentials = (
                payment_service.get_store_credentials(
                    store_id=int(store_id) if store_id else 0, provider="click"
                )
                if store_id
                else None
            )
            if not credentials and not payment_service.click_enabled:
                return add_cors_headers(
                    web.json_response({"error": "Click not configured for this store"}, status=400)
                )
            payment_url = payment_service.generate_click_url(
                order_id=int(order_id),
                amount=int(amount),
                return_url=return_url,
                user_id=int(user_id) if user_id else 0,
                store_id=int(store_id) if store_id else 0,
            )
            set_cached_payment_link(int(order_id), "click", payment_url)
            return add_cors_headers(web.json_response({"payment_url": payment_url, "provider": "click"}))

        except Exception as e:
            logger.error(f"API create payment error: {e}")
            return add_cors_headers(web.json_response({"error": str(e)}, status=500))

    return api_get_payment_providers, api_create_payment
