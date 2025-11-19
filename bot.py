"""
Fudly Telegram Bot - Main Module

This file is being refactored to use modular handlers from the handlers/ package.
See handlers/README.md for details on the refactoring structure.

Current status: Foundation laid with handlers/common.py, handlers/registration.py,
handlers/user_commands.py, and handlers/admin.py created. Full integration pending.
"""
from __future__ import annotations

import asyncio
import os
import random
import signal
import socket
import sqlite3
import string
import sys
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from aiogram import F, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import FSInputFile
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.core.bootstrap import build_application
from app.core.config import load_settings
from app.core.security import (
    PRODUCTION_FEATURES,
    logger,
    rate_limiter,
    secure_user_input,
    start_background_tasks,
    validate_admin_action,
    validator,
)
from app.core.utils import get_store_field, get_user_field
from app.services.admin_service import AdminService
from app.services.offer_service import OfferService

# Import states from handlers.common_states package
from handlers.common_states import (
    BookOffer,
    BrowseOffers,
    BulkCreate,
    ChangeCity,
    ConfirmOrder,
    CreateOffer,
    EditOffer,
    OrderDelivery,
    Registration,
    RegisterStore,
)
# Import utilities from handlers/common.py module
from handlers import common as handlers_common_module
RegistrationCheckMiddleware = handlers_common_module.RegistrationCheckMiddleware
common_get_appropriate_menu = handlers_common_module.get_appropriate_menu
common_has_approved_store = handlers_common_module.has_approved_store
handler_user_view_mode = handlers_common_module.user_view_mode
get_uzb_time = handlers_common_module.get_uzb_time

from app.keyboards import (
    admin_menu,
    booking_filters_keyboard,
    cancel_keyboard,
    city_keyboard,
    language_keyboard,
    main_menu_customer,
    main_menu_seller,
    moderation_keyboard,
    offers_category_filter,
    phone_request_keyboard,
    product_categories_keyboard,
    units_keyboard,
)
from localization import get_categories, get_cities, get_text, normalize_category

# Load typed settings and bootstrap application components
settings = load_settings()

ADMIN_ID = settings.admin_id
DATABASE_URL = settings.database_url
USE_WEBHOOK = settings.webhook.enabled
WEBHOOK_URL = settings.webhook.url
WEBHOOK_PATH = settings.webhook.path
PORT = settings.webhook.port
SECRET_TOKEN = settings.webhook.secret_token

# Optional: allow overriding lock port or disabling duplicate-run check via env
LOCK_PORT = int(os.getenv("LOCK_PORT", "8444"))
DISABLE_LOCK = os.getenv("DISABLE_LOCK", "0").strip().lower() in {"1", "true", "yes"}
POLLING_HEALTH_PORT = int(os.getenv("POLLING_HEALTH_PORT", "0") or 0)

bot, dp, db, cache = build_application(settings)
offer_service = OfferService(db, cache)
admin_service = AdminService(db, bool(DATABASE_URL))

# Initialize metrics dictionary
METRICS: Dict[str, int] = {
    "updates_received": 0,
    "updates_errors": 0,
    "webhook_json_errors": 0,
    "webhook_validation_errors": 0,
    "webhook_unexpected_errors": 0,
    "bookings_created": 0,
    "bookings_cancelled": 0
}

# Use imported utilities (override local definitions)
user_view_mode = handler_user_view_mode


def has_approved_store(user_id: int) -> bool:
    """Check if user has approved store."""
    return common_has_approved_store(user_id, db)


def get_appropriate_menu(user_id: int, lang: str) -> Any:
    """Get appropriate menu for user."""
    return common_get_appropriate_menu(user_id, lang, db, main_menu_seller, main_menu_customer)


def get_cached_user_data(user_id: int) -> Dict[str, Any]:
    """Get cached user data or fetch from DB."""
    return cache.get_user_data(user_id)


def invalidate_user_cache(user_id: int) -> None:
    """Invalidate user cache after updates."""
    cache.invalidate_user(user_id)


def get_user_language_cached(user_id: int) -> str:
    """Cached version of get_user_language."""
    return cache.get_user_data(user_id)['lang']

# Устанавливаем первого админа при старте
if ADMIN_ID > 0:
    try:
        # Проверяем существует ли пользователь
        user = db.get_user(ADMIN_ID)
        if not user:
            # Создаём пользователя-админа
            db.add_user(ADMIN_ID, "admin", "Admin")
        # Делаем админом
        db.set_admin(ADMIN_ID)
        print(f"✅ Админ установлен: {ADMIN_ID}")
    except Exception as e:
        print(f"⚠️ Ошибка при установке админа: {e}")

# Initialize Sentry for error tracking
print("🔧 Initializing Sentry error tracking...")
print(f"   SENTRY_DSN present: {'Yes' if os.getenv('SENTRY_DSN') else 'No'}")
try:
    from app.core.sentry_integration import init_sentry
    sentry_enabled = init_sentry(
        environment="production" if USE_WEBHOOK else "development",
        enable_logging=True,
        sample_rate=1.0,
        traces_sample_rate=0.1
    )
    if sentry_enabled:
        print("✅ Sentry initialized for production environment")
        print("✅ Sentry error tracking enabled")
    else:
        print("⚠️ Sentry not enabled (check SENTRY_DSN)")
except Exception as e:
    print(f"⚠️ Sentry initialization failed: {e}")
    import traceback
    traceback.print_exc()
    sentry_enabled = False

# ============== FALLBACK HANDLERS (defined early, registered late) ==============

from aiogram import Router
fallback_router = Router(name="fallback_handlers")

