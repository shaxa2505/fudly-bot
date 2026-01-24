"""Webhook server for production deployment."""
from __future__ import annotations

import os
import time
from typing import Any

from aiogram import Bot, Dispatcher, types
import aiohttp
from aiohttp import web

from app.core.notifications import get_notification_service
from app.core.webhook_api_utils import add_cors_headers, build_authenticated_user_id, cors_preflight
from app.core.webhook_meta import (
    build_docs_handler,
    build_health_check,
    build_metrics_json,
    build_metrics_prom,
    build_openapi_spec_handler,
    build_version_info,
)
from app.core.webhook_cart_routes import build_cart_handlers
from app.core.webhook_discovery_routes import build_discovery_handlers
from app.core.webhook_misc_routes import build_misc_handlers
from app.core.webhook_orders_routes import build_order_handlers
from app.core.webhook_offers_routes import build_offer_store_handlers
from app.core.webhook_payment_callbacks import build_click_callback, build_payme_callback
from app.core.webhook_payment_routes import build_payment_handlers
from app.core.webhook_media_routes import build_media_handlers
from app.core.webhook_user_history import (
    build_recently_viewed_handlers,
    build_search_history_handlers,
)
from app.core.websocket import get_websocket_manager, setup_websocket_routes
from logging_config import logger

