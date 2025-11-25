"""Admin-specific keyboards."""
from __future__ import annotations

from aiogram.types import InlineKeyboardMarkup, ReplyKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder


def admin_menu(lang: str = "ru") -> ReplyKeyboardMarkup:
    """Compact admin menu with improved grouping."""
    builder = ReplyKeyboardBuilder()
    builder.button(text="📊 Dashboard")
    builder.button(text="👥 Пользователи")
    builder.button(text="🏪 Магазины")
    builder.button(text="📋 Товары")
    builder.button(text="📦 Бронирования")
    builder.button(text="📈 Аналитика")
    builder.button(text="📢 Рассылка")
    builder.button(text="⚙️ Настройки")
    builder.button(text="🔙 Выход")
    builder.adjust(2, 2, 2, 2, 1)
    return builder.as_markup(resize_keyboard=True)


def admin_users_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="📋 Список партнёров", callback_data="admin_list_sellers")
    builder.button(text="🔍 Поиск пользователя", callback_data="admin_search_user")
    builder.adjust(1)
    return builder.as_markup()


def admin_stores_keyboard(pending: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    if pending > 0:
        builder.button(text=f"⏳ Модерация ({pending})", callback_data="admin_moderation")
    builder.button(text="✅ Одобренные", callback_data="admin_approved_stores")
    builder.button(text="❌ Отклонённые", callback_data="admin_rejected_stores")
    builder.button(text="🔍 Поиск магазина", callback_data="admin_search_store")
    builder.adjust(1)
    return builder.as_markup()


def admin_offers_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="📋 Все активные", callback_data="admin_all_offers")
    builder.button(text="🗑 Очистить старые", callback_data="admin_cleanup_offers")
    builder.adjust(1)
    return builder.as_markup()


def admin_bookings_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="⏳ Активные", callback_data="admin_pending_bookings")
    builder.button(text="✅ Завершённые", callback_data="admin_completed_bookings")
    builder.button(text="📊 Статистика", callback_data="admin_bookings_stats")
    builder.adjust(1)
    return builder.as_markup()