@fallback_router.message(F.photo)
async def unexpected_photo_handler(message: types.Message, state: FSMContext):
    """Обработчик для фото без активного состояния"""
    lang = db.get_user_language(message.from_user.id)
    current_state = await state.get_state()
    
    logger.warning(f"⚠️ User {message.from_user.id} sent photo without FSM state (current: {current_state})")
    
    await message.answer(
        "⚠️ " + (
            "Произошла ошибка: данные заказа потеряны.\n\n"
            "Это может произойти если:\n"
            "• Прошло много времени между шагами\n"
            "• Сервер был перезапущен\n\n"
            "Пожалуйста, начните оформление заказа заново:\n"
            "1. Откройте 🔥 Горячее или 📍 Места\n"
            "2. Выберите товар\n"
            "3. Нажмите 🚚 Заказать с доставкой"
            if lang == 'ru' else
            "⚠️ Xatolik: buyurtma ma'lumotlari yo'qoldi.\n\n"
            "Bu quyidagi hollarda sodir bo'lishi mumkin:\n"
            "• Qadamlar orasida ko'p vaqt o'tdi\n"
            "• Server qayta ishga tushirildi\n\n"
            "Iltimos, buyurtmani qaytadan boshlang:\n"
            "1. 🔥 Issiq yoki 📍 Joylar ni oching\n"
            "2. Mahsulotni tanlang\n"
            "3. 🚚 Yetkazib berish bilan tugmasini bosing"
        ),
        reply_markup=get_appropriate_menu(message.from_user.id, lang)
    )

@fallback_router.message(F.text)
async def unknown_message_debug(message: types.Message, state: FSMContext):
    """Отладочный обработчик для неизвестных текстовых сообщений"""
    lang = db.get_user_language(message.from_user.id)
    current_state = await state.get_state()
    user_id = message.from_user.id
    text = message.text
    
    # ПОДРОБНОЕ ЛОГИРОВАНИЕ ДЛЯ ОТЛАДКИ
    logger.warning(f"⚠️ НЕИЗВЕСТНОЕ СООБЩЕНИЕ от {user_id}: '{text}' (состояние: {current_state})")
    logger.warning(f"   User ID: {user_id}, Username: {message.from_user.username}")
    logger.warning(f"   Chat ID: {message.chat.id}, Message ID: {message.message_id}")
    
    # Проверяем роль пользователя
    user_data = db.get_user(user_id)
    if user_data:
        logger.warning(f"   Роль пользователя: {user_data.get('role', 'неизвестно')}")
    else:
        logger.warning(f"   ❌ Пользователь не найден в БД!")
    
    # Если пользователь вводит число, но нет активного состояния - подсказываем
    if text.isdigit():
        hint_ru = "Чтобы выбрать товар по номеру, сначала откройте список товаров через кнопку 🔥 Горячее или 📍 Места"
        hint_uz = "Mahsulotni raqam bo'yicha tanlash uchun avval 🔥 Issiq yoki 📍 Joylar tugmasidan mahsulotlar ro'yxatini oching"
        await message.answer(hint_ru if lang == 'ru' else hint_uz)
    else:
        # Отправляем диагностическое сообщение
        await message.answer(
            f"⚠️ DEBUG: Неизвестная команда\n"
            f"Текст: {text}\n"
            f"Состояние: {current_state}\n"
            f"Роль: {user_data.get('role', 'неизвестно') if user_data else 'НЕ В БД'}"
        )

@fallback_router.callback_query()
async def catch_all_callbacks(callback: types.CallbackQuery):
    """Логирование всех callback_data для отладки непойманных обработчиков"""
    data = callback.data or ""
    user_id = callback.from_user.id
    
    # ПОДРОБНОЕ ЛОГИРОВАНИЕ ДЛЯ ОТЛАДКИ
    logger.warning(f"⚠️ UNHANDLED CALLBACK от {user_id}: '{data}'")
    logger.warning(f"   User ID: {user_id}, Username: {callback.from_user.username}")
    logger.warning(f"   Message ID: {callback.message.message_id if callback.message else 'None'}")
    
    # Проверяем роль пользователя
    user_data = db.get_user(user_id)
    if user_data:
        logger.warning(f"   Роль пользователя: {user_data.get('role', 'неизвестно')}")
    
    try:
        await callback.answer("⚠️ DEBUG: Необработанный callback")
    except Exception:
        pass

# Register modular handlers from handlers package
# ============== PHASE 3: EXTRACTED HANDLERS INTEGRATION ==============
# Import extracted handler modules (FIRST - for router registration priority)
from handlers import bookings, orders, partner, common_user
from handlers.seller import create_offer, management, analytics, order_management, bulk_import
from handlers.user import profile, favorites
from handlers.admin import dashboard as admin_dashboard, legacy as admin_legacy

# Setup dependencies for extracted handlers
bookings.setup_dependencies(db, cache, bot, METRICS)
orders.setup_dependencies(db, bot, user_view_mode)
partner.setup_dependencies(db, bot, user_view_mode)
create_offer.setup_dependencies(db, bot)
management.setup_dependencies(db, bot)
analytics.setup_dependencies(db, bot)
bulk_import.setup_dependencies(db, bot)  # Bulk import dependencies
profile.setup_dependencies(db, bot, user_view_mode)
favorites.setup_dependencies(db, bot, user_view_mode)
order_management.setup(bot, db)
common_user.setup(bot, db, user_view_mode, get_text, main_menu_customer, booking_filters_keyboard, main_menu_seller)
admin_dashboard.setup(bot, db, get_text, moderation_keyboard, get_uzb_time)
admin_legacy.setup(bot, db, get_text, moderation_keyboard, get_uzb_time, ADMIN_ID, DATABASE_URL)

# Include extracted routers in dispatcher (SPECIFIC HANDLERS FIRST - higher priority)
dp.include_router(bulk_import.router)  # Seller: 📦 Массовый импорт
dp.include_router(profile.router)  # User profile
dp.include_router(favorites.router)  # User favorites
dp.include_router(create_offer.router)  # Seller: ➕ Добавить
dp.include_router(management.router)  # Seller: 📦 Мои товары (BEFORE common_user to catch seller orders first)
dp.include_router(analytics.router)  # Seller: 📊 Аналитика
dp.include_router(order_management.router)  # Seller: order operations
dp.include_router(common_user.router)  # Common user operations (AFTER management so sellers are handled first)
dp.include_router(orders.router)  # Orders: 🎫 Заказы
dp.include_router(bookings.router)  # Bookings and ratings
dp.include_router(partner.router)  # Partner registration
dp.include_router(admin_dashboard.router)  # Admin dashboard
dp.include_router(admin_legacy.router)  # Admin legacy

