"""
Fudly Telegram Bot - Main Module (Production Ready)

A professional Telegram bot for selling discounted food products.
Architecture: Clean modular design with aiogram 3.x routers.

Author: shaxa2505
Version: 2.0.0
"""
from __future__ import annotations

import asyncio
import os
import signal
import sys
from types import FrameType
from typing import Any

from aiogram import F, Router, types
from aiogram.fsm.context import FSMContext

# =============================================================================
# CONFIGURATION
# =============================================================================
from app.core.bootstrap import build_application
from app.core.config import load_settings
from app.core.security import (
    PRODUCTION_FEATURES,
    logger,
    start_background_tasks,
)

# Load typed settings
settings = load_settings()

ADMIN_ID: int = settings.admin_id
DATABASE_URL: str | None = settings.database_url
USE_WEBHOOK: bool = settings.webhook.enabled
WEBHOOK_URL: str = settings.webhook.url
WEBHOOK_PATH: str = settings.webhook.path
PORT: int = settings.webhook.port
SECRET_TOKEN: str = settings.webhook.secret_token

# Lock configuration (prevent multiple instances)
LOCK_PORT: int = int(os.getenv("LOCK_PORT", "8444"))
DISABLE_LOCK: bool = os.getenv("DISABLE_LOCK", "0").strip().lower() in {"1", "true", "yes"}
POLLING_HEALTH_PORT: int = int(os.getenv("POLLING_HEALTH_PORT", "0") or 0)

# =============================================================================
# APPLICATION BOOTSTRAP
# =============================================================================

bot, dp, db, cache = build_application(settings)

# =============================================================================
# SERVICES
# =============================================================================

from app.services.admin_service import AdminService
from app.services.offer_service import OfferService

offer_service = OfferService(db, cache)
admin_service = AdminService(db, bool(DATABASE_URL))

# =============================================================================
# METRICS
# =============================================================================

METRICS: dict[str, int] = {
    "updates_received": 0,
    "updates_errors": 0,
    "webhook_json_errors": 0,
    "webhook_validation_errors": 0,
    "webhook_unexpected_errors": 0,
    "bookings_created": 0,
    "bookings_cancelled": 0,
}

# =============================================================================
# IMPORTS FOR HANDLERS
# =============================================================================

from app.keyboards import (
    booking_filters_keyboard,
    main_menu_customer,
    main_menu_seller,
    moderation_keyboard,
    phone_request_keyboard,
    settings_keyboard,
)
from handlers import common as handlers_common
from localization import get_text

# Re-export utilities from handlers
user_view_mode = handlers_common.user_view_mode
get_uzb_time = handlers_common.get_uzb_time
RegistrationCheckMiddleware = handlers_common.RegistrationCheckMiddleware


def has_approved_store(user_id: int) -> bool:
    """Check if user has an approved store."""
    return handlers_common.has_approved_store(user_id, db)


def get_appropriate_menu(user_id: int, lang: str) -> Any:
    """Get appropriate menu keyboard for user."""
    return handlers_common.get_appropriate_menu(
        user_id, lang, db, main_menu_seller, main_menu_customer
    )


# =============================================================================
# ADMIN INITIALIZATION
# =============================================================================


def _setup_admin() -> None:
    """Initialize admin user on startup."""
    if ADMIN_ID > 0:
        try:
            user = db.get_user(ADMIN_ID)
            if not user:
                db.add_user(ADMIN_ID, "admin", "Admin")
            db.set_admin(ADMIN_ID)
            logger.info(f"✅ Admin configured: {ADMIN_ID}")
        except Exception as e:
            logger.warning(f"⚠️ Admin setup failed: {e}")


_setup_admin()

# =============================================================================
# SENTRY INITIALIZATION
# =============================================================================


def _init_sentry() -> bool:
    """Initialize Sentry for error tracking."""
    logger.info("🔧 Initializing Sentry error tracking...")
    try:
        from app.core.sentry_integration import init_sentry

        enabled = init_sentry(
            environment="production" if USE_WEBHOOK else "development",
            enable_logging=True,
            sample_rate=1.0,
            traces_sample_rate=0.1,
        )
        if enabled:
            logger.info("✅ Sentry initialized successfully")
        else:
            logger.info("⚠️ Sentry not enabled (SENTRY_DSN not set)")
        return enabled
    except Exception as e:
        logger.warning(f"⚠️ Sentry initialization failed: {e}")
        return False


