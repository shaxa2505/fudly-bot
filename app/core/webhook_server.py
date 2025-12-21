"""Webhook server for production deployment."""
from __future__ import annotations

import asyncio
import os
import sys
from datetime import datetime
from typing import Any

from aiogram import Bot, Dispatcher, types
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiohttp import web

from app.core.metrics import metrics as app_metrics
from app.core.notifications import get_notification_service
from app.core.websocket import get_websocket_manager, setup_websocket_routes
from app.integrations.payment_service import get_payment_service
from logging_config import logger

# =============================================================================
# Mini App API Helpers
# =============================================================================


def get_offer_value(obj: Any, key: str, default: Any = None) -> Any:
    """Get value from dict or object."""
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


# Cache for photo URLs (file_id -> URL)
_photo_url_cache: dict[str, str] = {}


async def get_photo_url(bot: Bot, file_id: str | None) -> str | None:
    """Convert Telegram file_id to photo URL."""
    if not file_id:
        return None

    # Check cache
    if file_id in _photo_url_cache:
        return _photo_url_cache[file_id]

    try:
        file = await bot.get_file(file_id)
        if file and file.file_path:
            url = f"https://api.telegram.org/file/bot{bot.token}/{file.file_path}"
            _photo_url_cache[file_id] = url
            return url
    except Exception:
        pass
    return None


def offer_to_dict(offer: Any, photo_url: str | None = None) -> dict:
    """Convert offer to API response dict."""
    # Try offer_id first (PostgreSQL), then id (SQLite)
    offer_id = get_offer_value(offer, "offer_id", 0) or get_offer_value(offer, "id", 0)

    # Use provided photo_url, or fallback to photo field
    photo = photo_url or get_offer_value(offer, "photo")

    return {
        "id": offer_id,
        "title": get_offer_value(offer, "title", ""),
        "description": get_offer_value(offer, "description"),
        "original_price": float(get_offer_value(offer, "original_price", 0) or 0),
        "discount_price": float(get_offer_value(offer, "discount_price", 0) or 0),
        "discount_percent": float(get_offer_value(offer, "discount_percent", 0) or 0),
        "quantity": int(get_offer_value(offer, "quantity", 0) or 0),
        "category": get_offer_value(offer, "category", "other") or "other",
        "store_id": int(get_offer_value(offer, "store_id", 0) or 0),
        "store_name": get_offer_value(offer, "store_name", "") or "",
        "store_address": get_offer_value(offer, "store_address")
        or get_offer_value(offer, "address"),
        "photo": photo,
        "expiry_date": str(get_offer_value(offer, "expiry_date", ""))
        if get_offer_value(offer, "expiry_date")
        else None,
    }


def store_to_dict(store: Any, photo_url: str | None = None) -> dict:
    """Convert store to API response dict."""
    store_id = get_offer_value(store, "store_id", 0) or get_offer_value(store, "id", 0)

    # Get latitude/longitude safely
    lat = get_offer_value(store, "latitude")
    lng = get_offer_value(store, "longitude")

    return {
        "id": store_id,
        "name": get_offer_value(store, "name", ""),
        "address": get_offer_value(store, "address"),
        "city": get_offer_value(store, "city"),
        "business_type": get_offer_value(store, "business_type", "supermarket"),
        "rating": float(get_offer_value(store, "rating", 0) or 0),
        "offers_count": int(get_offer_value(store, "offers_count", 0) or 0),
        # Delivery settings
        "delivery_enabled": get_offer_value(store, "delivery_enabled", 1) == 1,
        "delivery_price": int(get_offer_value(store, "delivery_price", 15000) or 15000),
        "min_order_amount": int(get_offer_value(store, "min_order_amount", 30000) or 30000),
        # Photo
        "photo_url": photo_url,
        # Geolocation for map
        "latitude": float(lat) if lat else None,
        "longitude": float(lng) if lng else None,
    }


# Categories list
API_CATEGORIES = [
    {"id": "all", "name": "Все", "emoji": "🔥"},
    {"id": "dairy", "name": "Молочные", "emoji": "🥛"},
    {"id": "bakery", "name": "Выпечка", "emoji": "🍞"},
    {"id": "meat", "name": "Мясо", "emoji": "🥩"},
    {"id": "snacks", "name": "Снеки", "emoji": "🍿"},
    {"id": "drinks", "name": "Напитки", "emoji": "🥤"},
    {"id": "sweets", "name": "Сладости", "emoji": "🍰"},
    {"id": "frozen", "name": "Заморозка", "emoji": "🧊"},
    {"id": "other", "name": "Другое", "emoji": "📦"},
]