# ============== REGISTRATION & COMMANDS (AFTER SPECIFIC ROUTERS) ==============
from handlers import registration, user_commands, admin_panel, admin_stats, offers

# Setup registration handlers
registration.setup(dp, db, get_text, get_cities, city_keyboard, phone_request_keyboard, main_menu_customer,
                  validator, rate_limiter, logger, secure_user_input)

# Setup user command handlers
user_commands.setup(dp, db, get_text, get_cities, city_keyboard, language_keyboard,
                   phone_request_keyboard, main_menu_seller, main_menu_customer)

# Setup admin panel handlers
admin_panel.setup(dp, db, get_text, admin_menu)

# Setup offer browsing handlers (AFTER specific handlers to avoid catching their messages)
offers.setup(dp, db, offer_service, logger)

# Setup admin statistics handlers
admin_stats.setup(dp, admin_service, logger)

# Register middlewares
# 1. Rate limiting (FIRST - before any processing)
from app.middlewares.rate_limit import RateLimitMiddleware
dp.update.middleware(RateLimitMiddleware(rate_limit=30, burst_limit=5))

# 2. Registration check
dp.update.middleware(RegistrationCheckMiddleware(db, get_text, phone_request_keyboard))

# Register fallback router LAST (LOWEST PRIORITY - catches everything else)
dp.include_router(fallback_router)

# ============== REMAINING HANDLERS (TO BE MIGRATED) ==============
# Note: The handlers below will be gradually moved to the handlers/ package
# Handlers already migrated: registration, user_commands (start, language, cancel), admin (main panel)

# Skip duplicate handlers that are now in handler modules
# - Removed: Registration handlers (process_phone, process_city) - now in handlers/registration.py
# - Removed: User commands (cmd_start, choose_language, cancel_action, etc.) - now in handlers/user_commands.py
# - Removed: Admin commands (cmd_admin, admin_dashboard, admin_exit) - now in handlers/admin.py



# Old middleware registration removed - now registered above with imported class

# ============== HANDLERS BELOW WILL BE GRADUALLY MIGRATED ==============
# The following handlers remain in bot.py and can be moved to handler modules incrementally:
# - Store registration and management
# - Offer creation and management
# - Booking operations
# - Callback handlers (pagination, filters, etc.)
# - Additional admin handlers (moderation, detailed stats, etc.)

# ============== АДМИН ПАНЕЛЬ - ОБРАБОТЧИКИ ==============
# Admin statistics handlers moved to handlers/admin_stats.py

# @dp.message(F.text == "👥 Пользователи")
# async def admin_users(message: types.Message):
#     """Статистика пользователей с inline-меню (SQLite/PostgreSQL совместимо)"""
#     if not db.is_admin(message.from_user.id):
#         return

    # Собираем статистику внутри одного контекста подключения
#     try:
#         from datetime import datetime
#         today = datetime.now().strftime('%Y-%m-%d')
#         with db.get_connection() as conn:
#             cursor = conn.cursor()

#             cursor.execute('SELECT COUNT(*) FROM users')
#             total = cursor.fetchone()[0]

#             cursor.execute("SELECT COUNT(*) FROM users WHERE role = 'seller'")
#             sellers = cursor.fetchone()[0]

#             cursor.execute("SELECT COUNT(*) FROM users WHERE role = 'customer'")
#             customers = cursor.fetchone()[0]

#             if DATABASE_URL:
                # PostgreSQL syntax
#                 cursor.execute("SELECT COUNT(*) FROM users WHERE created_at >= CURRENT_DATE - INTERVAL '7 days'")
#                 week_users = cursor.fetchone()[0]
#                 cursor.execute('SELECT COUNT(*) FROM users WHERE DATE(created_at) = %s', (today,))
#                 today_users = cursor.fetchone()[0]
#             else:
                # SQLite syntax
#                 cursor.execute("""
#                     SELECT COUNT(*) FROM users 
#                     WHERE DATE(created_at) >= DATE('now', '-7 days')
#                 """)
#                 week_users = cursor.fetchone()[0]
#                 cursor.execute('SELECT COUNT(*) FROM users WHERE DATE(created_at) = ?', (today,))
#                 today_users = cursor.fetchone()[0]
#     except Exception as e:
#         logger.error(f"Admin users stats error: {e}")
#         return

#     text = "👥 <b>Пользователи</b>\n\n"
#     text += f"📊 Всего: {total}\n"
#     text += f"├ 🏪 Партнёры: {sellers}\n"
#     text += f"└ 🛍 Покупатели: {customers}\n\n"
#     text += f"📅 За неделю: +{week_users}\n"
#     text += f"📅 Сегодня: +{today_users}"

#     from aiogram.utils.keyboard import InlineKeyboardBuilder
#     kb = InlineKeyboardBuilder()
#     kb.button(text="📋 Список партнёров", callback_data="admin_list_sellers")
#     kb.button(text="🔍 Поиск пользователя", callback_data="admin_search_user")
#     kb.adjust(1)

#     await message.answer(text, parse_mode="HTML", reply_markup=kb.as_markup())

# @dp.message(F.text == "🏪 Магазины")
# async def admin_stores(message: types.Message):
#     """Управление магазинами с inline-меню"""
#     if not db.is_admin(message.from_user.id):
#         return
    
#     with db.get_connection() as conn:
#         cursor = conn.cursor()
        
#         cursor.execute("SELECT COUNT(*) FROM stores WHERE status = 'active'")
#         active = cursor.fetchone()[0]
        
#         cursor.execute("SELECT COUNT(*) FROM stores WHERE status = 'pending'")
#         pending = cursor.fetchone()[0]
        
#         cursor.execute("SELECT COUNT(*) FROM stores WHERE status = 'rejected'")
#         rejected = cursor.fetchone()[0]
    