sentry_enabled = _init_sentry()

# =============================================================================
# FALLBACK ROUTER (CATCH-ALL HANDLERS)
# =============================================================================

fallback_router = Router(name="fallback")


@fallback_router.message(F.photo)
async def fallback_photo_handler(message: types.Message, state: FSMContext) -> None:
    """Handle unexpected photo messages."""
    if not message.from_user:
        return

    user_id = message.from_user.id
    lang = db.get_user_language(user_id)
    current_state = await state.get_state()

    logger.warning(f"Unexpected photo from user {user_id} (state: {current_state})")

    error_text = (
        "⚠️ Произошла ошибка: данные заказа потеряны.\n\n"
        "Это может произойти если:\n"
        "• Прошло много времени между шагами\n"
        "• Сервер был перезапущен\n\n"
        "Пожалуйста, начните заново через 🔥 Горячее"
        if lang == "ru"
        else "⚠️ Xatolik: buyurtma ma'lumotlari yo'qoldi.\n\n"
        "Iltimos, 🔥 Issiq orqali qaytadan boshlang"
    )

    await message.answer(error_text, reply_markup=get_appropriate_menu(user_id, lang))


@fallback_router.message(F.text)
async def fallback_text_handler(message: types.Message, state: FSMContext) -> None:
    """Handle unknown text messages."""
    if not message.from_user or not message.text:
        return

    user_id = message.from_user.id
    text = message.text
    lang = db.get_user_language(user_id)
    current_state = await state.get_state()

    logger.debug(f"Unknown message from {user_id}: '{text[:50]}...' (state: {current_state})")

    # Help users who type numbers without context
    if text.isdigit():
        hint = (
            "Чтобы выбрать товар по номеру, сначала откройте 🔥 Горячее"
            if lang == "ru"
            else "Mahsulotni tanlash uchun avval 🔥 Issiq ni oching"
        )
        await message.answer(hint)


@fallback_router.callback_query()
async def fallback_callback_handler(callback: types.CallbackQuery) -> None:
    """Handle unhandled callback queries."""
    data = callback.data or ""
    user_id = callback.from_user.id if callback.from_user else 0

    logger.debug(f"Unhandled callback from {user_id}: {data}")

    try:
        await callback.answer()
    except Exception:
        pass


# =============================================================================
# HANDLER REGISTRATION
# =============================================================================


def _register_handlers() -> None:
    """Register all handlers in correct priority order."""

    # Import handler modules
    from handlers import bookings
    from handlers.admin import dashboard as admin_dashboard
    from handlers.admin import legacy as admin_legacy
    from handlers.admin import panel as admin_panel
    from handlers.admin import stats as admin_stats
    from handlers.common.router import router as common_router
    from handlers.customer import (
        favorites,
        profile,
    )
    from handlers.customer import (
        features as user_features,
    )
    from handlers.customer import (
        menu as customer_menu,
    )
    from handlers.customer.offers import browse as offers_browse
    from handlers.customer.offers import search as offers_search
    from handlers.customer.orders import delivery as orders
    from handlers.seller import (
        analytics,
        bulk_import,
        create_offer,
        management,
        order_management,
    )
    from handlers.seller import (
        registration as partner,
    )

    # Setup dependencies for handler modules
    bookings.setup_dependencies(db, bot, cache, METRICS)
    orders.setup_dependencies(db, bot, user_view_mode)
    partner.setup_dependencies(db, bot, user_view_mode)
    create_offer.setup_dependencies(db, bot)
    management.setup_dependencies(db, bot)
    analytics.setup_dependencies(db, bot)
    bulk_import.setup_dependencies(db, bot)
    profile.setup_dependencies(db, bot, user_view_mode)
    favorites.setup_dependencies(db, bot, user_view_mode)
    order_management.setup(bot, db)
    customer_menu.setup(
        bot,
        db,
        user_view_mode,
        get_text,
        main_menu_customer,
        booking_filters_keyboard,
        main_menu_seller,
    )
    user_features.setup(dp, db, get_text, booking_filters_keyboard, settings_keyboard)
    admin_dashboard.setup(bot, db, get_text, moderation_keyboard, get_uzb_time)
    admin_legacy.setup(bot, db, get_text, moderation_keyboard, get_uzb_time, ADMIN_ID, DATABASE_URL)
    admin_stats.setup(admin_service, logger)

    # Setup search handler
    offers_search.setup(dp, db, offer_service)

    # Register routers in PRIORITY order (most specific first)
    # 1. Seller-specific routers
    dp.include_router(bulk_import.router)
    dp.include_router(create_offer.router)
    dp.include_router(management.router)
    dp.include_router(analytics.router)
    dp.include_router(order_management.router)

    # 2. Customer routers
    dp.include_router(profile.router)
    dp.include_router(favorites.router)
    dp.include_router(customer_menu.router)
    dp.include_router(orders.router)
    dp.include_router(bookings.router)
    dp.include_router(partner.router)

    # 3. Admin routers
    dp.include_router(admin_dashboard.router)
    dp.include_router(admin_legacy.router)
    dp.include_router(admin_panel.router)
    dp.include_router(admin_stats.router)

    # 4. Common handlers (registration, commands, help)
    dp.include_router(common_router)

    # 5. Offer browsing (generic patterns, lower priority)
    offers_browse.setup(dp, db, offer_service, logger)

    # 6. Fallback handlers (LOWEST priority - catch-all)
    dp.include_router(fallback_router)


