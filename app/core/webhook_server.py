"""Webhook server for production deployment."""
from __future__ import annotations

import asyncio
import os
import sys
import time
from datetime import date, datetime, timedelta
from typing import Any

from aiogram import Bot, Dispatcher, types
from aiogram.exceptions import TelegramAPIError
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
import aiohttp
from aiohttp import web

from app.core.metrics import metrics as app_metrics
from app.core.notifications import get_notification_service
from app.core.websocket import get_websocket_manager, setup_websocket_routes
from app.core.utils import normalize_city
from app.core.idempotency import (
    build_request_hash,
    check_or_reserve_key,
    normalize_idempotency_key,
    store_idempotency_response,
)
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


def _parse_offer_expiry_date(value: Any) -> date | None:
    if not value:
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, str):
        raw = value.strip()
        if not raw:
            return None
        try:
            return datetime.fromisoformat(raw.replace("Z", "+00:00")).date()
        except ValueError:
            pass
        try:
            return datetime.strptime(raw[:10], "%Y-%m-%d").date()
        except ValueError:
            pass
        try:
            return datetime.strptime(raw[:10], "%d.%m.%Y").date()
        except ValueError:
            pass
    return None


def _get_offer_quantity(offer: Any) -> int | None:
    raw_qty = get_offer_value(offer, "stock_quantity")
    if raw_qty is None:
        raw_qty = get_offer_value(offer, "quantity")
    if raw_qty is None:
        return None
    try:
        return int(raw_qty)
    except (TypeError, ValueError):
        return None


def _is_offer_active(offer: Any) -> bool:
    if not offer:
        return False

    status = get_offer_value(offer, "status")
    if status and str(status).lower() != "active":
        return False

    qty = _get_offer_quantity(offer)
    if qty is not None and qty <= 0:
        return False

    expiry_date = _parse_offer_expiry_date(get_offer_value(offer, "expiry_date"))
    if expiry_date and expiry_date < date.today():
        return False

    return True


# Cache for photo URLs (file_id -> URL)
_photo_url_cache: dict[str, str] = {}
_reverse_geocode_cache: dict[str, tuple[float, dict[str, Any]]] = {}
_REVERSE_GEOCODE_TTL = 3600
_LEGACY_BOT_TOKEN = (
    os.getenv("LEGACY_TELEGRAM_BOT_TOKEN")
    or os.getenv("OLD_TELEGRAM_BOT_TOKEN")
    or os.getenv("PHOTO_FALLBACK_BOT_TOKEN")
)


async def get_photo_url(bot: Bot, file_id: str | None) -> str | None:
    """Convert Telegram file_id to photo URL."""
    if not file_id:
        return None

    # Check cache
    if file_id in _photo_url_cache:
        return _photo_url_cache[file_id]

    async def _try_get_url(token: str) -> str | None:
        temp_bot = bot if token == bot.token else Bot(token=token)
        try:
            file = await temp_bot.get_file(file_id)
            if file and file.file_path:
                url = f"https://api.telegram.org/file/bot{token}/{file.file_path}"
                _photo_url_cache[file_id] = url
                if token != bot.token:
                    logger.info("Photo resolved using legacy bot token")
                return url
        finally:
            # Do not close shared bot session
            if temp_bot is not bot:
                await temp_bot.session.close()
        return None

    try:
        url = await _try_get_url(bot.token)
        if url:
            return url
    except TelegramAPIError:
        pass
    except Exception:
        logger.debug("Primary bot failed to fetch photo_id %s", file_id, exc_info=True)

    if _LEGACY_BOT_TOKEN and _LEGACY_BOT_TOKEN != bot.token:
        try:
            return await _try_get_url(_LEGACY_BOT_TOKEN)
        except TelegramAPIError:
            logger.warning("Legacy bot token could not fetch photo_id %s", file_id)
        except Exception:
            logger.debug("Legacy bot fallback failed for %s", file_id, exc_info=True)

    return None