#     text = "🏪 <b>Магазины</b>\n\n"
#     text += f"✅ Активные: {active}\n"
#     text += f"⏳ На модерации: {pending}\n"
#     text += f"❌ Отклонённые: {rejected}"
    
#     from aiogram.utils.keyboard import InlineKeyboardBuilder
#     kb = InlineKeyboardBuilder()
    
#     if pending > 0:
#         kb.button(text=f"⏳ Модерация ({pending})", callback_data="admin_moderation")
    
#     kb.button(text="✅ Одобренные", callback_data="admin_approved_stores")
#     kb.button(text="❌ Отклонённые", callback_data="admin_rejected_stores")
#     kb.button(text="🔍 Поиск магазина", callback_data="admin_search_store")
#     kb.adjust(1)
    
#     await message.answer(text, parse_mode="HTML", reply_markup=kb.as_markup())

# @dp.message(F.text == "📦 Товары")
# async def admin_offers(message: types.Message):
#     """Статистика товаров"""
#     if not db.is_admin(message.from_user.id):
#         return
    
#     with db.get_connection() as conn:
#         cursor = conn.cursor()
        
#         cursor.execute('SELECT COUNT(*) FROM offers WHERE status = "active"')
#         active = cursor.fetchone()[0]
        
#         cursor.execute('SELECT COUNT(*) FROM offers WHERE status = "inactive"')
#         inactive = cursor.fetchone()[0]
    
#     cursor.execute('SELECT COUNT(*) FROM offers WHERE status = "deleted"')
#     deleted = cursor.fetchone()[0]
    
    # Топ категорий
#     cursor.execute('''
#         SELECT category, COUNT(*) as cnt 
#         FROM offers 
#         WHERE status = 'active' AND category IS NOT NULL
#         GROUP BY category 
#         ORDER BY cnt DESC 
#         LIMIT 5
#     ''')
#     top_categories = cursor.fetchall()
    
#     conn.close()
    
#     text = "📦 <b>Товары</b>\n\n"
#     text += f"✅ Активные: {active}\n"
#     text += f"❌ Неактивные: {inactive}\n"
#     text += f"🗑 Удалённые: {deleted}\n\n"
    
#     if top_categories:
#         text += "<b>Топ категорий:</b>\n"
#         for cat, cnt in top_categories:
#             text += f"├ {cat}: {cnt}\n"
    
#     from aiogram.utils.keyboard import InlineKeyboardBuilder
#     kb = InlineKeyboardBuilder()
#     kb.button(text="📋 Все активные", callback_data="admin_all_offers")
#     kb.button(text="🗑 Очистить старые", callback_data="admin_cleanup_offers")
#     kb.adjust(1)
    
#     await message.answer(text, parse_mode="HTML", reply_markup=kb.as_markup())

# @dp.message(F.text == "📋 Бронирования")
# async def admin_bookings(message: types.Message):
#     """Статистика бронирований"""
#     if not db.is_admin(message.from_user.id):
#         return
    
#     with db.get_connection() as conn:
#         cursor = conn.cursor()
        
#         cursor.execute('SELECT COUNT(*) FROM bookings')
#         total = cursor.fetchone()[0]
        
#         cursor.execute('SELECT COUNT(*) FROM bookings WHERE status = "pending"')
#         pending = cursor.fetchone()[0]
        
#         cursor.execute('SELECT COUNT(*) FROM bookings WHERE status = "completed"')
#     completed = cursor.fetchone()[0]
    
#     cursor.execute('SELECT COUNT(*) FROM bookings WHERE status = "cancelled"')
#     cancelled = cursor.fetchone()[0]
    
    # За сегодня
#     from datetime import datetime
#     today = datetime.now().strftime('%Y-%m-%d')
    
#     cursor.execute('SELECT COUNT(*) FROM bookings WHERE DATE(created_at) = ?', (today,))
#     today_bookings = cursor.fetchone()[0]
    
#     cursor.execute('''
#         SELECT SUM(o.discount_price * b.quantity)
#         FROM bookings b
#         JOIN offers o ON b.offer_id = o.offer_id
#         WHERE DATE(b.created_at) = ? AND b.status != 'cancelled'
#     ''', (today,))
#     today_revenue = cursor.fetchone()[0] or 0
    
#     conn.close()
    
#     text = "🎫 <b>Бронирования</b>\n\n"
#     text += f"📊 Всего: {total}\n"
#     text += f"├ ⏳ Активные: {pending}\n"
#     text += f"├ ✅ Завершённые: {completed}\n"
#     text += f"└ ❌ Отменённые: {cancelled}\n\n"
#     text += f"📅 Сегодня: {today_bookings}\n"
#     text += f"� Выручка: {int(today_revenue):,} сум"
    
#     from aiogram.utils.keyboard import InlineKeyboardBuilder
#     kb = InlineKeyboardBuilder()
#     kb.button(text="⏳ Активные", callback_data="admin_pending_bookings")
#     kb.button(text="✅ Завершённые", callback_data="admin_completed_bookings")
#     kb.button(text="📊 Статистика", callback_data="admin_bookings_stats")
#     kb.adjust(1)
    
#     await message.answer(text, parse_mode="HTML", reply_markup=kb.as_markup())

# ============== EXTRACTED HANDLERS ==============
# The following handlers have been extracted to modular files:
# - handlers/bookings.py: Booking operations (8 handlers)
# - handlers/orders.py: Delivery orders (10 handlers)
# - handlers/partner.py: Partner registration (7 handlers)
# - handlers/seller/create_offer.py: Offer creation (12 handlers)
# - handlers/seller/management.py: Offer management (15 handlers)
# - handlers/seller/analytics.py: Analytics (2 handlers)
# - handlers/user/profile.py: User profile (9 handlers)
# - handlers/user/favorites.py: Favorites and city (5 handlers)
# - handlers/seller/order_management.py: Order operations (4 handlers)
# - handlers/booking_rating.py: Booking ratings (1 handler)
# - handlers/common_user.py: Common user features (1 handler)
# Total: 75 handlers extracted, integrated via routers in lines 171-203

