"""
FastAPI server for Mini App API.

Runs alongside the Telegram bot to provide REST API for the web app.
"""
from __future__ import annotations

import asyncio
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import uvicorn
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from starlette.datastructures import Headers

from app.api.auth import router as auth_router
from app.api.auth import set_auth_db
from app.api.orders import router as orders_router
from app.api.orders import set_orders_db
from app.api.partner_panel_simple import router as partner_panel_router
from app.api.partner_panel_simple import set_partner_db
from app.api.webapp_api import router as webapp_router
from app.api.webapp_api import set_db_instance

logger = logging.getLogger(__name__)


# 🔥 Custom StaticFiles that always returns 200, never 304
class NoCacheStaticFiles(StaticFiles):
    """StaticFiles that disables caching by overriding is_not_modified check"""

    def is_not_modified(self, response_headers, request_headers):
        """Always return False to prevent 304 responses"""
        return False


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
        set_db_instance(_app_db, _app_offer_service)
        set_auth_db(_app_db)
        set_orders_db(_app_db, bot_token)
        set_partner_db(_app_db, bot_token)
        logger.info("✅ Database connected to API (immediate init)")

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # Startup - also set here for standalone FastAPI usage
        logger.info("🚀 Mini App API starting...")
        if _app_db:
            set_db_instance(_app_db, _app_offer_service)
            set_auth_db(_app_db)
            set_orders_db(_app_db, bot_token)
            set_partner_db(_app_db, bot_token)
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

    # Add rate limiter
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

    # ✅ SECURITY: Strict CORS - only allow specific origins
    # In production, restrict to actual domains only
    environment = os.getenv("ENVIRONMENT", "production").lower()
    is_dev = environment in ("development", "dev", "local", "test")

    allowed_origins = [
        # Telegram WebApp
        "https://web.telegram.org",
        "https://telegram.org",
    ]

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
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        # ✅ SECURITY: Restrict headers
        allow_headers=[
            "Content-Type",
            "Authorization",
            "X-Requested-With",
            "X-Telegram-Init-Data",
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
            "script-src 'self' 'unsafe-inline' https://telegram.org https://web.telegram.org; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data: https:; "
            "font-src 'self' data:; "
            "connect-src 'self' https://api.telegram.org; "
            "frame-ancestors 'self' https://web.telegram.org"
        )
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

    # Include routers
    app.include_router(auth_router)
    app.include_router(orders_router)
    app.include_router(webapp_router)
    app.include_router(partner_panel_router, prefix="/api/partner")

    @app.get("/")
    async def root():
        return {"service": "Fudly Mini App API", "version": "1.0.0", "docs": "/api/docs"}

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

    # Serve static files (MUST be after all API routes)
    logger.info(f"📁 Looking for Partner Panel at: {partner_panel_path.absolute()}")
    logger.info(f"📁 Partner Panel exists: {partner_panel_path.exists()}")
    if partner_panel_path.exists():
        logger.info(f"📁 Partner Panel contents: {list(partner_panel_path.iterdir())[:5]}")

    logger.info(f"📁 Looking for Mini App at: {webapp_dist_path.absolute()}")
    logger.info(f"📁 Mini App exists: {webapp_dist_path.exists()}")

    # Mount Partner Panel FIRST (more specific path)
    if partner_panel_path.exists() and (partner_panel_path / "index.html").exists():
        # Mount static assets with NoCacheStaticFiles to prevent 304 responses
        app.mount(
            "/partner-panel/styles",
            NoCacheStaticFiles(directory=str(partner_panel_path / "styles")),
            name="partner-panel-styles",
        )
        app.mount(
            "/partner-panel/js",
            NoCacheStaticFiles(directory=str(partner_panel_path / "js")),
            name="partner-panel-js",
        )

        # Mount main app with HTML fallback
        app.mount(
            "/partner-panel",
            NoCacheStaticFiles(directory=str(partner_panel_path), html=True),
            name="partner-panel",
        )
        logger.info(f"✅ Partner Panel mounted at /partner-panel from {partner_panel_path}")
        logger.info("   Access at: http://localhost:8000/partner-panel/")
        logger.info("   Static files: /partner-panel/styles/, /partner-panel/js/")
    else:
        logger.error(f"❌ Partner Panel not found or missing index.html at {partner_panel_path}")
        logger.error(f"   Expected file: {partner_panel_path / 'index.html'}")

    # Mount Mini App (main webapp) - must be last to avoid conflicts
    if webapp_dist_path.exists() and (webapp_dist_path / "index.html").exists():
        app.mount("/", StaticFiles(directory=str(webapp_dist_path), html=True), name="webapp")
        logger.info(f"✅ Mini App mounted at / from {webapp_dist_path}")
    else:
        logger.error(f"❌ Mini App dist not found or missing index.html at {webapp_dist_path}")

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

    app = create_api_app()
    uvicorn.run(app, host="0.0.0.0", port=8000)
