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
        """GET /api/v1/debug - Debug database info."""
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
            )
            from app.services.unified_order_service import (
                OrderResult,
                get_unified_order_service,
            )

            data = await request.json()
            logger.info(f"API /orders request: {data}")

            # Extract order data
            items = data.get("items", [])
            user_id = data.get("user_id")
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

            if not user_id:
                return add_cors_headers(
                    web.json_response({"error": "User ID required"}, status=400)
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
                    # 🔴 CRITICAL: DELIVERY + CARD orders must wait for payment proof
                    # They should NOT notify sellers until admin confirms payment
                    if is_delivery and data.get("payment_method") == "card":
                        # Create order with awaiting_payment status
                        # Seller will be notified ONLY after admin confirms payment
                        result: OrderResult = await order_service.create_order(
                            user_id=int(user_id),
                            items=order_items,
                            order_type="delivery",
                            delivery_address=address,
                            payment_method="card",
                            notify_customer=True,  # ✅ Tell customer order created
                            notify_sellers=False,  # ❌ DON'T notify seller yet!
                        )

                        if result and result.success and result.order_ids:
                            # Get payment card info
                            payment_card_info = None
                            if hasattr(db, "get_payment_card"):
                                card = db.get_payment_card()
                                if card:
                                    payment_card_info = {
                                        "card_number": card.get("card_number") or card[0]
                                        if isinstance(card, tuple)
                                        else None,
                                        "card_holder": card.get("card_holder") or card[1]
                                        if isinstance(card, tuple) and len(card) > 1
                                        else None,
                                    }

                            # Return response with card info - user can pay and upload proof later
                            return add_cors_headers(
                                web.json_response(
                                    {
                                        "success": True,
                                        "order_id": result.order_ids[0],
                                        "awaiting_payment": True,  # Payment confirmation needed
                                        "payment_card": payment_card_info,
                                        "message": "Buyurtma yaratildi. Iltimos, to'lovni amalga oshiring va chekni yuklang.",
                                    }
                                )
                            )

                    # For PICKUP or CASH delivery - normal flow
                    else:
                        result: OrderResult = await order_service.create_order(
                            user_id=int(user_id),
                            items=order_items,
                            order_type="delivery" if is_delivery else "pickup",
                            delivery_address=address if is_delivery else None,
                            payment_method=data.get("payment_method", "card"),
                            notify_customer=True,
                            notify_sellers=True,  # ✅ OK for pickup/cash
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
                    # For compatibility this endpoint still returns bookings-style data
                    if is_delivery:
                        for item_obj, oid in zip(order_items, result.order_ids):
                            created_bookings.append(
                                {
                                    "booking_id": oid,
                                    "booking_code": None,
                                    "offer_id": item_obj.offer_id,
                                    "quantity": item_obj.quantity,
                                }
                            )
                    else:
                        for item_obj, bid in zip(order_items, result.booking_ids):
                            created_bookings.append(
                                {
                                    "booking_id": bid,
                                    "booking_code": None,
                                    "offer_id": item_obj.offer_id,
                                    "quantity": item_obj.quantity,
                                }
                            )

            # Fallback: legacy per-item booking creation
            if not created_bookings and not failed_items:
                for item in items:
                    offer_id = item.get("id") or item.get("offer_id")
                    quantity = item.get("quantity", 1)

                    if not offer_id:
                        failed_items.append({"item": item, "error": "Missing offer_id"})
                        continue

                    try:
                        result = db.create_booking_atomic(
                            offer_id=int(offer_id),
                            user_id=int(user_id),
                            quantity=int(quantity),
                            pickup_time=None,
                            pickup_address=address if delivery_type == "pickup" else None,
                        )

                        # Handle result (3 or 4 tuple)
                        if len(result) == 4:
                            ok, booking_id, booking_code, error_reason = result
                        else:
                            ok, booking_id, booking_code = result
                            error_reason = None

                        if ok and booking_id:
                            created_bookings.append(
                                {
                                    "booking_id": booking_id,
                                    "booking_code": booking_code,
                                    "offer_id": offer_id,
                                    "quantity": quantity,
                                }
                            )

                            # Send notification to seller
                            try:
                                offer = (
                                    db.get_offer(int(offer_id))
                                    if hasattr(db, "get_offer")
                                    else None
                                )
                                if offer:
                                    store_id = get_offer_value(offer, "store_id")
                                    if store_id and hasattr(db, "get_store"):
                                        store = db.get_store(store_id)
                                        if store:
                                            seller_id = get_offer_value(
                                                store, "owner_id"
                                            ) or get_offer_value(store, "user_id")
                                            if seller_id:
                                                title = get_offer_value(offer, "title", "Товар")
                                                price = get_offer_value(offer, "discount_price", 0)

                                                # Format notification message
                                                msg = (
                                                    f"🛒 <b>Новый заказ из Mini App!</b>\n\n"
                                                    f"📦 Товар: {title}\n"
                                                    f"🔢 Количество: {quantity}\n"
                                                    f"💰 Сумма: {int(price * quantity):,} сум\n"
                                                    f"🎫 Код: <code>{booking_code}</code>\n\n"
                                                    f"📱 Телефон: {phone or 'не указан'}\n"
                                                    f"🚚 Тип: {'Самовывоз' if delivery_type == 'pickup' else 'Доставка'}\n"
                                                )
                                                if address:
                                                    msg += f"📍 Адрес: {address}\n"
                                                if notes:
                                                    msg += f"📝 Примечание: {notes}\n"

                                                keyboard = InlineKeyboardMarkup(
                                                    inline_keyboard=[
                                                        [
                                                            InlineKeyboardButton(
                                                                text="✅ Принять",
                                                                callback_data=f"booking_confirm_{booking_id}",
                                                            ),
                                                            InlineKeyboardButton(
                                                                text="❌ Отклонить",
                                                                callback_data=f"booking_reject_{booking_id}",
                                                            ),
                                                        ]
                                                    ]
                                                )

                                                await bot.send_message(
                                                    chat_id=int(seller_id),
                                                    text=msg,
                                                    parse_mode="HTML",
                                                    reply_markup=keyboard,
                                                )
                                                logger.info(
                                                    f"Notification sent to seller {seller_id}"
                                                )
                            except Exception as notify_err:
                                logger.warning(f"Failed to notify seller: {notify_err}")

                        else:
                            failed_items.append(
                                {
                                    "offer_id": offer_id,
                                    "error": error_reason or "Booking failed",
                                }
                            )

                    except Exception as item_err:
                        logger.error(f"Error processing item {offer_id}: {item_err}")
                        failed_items.append({"offer_id": offer_id, "error": str(item_err)})

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
            user_id = request.query.get("user_id")
            if not user_id:
                return add_cors_headers(
                    web.json_response({"error": "user_id required"}, status=400)
                )

            # Get delivery orders (new system)
            delivery_orders = []
            if hasattr(db, "get_user_delivery_orders"):
                raw_orders = db.get_user_delivery_orders(int(user_id)) or []
                for order_row in raw_orders:
                    # Parse order from tuple: (id, user_id, status, order_type, payment_method,
                    # delivery_address, phone, total_price, created_at, ...)
                    order_id = order_row[0] if len(order_row) > 0 else None

                    # Get order items
                    items = []
                    if order_id and hasattr(db, "get_delivery_order_items"):
                        raw_items = db.get_delivery_order_items(order_id) or []
                        for item_row in raw_items:
                            # Parse item: (offer_id, store_id, title, price, quantity, store_name, photo_id, ...)
                            photo_url = None
                            if len(item_row) > 6 and item_row[6]:
                                try:
                                    file = await bot.get_file(item_row[6])
                                    if file and file.file_path:
                                        photo_url = f"https://api.telegram.org/file/bot{bot.token}/{file.file_path}"
                                except Exception:
                                    pass

                            items.append(
                                {
                                    "offer_id": item_row[0] if len(item_row) > 0 else None,
                                    "store_id": item_row[1] if len(item_row) > 1 else None,
                                    "title": item_row[2] if len(item_row) > 2 else "Mahsulot",
                                    "price": item_row[3] if len(item_row) > 3 else 0,
                                    "quantity": item_row[4] if len(item_row) > 4 else 1,
                                    "store_name": item_row[5] if len(item_row) > 5 else "Do'kon",
                                    "photo_url": photo_url,
                                }
                            )

                    order_dict = {
                        "id": order_id,
                        "order_id": order_id,
                        "user_id": order_row[1] if len(order_row) > 1 else None,
                        "status": order_row[2] if len(order_row) > 2 else None,
                        "order_type": order_row[3] if len(order_row) > 3 else None,
                        "payment_method": order_row[4] if len(order_row) > 4 else None,
                        "delivery_address": order_row[5] if len(order_row) > 5 else None,
                        "phone": order_row[6] if len(order_row) > 6 else None,
                        "total_price": order_row[7] if len(order_row) > 7 else 0,
                        "created_at": str(order_row[8])
                        if len(order_row) > 8 and order_row[8]
                        else None,
                        "items": items,
                    }
                    delivery_orders.append(order_dict)

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

            return add_cors_headers(
                web.json_response({"bookings": bookings, "orders": delivery_orders})
            )

        except Exception as e:
            logger.error(f"API user orders error: {e}")
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
                    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

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

                            # Update order status to awaiting_admin_confirmation
                            if hasattr(db, "update_order_status"):
                                db.update_order_status(order_id, "awaiting_admin_confirmation")

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
            user_id = data.get("user_id")
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
            user_id = request.query.get("user_id")
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
            user_id = data.get("user_id")
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
            user_id = request.query.get("user_id")
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

    # Partner Panel API - FastAPI integration via a2wsgi
    if offer_service and bot_token:
        try:
            from a2wsgi import ASGIMiddleware

            from app.api.api_server import create_api_app

            # Create FastAPI app with real Partner Panel endpoints
            fastapi_app = create_api_app(db, offer_service, bot_token)

            # Wrap FastAPI in WSGI middleware
            wsgi_app = ASGIMiddleware(fastapi_app)

            # Create handler for /api/* routes
            async def fastapi_handler(request: web.Request) -> web.Response:
                """Proxy requests to FastAPI app"""
                # Build WSGI environ
                environ = {
                    "REQUEST_METHOD": request.method,
                    "SCRIPT_NAME": "",
                    "PATH_INFO": request.path,
                    "QUERY_STRING": request.query_string,
                    "CONTENT_TYPE": request.headers.get("Content-Type", ""),
                    "CONTENT_LENGTH": request.headers.get("Content-Length", ""),
                    "SERVER_NAME": request.host.split(":")[0],
                    "SERVER_PORT": str(request.url.port or 80),
                    "SERVER_PROTOCOL": "HTTP/1.1",
                    "wsgi.version": (1, 0),
                    "wsgi.url_scheme": request.url.scheme,
                    "wsgi.input": request.content,
                    "wsgi.errors": sys.stderr,
                    "wsgi.multithread": True,
                    "wsgi.multiprocess": False,
                    "wsgi.run_once": False,
                }

                # Add headers
                for key, value in request.headers.items():
                    key = key.upper().replace("-", "_")
                    if key not in ("CONTENT_TYPE", "CONTENT_LENGTH"):
                        environ[f"HTTP_{key}"] = value

                # Call WSGI app
                response_started = False
                status_code = 200
                headers_list = []

                def start_response(status, response_headers):
                    nonlocal response_started, status_code, headers_list
                    response_started = True
                    status_code = int(status.split(" ")[0])
                    headers_list = response_headers

                body_parts = []
                async for part in wsgi_app(environ, start_response):
                    if isinstance(part, bytes):
                        body_parts.append(part)
                    else:
                        body_parts.append(part.encode())

                body = b"".join(body_parts)
                return web.Response(body=body, status=status_code, headers=dict(headers_list))

            # Register handler for all /api/* routes
            app.router.add_route("*", "/api/{path:.*}", fastapi_handler)

            logger.info("✅ Partner Panel API endpoints registered (FastAPI via a2wsgi)")
        except ImportError as e:
            logger.error(f"❌ Failed to import a2wsgi: {e}")
            logger.warning("⚠️ Partner Panel API will not be available - install a2wsgi")
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