def offer_to_dict(offer: Any, photo_url: str | None = None) -> dict:
    """Convert offer to API response dict."""
    # Try offer_id first (PostgreSQL), then id (SQLite)
    offer_id = get_offer_value(offer, "offer_id", 0) or get_offer_value(offer, "id", 0)

    # Use provided photo_url, or fallback to photo field
    photo = photo_url or get_offer_value(offer, "photo")

    price_unit = os.getenv("PRICE_STORAGE_UNIT", "sums").lower()
    convert = (lambda v: float(v or 0) / 100) if price_unit == "kopeks" else (lambda v: float(v or 0))

    return {
        "id": offer_id,
        "title": get_offer_value(offer, "title", ""),
        "description": get_offer_value(offer, "description"),
        "original_price": convert(get_offer_value(offer, "original_price", 0)),
        "discount_price": convert(get_offer_value(offer, "discount_price", 0)),
        "discount_percent": float(get_offer_value(offer, "discount_percent", 0) or 0),
        "quantity": int(get_offer_value(offer, "quantity", 0) or 0),
        "category": get_offer_value(offer, "category", "other") or "other",
        "store_id": int(get_offer_value(offer, "store_id", 0) or 0),
        "store_name": get_offer_value(offer, "store_name", "") or "",
        "store_address": get_offer_value(offer, "store_address")
        or get_offer_value(offer, "address"),
        "delivery_enabled": bool(get_offer_value(offer, "delivery_enabled", False)),
        "delivery_price": convert(get_offer_value(offer, "delivery_price", 0) or 0),
        "min_order_amount": convert(get_offer_value(offer, "min_order_amount", 0) or 0),
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

CATEGORY_ALIASES = {
    "sweets": ["sweets", "snacks"],
}


def expand_category_filter(category: str | None) -> list[str] | None:
    if not category:
        return None
    normalized = str(category).strip().lower()
    if not normalized or normalized == "all":
        return None
    return CATEGORY_ALIASES.get(normalized, [normalized])


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
                "Access-Control-Allow-Methods": "GET, POST, DELETE, OPTIONS",
                "Access-Control-Allow-Headers": (
                    "Content-Type, X-Telegram-Init-Data, Idempotency-Key, X-Idempotency-Key"
                ),
                "Access-Control-Max-Age": "86400",
            },
        )

    def add_cors_headers(response: web.Response) -> web.Response:
        """Add CORS headers to response."""
        response.headers["Access-Control-Allow-Origin"] = "*"
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, DELETE, OPTIONS"
        response.headers["Access-Control-Allow-Headers"] = (
            "Content-Type, X-Telegram-Init-Data, Idempotency-Key, X-Idempotency-Key"
        )
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
        city = request.query.get("city", "")
        city = city.strip() if isinstance(city, str) else city
        city = city or None
        region = request.query.get("region", "")
        region = region.strip() if isinstance(region, str) else region
        region = region or None
        district = request.query.get("district", "")
        district = district.strip() if isinstance(district, str) else district
        district = district or None
        normalized_city = normalize_city(city) if city else None
        normalized_region = normalize_city(region) if region else None
        normalized_district = normalize_city(district) if district else None
        result = []

        def _count_for_scope(
            category_filter: list[str] | None,
            city_scope: str | None,
            region_scope: str | None,
            district_scope: str | None,
        ) -> int:
            if hasattr(db, "count_offers_by_filters"):
                return int(
                    db.count_offers_by_filters(
                        city=city_scope,
                        region=region_scope,
                        district=district_scope,
                        category=category_filter,
                    )
                )
            if category_filter:
                if hasattr(db, "get_offers_by_city_and_category"):
                    offers = db.get_offers_by_city_and_category(
                        city=city_scope,
                        category=category_filter,
                        region=region_scope,
                        district=district_scope,
                        limit=1000,
                        offset=0,
                    ) or []
                    return len(offers)
                if hasattr(db, "get_offers_by_category"):
                    if isinstance(category_filter, (list, tuple)):
                        offers = []
                        for item in category_filter:
                            offers.extend(db.get_offers_by_category(item, city_scope) or [])
                        return len(offers)
                    offers = db.get_offers_by_category(category_filter, city_scope) or []
                    return len(offers)
                return 0
            if hasattr(db, "count_hot_offers"):
                return (
                    db.count_hot_offers(
                        city_scope,
                        region=region_scope,
                        district=district_scope,
                    )
                    or 0
                )
            return 0

        scopes: list[tuple[str | None, str | None, str | None]] = []
        if normalized_district:
            scopes.append((None, normalized_region, normalized_district))
        if normalized_region:
            scopes.append((None, normalized_region, None))
        if normalized_city:
            scopes.append((normalized_city, None, None))
            if not normalized_region:
                scopes.append((None, normalized_city, None))
        if not scopes:
            scopes.append((None, None, None))

        for cat in API_CATEGORIES:
            count = 0
            category_filter = expand_category_filter(cat["id"])
            try:
                for city_scope, region_scope, district_scope in scopes:
                    count = _count_for_scope(
                        category_filter if cat["id"] != "all" else None,
                        city_scope,
                        region_scope,
                        district_scope,
                    )
                    if count:
                        break
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

    async def api_search_suggestions(request: web.Request) -> web.Response:
        """GET /api/v1/search/suggestions - Search autocomplete suggestions."""
        query = request.query.get("query", "")
        city = request.query.get("city")
        region = request.query.get("region")
        district = request.query.get("district")
        limit_raw = request.query.get("limit", "5")
        try:
            limit = max(1, min(int(limit_raw), 10))
        except (TypeError, ValueError):
            limit = 5

        if not query or len(query) < 2:
            return add_cors_headers(web.json_response([]))

        city = city.strip() if isinstance(city, str) else city
        city = city or None
        region = region.strip() if isinstance(region, str) else region
        region = region or None
        district = district.strip() if isinstance(district, str) else district
        district = district or None

        normalized_city = normalize_city(city) if city else None
        normalized_region = normalize_city(region) if region else None
        normalized_district = normalize_city(district) if district else None
        suggestions: list[str] = []
        try:
            if hasattr(db, "get_search_suggestions"):
                suggestions = (
                    db.get_search_suggestions(
                        query,
                        limit=limit,
                        city=normalized_city,
                        region=normalized_region,
                        district=normalized_district,
                    )
                    or []
                )
            elif hasattr(db, "get_offer_suggestions"):
                suggestions = (
                    db.get_offer_suggestions(
                        query,
                        limit=limit,
                        city=normalized_city,
                        region=normalized_region,
                        district=normalized_district,
                    )
                    or []
                )
            elif hasattr(db, "search_offers"):
                offers = (
                    db.search_offers(
                        query,
                        city=normalized_city,
                        limit=limit * 2,
                        region=normalized_region,
                        district=normalized_district,
                    )
                    or []
                )
                titles = {
                    get_offer_value(o, "title", "") for o in offers if get_offer_value(o, "title")
                }
                suggestions.extend(list(titles)[:limit])
        except Exception as exc:
            logger.error("API search suggestions error: %s", exc)
            suggestions = []

        return add_cors_headers(web.json_response(suggestions[:limit]))

    async def api_hot_deals_stats(request: web.Request) -> web.Response:
        """GET /api/v1/stats/hot-deals - Stats for hot deals."""
        city = request.query.get("city")
        normalized_city = normalize_city(city) if city else None
        stats = {
            "total_offers": 0,
            "total_stores": 0,
            "avg_discount": 0.0,
            "max_discount": 0.0,
            "categories_count": len(API_CATEGORIES) - 1,
        }

        try:
            if hasattr(db, "get_hot_offers"):
                offers = db.get_hot_offers(normalized_city, limit=1000) or []
                stats["total_offers"] = len(offers)
                discounts: list[float] = []
                for offer in offers:
                    discount = float(get_offer_value(offer, "discount_percent", 0) or 0)
                    discounts.append(discount)
                if discounts:
                    stats["avg_discount"] = round(sum(discounts) / len(discounts), 1)
                    stats["max_discount"] = round(max(discounts), 1)

            if hasattr(db, "get_stores_by_city"):
                stores = db.get_stores_by_city(normalized_city)
                stats["total_stores"] = len(stores or [])
        except Exception as exc:
            logger.error("API hot deals stats error: %s", exc)

        return add_cors_headers(web.json_response(stats))

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

    async def api_offers(request: web.Request) -> web.Response:
        """GET /api/v1/offers - List offers."""
        def _parse_float(value: str | None) -> float | None:
            if value is None or value == "":
                return None
            try:
                return float(value)
            except ValueError:
                return None

        city = request.query.get("city", "")  # Empty = all cities
        region = request.query.get("region") or None
        district = request.query.get("district") or None
        category = request.query.get("category", "all")
        category_filter = expand_category_filter(category)
        store_id = request.query.get("store_id")
        search = request.query.get("search")
        limit = int(request.query.get("limit", "50"))
        offset = int(request.query.get("offset", "0"))
        sort_by = request.query.get("sort_by")
        min_price = _parse_float(request.query.get("min_price"))
        max_price = _parse_float(request.query.get("max_price"))
        min_discount = _parse_float(request.query.get("min_discount"))
        lat = _parse_float(request.query.get("lat") or request.query.get("latitude"))
        lon = _parse_float(request.query.get("lon") or request.query.get("longitude"))
        price_unit = os.getenv("PRICE_STORAGE_UNIT", "sums").lower()
        if price_unit == "kopeks":
            if min_price is not None:
                min_price *= 100
            if max_price is not None:
                max_price *= 100

        city = city.strip() if isinstance(city, str) else city
        city = city or None
        region = region.strip() if isinstance(region, str) else region
        region = region or None
        district = district.strip() if isinstance(district, str) else district
        district = district or None

        city = normalize_city(city) if city else None
        region = normalize_city(region) if region else None
        district = normalize_city(district) if district else None

        logger.info(f"API /offers request: city={city}, category={category}, limit={limit}")

        try:
            raw_offers: list[Any] = []

            if store_id:
                if hasattr(db, "get_store_offers"):
                    raw_offers = db.get_store_offers(int(store_id)) or []
                    logger.info(f"get_store_offers({store_id}) returned {len(raw_offers)} items")
            elif search:
                if hasattr(db, "search_offers"):
                    def _search_scoped(
                        city_scope: str | None,
                        region_scope: str | None,
                        district_scope: str | None,
                    ) -> list[Any]:
                        return (
                            db.search_offers(
                                search,
                                city_scope,
                                limit=limit,
                                offset=offset,
                                region=region_scope,
                                district=district_scope,
                                min_price=min_price,
                                max_price=max_price,
                                min_discount=min_discount,
                                category=category_filter,
                            )
                            or []
                        )

                    raw_offers = _search_scoped(city, region, district)
                    if not raw_offers:
                        scopes: list[tuple[str | None, str | None, str | None]] = []
                        if district:
                            scopes.append((None, region, district))
                        if region:
                            scopes.append((None, region, None))
                        if city:
                            scopes.append((city, None, None))
                            if not region:
                                scopes.append((None, city, None))
                        scopes.append((None, None, None))

                        seen: set[tuple[str | None, str | None, str | None]] = set()
                        for scope in scopes:
                            if scope in seen:
                                continue
                            seen.add(scope)
                            raw_offers = _search_scoped(*scope)
                            if raw_offers:
                                break
                    logger.info(f"search_offers returned {len(raw_offers)} items")
            else:
                def _fetch_scoped_offers(
                    city_scope: str | None, region_scope: str | None, district_scope: str | None
                ) -> list[Any]:
                    if category_filter:
                        if hasattr(db, "get_offers_by_city_and_category"):
                            return (
                                db.get_offers_by_city_and_category(
                                    city_scope,
                                    category_filter,
                                    limit=limit,
                                    offset=offset,
                                    region=region_scope,
                                    district=district_scope,
                                    sort_by=sort_by,
                                    min_price=min_price,
                                    max_price=max_price,
                                    min_discount=min_discount,
                                )
                                or []
                            )
                        if hasattr(db, "get_hot_offers"):
                            all_offers = (
                                db.get_hot_offers(
                                    city_scope,
                                    limit=100,
                                    offset=0,
                                    region=region_scope,
                                    district=district_scope,
                                    sort_by=sort_by,
                                    min_price=min_price,
                                    max_price=max_price,
                                    min_discount=min_discount,
                                )
                                or []
                            )
                            if isinstance(category_filter, (list, tuple)):
                                return [
                                    o
                                    for o in all_offers
                                    if get_offer_value(o, "category") in category_filter
                                ][:limit]
                            return [
                                o for o in all_offers if get_offer_value(o, "category") == category_filter
                            ][:limit]
                        return []
                    if hasattr(db, "get_hot_offers"):
                        return (
                            db.get_hot_offers(
                                city_scope,
                                limit=limit,
                                offset=offset,
                                region=region_scope,
                                district=district_scope,
                                sort_by=sort_by,
                                min_price=min_price,
                                max_price=max_price,
                                min_discount=min_discount,
                            )
                            or []
                        )
                    return []

                scopes: list[tuple[str | None, str | None, str | None]] = []
                if district:
                    scopes.append((None, region, district))
                if region:
                    scopes.append((None, region, None))
                if city:
                    scopes.append((city, None, None))
                    if not region:
                        scopes.append((None, city, None))
                if not scopes:
                    scopes.append((None, None, None))

                seen: set[tuple[str | None, str | None, str | None]] = set()
                for scope in scopes:
                    if scope in seen:
                        continue
                    seen.add(scope)
                    raw_offers = _fetch_scoped_offers(*scope)
                    if raw_offers:
                        break

                if (
                    not raw_offers
                    and lat is not None
                    and lon is not None
                    and hasattr(db, "get_nearby_offers")
                ):
                    raw_offers = (
                        db.get_nearby_offers(
                            latitude=lat,
                            longitude=lon,
                            limit=limit,
                            offset=offset,
                            category=category_filter,
                            sort_by=sort_by,
                            min_price=min_price,
                            max_price=max_price,
                            min_discount=min_discount,
                        )
                        or []
                    )

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
            if not _is_offer_active(offer):
                return add_cors_headers(web.json_response({"error": "Not found"}, status=404))

            # Convert photo_id to URL
            photo_id = get_offer_value(offer, "photo_id")
            photo_url = await get_photo_url(bot, photo_id) if photo_id else None

            return add_cors_headers(web.json_response(offer_to_dict(offer, photo_url)))

        except Exception as e:
            logger.error(f"API offer detail error: {e}")
            return add_cors_headers(web.json_response({"error": str(e)}, status=500))

    async def api_flash_deals(request: web.Request) -> web.Response:
        """GET /api/v1/flash-deals - High discount or expiring soon offers."""
        city = request.query.get("city")
        region = request.query.get("region") or None
        district = request.query.get("district") or None
        limit_raw = request.query.get("limit", "10")
        try:
            limit = int(limit_raw)
        except (TypeError, ValueError):
            limit = 10
        limit = max(1, min(limit, 50))

        normalized_city = normalize_city(city) if city else None
        normalized_region = normalize_city(region) if region else None
        normalized_district = normalize_city(district) if district else None
        try:
            raw_offers = (
                db.get_hot_offers(
                    normalized_city,
                    limit=100,
                    offset=0,
                    region=normalized_region,
                    district=normalized_district,
                )
                if hasattr(db, "get_hot_offers")
                else []
            )
            if (
                not raw_offers
                and normalized_city
                and (normalized_region or normalized_district)
                and hasattr(db, "get_hot_offers")
            ):
                raw_offers = db.get_hot_offers(normalized_city, limit=100, offset=0)
            if not raw_offers:
                raw_offers = []

            today = datetime.now().date()
            max_expiry = today + timedelta(days=7)
            filtered: list[tuple[Any, float, str | None]] = []

            for offer in raw_offers:
                try:
                    discount = float(get_offer_value(offer, "discount_percent", 0) or 0)
                    if not discount:
                        original_price = float(get_offer_value(offer, "original_price", 0) or 0)
                        discount_price = float(get_offer_value(offer, "discount_price", 0) or 0)
                        if (
                            original_price
                            and original_price > 0
                            and discount_price >= 0
                            and original_price > discount_price
                        ):
                            discount = round(
                                (1.0 - (discount_price / original_price)) * 100.0, 1
                            )

                    expiry_str = get_offer_value(offer, "expiry_date")
                    is_expiring_soon = False
                    if expiry_str:
                        try:
                            expiry = datetime.fromisoformat(str(expiry_str).split("T")[0]).date()
                            is_expiring_soon = today <= expiry <= max_expiry
                        except (ValueError, AttributeError):
                            pass

                    if discount >= 20 or is_expiring_soon:
                        filtered.append((offer, discount, expiry_str))
                except Exception as exc:
                    logger.warning("Flash deals filter error: %s", exc)
                    continue

            filtered.sort(key=lambda item: (-item[1], str(item[2] or "9999")))
            selected = filtered[:limit]

            async def load_offer_with_photo(item: tuple[Any, float, str | None]) -> dict:
                offer, discount, _expiry = item
                photo_id = get_offer_value(offer, "photo_id") or get_offer_value(offer, "photo")
                photo_url = await get_photo_url(bot, photo_id) if photo_id else None
                offer_dict = offer_to_dict(offer, photo_url)
                if discount and not offer_dict.get("discount_percent"):
                    offer_dict["discount_percent"] = discount
                return offer_dict

            offers = await asyncio.gather(*[load_offer_with_photo(item) for item in selected])
            return add_cors_headers(web.json_response(offers))

        except Exception as e:
            logger.error(f"API flash deals error: {e}")
            return add_cors_headers(web.json_response({"error": str(e)}, status=500))

    async def api_stores(request: web.Request) -> web.Response:
        """GET /api/v1/stores - List stores."""
        def _parse_float(value: str | None) -> float | None:
            if value is None or value == "":
                return None
            try:
                return float(value)
            except ValueError:
                return None

        city = request.query.get("city", "")  # Empty = all cities
        region = request.query.get("region") or None
        district = request.query.get("district") or None
        business_type = request.query.get("business_type")
        lat = _parse_float(request.query.get("lat") or request.query.get("latitude"))
        lon = _parse_float(request.query.get("lon") or request.query.get("longitude"))
        city = city.strip() if isinstance(city, str) else city
        city = city or None
        region = region.strip() if isinstance(region, str) else region
        region = region or None
        district = district.strip() if isinstance(district, str) else district
        district = district or None

        city = normalize_city(city) if city else None
        region = normalize_city(region) if region else None
        district = normalize_city(district) if district else None

        try:
            raw_stores: list[Any] = []

            # Get stores from database with offers count
            if hasattr(db, "get_stores_by_location"):
                def _fetch_scoped_stores(
                    city_scope: str | None, region_scope: str | None, district_scope: str | None
                ) -> list[Any]:
                    return db.get_stores_by_location(
                        city=city_scope,
                        region=region_scope,
                        district=district_scope,
                        business_type=business_type,
                    )

                scopes: list[tuple[str | None, str | None, str | None]] = []
                if district:
                    scopes.append((None, region, district))
                if region:
                    scopes.append((None, region, None))
                if city:
                    scopes.append((city, None, None))
                    if not region:
                        scopes.append((None, city, None))
                if not scopes:
                    scopes.append((None, None, None))

                seen: set[tuple[str | None, str | None, str | None]] = set()
                for scope in scopes:
                    if scope in seen:
                        continue
                    seen.add(scope)
                    raw_stores = _fetch_scoped_stores(*scope) or []
                    if raw_stores:
                        break

                if (
                    not raw_stores
                    and lat is not None
                    and lon is not None
                    and hasattr(db, "get_nearby_stores")
                ):
                    raw_stores = (
                        db.get_nearby_stores(
                            latitude=lat,
                            longitude=lon,
                            business_type=business_type,
                            limit=200,
                            offset=0,
                        )
                        or []
                    )
            elif hasattr(db, "get_connection"):
                with db.get_connection() as conn:
                    cursor = conn.cursor()
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

    async def api_store_detail(request: web.Request) -> web.Response:
        """GET /api/v1/stores/{store_id} - Store details."""
        store_id_raw = request.match_info.get("store_id")
        try:
            store_id = int(store_id_raw)
        except (TypeError, ValueError):
            return add_cors_headers(web.json_response({"error": "Invalid store_id"}, status=400))

        try:
            store = db.get_store(store_id) if hasattr(db, "get_store") else None
            if not store:
                return add_cors_headers(web.json_response({"error": "Store not found"}, status=404))

            offers_count = int(get_offer_value(store, "offers_count", 0) or 0)
            if offers_count == 0 and hasattr(db, "get_store_offers"):
                try:
                    offers_count = len(db.get_store_offers(store_id) or [])
                except Exception:
                    offers_count = 0

            rating = float(
                get_offer_value(store, "avg_rating", 0) or get_offer_value(store, "rating", 0) or 0
            )
            if rating == 0.0 and hasattr(db, "get_store_average_rating"):
                try:
                    rating = float(db.get_store_average_rating(store_id) or 0)
                except Exception:
                    rating = 0.0

            photo_id = get_offer_value(store, "photo")
            photo_url = await get_photo_url(bot, photo_id) if photo_id else None
            store_dict = store_to_dict(store, photo_url)
            store_dict["offers_count"] = offers_count
            store_dict["rating"] = rating

            region = get_offer_value(store, "region")
            if region is not None:
                store_dict["region"] = region
            district = get_offer_value(store, "district")
            if district is not None:
                store_dict["district"] = district

            return add_cors_headers(web.json_response(store_dict))

        except Exception as e:
            logger.error(f"API store detail error: {e}")
            return add_cors_headers(web.json_response({"error": str(e)}, status=500))

    async def api_calculate_cart(request: web.Request) -> web.Response:
        """GET /api/v1/cart/calculate - Calculate cart totals."""
        offer_ids = request.query.get("offer_ids", "")
        if not offer_ids:
            return add_cors_headers(
                web.json_response({"error": "offer_ids required"}, status=400)
            )

        price_unit = os.getenv("PRICE_STORAGE_UNIT", "sums").lower()
        convert = (lambda v: float(v or 0) / 100) if price_unit == "kopeks" else (
            lambda v: float(v or 0)
        )

        items = []
        total = 0.0
        items_count = 0

        try:
            for item_str in offer_ids.split(","):
                if ":" not in item_str:
                    continue
                offer_id_str, qty_str = item_str.split(":", 1)
                try:
                    offer_id = int(offer_id_str)
                    quantity = int(qty_str)
                except (TypeError, ValueError):
                    continue

                offer = db.get_offer(offer_id) if hasattr(db, "get_offer") else None
                if not offer or not _is_offer_active(offer):
                    continue

                price = convert(get_offer_value(offer, "discount_price", 0))
                items.append(
                    {
                        "offer_id": offer_id,
                        "quantity": quantity,
                        "title": get_offer_value(offer, "title", ""),
                        "price": price,
                        "photo": get_offer_value(offer, "photo") or get_offer_value(offer, "photo_id"),
                    }
                )
                total += price * quantity
                items_count += quantity

            payload = {"items": items, "total": total, "items_count": items_count}
            return add_cors_headers(web.json_response(payload))
        except Exception as e:
            logger.error(f"API cart calculate error: {e}")
            return add_cors_headers(web.json_response({"error": str(e)}, status=500))

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
            if isinstance(payment_proof, str) and payment_proof.strip().startswith("data:"):
                logger.info("Ignoring data URL payment_proof in create_order payload")
                payment_proof = None

            if not items:
                return add_cors_headers(
                    web.json_response({"error": "No items in order"}, status=400)
                )

            is_delivery = delivery_type == "delivery"
            payment_method = data.get("payment_method")
            if not payment_method:
                payment_method = "card" if is_delivery else "cash"
            payment_method = PaymentStatus.normalize_method(payment_method)

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
            if is_delivery and payment_method == "cash":
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
                        payment_proof=str(payment_proof) if payment_proof else None,
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

                    initial_payment_status = PaymentStatus.initial_for_method(payment_method)
                    resolved_payment_status = initial_payment_status
                    if payment_proof and result.order_ids and hasattr(db, "update_payment_status"):
                        try:
                            for order_id in result.order_ids:
                                db.update_payment_status(
                                    int(order_id),
                                    PaymentStatus.PROOF_SUBMITTED,
                                    str(payment_proof),
                                )
                            resolved_payment_status = PaymentStatus.PROOF_SUBMITTED
                        except Exception as proof_err:
                            logger.warning(f"Failed to attach payment_proof to orders: {proof_err}")

                    awaiting_payment = resolved_payment_status in (
                        PaymentStatus.AWAITING_PAYMENT,
                        PaymentStatus.AWAITING_PROOF,
                        PaymentStatus.PROOF_SUBMITTED,
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
                        "payment_status": resolved_payment_status,
                        "awaiting_payment": awaiting_payment,
                        "payment_card": payment_card_info,
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
                        payment_proof=str(payment_proof) if payment_proof else None,
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
                order_status_raw = r.get("order_status") or "pending"
                order_status = OrderStatus.normalize(str(order_status_raw).strip().lower())

                raw_payment_method = r.get("payment_method")
                if raw_payment_method:
                    payment_method = PaymentStatus.normalize_method(raw_payment_method)
                else:
                    payment_method = "card" if order_type == "delivery" else "cash"
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
            photo_url = await get_photo_url(bot, file_id)
            if photo_url:
                raise web.HTTPFound(location=photo_url)
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
                    import json

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
                        try:
                            cart_items = (
                                json.loads(cart_items_json)
                                if isinstance(cart_items_json, str)
                                else cart_items_json
                            )
                        except Exception:
                            pass

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
                            item_total = price * qty
                            admin_msg += f"{idx}. {title} × {qty} = {int(item_total):,} сум\n"

                        if len(cart_items) > 5:
                            admin_msg += f"   ... и ещё {len(cart_items) - 5}\n"

                    # Total
                    subtotal = total_price - delivery_fee if delivery_fee else total_price
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
                return add_cors_headers(web.json_response({"success": False}))

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
                return add_cors_headers(web.json_response({"offers": []}))

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
                        if offer and isinstance(offer, dict) and _is_offer_active(offer):
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
                return add_cors_headers(web.json_response({"success": False}))

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
                return add_cors_headers(web.json_response({"history": []}))

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
            authenticated_user_id = _get_authenticated_user_id(request)
            if not authenticated_user_id:
                return add_cors_headers(web.json_response({"success": False}))

            if hasattr(db, "clear_search_history"):
                db.clear_search_history(int(authenticated_user_id))
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
            store_id = request.query.get("store_id")
            store_id_int = int(store_id) if store_id and store_id.isdigit() else None
            providers = payment_service.get_available_providers(store_id_int)

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
            authenticated_user_id = _get_authenticated_user_id(request)
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
                    return add_cors_headers(
                        web.json_response({"error": "Access denied"}, status=403)
                    )
            order_id = data.get("order_id")
            amount = data.get("amount")
            provider = str(data.get("provider", "card")).lower()
            user_id = authenticated_user_id
            return_url = data.get("return_url")
            store_id = data.get("store_id")  # For per-store credentials

            if not order_id:
                return add_cors_headers(
                    web.json_response({"error": "order_id required"}, status=400)
                )

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

            if not store_id:
                store_id = order.get("store_id")

            if not amount:
                amount = order.get("total_price")
            else:
                order_total = order.get("total_price")
                if order_total is not None and int(amount) != int(order_total):
                    amount = order_total

            order_status = str(order.get("order_status") or order.get("status") or "").lower()
            payment_status = str(order.get("payment_status") or "").lower()
            payment_method = str(order.get("payment_method") or "").lower()

            if order_status in ("completed", "cancelled", "rejected"):
                return add_cors_headers(
                    web.json_response({"error": "Order already finalized"}, status=400)
                )

            if provider in ("click", "payme"):
                if payment_method and payment_method != provider:
                    return add_cors_headers(
                        web.json_response({"error": "Payment method mismatch"}, status=400)
                    )
                if payment_status not in ("awaiting_payment", ""):
                    return add_cors_headers(
                        web.json_response(
                            {"error": "Payment not awaiting online payment"}, status=400
                        )
                    )
            elif provider == "card":
                if payment_status in ("proof_submitted", "completed"):
                    return add_cors_headers(
                        web.json_response({"error": "Payment already submitted"}, status=400)
                    )
            else:
                return add_cors_headers(
                    web.json_response({"error": "Unknown payment provider"}, status=400)
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
                set_cached_payment_link(int(order_id), "click", payment_url)
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
                set_cached_payment_link(int(order_id), "payme", payment_url)
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
            data = None
            try:
                data = await request.post()
            except Exception:
                data = None

            payload: dict[str, Any] = {}
            if data:
                payload = dict(data)
            else:
                try:
                    json_payload = await request.json()
                    if isinstance(json_payload, dict):
                        payload = json_payload
                except Exception:
                    payload = {}

            if not payload:
                try:
                    payload = dict(request.query)
                except Exception:
                    payload = {}

            def _get_value(key: str, default: Any = "") -> Any:
                value = payload.get(key, default)
                if isinstance(value, (list, tuple)):
                    return value[0] if value else default
                return value

            payment_service = get_payment_service()
            if hasattr(payment_service, "set_database"):
                payment_service.set_database(db)

            click_trans_id = _get_value("click_trans_id", "")
            service_id = _get_value("service_id", "")
            merchant_trans_id = _get_value("merchant_trans_id", "")
            amount = _get_value("amount", "0")
            action = _get_value("action", "")
            sign_time = _get_value("sign_time", "")
            sign_string = _get_value("sign_string", "")
            error_raw = _get_value("error", 0)
            try:
                error = int(error_raw or 0)
            except (TypeError, ValueError):
                error = 0

            if action == "0":  # Prepare
                result = await payment_service.process_click_prepare(
                    click_trans_id=click_trans_id,
                    merchant_trans_id=merchant_trans_id,
                    amount=amount,
                    action=action,
                    sign_time=sign_time,
                    sign_string=sign_string,
                    service_id=service_id,
                )
            else:  # Complete
                result = await payment_service.process_click_complete(
                    click_trans_id=click_trans_id,
                    merchant_trans_id=merchant_trans_id,
                    merchant_prepare_id=_get_value("merchant_prepare_id", ""),
                    amount=amount,
                    action=action,
                    sign_time=sign_time,
                    sign_string=sign_string,
                    error=error,
                    service_id=service_id,
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