# Cache for reverse geocoding results (lat,lng -> payload)
_reverse_geocode_cache: dict[str, tuple[float, dict[str, Any]]] = {}
_REVERSE_GEOCODE_TTL = 3600


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
    payment_link_cache: dict[tuple[int, str], dict[str, Any]] = {}
    payment_link_ttl = 90.0

    def get_cached_payment_link(order_id: int, provider: str) -> str | None:
        key = (order_id, provider)
        cached = payment_link_cache.get(key)
        if not cached:
            return None
        if time.monotonic() - cached["ts"] > payment_link_ttl:
            payment_link_cache.pop(key, None)
            return None
        return cached["url"]

    def set_cached_payment_link(order_id: int, provider: str, url: str) -> None:
        payment_link_cache[(order_id, provider)] = {"url": url, "ts": time.monotonic()}

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

    async def webhook_get(request: web.Request) -> web.Response:
        """Simple GET responder for webhook URL health checks."""
        return web.Response(status=200, text="OK")

    health_check = build_health_check(db, metrics)
    version_info = build_version_info()
    metrics_prom = build_metrics_prom()
    metrics_json = build_metrics_json(metrics)
    docs_handler = build_docs_handler()
    openapi_spec_handler = build_openapi_spec_handler()

    # =========================================================================
    # Mini App API Endpoints
    # =========================================================================

    _get_authenticated_user_id = build_authenticated_user_id(bot.token)

    api_categories, api_search_suggestions, api_hot_deals_stats = build_discovery_handlers(db)

    async def api_reverse_geocode(request: web.Request) -> web.Response:
        """GET /api/v1/location/reverse - Reverse geocode."""
        def _parse_float(value: str | None) -> float | None:
            if value is None or value == "":
                return None
            try:
                return float(value)
            except ValueError:
                return None

        lat = _parse_float(request.query.get("lat") or request.query.get("latitude"))
        lon = _parse_float(request.query.get("lon") or request.query.get("longitude"))
        lang = request.query.get("lang", "uz")

        if lat is None or lon is None:
            return add_cors_headers(
                web.json_response({"detail": "Latitude and longitude are required"}, status=400)
            )

        cache_key = f"{round(lat, 5)}:{round(lon, 5)}:{str(lang).strip().lower()}"
        cached = _reverse_geocode_cache.get(cache_key)
        if cached:
            cached_at, payload = cached
            if time.time() - cached_at < _REVERSE_GEOCODE_TTL:
                return add_cors_headers(web.json_response(payload))
            _reverse_geocode_cache.pop(cache_key, None)

        url = "https://nominatim.openstreetmap.org/reverse"
        params = {
            "format": "jsonv2",
            "lat": lat,
            "lon": lon,
            "accept-language": lang,
        }
        headers = {
            "User-Agent": "FudlyApp/1.0 (webapp reverse geocode)",
        }

        try:
            timeout = aiohttp.ClientTimeout(total=8)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(url, params=params, headers=headers) as response:
                    if response.status != 200:
                        return add_cors_headers(
                            web.json_response({"detail": "Geo lookup failed"}, status=502)
                        )
                    payload = await response.json()
        except Exception as exc:
            logger.error("API reverse geocode error: %s", exc)
            return add_cors_headers(
                web.json_response({"detail": "Geo lookup failed"}, status=502)
            )

        _reverse_geocode_cache[cache_key] = (time.time(), payload)
        return add_cors_headers(web.json_response(payload))

    api_offers, api_offer_detail, api_flash_deals, api_stores, api_store_detail = (
        build_offer_store_handlers(bot, db)
    )

    api_debug, api_health = build_misc_handlers(db)

    api_calculate_cart = build_cart_handlers(db)

    api_create_order, api_user_orders, api_order_status, api_order_timeline, api_order_qr, api_upload_payment_proof = (
        build_order_handlers(bot, db, _get_authenticated_user_id)
    )

    api_get_photo, api_get_payment_card = build_media_handlers(bot, db)

    api_add_recently_viewed, api_get_recently_viewed = build_recently_viewed_handlers(
        db, _get_authenticated_user_id
    )
    api_add_search_history, api_get_search_history, api_clear_search_history = (
        build_search_history_handlers(db, _get_authenticated_user_id)
    )

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

    api_get_payment_providers, api_create_payment = build_payment_handlers(
        db, _get_authenticated_user_id, get_cached_payment_link, set_cached_payment_link
    )

    api_click_callback = build_click_callback(db)
    api_payme_callback = build_payme_callback()

    # Register routes
    path_main = webhook_path if webhook_path.startswith("/") else f"/{webhook_path}"
    path_alt = path_main.rstrip("/") + "/"

    app.router.add_post(path_main, webhook_handler)
    app.router.add_post(path_alt, webhook_handler)
    app.router.add_get(path_main, webhook_get)
    app.router.add_get(path_alt, webhook_get)
    app.router.add_get("/health", health_check)
    app.router.add_get("/", health_check)
    app.router.add_get("/version", version_info)
    app.router.add_get("/metrics", metrics_prom)
    app.router.add_get("/metrics.json", metrics_json)
    app.router.add_get("/docs", docs_handler)
    app.router.add_get("/openapi.yaml", openapi_spec_handler)

    # Mini App API routes
    app.router.add_options("/api/v1/payment-card/{store_id}", cors_preflight)
    app.router.add_get("/api/v1/payment-card/{store_id}", api_get_payment_card)
    app.router.add_get("/api/v1/debug", api_debug)

    # User history routes (recently viewed, search history)
    app.router.add_options("/api/v1/user/recently-viewed", cors_preflight)
    app.router.add_post("/api/v1/user/recently-viewed", api_add_recently_viewed)
    app.router.add_get("/api/v1/user/recently-viewed", api_get_recently_viewed)
    app.router.add_options("/api/v1/user/search-history", cors_preflight)
    app.router.add_post("/api/v1/user/search-history", api_add_search_history)
    app.router.add_get("/api/v1/user/search-history", api_get_search_history)
    app.router.add_delete("/api/v1/user/search-history", api_clear_search_history)

    # Payment routes
    app.router.add_options("/api/v1/payment/providers", cors_preflight)
    app.router.add_get("/api/v1/payment/providers", api_get_payment_providers)
    app.router.add_options("/api/v1/payment/create", cors_preflight)
    app.router.add_post("/api/v1/payment/create", api_create_payment)
    app.router.add_post("/api/v1/payment/click/callback", api_click_callback)
    app.router.add_post("/api/v1/payment/payme/callback", api_payme_callback)

    fastapi_handler = None

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

            # Register handler for Partner Panel API routes
            app.router.add_route("*", "/api/partner{path:.*}", fastapi_handler)

            logger.info("✅ Partner Panel API endpoints registered (FastAPI direct ASGI)")
        except Exception as e:
            logger.error(f"❌ Failed to mount FastAPI app: {e}", exc_info=True)
            logger.warning("⚠️ Partner Panel API will not be available")
    else:
        logger.warning("⚠️ Partner Panel API disabled (missing offer_service or bot_token)")

    if fastapi_handler:
        app.router.add_route("*", "/api/merchant{path:.*}", fastapi_handler)
        app.router.add_route("*", "/api/v1/auth{path:.*}", fastapi_handler)
        app.router.add_route("*", "/api/v1/orders{path:.*}", fastapi_handler)
        app.router.add_route("*", "/api/v1/user/orders{path:.*}", fastapi_handler)
        app.router.add_route("*", "/api/v1/user/bookings{path:.*}", fastapi_handler)
        app.router.add_route("*", "/api/v1/user/profile{path:.*}", fastapi_handler)
        app.router.add_route("*", "/api/v1/user/notifications{path:.*}", fastapi_handler)
        app.router.add_route("*", "/api/v1/cart{path:.*}", fastapi_handler)
        app.router.add_route("*", "/api/v1/categories{path:.*}", fastapi_handler)
        app.router.add_route("*", "/api/v1/favorites{path:.*}", fastapi_handler)
        app.router.add_route("*", "/api/v1/flash-deals{path:.*}", fastapi_handler)
        app.router.add_route("*", "/api/v1/offers{path:.*}", fastapi_handler)
        app.router.add_route("*", "/api/v1/search{path:.*}", fastapi_handler)
        app.router.add_route("*", "/api/v1/stats{path:.*}", fastapi_handler)
        app.router.add_route("*", "/api/v1/stores{path:.*}", fastapi_handler)
        app.router.add_route("*", "/api/v1/photo{path:.*}", fastapi_handler)
        app.router.add_route("*", "/api/v1/location{path:.*}", fastapi_handler)
        app.router.add_route("*", "/api/v1/health{path:.*}", fastapi_handler)
        logger.info("✅ /api/v1/orders routed to FastAPI")
    else:
        app.router.add_options("/api/v1/categories", cors_preflight)
        app.router.add_get("/api/v1/categories", api_categories)
        app.router.add_options("/api/v1/search/suggestions", cors_preflight)
        app.router.add_get("/api/v1/search/suggestions", api_search_suggestions)
        app.router.add_options("/api/v1/stats/hot-deals", cors_preflight)
        app.router.add_get("/api/v1/stats/hot-deals", api_hot_deals_stats)
        app.router.add_options("/api/v1/location/reverse", cors_preflight)
        app.router.add_get("/api/v1/location/reverse", api_reverse_geocode)
        app.router.add_options("/api/v1/flash-deals", cors_preflight)
        app.router.add_get("/api/v1/flash-deals", api_flash_deals)
        app.router.add_options("/api/v1/offers", cors_preflight)
        app.router.add_get("/api/v1/offers", api_offers)
        app.router.add_options("/api/v1/offers/{offer_id}", cors_preflight)
        app.router.add_get("/api/v1/offers/{offer_id}", api_offer_detail)
        app.router.add_options("/api/v1/stores", cors_preflight)
        app.router.add_get("/api/v1/stores", api_stores)
        app.router.add_options("/api/v1/stores/{store_id}", cors_preflight)
        app.router.add_get("/api/v1/stores/{store_id}", api_store_detail)
        app.router.add_options("/api/v1/cart/calculate", cors_preflight)
        app.router.add_get("/api/v1/cart/calculate", api_calculate_cart)
        app.router.add_options("/api/v1/photo/{file_id}", cors_preflight)
        app.router.add_get("/api/v1/photo/{file_id}", api_get_photo)
        app.router.add_get("/api/v1/health", api_health)
        app.router.add_options("/api/v1/orders", cors_preflight)
        app.router.add_post("/api/v1/orders", api_create_order)
        app.router.add_get("/api/v1/orders", api_user_orders)
        app.router.add_options("/api/v1/orders/{order_id}/status", cors_preflight)
        app.router.add_get("/api/v1/orders/{order_id}/status", api_order_status)
        app.router.add_options("/api/v1/orders/{order_id}/timeline", cors_preflight)
        app.router.add_get("/api/v1/orders/{order_id}/timeline", api_order_timeline)
        app.router.add_options("/api/v1/orders/{order_id}/qr", cors_preflight)
        app.router.add_get("/api/v1/orders/{order_id}/qr", api_order_qr)
        app.router.add_options("/api/v1/orders/{order_id}/payment-proof", cors_preflight)
        app.router.add_post("/api/v1/orders/{order_id}/payment-proof", api_upload_payment_proof)
        app.router.add_options("/api/v1/stores/{store_id}/reviews", cors_preflight)
        app.router.add_get("/api/v1/stores/{store_id}/reviews", api_get_store_reviews)

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
    app["db"] = db

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
