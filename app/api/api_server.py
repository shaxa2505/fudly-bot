"""
FastAPI server for Mini App API.

Runs alongside the Telegram bot to provide REST API for the web app.
"""
from __future__ import annotations

import asyncio
import logging
import os
import time
import urllib.parse
from collections import deque
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import uvicorn
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from app.api.auth import router as auth_router
from app.api.auth import set_auth_db
from app.api.orders import router as orders_router
from app.api.orders import set_orders_db
from app.api.partner_panel_simple import router as partner_panel_router
from app.api.partner_panel_simple import set_partner_db
from app.api.webapp_api import router as webapp_router
from app.api.webapp_api import set_db_instance
from app.api.merchant_webhooks import router as merchant_webhooks_router, set_merchant_db

logger = logging.getLogger(__name__)


def _is_truthy(value: str | None) -> bool:
    if value is None:
        return False
    return value.strip().lower() in {"1", "true", "yes"}


class _PerfTracker:
    """Lightweight in-process latency tracker for API endpoints."""

    def __init__(self, window: int, log_every: int, top_n: int) -> None:
        self._window = max(10, window)
        self._log_every = max(5, log_every)
        self._top_n = max(1, top_n)
        self._buckets: dict[str, dict[str, object]] = {}
        self._last_log = time.time()
        self._logger = logging.getLogger("fudly")

    def record(self, key: str, latency_s: float, status_code: int) -> None:
        bucket = self._buckets.get(key)
        if bucket is None:
            bucket = {
                "lat": deque(maxlen=self._window),
                "count": 0,
                "errors": 0,
            }
            self._buckets[key] = bucket
        lat: deque[float] = bucket["lat"]  # type: ignore[assignment]
        lat.append(latency_s)
        bucket["count"] = int(bucket["count"]) + 1  # type: ignore[assignment]
        if status_code >= 400:
            bucket["errors"] = int(bucket["errors"]) + 1  # type: ignore[assignment]
        self._maybe_log()

    def _maybe_log(self) -> None:
        now = time.time()
        if (now - self._last_log) < self._log_every:
            return
        self._last_log = now

        summaries: list[tuple[str, float, float, int, int]] = []
        for key, bucket in self._buckets.items():
            values = list(bucket["lat"])  # type: ignore[arg-type]
            if not values:
                continue
            values.sort()
            p50 = values[int((len(values) - 1) * 0.50)]
            p95 = values[int((len(values) - 1) * 0.95)]
            count = int(bucket["count"])  # type: ignore[arg-type]
            errors = int(bucket["errors"])  # type: ignore[arg-type]
            summaries.append((key, p50, p95, count, errors))

        if not summaries:
            return

        summaries.sort(key=lambda item: item[2], reverse=True)
        top = summaries[: self._top_n]
        lines = [
            "API perf (window=%s, log_every=%ss):" % (self._window, self._log_every)
        ]
        for key, p50, p95, count, errors in top:
            err_pct = (errors / count * 100) if count else 0.0
            lines.append(
                f"{key} count={count} err%={err_pct:.1f} "
                f"p50={p50*1000:.1f}ms p95={p95*1000:.1f}ms"
            )
        self._logger.info(" | ".join(lines))

# Global reference to the bot's database
_app_db = None
_app_offer_service = None

# Rate limiter configuration
limiter = Limiter(key_func=get_remote_address, default_limits=["100/minute"])


