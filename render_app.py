#!/usr/bin/env python3
"""
Render.com deployment application
Combines Flask webhook server with Telegram bot
"""

import os
import asyncio
import logging
from flask import Flask, request, jsonify
from aiogram import Bot, Dispatcher
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiohttp import web
from aiohttp.web import Application
import threading
import signal
import sys

# Import bot components
from bot import dp, bot, db, logger, start_background_tasks, PRODUCTION_FEATURES

# Environment variables for Render
PORT = int(os.environ.get("PORT", 8000))  # Render sets PORT env var
WEBHOOK_HOST = os.environ.get("RENDER_EXTERNAL_URL", "")  # Render sets this
WEBHOOK_PATH = "/webhook"
WEBHOOK_URL = f"{WEBHOOK_HOST}{WEBHOOK_PATH}"

# Configure logging for Render
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)

async def setup_webhook():
    """Setup webhook for Telegram bot"""
    try:
        # Delete existing webhook
        await bot.delete_webhook(drop_pending_updates=True)
        logger.info("Deleted existing webhook")
        
        # Set new webhook
        webhook_info = await bot.get_webhook_info()
        if webhook_info.url != WEBHOOK_URL:
            await bot.set_webhook(
                url=WEBHOOK_URL,
                allowed_updates=dp.resolve_used_update_types()
            )
            logger.info(f"Webhook set to: {WEBHOOK_URL}")
        else:
            logger.info("Webhook already configured")
            
    except Exception as e:
        logger.error(f"Failed to setup webhook: {e}")

async def on_startup():
    """Application startup handler"""
    logger.info("Starting Fudly Bot on Render...")
    
    # Initialize database
    logger.info("Initializing database...")
    
    # Start background tasks
    if PRODUCTION_FEATURES:
        logger.info("Starting background tasks...")
        from background import start_background_tasks
        start_background_tasks(db)
    
    # Setup webhook
    await setup_webhook()
    
    logger.info("Bot started successfully!")

async def on_shutdown():
    """Application shutdown handler"""
    logger.info("Shutting down bot...")
    await bot.delete_webhook()
    await bot.session.close()

def create_app():
    """Create aiohttp application"""
    app = Application()
    
    # Setup webhook handler
    SimpleRequestHandler(
        dispatcher=dp,
        bot=bot
    ).register(app, path=WEBHOOK_PATH)
    
    # Health check endpoint
    async def health_check(request):
        return web.json_response({
            "status": "ok",
            "service": "fudly-bot",
            "webhook_url": WEBHOOK_URL
        })
    
    app.router.add_get("/health", health_check)
    app.router.add_get("/", health_check)  # Root endpoint
    
    # Setup startup/shutdown handlers
    app.on_startup.append(lambda app: asyncio.create_task(on_startup()))
    app.on_cleanup.append(lambda app: asyncio.create_task(on_shutdown()))
    
    return app

def signal_handler(sig, frame):
    """Handle shutdown signals"""
    logger.info("Received shutdown signal")
    sys.exit(0)

if __name__ == "__main__":
    # Register signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    logger.info(f"Starting Fudly Bot on port {PORT}")
    logger.info(f"Webhook URL: {WEBHOOK_URL}")
    
    # Create and run app
    app = create_app()
    
    try:
        web.run_app(
            app,
            host="0.0.0.0",
            port=PORT,
            access_log=logger
        )
    except Exception as e:
        logger.error(f"Failed to start application: {e}")
        sys.exit(1)