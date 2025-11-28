"""Webhook server for production deployment."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from aiogram import Bot, Dispatcher, types
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


def offer_to_dict(offer: Any) -> dict:
    """Convert offer to API response dict."""
    # Try offer_id first (PostgreSQL), then id (SQLite)
    offer_id = get_offer_value(offer, "offer_id", 0) or get_offer_value(offer, "id", 0)
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
        "photo": get_offer_value(offer, "photo"),
        "expiry_date": str(get_offer_value(offer, "expiry_date", ""))
        if get_offer_value(offer, "expiry_date")
        else None,
    }


def store_to_dict(store: Any) -> dict:
    """Convert store to API response dict."""
    return {
        "id": get_offer_value(store, "id", 0),
        "name": get_offer_value(store, "name", ""),
        "address": get_offer_value(store, "address"),
        "city": get_offer_value(store, "city"),
        "business_type": get_offer_value(store, "business_type", "supermarket"),
        "rating": float(get_offer_value(store, "rating", 0) or 0),
        "offers_count": int(get_offer_value(store, "offers_count", 0) or 0),
    }


# Categories list
API_CATEGORIES = [
    {"id": "all", "name": "Все", "emoji": "🔥"},
    {"id": "dairy", "name": "Молочные", "emoji": "🥛"},
    {"id": "bakery", "name": "Выпечка", "emoji": "🍞"},
    {"id": "meat", "name": "Мясо", "emoji": "🥩"},
    {"id": "fruits", "name": "Фрукты", "emoji": "🍎"},
    {"id": "vegetables", "name": "Овощи", "emoji": "🥕"},
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
                if hasattr(db, "get_offers_by_category"):
                    raw_offers = db.get_offers_by_category(category, city) or []
                    logger.info(
                        f"get_offers_by_category({category}) returned {len(raw_offers)} items"
                    )
            else:
                if hasattr(db, "get_hot_offers"):
                    raw_offers = db.get_hot_offers(city, limit=limit, offset=offset) or []
                    logger.info(f"get_hot_offers({city}) returned {len(raw_offers)} items")
                else:
                    logger.warning("db has no get_hot_offers method!")

            offers = [offer_to_dict(o) for o in raw_offers]
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

            return add_cors_headers(web.json_response(offer_to_dict(offer)))

        except Exception as e:
            logger.error(f"API offer detail error: {e}")
            return add_cors_headers(web.json_response({"error": str(e)}, status=500))

    async def api_stores(request: web.Request) -> web.Response:
        """GET /api/v1/stores - List stores."""
        city = request.query.get("city", "Ташкент")
        business_type = request.query.get("business_type")

        try:
            raw_stores: list[Any] = []

            if business_type:
                if hasattr(db, "get_stores_by_business_type"):
                    raw_stores = db.get_stores_by_business_type(business_type, city) or []
            else:
                if hasattr(db, "get_all_stores"):
                    raw_stores = db.get_all_stores(city) or []

            stores = [store_to_dict(s) for s in raw_stores]
            return add_cors_headers(web.json_response(stores))

        except Exception as e:
            logger.error(f"API stores error: {e}")
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