def create_api_app(db: Any = None, offer_service: Any = None, bot_token: str = None) -> FastAPI:
    """
    Create FastAPI application for Mini App.

    Args:
        db: Database instance from the bot
        offer_service: OfferService instance
        bot_token: Telegram bot token for photo uploads
    """
    global _app_db, _app_offer_service
    _app_db = db
    _app_offer_service = offer_service

    # Initialize database connections immediately (for ASGI adapter usage)
    # This ensures db is available even when lifespan events are not triggered
    if _app_db:
        from app.core.async_db import AsyncDBProxy

        async_db = AsyncDBProxy(_app_db)
        set_db_instance(async_db, _app_offer_service)
        set_auth_db(_app_db)
        set_orders_db(_app_db, bot_token)
        # Partner panel + merchant webhooks can remain sync for now
        set_partner_db(_app_db, bot_token)
        set_merchant_db(_app_db)
        logger.info("✅ Database connected to API (immediate init)")

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # Startup - also set here for standalone FastAPI usage
        logger.info("🚀 Mini App API starting...")
        if _app_db:
            from app.core.async_db import AsyncDBProxy

            async_db = AsyncDBProxy(_app_db)
            set_db_instance(async_db, _app_offer_service)
            set_auth_db(_app_db)
            set_orders_db(_app_db, bot_token)
            set_partner_db(_app_db, bot_token)
            set_merchant_db(_app_db)
            logger.info("✅ Database connected to API (lifespan)")
        yield
        # Shutdown
        logger.info("👋 Mini App API shutting down...")

    app = FastAPI(
        title="Fudly Mini App API",
        description="REST API for Fudly Telegram Mini App",
        version="1.0.0",
        lifespan=lifespan,
        docs_url="/api/docs",
        redoc_url="/api/redoc",
        openapi_url="/api/openapi.json",
    )

    # Lightweight profiling middleware (disabled by default)
    if _is_truthy(os.getenv("API_PROFILE", "0")):
        window = int(os.getenv("API_PROFILE_WINDOW", "200"))
        log_every = int(os.getenv("API_PROFILE_LOG_EVERY", "60"))
        top_n = int(os.getenv("API_PROFILE_TOP_N", "6"))
        tracker = _PerfTracker(window=window, log_every=log_every, top_n=top_n)

        @app.middleware("http")
        async def perf_middleware(request: Request, call_next):  # type: ignore[override]
            start = time.perf_counter()
            status_code = 500
            try:
                response = await call_next(request)
                status_code = response.status_code
                return response
            finally:
                route = request.scope.get("route")
                route_path = getattr(route, "path", None)
                path = route_path or request.url.path
                key = f"{request.method} {path}"
                tracker.record(key, time.perf_counter() - start, status_code)

    # Add rate limiter
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

    # ✅ SECURITY: Strict CORS - only allow specific origins
    # In production, restrict to actual domains only
    environment = os.getenv("ENVIRONMENT", "production").lower()
    is_dev = environment in ("development", "dev", "local", "test")

    def _origin_from_url(value: str | None) -> str | None:
        if not value:
            return None
        try:
            parsed = urllib.parse.urlsplit(value.strip())
        except Exception:
            return None
        if not parsed.scheme or not parsed.netloc:
            return None
        return f"{parsed.scheme}://{parsed.netloc}"

    allowed_origins = [
        # Telegram WebApp
        "https://web.telegram.org",
        "https://telegram.org",
        "https://fudly-webapp.vercel.app",
    ]

    # Allow explicitly configured origins (webapp + partner panel)
    for env_name in ("WEBAPP_URL", "PARTNER_PANEL_URL", "WEBAPP_ORIGIN", "PARTNER_PANEL_ORIGIN"):
        origin = _origin_from_url(os.getenv(env_name))
        if origin and origin not in allowed_origins:
            allowed_origins.append(origin)

    extra_origins = os.getenv("CORS_ALLOWED_ORIGINS", "")
    if extra_origins:
        for raw in extra_origins.split(","):
            origin = _origin_from_url(raw)
            if origin and origin not in allowed_origins:
                allowed_origins.append(origin)

    # Only allow localhost in development
    if is_dev:
        allowed_origins.extend(
            [
                "http://localhost:8080",
                "http://localhost:5173",
                "http://localhost:3000",
                "http://localhost:3001",
                "http://localhost:3002",
                "http://127.0.0.1:5500",
                "http://127.0.0.1:8080",
            ]
        )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        # Allow all Vercel preview/production URLs (only for webapp)
        allow_origin_regex=r"https://fudly-webapp.*\.vercel\.app",
        allow_credentials=True,
        # ✅ SECURITY: Restrict methods to only what's needed
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        # ✅ SECURITY: Restrict headers
        allow_headers=[
            "Content-Type",
            "Authorization",
            "X-Requested-With",
            "X-Telegram-Init-Data",
            "Idempotency-Key",
            "X-Idempotency-Key",
            "Sentry-Trace",
            "Baggage",
        ],
        expose_headers=["Content-Length", "Content-Type"],
    )

    # ✅ SECURITY: Add security headers middleware
    @app.middleware("http")
    async def add_security_headers(request: Request, call_next):
        response = await call_next(request)
        # Content Security Policy
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' https://telegram.org https://web.telegram.org https://cdn.jsdelivr.net https://unpkg.com; "
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com https://unpkg.com; "
            "img-src 'self' data: https:; "
            "font-src 'self' data: https://fonts.gstatic.com; "
            "connect-src 'self' https://api.telegram.org; "
            "frame-ancestors 'self' https://web.telegram.org"
        )
        if request.url.path.startswith("/partner-panel"):
            response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"
        # Prevent clickjacking
        response.headers["X-Frame-Options"] = "SAMEORIGIN"
        # Prevent MIME sniffing
        response.headers["X-Content-Type-Options"] = "nosniff"
        # XSS Protection (legacy but still useful)
        response.headers["X-XSS-Protection"] = "1; mode=block"
        # Referrer Policy
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        return response

    # Define static file paths (needed for debug endpoint)
    webapp_dist_path = Path(__file__).parent.parent.parent / "webapp" / "dist"
    partner_panel_path = Path(__file__).parent.parent.parent / "webapp" / "partner-panel"

    # Include routers (API routes must be registered BEFORE static files)
    app.include_router(auth_router)
    app.include_router(webapp_router)
    app.include_router(orders_router)
    app.include_router(partner_panel_router, prefix="/api/partner")
    app.include_router(merchant_webhooks_router)

    @app.get("/")
    async def root():
        return {"service": "Fudly Mini App API", "version": "1.0.0", "docs": "/api/docs"}

    # Serve partner panel static files if directory exists
    # MUST be mounted AFTER API routes to avoid conflicts
    if partner_panel_path.exists():
        logger.info(f"✅ Mounting partner panel static files from {partner_panel_path}")
        try:
            # Mount static files with html=True to serve index.html for directory requests
            app.mount(
                "/partner-panel",
                StaticFiles(directory=str(partner_panel_path), html=True),
                name="partner-panel",
            )
        except Exception as e:
            logger.error(f"❌ Failed to mount partner panel: {e}")
    else:
        logger.warning(f"⚠️ Partner panel directory not found: {partner_panel_path}")

    # Debug endpoint - DEV ONLY (leaks filesystem layout)
    if is_dev:

        @app.get("/api/debug/paths")
        async def debug_paths():
            """Debug endpoint to check file paths (development only)."""
            return {
                "partner_panel": {
                    "path": str(partner_panel_path.absolute()),
                    "exists": partner_panel_path.exists(),
                    "index_exists": (partner_panel_path / "index.html").exists()
                    if partner_panel_path.exists()
                    else False,
                    "files": [f.name for f in partner_panel_path.iterdir()][:10]
                    if partner_panel_path.exists()
                    else [],
                },
                "webapp": {
                    "path": str(webapp_dist_path.absolute()),
                    "exists": webapp_dist_path.exists(),
                    "index_exists": (webapp_dist_path / "index.html").exists()
                    if webapp_dist_path.exists()
                    else False,
                    "files": [f.name for f in webapp_dist_path.iterdir()][:10]
                    if webapp_dist_path.exists()
                    else [],
                },
                "cwd": os.getcwd(),
                "file_location": str(Path(__file__).absolute()),
            }

    return app