async def create_webhook_app(
    bot: Bot,
    dp: Dispatcher,
    webhook_path: str,
    secret_token: str | None,
    metrics: dict[str, int],
    db: Any,
    offer_service: Any = None,
    bot_token: str = None,
) -> web.Application:
    """Create aiohttp web application with webhook handlers."""
    app = web.Application()

    async def webhook_handler(request: web.Request) -> web.Response:
        """Handle incoming Telegram updates via webhook."""
        import time

        start_ts = time.time()

        # Only allow POST requests
        if request.method != "POST":
            return web.Response(status=405, text="Method Not Allowed")

        try:
            logger.info(f"Webhook request received from {request.remote}")

            # Verify secret token if configured
            if secret_token:
                hdr = request.headers.get("X-Telegram-Bot-Api-Secret-Token")
                if hdr != secret_token:
                    logger.warning("Invalid secret token")
                    metrics["updates_errors"] += 1
                    return web.Response(status=403, text="Forbidden")

            # Parse JSON
            try:
                update_data = await request.json()
            except Exception as json_e:
                logger.error(f"Webhook JSON parse error: {repr(json_e)}")
                metrics["webhook_json_errors"] += 1
                return web.Response(status=200, text="OK")

            logger.debug(f"Raw update: {update_data}")

            # Validate Update structure
            try:
                telegram_update = types.Update.model_validate(update_data)
            except Exception as validate_e:
                logger.error(f"Webhook validation error: {repr(validate_e)}")
                metrics["webhook_validation_errors"] += 1
                return web.Response(status=200, text="OK")

            # Process update
            await dp.feed_update(bot, telegram_update)
            metrics["updates_received"] += 1
            proc_ms = int((time.time() - start_ts) * 1000)
            logger.info(f"Update processed successfully ({proc_ms}ms)")
            return web.Response(status=200, text="OK")

        except Exception as e:
            logger.error(f"Webhook unexpected error: {repr(e)}", exc_info=True)
            metrics["webhook_unexpected_errors"] += 1
            metrics["updates_errors"] += 1
            return web.Response(status=200, text="OK")

    async def health_check(request: web.Request) -> web.Response:
        """Comprehensive health check endpoint."""
        try:
            # Check database connection
            db_healthy = True
            db_error = None
            try:
                with db.get_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute("SELECT 1")
                    cursor.fetchone()
            except Exception as e:
                db_healthy = False
                db_error = str(e)
                logger.warning(f"Health check: Database unhealthy - {e}")

            status = {
                "status": "healthy" if db_healthy else "degraded",
                "bot": "Fudly",
                "timestamp": datetime.now().isoformat(),
                "components": {
                    "database": {
                        "status": "healthy" if db_healthy else "unhealthy",
                        "error": db_error,
                    },
                    "bot": {"status": "healthy"},
                },
            }

            # Add metrics
            status["metrics"] = {
                "updates_received": metrics.get("updates_received", 0),
                "updates_errors": metrics.get("updates_errors", 0),
                "error_rate": round(
                    metrics.get("updates_errors", 0)
                    / max(metrics.get("updates_received", 1), 1)
                    * 100,
                    2,
                ),
            }

            # Always return 200 for deployment health checks
            # Deployment platforms need 200 to pass health checks
            # The status field indicates actual health state
            return web.json_response(status, status=200)
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            # Return 200 even on error to keep service up during transient issues
            return web.json_response(
                {"status": "error", "error": str(e), "bot": "Fudly"}, status=200
            )

    async def version_info(request: web.Request) -> web.Response:
        """Return version and configuration info."""
        return web.json_response(
            {"app": "Fudly", "mode": "webhook", "ts": datetime.now().isoformat(timespec="seconds")}
        )

    def _prometheus_metrics_text() -> str:
        """Generate Prometheus-style metrics text."""
        # Use new metrics module for comprehensive metrics
        return app_metrics.export_prometheus()

    async def metrics_prom(request: web.Request) -> web.Response:
        """Return Prometheus-style metrics."""
        text = _prometheus_metrics_text()
        return web.Response(text=text, content_type="text/plain; version=0.0.4; charset=utf-8")

    async def metrics_json(request: web.Request) -> web.Response:
        """Return metrics as JSON."""
        # Combine old metrics with new summary
        combined = dict(metrics)
        combined.update(app_metrics.get_summary())
        return web.json_response(combined)

    async def webhook_get(request: web.Request) -> web.Response:
        """Handle GET requests to webhook endpoint (sanity check)."""
        return web.Response(text="OK", status=200)

    async def docs_handler(request: web.Request) -> web.Response:
        """Serve Swagger UI for API documentation."""
        html = """<!DOCTYPE html>
<html>
<head>
    <title>Fudly Bot API Documentation</title>
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui.css">
    <style>
        body { margin: 0; padding: 0; }
        .swagger-ui .topbar { display: none; }
    </style>
</head>
<body>
    <div id="swagger-ui"></div>
    <script src="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui-bundle.js"></script>
    <script>
        SwaggerUIBundle({
            url: '/openapi.yaml',
            dom_id: '#swagger-ui',
            presets: [SwaggerUIBundle.presets.apis, SwaggerUIBundle.SwaggerUIStandalonePreset],
            layout: "BaseLayout"
        });
    </script>
</body>
</html>"""
        return web.Response(text=html, content_type="text/html")

    async def openapi_spec_handler(request: web.Request) -> web.Response:
        """Serve OpenAPI specification."""
        import os

        spec_path = os.path.join(os.path.dirname(__file__), "..", "..", "docs", "openapi.yaml")
        try:
            with open(spec_path, encoding="utf-8") as f:
                spec = f.read()
            return web.Response(text=spec, content_type="application/x-yaml")
        except FileNotFoundError:
            return web.Response(text="OpenAPI spec not found", status=404)

    # =========================================================================
    # Mini App API Endpoints
    # =========================================================================

    async def cors_preflight(request: web.Request) -> web.Response:
        """Handle CORS preflight requests."""
        return web.Response(
            status=200,
            headers={
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
                "Access-Control-Allow-Headers": "Content-Type, X-Telegram-Init-Data",
                "Access-Control-Max-Age": "86400",
            },
        )

    def add_cors_headers(response: web.Response) -> web.Response:
        """Add CORS headers to response."""
        response.headers["Access-Control-Allow-Origin"] = "*"
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type, X-Telegram-Init-Data"
        return response

    def _get_authenticated_user_id(request: web.Request) -> int | None:
        """Validate Telegram initData and return authenticated user_id.

        Mini App must send `X-Telegram-Init-Data` header.
        """
        init_data = request.headers.get("X-Telegram-Init-Data")
        if not init_data:
            return None

        try:
            from app.api.webapp.common import validate_init_data

            validated = validate_init_data(init_data, bot.token)
        except Exception:
            return None

        if not validated:
            return None

        user = validated.get("user")
        if not isinstance(user, dict):
            return None

        try:
            return int(user.get("id"))
        except Exception:
            return None

    async def api_categories(request: web.Request) -> web.Response:
        """GET /api/v1/categories - List categories."""
        city = request.query.get("city", "Ташкент")
        result = []

        for cat in API_CATEGORIES:
            count = 0
            if cat["id"] != "all":
                try:
                    if hasattr(db, "get_offers_by_category"):
                        offers = db.get_offers_by_category(cat["id"], city) or []
                        count = len(offers)
                except Exception:
                    pass
            else:
                try:
                    if hasattr(db, "count_hot_offers"):
                        count = db.count_hot_offers(city) or 0
                except Exception:
                    pass

            result.append(
                {
                    "id": cat["id"],
                    "name": cat["name"],
                    "emoji": cat["emoji"],
                    "count": count,
                }
            )

        return add_cors_headers(web.json_response(result))

    async def api_offers(request: web.Request) -> web.Response:
        """GET /api/v1/offers - List offers."""
        city = request.query.get("city", "")  # Empty = all cities
        category = request.query.get("category", "all")
        store_id = request.query.get("store_id")
        search = request.query.get("search")
        limit = int(request.query.get("limit", "50"))
        offset = int(request.query.get("offset", "0"))

        logger.info(f"API /offers request: city={city}, category={category}, limit={limit}")

        try:
            raw_offers: list[Any] = []

            if store_id:
                if hasattr(db, "get_store_offers"):
                    raw_offers = db.get_store_offers(int(store_id)) or []
                    logger.info(f"get_store_offers({store_id}) returned {len(raw_offers)} items")
            elif search:
                if hasattr(db, "search_offers"):
                    raw_offers = db.search_offers(search, city) or []
                    logger.info(f"search_offers returned {len(raw_offers)} items")
            elif category and category != "all":
                if hasattr(db, "get_offers_by_city_and_category"):
                    raw_offers = db.get_offers_by_city_and_category(city, category, limit) or []
                    logger.info(
                        f"get_offers_by_city_and_category({city}, {category}) returned {len(raw_offers)} items"
                    )
                elif hasattr(db, "get_hot_offers"):
                    # Fallback: filter hot offers by category
                    all_offers = db.get_hot_offers(city, limit=100) or []
                    raw_offers = [
                        o for o in all_offers if get_offer_value(o, "category") == category
                    ][:limit]
                    logger.info(f"Filtered hot_offers by {category}: {len(raw_offers)} items")
            else:
                if hasattr(db, "get_hot_offers"):
                    raw_offers = db.get_hot_offers(city, limit=limit, offset=offset) or []
                    logger.info(f"get_hot_offers({city}) returned {len(raw_offers)} items")
                else:
                    logger.warning("db has no get_hot_offers method!")

            # Convert offers with photo URLs (parallel loading)
            async def load_offer_with_photo(o: Any) -> dict:
                photo_id = get_offer_value(o, "photo_id")
                photo_url = await get_photo_url(bot, photo_id) if photo_id else None
                return offer_to_dict(o, photo_url)

            offers = await asyncio.gather(*[load_offer_with_photo(o) for o in raw_offers])

            logger.info(f"Returning {len(offers)} offers")
            return add_cors_headers(web.json_response(offers))

        except Exception as e:
            logger.error(f"API offers error: {e}", exc_info=True)
            return add_cors_headers(web.json_response({"error": str(e)}, status=500))

    async def api_debug(request: web.Request) -> web.Response:
        """GET /api/v1/debug - Debug database info (dev only)."""
        # Security: only allow in non-production environments
        environment = os.getenv("ENVIRONMENT", "production").lower()
        if environment not in ("development", "dev", "local", "test"):
            return web.json_response({"error": "Not available"}, status=404)

        try:
            info = {
                "db_type": type(db).__name__,
                "has_get_hot_offers": hasattr(db, "get_hot_offers"),
                "has_get_store_offers": hasattr(db, "get_store_offers"),
            }

            # Try to count offers directly
            try:
                with db.get_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute("SELECT COUNT(*) FROM offers")
                    info["total_offers"] = cursor.fetchone()[0]
                    cursor.execute("SELECT COUNT(*) FROM offers WHERE status = 'active'")
                    info["active_offers"] = cursor.fetchone()[0]
                    cursor.execute("SELECT COUNT(*) FROM stores")
                    info["total_stores"] = cursor.fetchone()[0]
                    cursor.execute(
                        "SELECT COUNT(*) FROM stores WHERE status = 'active' OR status = 'approved'"
                    )
                    info["active_stores"] = cursor.fetchone()[0]
            except Exception as e:
                info["db_error"] = str(e)

            # Check photo_id in offers
            try:
                with db.get_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute(
                        "SELECT offer_id, title, photo_id FROM offers WHERE photo_id IS NOT NULL LIMIT 5"
                    )
                    rows = cursor.fetchall()
                    info["offers_with_photos"] = [
                        {"id": r[0], "title": r[1], "photo_id": r[2]} for r in rows
                    ]
            except Exception as e:
                info["photo_check_error"] = str(e)

            return add_cors_headers(web.json_response(info))
        except Exception as e:
            return add_cors_headers(web.json_response({"error": str(e)}, status=500))

    async def api_offer_detail(request: web.Request) -> web.Response:
        """GET /api/v1/offers/{offer_id} - Get single offer."""
        offer_id = int(request.match_info["offer_id"])

        try:
            offer = None
            if hasattr(db, "get_offer"):
                offer = db.get_offer(offer_id)

            if not offer:
                return add_cors_headers(web.json_response({"error": "Not found"}, status=404))

            # Convert photo_id to URL
            photo_id = get_offer_value(offer, "photo_id")
            photo_url = await get_photo_url(bot, photo_id) if photo_id else None

            return add_cors_headers(web.json_response(offer_to_dict(offer, photo_url)))

        except Exception as e:
            logger.error(f"API offer detail error: {e}")
            return add_cors_headers(web.json_response({"error": str(e)}, status=500))

    async def api_stores(request: web.Request) -> web.Response:
        """GET /api/v1/stores - List stores."""
        city = request.query.get("city", "")  # Empty = all cities
        business_type = request.query.get("business_type")

        try:
            raw_stores: list[Any] = []

            # Get stores from database with offers count
            if hasattr(db, "get_connection"):
                with db.get_connection() as conn:
                    cursor = conn.cursor()
                    # Join with offers to get count
                    base_query = """
                        SELECT s.*, COALESCE(oc.offer_count, 0) as offers_count
                        FROM stores s
                        LEFT JOIN (
                            SELECT store_id, COUNT(*) as offer_count
                            FROM offers
                            WHERE status = 'active'
                            GROUP BY store_id
                        ) oc ON s.store_id = oc.store_id
                        WHERE (s.status = 'active' OR s.status = 'approved')
                    """
                    if city:
                        cursor.execute(base_query + " AND s.city = %s", (city,))
                    else:
                        cursor.execute(base_query)
                    columns = [desc[0] for desc in cursor.description]
                    raw_stores = [dict(zip(columns, row)) for row in cursor.fetchall()]

            # Convert stores with photo URLs (parallel loading)
            async def load_store_with_photo(s: Any) -> dict:
                photo_id = get_offer_value(s, "photo")
                photo_url = await get_photo_url(bot, photo_id) if photo_id else None
                return store_to_dict(s, photo_url)

            stores = await asyncio.gather(*[load_store_with_photo(s) for s in raw_stores])

            logger.info(f"API /stores: returning {len(stores)} stores")
            return add_cors_headers(web.json_response(stores))

        except Exception as e:
            logger.error(f"API stores error: {e}")
            return add_cors_headers(web.json_response({"error": str(e)}, status=500))

    async def api_create_order(request: web.Request) -> web.Response:
        """POST /api/v1/orders - Create order from Mini App cart."""
        try:
            from app.services.unified_order_service import (
                OrderItem as UnifiedOrderItem,
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

            if not items:
                return add_cors_headers(
                    web.json_response({"error": "No items in order"}, status=400)
                )

            is_delivery = delivery_type == "delivery"

            # Try unified order service first
            created_bookings: list[dict[str, Any]] = []
            failed_items: list[dict[str, Any]] = []

            order_service = get_unified_order_service()
            if order_service and hasattr(db, "create_cart_order"):
                order_items: list[UnifiedOrderItem] = []

                for item in items:
                    offer_id = item.get("id") or item.get("offer_id")
                    quantity = int(item.get("quantity", 1))

                    if not offer_id:
                        failed_items.append({"item": item, "error": "Missing offer_id"})
                        continue

                    offer = db.get_offer(int(offer_id)) if hasattr(db, "get_offer") else None
                    if not offer:
                        failed_items.append({"offer_id": offer_id, "error": "Offer not found"})
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

                try:
                    payment_method = data.get("payment_method")
                    if not payment_method:
                        payment_method = "card" if is_delivery else "cash"

                    result: OrderResult = await order_service.create_order(
                        user_id=int(user_id),
                        items=order_items,
                        order_type="delivery" if is_delivery else "pickup",
                        delivery_address=address if is_delivery else None,
                        payment_method=payment_method,
                        notify_customer=True,
                        notify_sellers=True,
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

                    initial_payment_status = PaymentStatus.initial_for_method(payment_method)
                    awaiting_payment = initial_payment_status in (
                        PaymentStatus.AWAITING_PAYMENT,
                        PaymentStatus.AWAITING_PROOF,
                    )

                    payment_card_info = None
                    if payment_method == "card" and hasattr(db, "get_payment_card") and order_items:
                        try:
                            store_id = int(order_items[0].store_id)
                            card = db.get_payment_card(store_id)
                            if card:
                                payment_card_info = {
                                    "card_number": card.get("card_number")
                                    if isinstance(card, dict)
                                    else None,
                                    "card_holder": card.get("card_holder")
                                    if isinstance(card, dict)
                                    else None,
                                    "payment_instructions": card.get("payment_instructions")
                                    if isinstance(card, dict)
                                    else None,
                                }
                        except Exception:
                            payment_card_info = None

                    response = {
                        "success": True,
                        "order_id": order_id,
                        "order_ids": result.order_ids,
                        "pickup_code": pickup_code,
                        "pickup_codes": result.pickup_codes,
                        "payment_method": payment_method,
                        "payment_status": initial_payment_status,
                        "awaiting_payment": awaiting_payment,
                        "payment_card": payment_card_info,
                        "bookings": created_bookings,
                        "failed": failed_items,
                        "message": result.error_message or "OK",
                    }
                    return add_cors_headers(web.json_response(response, status=201))

            # Fallback: create an order row directly (no new bookings for Mini App)
            if (
                not created_bookings
                and not failed_items
                and order_items
                and hasattr(db, "create_cart_order")
            ):
                payment_method = data.get("payment_method")
                if not payment_method:
                    payment_method = "card" if is_delivery else "cash"

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
                        return add_cors_headers(
                            web.json_response(
                                {"success": False, "error": "Order service not available"},
                                status=500,
                            )
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
            return add_cors_headers(web.json_response(response, status=status_code))

        except Exception as e:
            logger.error(f"API create order error: {e}", exc_info=True)
            return add_cors_headers(
                web.json_response({"error": str(e), "success": False}, status=500)
            )

    async def api_user_orders(request: web.Request) -> web.Response:
        """GET /api/v1/orders - Get user's orders/bookings and delivery orders."""
        try:
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

            import json

            for r in raw_orders:
                if not hasattr(r, "get"):
                    continue

                order_id = r.get("order_id")
                if not order_id:
                    continue

                order_type = r.get("order_type") or (
                    "delivery" if r.get("delivery_address") else "pickup"
                )
                order_status = r.get("order_status") or "pending"

                payment_method = r.get("payment_method") or "cash"
                payment_status = r.get("payment_status")

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
                        title = it.get("title") or "Товар"
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
                    price = int(r.get("offer_price") or 0)
                    title = r.get("offer_title") or "Товар"
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
                    delivery_fee = max(0, total_price - items_total)

                orders.append(
                    {
                        "id": order_id,
                        "order_id": order_id,
                        "booking_id": order_id,  # legacy field used by UI
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
                                "total_price": (b[9] or 0) * (b[6] or 1) if len(b) > 9 else 0,
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

            return add_cors_headers(web.json_response({"bookings": bookings, "orders": orders}))

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
                    status = "preparing" if status == "confirmed" else status
                    booking_code = booking.get("booking_code") or ""
                    quantity = int(booking.get("quantity") or 1)

                    offer = (
                        db.get_offer(int(booking.get("offer_id")))
                        if booking.get("offer_id") and hasattr(db, "get_offer")
                        else None
                    )
                    offer_title = get_offer_value(offer, "title", "Товар") if offer else "Товар"
                    price = int(get_offer_value(offer, "discount_price", 0) or 0) if offer else 0
                    total_price = price * quantity
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
                    if booking_code and status in ("preparing", "confirmed", "ready"):
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

            import json
            from urllib.parse import quote

            items_total = 0
            qty_total = 0
            offer_title = "Заказ"
            offer_photo = None

            if is_cart and cart_items_json:
                try:
                    cart_items = (
                        json.loads(cart_items_json)
                        if isinstance(cart_items_json, str)
                        else cart_items_json
                    )
                except Exception:
                    cart_items = []

                if cart_items:
                    offer_title = cart_items[0].get("title") or "Заказ"
                    qty_total = sum(int(it.get("quantity") or 1) for it in cart_items)
                    items_total = sum(
                        int(it.get("price") or 0) * int(it.get("quantity") or 1)
                        for it in cart_items
                    )

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
                    items_total = price * qty_total
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
                delivery_cost = float(max(0, total_price - items_total))

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
                    status = "preparing" if status == "confirmed" else status
                    created_at = str(booking.get("created_at") or "")
                    updated_at = created_at

                    timeline = [
                        {"status": "pending", "timestamp": created_at, "message": "Заказ создан"}
                    ]
                    if status in ("preparing", "confirmed", "ready", "completed"):
                        timeline.append(
                            {
                                "status": "preparing",
                                "timestamp": updated_at,
                                "message": "Заказ принят и готовится",
                            }
                        )
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

            timeline = [{"status": "pending", "timestamp": created_at, "message": "Заказ создан"}]

            if status in ("preparing", "confirmed", "ready", "delivering", "completed"):
                timeline.append(
                    {
                        "status": "preparing",
                        "timestamp": updated_at,
                        "message": "Заказ принят и готовится",
                    }
                )

            if status in ("ready", "delivering", "completed"):
                timeline.append(
                    {"status": "ready", "timestamp": updated_at, "message": "Заказ готов"}
                )

            if status in ("delivering", "completed"):
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
            if status in ("preparing", "confirmed"):
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
                    status = "preparing" if status == "confirmed" else status
                    booking_code = booking.get("booking_code") or ""

                    if status not in ("preparing", "confirmed", "ready"):
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

    async def api_get_photo(request: web.Request) -> web.Response:
        """GET /api/v1/photo/{file_id} - Get photo URL from Telegram file_id and redirect."""
        file_id = request.match_info.get("file_id")
        if not file_id:
            return add_cors_headers(web.json_response({"error": "file_id required"}, status=400))

        try:
            # Check cache first
            if file_id in _photo_url_cache:
                # Redirect to cached URL
                raise web.HTTPFound(location=_photo_url_cache[file_id])

            # Get file info from Telegram
            file = await bot.get_file(file_id)
            if file and file.file_path:
                # Construct URL and cache it
                photo_url = f"https://api.telegram.org/file/bot{bot.token}/{file.file_path}"
                _photo_url_cache[file_id] = photo_url
                # Redirect to photo URL
                raise web.HTTPFound(location=photo_url)
            else:
                return add_cors_headers(web.json_response({"error": "File not found"}, status=404))
        except web.HTTPFound:
            raise  # Re-raise redirect
        except Exception as e:
            logger.error(f"API get photo error: {e}")
            return add_cors_headers(web.json_response({"error": str(e)}, status=500))

    async def api_get_payment_card(request: web.Request) -> web.Response:
        """GET /api/v1/payment-card/{store_id} - Get payment card for store."""
        store_id = request.match_info.get("store_id")
        try:
            payment_card = None
            payment_instructions = None

            # Try store-specific payment card first
            if store_id and hasattr(db, "get_payment_card"):
                try:
                    store_payment = db.get_payment_card(int(store_id))
                    if store_payment:
                        payment_card = store_payment
                        if isinstance(store_payment, dict):
                            payment_instructions = store_payment.get("payment_instructions")
                except Exception as e:
                    logger.warning(f"Failed to get store payment card: {e}")

            # Fallback to platform payment card
            if not payment_card and hasattr(db, "get_platform_payment_card"):
                payment_card = db.get_platform_payment_card()

            # Default payment card if not configured
            if not payment_card:
                payment_card = {
                    "card_number": "8600 1234 5678 9012",
                    "card_holder": "FUDLY",
                    "payment_instructions": "Chekni yuklashni unutmang!",
                }

            # Normalize payment card format
            if isinstance(payment_card, dict):
                card_number = payment_card.get("card_number", "")
                card_holder = payment_card.get("card_holder", "")
                if not payment_instructions:
                    payment_instructions = payment_card.get("payment_instructions")
            elif isinstance(payment_card, (tuple, list)) and len(payment_card) > 1:
                card_number = payment_card[1] if len(payment_card) > 1 else str(payment_card[0])
                card_holder = payment_card[2] if len(payment_card) > 2 else ""
            else:
                card_number = str(payment_card)
                card_holder = ""

            return add_cors_headers(
                web.json_response(
                    {
                        "card_number": card_number,
                        "card_holder": card_holder,
                        "payment_instructions": payment_instructions,
                    }
                )
            )
        except Exception as e:
            logger.error(f"API get payment card error: {e}")
            return add_cors_headers(web.json_response({"error": str(e)}, status=500))

    async def api_upload_payment_proof(request: web.Request) -> web.Response:
        """POST /api/v1/orders/{order_id}/payment-proof - Upload payment screenshot.

        For DELIVERY orders with CARD payment, this sends the payment proof to ADMIN
        for verification before notifying the seller.
        """
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

                if order_type == "delivery":
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

                    # Build admin message
                    admin_msg = (
                        f"💳 <b>НОВАЯ ДОСТАВКА - ПРОВЕРЬТЕ ОПЛАТУ</b>\n\n"
                        f"📦 Заказ #{order_id}\n"
                        f"👤 {customer_name or 'Клиент'}\n"
                    )
                    if customer_phone:
                        phone_display = customer_phone if customer_phone else "не указан"
                        admin_msg += f"📱 <code>{phone_display}</code>\n"
                    if delivery_address:
                        admin_msg += f"📍 {delivery_address}\n"
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

                    # Send to ADMIN
                    admin_id = int(os.getenv("ADMIN_ID", "0"))
                    if admin_id:
                        try:
                            # SECURITY: user can only upload proof for their own order
                            try:
                                order_user_id_int = int(user_id) if user_id is not None else None
                            except Exception:
                                order_user_id_int = None

                            if order_user_id_int != authenticated_user_id:
                                logger.warning(
                                    "IDOR attempt: user %s tried to upload payment proof for order #%s (owner=%s)",
                                    authenticated_user_id,
                                    order_id,
                                    order_user_id_int,
                                )
                                return add_cors_headers(
                                    web.json_response({"error": "Access denied"}, status=403)
                                )

                            sent_msg = await bot.send_photo(
                                chat_id=admin_id,
                                photo=photo_file,
                                caption=admin_msg,
                                parse_mode="HTML",
                                reply_markup=admin_keyboard,
                            )
                            file_id = sent_msg.photo[-1].file_id
                            logger.info(
                                f"Payment proof for delivery order #{order_id} sent to admin {admin_id}"
                            )

                            # Persist payment proof in DB for audit trail and later access
                            if hasattr(db, "update_payment_status"):
                                db.update_payment_status(order_id, "proof_submitted", file_id)
                            elif hasattr(db, "update_order_payment_proof"):
                                db.update_order_payment_proof(order_id, file_id)

                            return add_cors_headers(
                                web.json_response(
                                    {
                                        "success": True,
                                        "message": "Payment proof sent to admin for verification",
                                    }
                                )
                            )
                        except Exception as e:
                            logger.error(f"Failed to send payment proof to admin: {e}")
                            return add_cors_headers(
                                web.json_response({"error": "Failed to send to admin"}, status=500)
                            )
                    else:
                        return add_cors_headers(
                            web.json_response({"error": "Admin ID not configured"}, status=500)
                        )

            # Order not found or not a delivery order
            return add_cors_headers(
                web.json_response({"error": "Order not found or invalid order type"}, status=404)
            )

        except Exception as e:
            logger.error(f"API upload payment proof error: {e}")
            return add_cors_headers(web.json_response({"error": str(e)}, status=500))

    async def api_health(request: web.Request) -> web.Response:
        """GET /api/v1/health - API health check."""
        return add_cors_headers(
            web.json_response(
                {
                    "status": "ok",
                    "service": "fudly-webapp-api",
                    "timestamp": datetime.now().isoformat(),
                }
            )
        )

    async def api_add_recently_viewed(request: web.Request) -> web.Response:
        """POST /api/v1/user/recently-viewed - Add offer to recently viewed."""
        try:
            data = await request.json()
            authenticated_user_id = _get_authenticated_user_id(request)
            if not authenticated_user_id:
                return add_cors_headers(
                    web.json_response({"error": "Authentication required"}, status=401)
                )

            user_id = authenticated_user_id
            offer_id = data.get("offer_id")

            if not user_id or not offer_id:
                return add_cors_headers(
                    web.json_response({"error": "user_id and offer_id required"}, status=400)
                )

            if hasattr(db, "add_recently_viewed"):
                db.add_recently_viewed(int(user_id), int(offer_id))
                return add_cors_headers(web.json_response({"success": True}))
            else:
                return add_cors_headers(
                    web.json_response({"error": "Feature not available"}, status=501)
                )
        except Exception as e:
            logger.error(f"API add recently viewed error: {e}")
            return add_cors_headers(web.json_response({"error": str(e)}, status=500))

    async def api_get_recently_viewed(request: web.Request) -> web.Response:
        """GET /api/v1/user/recently-viewed - Get user's recently viewed offers."""
        try:
            authenticated_user_id = _get_authenticated_user_id(request)
            if not authenticated_user_id:
                return add_cors_headers(
                    web.json_response({"error": "Authentication required"}, status=401)
                )

            user_id = authenticated_user_id
            limit = int(request.query.get("limit", "20"))

            if not user_id:
                return add_cors_headers(
                    web.json_response({"error": "user_id required"}, status=400)
                )

            if hasattr(db, "get_recently_viewed"):
                offer_ids = db.get_recently_viewed(int(user_id), limit=limit)
                # Get full offer data for each ID
                formatted_offers = []
                for offer_id in offer_ids:
                    if hasattr(db, "get_offer"):
                        offer = db.get_offer(offer_id)
                        if offer and isinstance(offer, dict):
                            formatted_offers.append(
                                {
                                    "id": offer.get("id") or offer.get("offer_id"),
                                    "name": offer.get("name") or offer.get("title", ""),
                                    "title": offer.get("title") or offer.get("name", ""),
                                    "description": offer.get("description", ""),
                                    "old_price": float(
                                        offer.get("old_price") or offer.get("original_price") or 0
                                    ),
                                    "price": float(
                                        offer.get("price") or offer.get("discount_price") or 0
                                    ),
                                    "original_price": float(
                                        offer.get("original_price") or offer.get("old_price") or 0
                                    ),
                                    "discount_price": float(
                                        offer.get("discount_price") or offer.get("price") or 0
                                    ),
                                    "category_id": offer.get("category_id"),
                                    "store_id": offer.get("store_id"),
                                    "store_name": offer.get("store_name", ""),
                                    "photo": offer.get("photo"),
                                    "photo_id": offer.get("photo_id"),
                                    "quantity": offer.get("quantity", 0),
                                    "available": offer.get("status") == "active"
                                    if offer.get("status")
                                    else True,
                                }
                            )
                return add_cors_headers(web.json_response({"offers": formatted_offers}))
            else:
                return add_cors_headers(web.json_response({"offers": []}))
        except Exception as e:
            logger.error(f"API get recently viewed error: {e}")
            return add_cors_headers(web.json_response({"error": str(e)}, status=500))

    async def api_add_search_history(request: web.Request) -> web.Response:
        """POST /api/v1/user/search-history - Add search query to history."""
        try:
            data = await request.json()
            authenticated_user_id = _get_authenticated_user_id(request)
            if not authenticated_user_id:
                return add_cors_headers(
                    web.json_response({"error": "Authentication required"}, status=401)
                )

            user_id = authenticated_user_id
            query = data.get("query", "").strip()

            if not user_id or not query:
                return add_cors_headers(
                    web.json_response({"error": "user_id and query required"}, status=400)
                )

            if len(query) < 2:
                return add_cors_headers(web.json_response({"error": "Query too short"}, status=400))

            if hasattr(db, "add_search_query"):
                db.add_search_query(int(user_id), query)
                return add_cors_headers(web.json_response({"success": True}))
            else:
                return add_cors_headers(
                    web.json_response({"error": "Feature not available"}, status=501)
                )
        except Exception as e:
            logger.error(f"API add search history error: {e}")
            return add_cors_headers(web.json_response({"error": str(e)}, status=500))

    async def api_get_search_history(request: web.Request) -> web.Response:
        """GET /api/v1/user/search-history - Get user's search history."""
        try:
            authenticated_user_id = _get_authenticated_user_id(request)
            if not authenticated_user_id:
                return add_cors_headers(
                    web.json_response({"error": "Authentication required"}, status=401)
                )

            user_id = authenticated_user_id
            limit = int(request.query.get("limit", "10"))

            if not user_id:
                return add_cors_headers(
                    web.json_response({"error": "user_id required"}, status=400)
                )

            if hasattr(db, "get_search_history"):
                history = db.get_search_history(int(user_id), limit=limit)
                return add_cors_headers(web.json_response({"history": history}))
            else:
                return add_cors_headers(web.json_response({"history": []}))
        except Exception as e:
            logger.error(f"API get search history error: {e}")
            return add_cors_headers(web.json_response({"error": str(e)}, status=500))

    async def api_clear_search_history(request: web.Request) -> web.Response:
        """DELETE /api/v1/user/search-history - Clear user's search history."""
        try:
            user_id = request.query.get("user_id")

            if not user_id:
                return add_cors_headers(
                    web.json_response({"error": "user_id required"}, status=400)
                )

            if hasattr(db, "clear_search_history"):
                db.clear_search_history(int(user_id))
                return add_cors_headers(web.json_response({"success": True}))
            else:
                return add_cors_headers(
                    web.json_response({"error": "Feature not available"}, status=501)
                )
        except Exception as e:
            logger.error(f"API clear search history error: {e}")
            return add_cors_headers(web.json_response({"error": str(e)}, status=500))

    async def api_get_store_reviews(request: web.Request) -> web.Response:
        """GET /api/v1/stores/{store_id}/reviews - Get store reviews."""
        store_id = request.match_info.get("store_id")
        try:
            if not store_id:
                return add_cors_headers(
                    web.json_response({"error": "store_id required"}, status=400)
                )

            reviews = []
            avg_rating = 0.0
            total_reviews = 0

            if hasattr(db, "get_store_ratings"):
                raw_reviews = db.get_store_ratings(int(store_id))
                for r in raw_reviews:
                    reviews.append(
                        {
                            "id": r.get("id") or r.get("rating_id"),
                            "user_name": r.get("first_name", "Пользователь"),
                            "rating": r.get("rating", 5),
                            "comment": r.get("comment", ""),
                            "created_at": str(r.get("created_at", "")),
                        }
                    )

            if hasattr(db, "get_store_rating_summary"):
                avg_rating, total_reviews = db.get_store_rating_summary(int(store_id))

            return add_cors_headers(
                web.json_response(
                    {
                        "reviews": reviews,
                        "average_rating": avg_rating,
                        "total_reviews": total_reviews,
                    }
                )
            )
        except Exception as e:
            logger.error(f"API get store reviews error: {e}")
            return add_cors_headers(web.json_response({"error": str(e)}, status=500))

    async def api_get_payment_providers(request: web.Request) -> web.Response:
        """GET /api/v1/payment/providers - Get available payment providers."""
        try:
            payment_service = get_payment_service()
            providers = payment_service.get_available_providers()

            # Return provider info
            result = []
            for provider in providers:
                if provider == "click":
                    result.append({"id": "click", "name": "Click", "icon": "💳", "enabled": True})
                elif provider == "payme":
                    result.append({"id": "payme", "name": "Payme", "icon": "💳", "enabled": True})
                elif provider == "card":
                    result.append(
                        {
                            "id": "card",
                            "name": "Karta orqali",
                            "icon": "💳",
                            "enabled": True,
                            "description": "Karta raqamiga pul o'tkazish",
                        }
                    )

            return add_cors_headers(web.json_response({"providers": result}))
        except Exception as e:
            logger.error(f"API get payment providers error: {e}")
            return add_cors_headers(web.json_response({"error": str(e)}, status=500))

    async def api_create_payment(request: web.Request) -> web.Response:
        """POST /api/v1/payment/create - Create payment URL for order."""
        try:
            data = await request.json()
            order_id = data.get("order_id")
            amount = data.get("amount")
            provider = data.get("provider", "card")
            user_id = data.get("user_id")
            return_url = data.get("return_url")
            store_id = data.get("store_id")  # For per-store credentials

            if not order_id or not amount:
                return add_cors_headers(
                    web.json_response({"error": "order_id and amount required"}, status=400)
                )

            payment_service = get_payment_service()

            if provider == "click":
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
                        web.json_response(
                            {"error": "Click not configured for this store"}, status=400
                        )
                    )
                payment_url = payment_service.generate_click_url(
                    order_id=int(order_id),
                    amount=int(amount),
                    return_url=return_url,
                    user_id=int(user_id) if user_id else 0,
                    store_id=int(store_id) if store_id else 0,
                )
                return add_cors_headers(
                    web.json_response({"payment_url": payment_url, "provider": "click"})
                )

            elif provider == "payme":
                # Check for store-specific or platform-wide Payme credentials
                credentials = (
                    payment_service.get_store_credentials(
                        store_id=int(store_id) if store_id else 0, provider="payme"
                    )
                    if store_id
                    else None
                )
                if not credentials and not payment_service.payme_enabled:
                    return add_cors_headers(
                        web.json_response(
                            {"error": "Payme not configured for this store"}, status=400
                        )
                    )
                payment_url = payment_service.generate_payme_url(
                    order_id=int(order_id),
                    amount=int(amount),
                    return_url=return_url,
                    store_id=int(store_id) if store_id else 0,
                )
                return add_cors_headers(
                    web.json_response({"payment_url": payment_url, "provider": "payme"})
                )

            else:
                # Card payment - return card info
                return add_cors_headers(
                    web.json_response(
                        {
                            "provider": "card",
                            "message": "Use /api/v1/payment-card/{store_id} to get card details",
                        }
                    )
                )

        except Exception as e:
            logger.error(f"API create payment error: {e}")
            return add_cors_headers(web.json_response({"error": str(e)}, status=500))

    async def api_click_callback(request: web.Request) -> web.Response:
        """POST /api/v1/payment/click/callback - Click payment callback."""
        try:
            data = await request.post()

            payment_service = get_payment_service()

            click_trans_id = data.get("click_trans_id", "")
            service_id = data.get("service_id", "")
            merchant_trans_id = data.get("merchant_trans_id", "")
            amount = float(data.get("amount", 0))
            action = data.get("action", "")
            sign_time = data.get("sign_time", "")
            sign_string = data.get("sign_string", "")
            error = int(data.get("error", 0))

            if action == "0":  # Prepare
                result = await payment_service.process_click_prepare(
                    click_trans_id=click_trans_id,
                    merchant_trans_id=merchant_trans_id,
                    amount=amount,
                    action=action,
                    sign_time=sign_time,
                    sign_string=sign_string,
                )
            else:  # Complete
                result = await payment_service.process_click_complete(
                    click_trans_id=click_trans_id,
                    merchant_trans_id=merchant_trans_id,
                    merchant_prepare_id=data.get("merchant_prepare_id", ""),
                    amount=amount,
                    action=action,
                    sign_time=sign_time,
                    sign_string=sign_string,
                    error=error,
                )

            return web.json_response(result)
        except Exception as e:
            logger.error(f"Click callback error: {e}")
            return web.json_response({"error": -1, "error_note": str(e)})

    async def api_payme_callback(request: web.Request) -> web.Response:
        """POST /api/v1/payment/payme/callback - Payme JSON-RPC callback."""
        try:
            # Verify authorization
            payment_service = get_payment_service()
            auth_header = request.headers.get("Authorization", "")

            if not payment_service.verify_payme_signature(auth_header):
                return web.json_response(
                    {"error": {"code": -32504, "message": "Unauthorized"}, "id": None}, status=401
                )

            data = await request.json()
            method = data.get("method", "")
            params = data.get("params", {})
            request_id = data.get("id")

            result = await payment_service.process_payme_request(method, params, request_id)
            return web.json_response(result)
        except Exception as e:
            logger.error(f"Payme callback error: {e}")
            return web.json_response({"error": {"code": -32400, "message": str(e)}, "id": None})

    # Register routes
    path_main = webhook_path if webhook_path.startswith("/") else f"/{webhook_path}"
    path_alt = path_main.rstrip("/") + "/"

    app.router.add_post(path_main, webhook_handler)
    app.router.add_post(path_alt, webhook_handler)
    app.router.add_get(path_main, webhook_get)
    app.router.add_get(path_alt, webhook_get)
    app.router.add_get("/health", health_check)
    app.router.add_get("/version", version_info)
    app.router.add_get("/metrics", metrics_prom)
    app.router.add_get("/metrics.json", metrics_json)
    app.router.add_get("/docs", docs_handler)
    app.router.add_get("/openapi.yaml", openapi_spec_handler)
    app.router.add_get("/", health_check)  # Railway health check

    # Mini App API routes
    app.router.add_options("/api/v1/categories", cors_preflight)
    app.router.add_get("/api/v1/categories", api_categories)
    app.router.add_options("/api/v1/offers", cors_preflight)
    app.router.add_get("/api/v1/offers", api_offers)
    app.router.add_options("/api/v1/offers/{offer_id}", cors_preflight)
    app.router.add_get("/api/v1/offers/{offer_id}", api_offer_detail)
    app.router.add_options("/api/v1/stores", cors_preflight)
    app.router.add_get("/api/v1/stores", api_stores)
    app.router.add_options("/api/v1/orders", cors_preflight)
    app.router.add_post("/api/v1/orders", api_create_order)
    app.router.add_get("/api/v1/orders", api_user_orders)
    app.router.add_options("/api/v1/orders/{order_id}/status", cors_preflight)
    app.router.add_get("/api/v1/orders/{order_id}/status", api_order_status)
    app.router.add_options("/api/v1/orders/{order_id}/timeline", cors_preflight)
    app.router.add_get("/api/v1/orders/{order_id}/timeline", api_order_timeline)
    app.router.add_options("/api/v1/orders/{order_id}/qr", cors_preflight)
    app.router.add_get("/api/v1/orders/{order_id}/qr", api_order_qr)
    # Alias for compatibility
    app.router.add_options("/api/v1/user/bookings", cors_preflight)
    app.router.add_get("/api/v1/user/bookings", api_user_orders)
    app.router.add_options("/api/v1/photo/{file_id}", cors_preflight)
    app.router.add_get("/api/v1/photo/{file_id}", api_get_photo)
    app.router.add_options("/api/v1/payment-card/{store_id}", cors_preflight)
    app.router.add_get("/api/v1/payment-card/{store_id}", api_get_payment_card)
    app.router.add_options("/api/v1/orders/{order_id}/payment-proof", cors_preflight)
    app.router.add_post("/api/v1/orders/{order_id}/payment-proof", api_upload_payment_proof)
    app.router.add_get("/api/v1/health", api_health)
    app.router.add_get("/api/v1/debug", api_debug)

    # User history routes (recently viewed, search history)
    app.router.add_options("/api/v1/user/recently-viewed", cors_preflight)
    app.router.add_post("/api/v1/user/recently-viewed", api_add_recently_viewed)
    app.router.add_get("/api/v1/user/recently-viewed", api_get_recently_viewed)
    app.router.add_options("/api/v1/user/search-history", cors_preflight)
    app.router.add_post("/api/v1/user/search-history", api_add_search_history)
    app.router.add_get("/api/v1/user/search-history", api_get_search_history)
    app.router.add_delete("/api/v1/user/search-history", api_clear_search_history)

    # Store reviews routes
    app.router.add_options("/api/v1/stores/{store_id}/reviews", cors_preflight)
    app.router.add_get("/api/v1/stores/{store_id}/reviews", api_get_store_reviews)

    # Payment routes
    app.router.add_options("/api/v1/payment/providers", cors_preflight)
    app.router.add_get("/api/v1/payment/providers", api_get_payment_providers)
    app.router.add_options("/api/v1/payment/create", cors_preflight)
    app.router.add_post("/api/v1/payment/create", api_create_payment)
    app.router.add_post("/api/v1/payment/click/callback", api_click_callback)
    app.router.add_post("/api/v1/payment/payme/callback", api_payme_callback)

    # Partner Panel API - FastAPI integration via direct ASGI
    if offer_service and bot_token:
        try:
            from app.api.api_server import create_api_app

            # Create FastAPI app with real Partner Panel endpoints
            fastapi_app = create_api_app(db, offer_service, bot_token)

            # Create ASGI handler that calls FastAPI directly
            async def fastapi_handler(request: web.Request) -> web.Response:
                """Forward requests to FastAPI ASGI app"""
                # Read body
                body = await request.read()

                # Build ASGI scope
                scope = {
                    "type": "http",
                    "asgi": {"version": "3.0"},
                    "http_version": "1.1",
                    "method": request.method,
                    "scheme": request.url.scheme,
                    "path": request.path,
                    "query_string": request.query_string.encode(),
                    "root_path": "",
                    "headers": [
                        (k.encode().lower(), v.encode()) for k, v in request.headers.items()
                    ],
                    "server": (request.host.split(":")[0], request.url.port or 80),
                }

                # Collect response
                response_started = False
                status_code = 200
                headers = []
                body_parts = []

                async def receive():
                    return {"type": "http.request", "body": body}

                async def send(message):
                    nonlocal response_started, status_code, headers, body_parts
                    if message["type"] == "http.response.start":
                        response_started = True
                        status_code = message["status"]
                        headers = [(k.decode(), v.decode()) for k, v in message.get("headers", [])]
                    elif message["type"] == "http.response.body":
                        body_parts.append(message.get("body", b""))

                # Call FastAPI
                await fastapi_app(scope, receive, send)

                # Build response
                response_body = b"".join(body_parts)
                return web.Response(body=response_body, status=status_code, headers=dict(headers))

            # Register handler for all /api/* routes (including /api/partner/*)
            app.router.add_route("*", "/api/partner{path:.*}", fastapi_handler)

            logger.info("✅ Partner Panel API endpoints registered (FastAPI direct ASGI)")
        except Exception as e:
            logger.error(f"❌ Failed to mount FastAPI app: {e}", exc_info=True)
            logger.warning("⚠️ Partner Panel API will not be available")
    else:
        logger.warning("⚠️ Partner Panel API disabled (missing offer_service or bot_token)")

    # Setup WebSocket routes for real-time notifications
    setup_websocket_routes(app)

    # Initialize notification service
    redis_url = None  # Can be configured via env
    notification_service = get_notification_service(redis_url)
    notification_service.set_telegram_bot(bot)

    # Initialize WebSocket manager
    ws_manager = get_websocket_manager()
    ws_manager.set_notification_service(notification_service)

    # Store services in app for access in handlers
    app["notification_service"] = notification_service
    app["websocket_manager"] = ws_manager

    # Serve static files for Partner Panel and Mini App
    from pathlib import Path

    webapp_dist_path = Path(__file__).parent.parent.parent / "webapp" / "dist"
    partner_panel_path = Path(__file__).parent.parent.parent / "webapp" / "partner-panel"

    logger.info(f"📁 Partner Panel path: {partner_panel_path.absolute()}")
    logger.info(f"📁 Partner Panel exists: {partner_panel_path.exists()}")
    logger.info(f"📁 Mini App path: {webapp_dist_path.absolute()}")
    logger.info(f"📁 Mini App exists: {webapp_dist_path.exists()}")

    # Add static file handlers (Partner Panel FIRST - more specific path)
    if partner_panel_path.exists() and (partner_panel_path / "index.html").exists():

        async def serve_partner_panel(request):
            """Serve Partner Panel files."""
            filename = request.match_info.get("filename", "")

            # If no filename or ends with /, serve index.html
            if not filename or filename.endswith("/"):
                return web.FileResponse(partner_panel_path / "index.html")

            full_path = partner_panel_path / filename

            # Serve file if exists
            if full_path.exists() and full_path.is_file():
                return web.FileResponse(full_path)

            # Otherwise serve index.html (for SPA routing)
            return web.FileResponse(partner_panel_path / "index.html")

        # Register Partner Panel routes
        app.router.add_get("/partner-panel", serve_partner_panel)
        app.router.add_get("/partner-panel/", serve_partner_panel)
        app.router.add_get("/partner-panel/{filename:.*}", serve_partner_panel)

        logger.info("✅ Partner Panel mounted at /partner-panel")
        logger.info("   Access at: https://fudly-bot-production.up.railway.app/partner-panel/")
    else:
        logger.error(f"❌ Partner Panel not found at {partner_panel_path}")
        if partner_panel_path.exists():
            logger.error(f"   Files: {list(partner_panel_path.iterdir())[:5]}")

    # Add Mini App static file handler (LAST - catches all remaining /)
    if webapp_dist_path.exists() and (webapp_dist_path / "index.html").exists():

        async def serve_webapp(request):
            """Serve Mini App index.html for all /* routes not caught by other handlers."""
            file_path = request.match_info.get("filename", "index.html")
            full_path = webapp_dist_path / file_path

            # Serve file if exists
            if full_path.exists() and full_path.is_file():
                return web.FileResponse(full_path)

            # Otherwise serve index.html for SPA routing
            return web.FileResponse(webapp_dist_path / "index.html")

        # Register Mini App routes (will catch anything not matched above)
        app.router.add_get("/{filename:.*\\..*}", serve_webapp)  # Files with extensions

        logger.info("✅ Mini App mounted at /")
    else:
        logger.error(f"❌ Mini App not found at {webapp_dist_path}")

    return app


async def run_webhook_server(
    app: web.Application,
    port: int,
) -> web.AppRunner:
    """Start webhook server and return runner for cleanup."""
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()

    logger.info(f"🌐 Webhook server started on port {port}")
    return runner