# ============== ОСТАЛЬНЫЕ ОБРАБОТЧИКИ ==============
# Handlers below will be extracted in next phases

# Lines 433-457: Handlers extracted to booking_rating module
# Lines 459-632: Handlers extracted to seller/order_management module
# Lines 634-642: Handlers extracted to common_user module
# Lines 647-726: Handlers extracted to seller/analytics module
# Lines 447-1286: Handlers extracted to admin/dashboard module (17 handlers)
# Lines 452-1064: Handlers extracted to admin/legacy module (10 handlers: analytics, moderation, system commands)

# ============== FALLBACK HANDLERS (will be registered LAST) ==============

def setup_fallback_handlers():
    """Register fallback handlers AFTER all specific handlers"""
    
    @dp.message(F.photo)
    async def unexpected_photo_handler(message: types.Message, state: FSMContext):
        """Обработчик для фото без активного состояния"""
        lang = db.get_user_language(message.from_user.id)
        current_state = await state.get_state()
        
        logger.warning(f"⚠️ User {message.from_user.id} sent photo without FSM state (current: {current_state})")
        
        await message.answer(
            "⚠️ " + (
                "Произошла ошибка: данные заказа потеряны.\n\n"
                "Это может произойти если:\n"
                "• Прошло много времени между шагами\n"
                "• Сервер был перезапущен\n\n"
                "Пожалуйста, начните оформление заказа заново:\n"
                "1. Откройте 🔥 Горячее или 📍 Места\n"
                "2. Выберите товар\n"
                "3. Нажмите 🚚 Заказать с доставкой"
                if lang == 'ru' else
                "⚠️ Xatolik: buyurtma ma'lumotlari yo'qoldi.\n\n"
                "Bu quyidagi hollarda sodir bo'lishi mumkin:\n"
                "• Qadamlar orasida ko'p vaqt o'tdi\n"
                "• Server qayta ishga tushirildi\n\n"
                "Iltimos, buyurtmani qaytadan boshlang:\n"
                "1. 🔥 Issiq yoki 📍 Joylar ni oching\n"
                "2. Mahsulotni tanlang\n"
                "3. 🚚 Yetkazib berish bilan tugmasini bosing"
            ),
            reply_markup=get_appropriate_menu(message.from_user.id, lang)
        )
    
    @dp.message(F.text)
    async def unknown_message_debug(message: types.Message, state: FSMContext):
        """Отладочный обработчик для неизвестных текстовых сообщений"""
        lang = db.get_user_language(message.from_user.id)
        current_state = await state.get_state()
        
        # Если пользователь вводит число, но нет активного состояния - подсказываем
        if message.text.isdigit():
            hint_ru = "Чтобы выбрать товар по номеру, сначала откройте список товаров через кнопку 🔥 Горячее или 📍 Места"
            hint_uz = "Mahsulotni raqam bo'yicha tanlash uchun avval 🔥 Issiq yoki 📍 Joylar tugmasidan mahsulotlar ro'yxatini oching"
            await message.answer(hint_ru if lang == 'ru' else hint_uz)
        else:
            # Просто логируем для отладки без спама пользователю
            logger.debug(f"⚠️ НЕИЗВЕСТНОЕ СООБЩЕНИЕ от {message.from_user.id}: '{message.text}' (состояние: {current_state})")

# ============== CATCH ALL CALLBACKS ==============

def setup_catch_all():
    """Register catch-all callback handler LAST"""
    
    @dp.callback_query()
    async def catch_all_callbacks(callback: types.CallbackQuery):
        """Логирование всех callback_data для отладки непойманных обработчиков"""
        data = callback.data or ""
        logger.info(f"UNHANDLED callback: {data}")
        try:
            await callback.answer()
        except Exception:
            pass

# ============== ЗАПУСК БОТА ==============

# ============================================
# ФОНОВАЯ ЗАДАЧА - УДАЛЕНИЕ ИСТЕКШИХ ТОВАРОВ
# ============================================

async def cleanup_expired_offers():
    """Фоновая задача для удаления истекших предложений"""
    while True:
        try:
            await asyncio.sleep(300)  # Проверяем каждые 5 минут (300 секунд)
            deleted_count = db.delete_expired_offers()
            if deleted_count > 0:
                print(f"🗑 Удалено истекших предложений: {deleted_count}")
        except Exception as e:
            print(f"⚠️ Ошибка при очистке истекших товаров: {e}")

# ============================================
# ЗАПУСК БОТА
# ============================================

async def on_startup():
    """Действия при запуске бота"""
    if USE_WEBHOOK:
        # Устанавливаем webhook
        webhook_url = f"{WEBHOOK_URL}{WEBHOOK_PATH}"
        try:
            await bot.set_webhook(
                url=webhook_url,
                drop_pending_updates=True,
                # Don't restrict allowed_updates to avoid missing types in production
                secret_token=SECRET_TOKEN or None
            )
            print(f"✅ Webhook установлен: {webhook_url}")
        except Exception as e:
            logger.error(f"Failed to set webhook: {e}")
            # Продолжаем запуск HTTP сервера даже если установить webhook не удалось
    else:
        # Удаляем webhook если используем polling
        await bot.delete_webhook(drop_pending_updates=True)
        print("✅ Polling режим активирован")

async def on_shutdown():
    """Действия при остановке бота"""
    await bot.session.close()
    print("👋 Бот остановлен")

# ============== HANDLER REGISTRATION ==============
# NOTE: Fallback handlers registered LAST via setup functions called in main()

# ============== ЗАПУСК БОТА ==============