def _register_middlewares() -> None:
    """Register middlewares in correct order."""
    from app.middlewares.db_middleware import DbSessionMiddleware
    from app.middlewares.rate_limit import RateLimitMiddleware

    # 1. Database session middleware
    dp.update.middleware(DbSessionMiddleware(db))

    # 2. Rate limiting (prevent abuse)
    dp.update.middleware(RateLimitMiddleware(rate_limit=30, burst_limit=20))

    # 3. Registration check (ensure users are registered)
    dp.update.middleware(RegistrationCheckMiddleware(db, get_text, phone_request_keyboard))


# =============================================================================
# BACKGROUND TASKS
# =============================================================================


async def cleanup_expired_offers() -> None:
    """Background task to cleanup expired offers."""
    while True:
        try:
            await asyncio.sleep(300)  # Every 5 minutes
            deleted_count = db.delete_expired_offers()
            if deleted_count > 0:
                logger.info(f"🗑 Cleaned up {deleted_count} expired offers")
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Error cleaning expired offers: {e}")


async def cleanup_expired_fsm_states() -> None:
    """Background task to cleanup expired FSM states."""
    while True:
        try:
            await asyncio.sleep(3600)  # Every hour
            # Check if storage supports cleanup
            storage = dp.storage
            if hasattr(storage, "cleanup_expired"):
                deleted = await storage.cleanup_expired()
                if deleted > 0:
                    logger.info(f"🧹 Cleaned up {deleted} expired FSM states")
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Error cleaning expired FSM states: {e}")


async def start_booking_worker() -> asyncio.Task | None:
    """Start the booking expiry worker if available."""
    try:
        from tasks.booking_expiry_worker import start_booking_expiry_worker

        task = asyncio.create_task(start_booking_expiry_worker(db, bot))
        logger.info("✅ Booking expiry worker started")
        return task
    except Exception as e:
        logger.warning(f"Could not start booking expiry worker: {e}")
        return None


# =============================================================================
# LIFECYCLE HOOKS
# =============================================================================


async def on_startup() -> None:
    """Actions on bot startup."""
    if USE_WEBHOOK:
        webhook_url = f"{WEBHOOK_URL}{WEBHOOK_PATH}"
        try:
            await bot.set_webhook(
                url=webhook_url,
                drop_pending_updates=True,
                secret_token=SECRET_TOKEN or None,
            )
            logger.info(f"✅ Webhook set: {webhook_url}")
        except Exception as e:
            logger.error(f"Failed to set webhook: {e}")
    else:
        await bot.delete_webhook(drop_pending_updates=True)
        logger.info("✅ Polling mode activated")


async def on_shutdown() -> None:
    """Actions on bot shutdown."""
    await bot.session.close()

    try:
        if db and hasattr(db, "close"):
            db.close()
            logger.info("Database pool closed")
    except Exception as e:
        logger.warning(f"Failed to close database: {e}")

    logger.info("👋 Bot stopped")


# =============================================================================
# INSTANCE LOCK
# =============================================================================


