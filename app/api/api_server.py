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
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api.auth import router as auth_router
from app.api.auth import set_auth_db
from app.api.orders import router as orders_router
from app.api.orders import set_orders_db
from app.api.partner_panel_simple import router as partner_panel_router
from app.api.partner_panel_simple import set_partner_db
from app.api.webapp_api import router as webapp_router
from app.api.webapp_api import set_db_instance

logger = logging.getLogger(__name__)

# Global reference to the bot's database
_app_db = None
_app_offer_service = None


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

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # Startup
        logger.info("🚀 Mini App API starting...")
        if _app_db:
            set_db_instance(_app_db, _app_offer_service)
            set_auth_db(_app_db)
            set_orders_db(_app_db)
            set_partner_db(_app_db, bot_token)
            logger.info("✅ Database connected to API")
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

    # CORS for Mini App
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            # Production domains (постоянные URL)
            "https://partner-panel-shaxbozs-projects-d385e345.vercel.app",  # Partner Panel постоянный URL
            "https://fudly-partner-panel.vercel.app",
            "https://fudly-webapp.vercel.app",
            # Telegram
            "https://web.telegram.org",
            "https://telegram.org",
            # Dev tools
            "https://*.ngrok-free.dev",
            "https://*.ngrok-free.app",
            "https://*.ngrok.io",
            "https://*.loca.lt",
            # Local dev
            "http://localhost:8080",
            "http://localhost:5173",
            "http://localhost:3000",
            "http://localhost:3001",
            "http://localhost:3002",
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["*"],
    )

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

    @app.get("/api/debug/paths")
    async def debug_paths():
        """Debug endpoint to check file paths."""
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
        app.mount(
            "/partner-panel",
            StaticFiles(directory=str(partner_panel_path), html=True),
            name="partner-panel",
        )
        logger.info(f"✅ Partner Panel mounted at /partner-panel from {partner_panel_path}")
        logger.info("   Access at: http://localhost:8000/partner-panel/")
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
