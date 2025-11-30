"""Webhook server for production deployment."""
from __future__ import annotations

import os
from datetime import datetime
from typing import Any

from aiogram import Bot, Dispatcher, types
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiohttp import web

from app.core.metrics import metrics as app_metrics
from app.core.notifications import get_notification_service
from app.core.websocket import get_websocket_manager, setup_websocket_routes
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

            http_status = 200 if db_healthy else 503
            return web.json_response(status, status=http_status)
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return web.json_response({"status": "error", "error": str(e)}, status=500)

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

            # Convert offers with photo URLs
            offers = []
            for o in raw_offers:
                photo_id = get_offer_value(o, "photo_id")
                photo_url = await get_photo_url(bot, photo_id) if photo_id else None
                offers.append(offer_to_dict(o, photo_url))

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

            # Get stores from database
            if hasattr(db, "get_connection"):
                with db.get_connection() as conn:
                    cursor = conn.cursor()
                    if city:
                        cursor.execute(
                            "SELECT * FROM stores WHERE (status = 'active' OR status = 'approved') AND city = %s",
                            (city,),
                        )
                    else:
                        cursor.execute(
                            "SELECT * FROM stores WHERE status = 'active' OR status = 'approved'"
                        )
                    columns = [desc[0] for desc in cursor.description]
                    raw_stores = [dict(zip(columns, row)) for row in cursor.fetchall()]

            # Convert stores with photo URLs
            stores = []
            for s in raw_stores:
                photo_id = get_offer_value(s, "photo")
                photo_url = await get_photo_url(bot, photo_id) if photo_id else None
                stores.append(store_to_dict(s, photo_url))

            logger.info(f"API /stores: returning {len(stores)} stores")
            return add_cors_headers(web.json_response(stores))

        except Exception as e:
            logger.error(f"API stores error: {e}")
            return add_cors_headers(web.json_response({"error": str(e)}, status=500))

    async def api_create_order(request: web.Request) -> web.Response:
        """POST /api/v1/orders - Create order from Mini App cart."""
        try:
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

            # Process each item in cart
            created_bookings = []
            failed_items = []

            for item in items:
                offer_id = item.get("id") or item.get("offer_id")
                quantity = item.get("quantity", 1)

                if not offer_id:
                    failed_items.append({"item": item, "error": "Missing offer_id"})
                    continue

                try:
                    # Create booking atomically
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
                                db.get_offer(int(offer_id)) if hasattr(db, "get_offer") else None
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

                                            # Create inline keyboard for seller actions
                                            keyboard = InlineKeyboardMarkup(
                                                inline_keyboard=[
                                                    [
                                                        InlineKeyboardButton(
                                                            text="✅ Принять",
                                                            callback_data=f"order_accept:{booking_code}:{user_id}",
                                                        ),
                                                        InlineKeyboardButton(
                                                            text="❌ Отклонить",
                                                            callback_data=f"order_reject:{booking_code}:{user_id}",
                                                        ),
                                                    ]
                                                ]
                                            )

                                            # Send via bot with keyboard
                                            await bot.send_message(
                                                chat_id=int(seller_id),
                                                text=msg,
                                                parse_mode="HTML",
                                                reply_markup=keyboard,
                                            )
                                            logger.info(f"Notification sent to seller {seller_id}")
                        except Exception as notify_err:
                            logger.warning(f"Failed to notify seller: {notify_err}")

                    else:
                        failed_items.append(
                            {"offer_id": offer_id, "error": error_reason or "Booking failed"}
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
        """GET /api/v1/orders - Get user's orders/bookings."""
        try:
            user_id = request.query.get("user_id")
            if not user_id:
                return add_cors_headers(
                    web.json_response({"error": "user_id required"}, status=400)
                )

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
                                    photo_file_id = get_offer_value(offer, "photo_file_id")
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

            return add_cors_headers(web.json_response({"bookings": bookings}))

        except Exception as e:
            logger.error(f"API user orders error: {e}")
            return add_cors_headers(web.json_response({"error": str(e)}, status=500))

    async def api_get_photo(request: web.Request) -> web.Response:
        """GET /api/v1/photo/{file_id} - Get photo URL from Telegram file_id."""
        file_id = request.match_info.get("file_id")
        if not file_id:
            return add_cors_headers(web.json_response({"error": "file_id required"}, status=400))

        try:
            # Get file info from Telegram
            file = await bot.get_file(file_id)
            if file and file.file_path:
                # Construct URL
                photo_url = f"https://api.telegram.org/file/bot{bot.token}/{file.file_path}"
                return add_cors_headers(web.json_response({"url": photo_url}))
            else:
                return add_cors_headers(web.json_response({"error": "File not found"}, status=404))
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
        """POST /api/v1/orders/{order_id}/payment-proof - Upload payment screenshot."""
        order_id = request.match_info.get("order_id")
        try:
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

            # Upload photo to Telegram and get file_id
            from aiogram.types import BufferedInputFile

            photo_file = BufferedInputFile(photo_data, filename=filename)
            # Send to admin/bot to get file_id
            admin_id = int(os.getenv("ADMIN_ID", "0"))
            if admin_id:
                sent_msg = await bot.send_photo(
                    admin_id, photo_file, caption=f"📸 Чек для заказа #{order_id} (Mini App)"
                )
                file_id = sent_msg.photo[-1].file_id

                # Update order with payment proof
                if hasattr(db, "update_payment_status"):
                    db.update_payment_status(int(order_id), "pending", file_id)

                return add_cors_headers(
                    web.json_response(
                        {
                            "success": True,
                            "message": "Payment proof uploaded",
                            "file_id": file_id,
                        }
                    )
                )
            else:
                return add_cors_headers(
                    web.json_response({"error": "Admin not configured"}, status=500)
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