def is_bot_already_running() -> bool:
    """Check if another bot instance is running using TCP port binding."""
    if DISABLE_LOCK:
        return False

    import socket

    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.bind(("127.0.0.1", LOCK_PORT))
        sock.close()
        return False
    except OSError:
        logger.error(f"🛑 Bot already running on port {LOCK_PORT}!")
        return True


# =============================================================================
# SIGNAL HANDLING
# =============================================================================

shutdown_event = asyncio.Event()


def signal_handler(sig: int, frame: FrameType | None) -> None:
    """Handle termination signals."""
    logger.info(f"Received signal {sig}, initiating shutdown...")
    shutdown_event.set()


# =============================================================================
# MAIN ENTRY POINT
# =============================================================================


async def main() -> None:
    """Main bot entry point."""
    logger.info("=" * 50)
    logger.info("🚀 Starting Fudly Bot (Production)")
    logger.info("=" * 50)
    logger.info("📊 Database: PostgreSQL" if DATABASE_URL else "📊 Database: Not configured")
    logger.info(f"🔄 Mode: {'Webhook' if USE_WEBHOOK else 'Polling'}")
    logger.info(f"👑 Admin ID: {ADMIN_ID}")
    logger.info("=" * 50)

    # Start background tasks
    cleanup_task = asyncio.create_task(cleanup_expired_offers())
    fsm_cleanup_task = asyncio.create_task(cleanup_expired_fsm_states())
    booking_task = await start_booking_worker()

    if PRODUCTION_FEATURES:
        start_background_tasks(db)
        logger.info("✅ Production features enabled")

    if USE_WEBHOOK:
        # Webhook mode (Railway, Heroku, etc.)
        from app.core.webhook_server import create_webhook_app, run_webhook_server

        await on_startup()

        app = await create_webhook_app(
            bot=bot,
            dp=dp,
            webhook_path=WEBHOOK_PATH,
            secret_token=SECRET_TOKEN,
            metrics=METRICS,
            db=db,
        )

        runner = await run_webhook_server(app, PORT)
        logger.info(f"🌐 Webhook server running on port {PORT}")

        try:
            await shutdown_event.wait()
        finally:
            cleanup_task.cancel()
            fsm_cleanup_task.cancel()
            if booking_task:
                booking_task.cancel()
            await runner.cleanup()
            await on_shutdown()
    else:
        # Polling mode (local development)
        await on_startup()

        polling_task = asyncio.create_task(
            dp.start_polling(
                bot,
                allowed_updates=dp.resolve_used_update_types(),
                drop_pending_updates=True,
            )
        )

        # Optional health server for polling mode
        health_runner = None
        if POLLING_HEALTH_PORT > 0:
            health_runner = await _start_health_server()

        try:
            await shutdown_event.wait()
            logger.info("Shutting down...")
            polling_task.cancel()
            try:
                await polling_task
            except asyncio.CancelledError:
                pass
        finally:
            cleanup_task.cancel()
            if booking_task:
                booking_task.cancel()
            try:
                await cleanup_task
            except asyncio.CancelledError:
                pass
            if health_runner:
                await health_runner.cleanup()
            await on_shutdown()


async def _start_health_server():
    """Start health check server for polling mode."""
    from aiohttp import web

    async def health_check(_: web.Request) -> web.Response:
        return web.json_response({"status": "ok", "mode": "polling"})

    async def metrics_endpoint(_: web.Request) -> web.Response:
        lines = []
        for key, val in METRICS.items():
            metric = f"fudly_{key}"
            lines.append(f"# TYPE {metric} counter")
            lines.append(f"{metric} {val}")
        return web.Response(
            text="\n".join(lines) + "\n",
            content_type="text/plain",
        )

    app = web.Application()
    app.router.add_get("/health", health_check)
    app.router.add_get("/metrics", metrics_endpoint)
    app.router.add_get("/", health_check)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", POLLING_HEALTH_PORT)
    await site.start()
    logger.info(f"🩺 Health server running on port {POLLING_HEALTH_PORT}")

    return runner


# =============================================================================
# STARTUP
# =============================================================================

if __name__ == "__main__":
    # Check for duplicate instances
    if is_bot_already_running():
        logger.error("❌ Exiting: Another instance is running")
        sys.exit(1)

    # Register handlers and middlewares
    _register_middlewares()
    _register_handlers()

    # Setup signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Run the bot
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Bot crashed: {e}")
        sys.exit(1)