async def main():
    print("✅ Бот успешно запущен!")
    print(f"🔄 Режим: {'Webhook' if USE_WEBHOOK else 'Polling'}")
    print("⚠️ Нажмите Ctrl+C для остановки")
    print("=" * 50)
    
    # ПРИНУДИТЕЛЬНАЯ МИГРАЦИЯ БД (только для SQLite)
    if not DATABASE_URL:
        try:
            print("🔄 Проверка структуры базы данных...")
            conn = sqlite3.connect(db.db_name)
            cursor = conn.cursor()
            
            # Проверяем наличие полей доставки
            cursor.execute('PRAGMA table_info(stores)')
            columns = [col[1] for col in cursor.fetchall()]
            
            if 'delivery_enabled' not in columns:
                print("⚠️ Поля доставки отсутствуют! Добавляем...")
                cursor.execute('ALTER TABLE stores ADD COLUMN delivery_enabled INTEGER DEFAULT 1')
                cursor.execute('ALTER TABLE stores ADD COLUMN delivery_price INTEGER DEFAULT 15000')
                cursor.execute('ALTER TABLE stores ADD COLUMN min_order_amount INTEGER DEFAULT 30000')
                conn.commit()
                print("✅ Поля доставки добавлены!")
            else:
                print("✅ Поля доставки уже существуют")
                # ВКЛЮЧАЕМ доставку для всех магазинов автоматически
                cursor.execute('UPDATE stores SET delivery_enabled = 1 WHERE delivery_enabled = 0 OR delivery_enabled IS NULL')
                updated = cursor.rowcount
                conn.commit()
                if updated > 0:
                    print(f"✅ Доставка включена для {updated} магазина(ов)")
            
            # СОЗДАЕМ ТЕСТОВЫЕ ДАННЫЕ (если нет активных товаров)
            cursor.execute('SELECT COUNT(*) FROM offers WHERE status = "active"')
            offers_count = cursor.fetchone()[0]
            
            if offers_count == 0:
                print("⚠️ Нет активных товаров! Создаю тестовые данные...")
                
                # Создаем тестового пользователя (админ)
                cursor.execute('SELECT COUNT(*) FROM users WHERE user_id = ?', (ADMIN_ID,))
                if cursor.fetchone()[0] == 0:
                    cursor.execute('''
                        INSERT INTO users (user_id, username, first_name, phone, city, language, role)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                    ''', (ADMIN_ID, 'admin', 'Admin', '+998901234567', 'Ташкент', 'ru', 'seller'))
                
                # Создаем тестовый магазин
                cursor.execute('''
                    INSERT INTO stores (owner_id, name, city, address, description, category, phone, status, business_type, delivery_enabled, delivery_price, min_order_amount)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (ADMIN_ID, 'Demo Market', 'Ташкент', 'пр. Амира Темура, 1', 'Тестовый магазин с горячими предложениями', 'Супермаркет', '+998901234567', 'active', 'supermarket', 1, 15000, 30000))
                store_id = cursor.lastrowid
                
                # Создаем тестовые товары с большими скидками
                from datetime import datetime, timedelta
                now = datetime.now()
                tomorrow = now + timedelta(days=1)
                
                test_products = [
                    ('Хлеб свежий', 'Свежеиспеченный хлеб', 8000, 3000, 50, tomorrow.strftime('%Y-%m-%d %H:%M:%S'), 'bakery', 'шт'),
                    ('Молоко 1л', 'Свежее молоко', 12000, 5000, 30, tomorrow.strftime('%Y-%m-%d %H:%M:%S'), 'dairy', 'л'),
                    ('Яблоки 1кг', 'Свежие яблоки', 20000, 8000, 100, tomorrow.strftime('%Y-%m-%d %H:%M:%S'), 'fruits', 'кг'),
                    ('Курица 1кг', 'Охлажденная курица', 35000, 18000, 25, tomorrow.strftime('%Y-%m-%d %H:%M:%S'), 'meat', 'кг'),
                    ('Торт праздничный', 'Вкусный торт', 80000, 40000, 10, tomorrow.strftime('%Y-%m-%d %H:%M:%S'), 'ready_food', 'шт'),
                ]
                
                for title, desc, orig_price, disc_price, qty, exp, cat, unit in test_products:
                    cursor.execute('''
                        INSERT INTO offers (store_id, title, description, original_price, discount_price, quantity, available_from, available_until, expiry_date, status, unit, category)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'active', ?, ?)
                    ''', (store_id, title, desc, orig_price, disc_price, qty, now.strftime('%Y-%m-%d %H:%M:%S'), tomorrow.strftime('%Y-%m-%d %H:%M:%S'), exp, unit, cat))
                
                conn.commit()
                print(f"✅ Создан тестовый магазин с {len(test_products)} товарами!")
            else:
                cursor.execute('SELECT COUNT(*) FROM stores WHERE status = "active"')
                stores_count = cursor.fetchone()[0]
                print(f"✅ В БД есть {stores_count} активных магазинов и {offers_count} активных товаров")
            
            conn.close()
        except Exception as e:
            print(f"⚠️ Ошибка миграции: {e}")
    else:
        print("✅ PostgreSQL - миграция не требуется")
    
    # Запускаем фоновую задачу очистки
    cleanup_task = asyncio.create_task(cleanup_expired_offers())
    
    if USE_WEBHOOK:
        # Webhook режим (для production на Railway)
        from aiohttp import web
        
        await on_startup()
        
        app = web.Application()
        
        # Webhook endpoint
        async def webhook_handler(request):
            import time
            start_ts = time.time()
            # Разрешаем только POST запросы Telegram
            if request.method != 'POST':
                return web.Response(status=405, text='Method Not Allowed')
            try:
                logger.info(f"Webhook request received from {request.remote}")

                # Проверяем секретный токен (если настроен)
                if SECRET_TOKEN:
                    hdr = request.headers.get("X-Telegram-Bot-Api-Secret-Token")
                    if hdr != SECRET_TOKEN:
                        logger.warning("Invalid secret token")
                        METRICS["updates_errors"] += 1
                        return web.Response(status=403, text="Forbidden")

                # Парсинг JSON
                try:
                    update_data = await request.json()
                except Exception as json_e:
                    logger.error(f"Webhook JSON parse error: {repr(json_e)}")
                    METRICS["webhook_json_errors"] += 1
                    # Возвращаем 200 чтобы Telegram не ретраил бесконечно
                    return web.Response(status=200, text="OK")

                logger.debug(f"Raw update: {update_data}")

                # Валидация структуры Update
                try:
                    telegram_update = types.Update.model_validate(update_data)
                except Exception as validate_e:
                    logger.error(f"Webhook validation error: {repr(validate_e)}")
                    METRICS["webhook_validation_errors"] += 1
                    return web.Response(status=200, text="OK")

                # Обработка апдейта
                await dp.feed_update(bot, telegram_update)
                METRICS["updates_received"] += 1
                proc_ms = int((time.time() - start_ts) * 1000)
                logger.info(f"Update processed successfully ({proc_ms}ms)")
                return web.Response(status=200, text="OK")
            except Exception as e:
                logger.error(f"Webhook unexpected error: {repr(e)}", exc_info=True)
                METRICS["webhook_unexpected_errors"] += 1
                METRICS["updates_errors"] += 1
                return web.Response(status=200, text="OK")
        
        # Health check endpoint with DB status
        async def health_check(request):
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
                            "error": db_error
                        },
                        "bot": {"status": "healthy"}
                    }
                }
                
                # Add metrics
                status["metrics"] = {
                    "updates_received": METRICS.get("updates_received", 0),
                    "updates_errors": METRICS.get("updates_errors", 0),
                    "error_rate": round(
                        METRICS.get("updates_errors", 0) / max(METRICS.get("updates_received", 1), 1) * 100, 2
                    )
                }
                
                http_status = 200 if db_healthy else 503
                return web.json_response(status, status=http_status)
            except Exception as e:
                logger.error(f"Health check failed: {e}")
                return web.json_response({
                    "status": "error",
                    "error": str(e)
                }, status=500)
        
        async def version_info(request):
            return web.json_response({
                "app": "Fudly",
                "mode": "webhook",
                "port": PORT,
                "use_webhook": USE_WEBHOOK,
                "ts": datetime.now().isoformat(timespec='seconds')
            })
        # Prometheus-style metrics (text/plain) and JSON variant
        def _prometheus_metrics_text():
            help_map = {
                "updates_received": "Total updates received",
                "updates_errors": "Total webhook errors",
                "bookings_created": "Total bookings created",
                "bookings_cancelled": "Total bookings cancelled",
            }
            lines = []
            for key, val in METRICS.items():
                metric = f"fudly_{key}"
                lines.append(f"# HELP {metric} {help_map.get(key, key)}")
                lines.append(f"# TYPE {metric} counter")
                try:
                    v = int(val)
                except Exception:
                    v = 0
                lines.append(f"{metric} {v}")
            return "\n".join(lines) + "\n"

        async def metrics_prom(request):
            text = _prometheus_metrics_text()
            return web.Response(text=text, content_type='text/plain; version=0.0.4; charset=utf-8')

        async def metrics_json(request):
            return web.json_response(METRICS)
        
        # Webhook endpoints (POST + GET for sanity) — register both with and without trailing slash
        path_main = WEBHOOK_PATH if WEBHOOK_PATH.startswith('/') else f'/{WEBHOOK_PATH}'
        path_alt = path_main.rstrip('/') + '/'
        app.router.add_post(path_main, webhook_handler)
        app.router.add_post(path_alt, webhook_handler)
        async def webhook_get(_request):
            return web.Response(text="OK", status=200)
        app.router.add_get(path_main, webhook_get)
        app.router.add_get(path_alt, webhook_get)
        app.router.add_get("/health", health_check)
        app.router.add_get("/version", version_info)
        app.router.add_get("/metrics", metrics_prom)
        app.router.add_get("/metrics.json", metrics_json)
        app.router.add_get("/", health_check)  # Railway health check
        
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, '0.0.0.0', PORT)
        await site.start()
        
        print(f"🌐 Webhook сервер запущен на порту {PORT}")
        
        try:
            await shutdown_event.wait()
        finally:
            cleanup_task.cancel()
            await runner.cleanup()
            await on_shutdown()
    else:
        # Polling режим (для локальной разработки)
        await on_startup()
        
        # Создаём задачу для polling
        polling_task = asyncio.create_task(dp.start_polling(
            bot,
            allowed_updates=dp.resolve_used_update_types(),
            drop_pending_updates=True
        ))
        # Дополнительный HTTP-сервер здоровья/метрик для polling-режима (по желанию)
        health_runner = None
        if POLLING_HEALTH_PORT > 0:
            try:
                from aiohttp import web  # lazy import

                async def health_check(_request):
                    return web.json_response({"status": "ok", "mode": "polling"})

                def _metrics_text():
                    help_map = {
                        "updates_received": "Total updates received",
                        "updates_errors": "Total webhook errors",
                        "bookings_created": "Total bookings created",
                        "bookings_cancelled": "Total bookings cancelled",
                    }
                    lines = []
                    for key, val in METRICS.items():
                        metric = f"fudly_{key}"
                        lines.append(f"# HELP {metric} {help_map.get(key, key)}")
                        lines.append(f"# TYPE {metric} counter")
                        try:
                            v = int(val)
                        except Exception:
                            v = 0
                        lines.append(f"{metric} {v}")
                    return "\n".join(lines) + "\n"

                async def metrics_prom(_request):
                    return web.Response(text=_metrics_text(), content_type='text/plain; version=0.0.4; charset=utf-8')

                app = web.Application()
                app.router.add_get("/health", health_check)
                app.router.add_get("/metrics", metrics_prom)
                app.router.add_get("/", health_check)

                health_runner = web.AppRunner(app)
                await health_runner.setup()
                site = web.TCPSite(health_runner, '0.0.0.0', POLLING_HEALTH_PORT)
                await site.start()
                print(f"🩺 Health server (polling) on port {POLLING_HEALTH_PORT}")
            except Exception as e:
                print(f"⚠️ Failed to start polling health server: {e}")
        
        try:
            await shutdown_event.wait()
            print("\n🛑 Завершение по сигналу...")
            polling_task.cancel()
            try:
                await polling_task
            except asyncio.CancelledError:
                pass
        except Exception as e:
            print(f"\n❌ Критическая ошибка: {type(e).__name__}: {e}")
        finally:
            cleanup_task.cancel()
            try:
                await cleanup_task
            except asyncio.CancelledError:
                pass
            if health_runner is not None:
                try:
                    await health_runner.cleanup()
                except Exception:
                    pass
            await on_shutdown()

# ============================================
# ЗАЩИТА ОТ МНОЖЕСТВЕННОГО ЗАПУСКА
# ============================================

def is_bot_already_running(port: int | None = None) -> bool:
    """Проверяет, не запущен ли уже бот (лок-биндинг TCP порта).

    Можно отключить через переменную окружения `DISABLE_LOCK=1`.
    Порт можно переопределить через `LOCK_PORT`.
    """
    if DISABLE_LOCK:
        return False
    p = port or LOCK_PORT
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.bind(('127.0.0.1', p))
        sock.close()
        return False
    except OSError:
        print(f"🛑 ОШИБКА: Бот уже запущен на порту {p}!")
        print("⚠️ Остановите другой экземпляр перед запуском нового или установите DISABLE_LOCK=1.")
        return True

# Глобальная переменная для graceful shutdown
shutdown_event = asyncio.Event()

def signal_handler(sig, frame):
    """Обработчик сигнала завершения (Ctrl+C)"""
    print("\n🛑 Получен сигнал завершения...")
    shutdown_event.set()

if __name__ == "__main__":
    # Проверяем, не запущен ли бот уже
    if is_bot_already_running():
        print("❌ Завершение работы дубликата...")
        sys.exit(1)
    
    # ПРИНУДИТЕЛЬНО создаём таблицы для доставки (только для SQLite)
    if not DATABASE_URL:
        try:
            conn = sqlite3.connect(db.db_name)
            cursor = conn.cursor()
            
            print("🔄 Проверяю и создаю таблицы для доставки...")
            
            # Создаём таблицу orders
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS orders (
                        order_id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id INTEGER NOT NULL,
                        store_id INTEGER NOT NULL,
                        offer_id INTEGER NOT NULL,
                        quantity INTEGER NOT NULL,
                        total_amount REAL NOT NULL,
                        delivery_price REAL NOT NULL,
                        delivery_address TEXT NOT NULL,
                        payment_method TEXT NOT NULL,
                        payment_proof TEXT,
                        status TEXT DEFAULT 'pending',
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (user_id) REFERENCES users(user_id),
                        FOREIGN KEY (store_id) REFERENCES stores(store_id),
                        FOREIGN KEY (offer_id) REFERENCES offers(offer_id)
                    )
            ''')
            
            # Создаём таблицу payment_settings
            cursor.execute('''
                    CREATE TABLE IF NOT EXISTS payment_settings (
                        setting_id INTEGER PRIMARY KEY AUTOINCREMENT,
                        card_number TEXT NOT NULL,
                        card_holder TEXT NOT NULL,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Добавляем дефолтную карту
            cursor.execute('SELECT COUNT(*) FROM payment_settings')
            if cursor.fetchone()[0] == 0:
                cursor.execute('''
                    INSERT INTO payment_settings (card_number, card_holder)
                    VALUES (?, ?)
                ''', ('8600 0000 0000 0000', 'FUDLY PLATFORM'))
            
            # Добавляем поля доставки в stores
            try:
                cursor.execute('ALTER TABLE stores ADD COLUMN delivery_enabled INTEGER DEFAULT 0')
            except:
                pass
            try:
                cursor.execute('ALTER TABLE stores ADD COLUMN delivery_price INTEGER DEFAULT 10000')
            except:
                pass
            try:
                cursor.execute('ALTER TABLE stores ADD COLUMN min_order_amount INTEGER DEFAULT 20000')
            except:
                pass
            
            # Создаём индексы
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_orders_user ON orders(user_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_orders_store ON orders(store_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status)')
            
            conn.commit()
            print("✅ Таблицы для доставки созданы")
            
            # Автоматически включаем доставку для всех магазинов
            cursor.execute('SELECT COUNT(*) FROM stores WHERE delivery_enabled = 1')
            enabled_count = cursor.fetchone()[0]
            cursor.execute('SELECT COUNT(*) FROM stores')
            total_count = cursor.fetchone()[0]
            
            if total_count > 0 and enabled_count == 0:
                print("🚚 Включаю доставку для всех магазинов...")
                cursor.execute('''
                    UPDATE stores 
                    SET delivery_enabled = 1,
                        delivery_price = 15000,
                        min_order_amount = 30000
                    WHERE delivery_enabled = 0
                ''')
                conn.commit()
                print(f"✅ Доставка включена для {total_count} магазина(ов)")
            
            conn.close()
        except Exception as e:
            print(f"⚠️ Ошибка при настройке доставки: {e}")
    
    print("=" * 50)
    print("🚀 Запуск бота Fudly (Production Optimized)...")
    print("=" * 50)
    print(f"📊 База данных: {db.db_name}")
    if ADMIN_ID > 0:
        print(f"👑 Главный админ: {ADMIN_ID}")
    print(f"🔒 Порт блокировки: 8444")
    print(f"🌍 Языки: Русский, Узбекский")
    print(f"📸 Поддержка фото: Да")
    print(f"⚡ Оптимизация: Пулинг соединений, кэширование, безопасность")
    print("=" * 50)
    
    # Start background tasks for cleanup and maintenance
    if PRODUCTION_FEATURES:
        logger.info("Starting background tasks...")
        start_background_tasks(db)
        print("✅ Background tasks started")
    else:
        print("⚠️ Running in basic mode (production features disabled)")
    
    # Устанавливаем обработчик сигналов
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        logger.info("Bot starting...")
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
        print("\n👋 Бот остановлен пользователем")
    except Exception as e:
        logger.error(f"Bot crashed: {str(e)}")
        print(f"\n❌ Ошибка: {e}")
    finally:
        logger.info("Bot shutdown complete")

