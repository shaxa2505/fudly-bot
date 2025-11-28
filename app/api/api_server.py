"""
FastAPI server for Mini App API.

Runs alongside the Telegram bot to provide REST API for the web app.
"""
from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Any

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.webapp_api import router as webapp_router
from app.api.webapp_api import set_db_instance
from app.api.auth import router as auth_router, set_auth_db
from app.api.orders import router as orders_router, set_orders_db

logger = logging.getLogger(__name__)

# Global reference to the bot's database
_app_db = None
_app_offer_service = None


def create_api_app(db: Any = None, offer_service: Any = None) -> FastAPI:
    """
    Create FastAPI application for Mini App.

    Args:
        db: Database instance from the bot
        offer_service: OfferService instance
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
            "https://fudly-webapp.vercel.app",
            "https://web.telegram.org",
            "https://telegram.org",
            "http://localhost:5173",  # Vite dev server
            "http://localhost:3000",
            "*",  # Allow all for development
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Include routers
    app.include_router(auth_router)
    app.include_router(orders_router)
    app.include_router(webapp_router)

    @app.get("/")
    async def root():
        return {"service": "Fudly Mini App API", "version": "1.0.0", "docs": "/api/docs"}

    return app


async def run_api_server(
    db: Any = None, offer_service: Any = None, host: str = "0.0.0.0", port: int = 8000
):
    """
    Run FastAPI server as async task.

    Can be started alongside the bot.
    """
    app = create_api_app(db, offer_service)

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