async def run_api_server(
    db: Any = None,
    offer_service: Any = None,
    bot_token: str = None,
    host: str = "0.0.0.0",
    port: int = 8000,
):
    """
    Run FastAPI server as async task.

    Can be started alongside the bot.
    """
    app = create_api_app(db, offer_service, bot_token)

    config = uvicorn.Config(app, host=host, port=port, log_level="info", access_log=True)
    server = uvicorn.Server(config)

    logger.info(f"🌐 Starting Mini App API on http://{host}:{port}")
    await server.serve()


def start_api_in_thread(
    db: Any = None, offer_service: Any = None, host: str = "0.0.0.0", port: int = 8000
):
    """
    Start API server in a separate thread.

    Useful when running alongside polling bot.
    """
    import threading

    def run():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(run_api_server(db, offer_service, host, port))

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    logger.info(f"🌐 API server started in background thread on port {port}")
    return thread


if __name__ == "__main__":
    # For testing without bot
    import sys

    sys.path.insert(
        0,
        str(__file__)
        .replace("\\app\\api\\api_server.py", "")
        .replace("/app/api/api_server.py", ""),
    )

    db = None
    offer_service = None
    bot_token = None
    try:
        from app.core.cache import CacheManager
        from app.core.config import load_settings
        from app.core.database import create_database
        from app.services.offer_service import OfferService

        settings = load_settings()
        bot_token = settings.bot_token
        db = create_database(settings.database_url)
        cache = CacheManager(db, redis_url=settings.redis_url)
        offer_service = OfferService(db, cache)
        logger.info("✅ API server initialized with DB bindings")
    except Exception as exc:
        logger.warning("⚠️ API running without DB bindings: %s", exc)

    app = create_api_app(db, offer_service, bot_token)
    port = int(os.getenv("API_PORT", "8000"))
    uvicorn.run(app, host="0.0.0.0", port=port)
