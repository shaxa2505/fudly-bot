"""Seller analytics handlers."""
from __future__ import annotations

from typing import Any

from aiogram import F, Router, types
from aiogram.utils.keyboard import InlineKeyboardBuilder

from database_protocol import DatabaseProtocol
from handlers.common.utils import can_manage_store
from localization import get_text
from logging_config import logger

# Module-level dependencies
db: DatabaseProtocol | None = None
bot: Any | None = None

router = Router()


def setup_dependencies(database: DatabaseProtocol, bot_instance: Any) -> None:
    """Setup module dependencies."""
    global db, bot
    db = database
    bot = bot_instance


@router.message(
    F.text.in_(
        {
            get_text("ru", "analytics"),
            get_text("uz", "analytics"),
            "Аналитика",
            "Analitika",
        }
    )
)
async def show_analytics(message: types.Message) -> None:
    """Show analytics menu for seller."""
    if not db:
        await message.answer("System error")
        return

    lang = db.get_user_language(message.from_user.id)
    stores = db.get_user_accessible_stores(message.from_user.id)

    if not stores:
        await message.answer(get_text(lang, "no_stores"))
        return

    keyboard = InlineKeyboardBuilder()
    for store in stores:
        # Dict-compatible access
        store_id = store.get("store_id") if isinstance(store, dict) else store[0]
        store_name = store.get("name") if isinstance(store, dict) else store[2]
        label = get_text(lang, "analytics")
        keyboard.button(text=f"{label}: {store_name}", callback_data=f"analytics_{store_id}")
    keyboard.adjust(1)

    await message.answer(
        get_text(lang, "select_store_for_analytics"), reply_markup=keyboard.as_markup()
    )


@router.callback_query(F.data.startswith("analytics_"))
async def show_store_analytics(callback: types.CallbackQuery) -> None:
    """Show detailed store analytics."""
    if not db:
        await callback.answer("System error")
        return

    lang = db.get_user_language(callback.from_user.id)

    try:
        store_id = int(callback.data.split("_")[1])
    except (ValueError, IndexError) as e:
        logger.error(f"Invalid store_id in callback data: {callback.data}, error: {e}")
        await callback.answer(get_text(lang, "error"), show_alert=True)
        return

    store = db.get_store(store_id)
    if not can_manage_store(db, store_id, callback.from_user.id, store=store):
        await callback.answer(get_text(lang, "no_access"), show_alert=True)
        return

    analytics = db.get_store_analytics(store_id)

    # Dict-compatible access
    store_name = store.get("name") if isinstance(store, dict) else store[2]

    text = f"<b>Аналитика магазина {store_name}</b>\n\n"

    text += "<b>Общая статистика</b>\n"
    text += f"Всего бронирований: {analytics['total_bookings']}\n"
    text += f"Выдано: {analytics['completed']}\n"
    text += f"Отменено: {analytics['cancelled']}\n"
    text += f"Конверсия: {analytics['conversion_rate']:.1f}%\n\n"

    if analytics.get("days_of_week"):
        text += "<b>По дням недели</b>\n"
        days_ru = ["Вс", "Пн", "Вт", "Ср", "Чт", "Пт", "Сб"]
        for day, count in analytics["days_of_week"].items():
            text += f"{days_ru[day]}: {count} бронирований\n"
        text += "\n"

    if analytics.get("popular_categories"):
        text += "<b>Популярные категории</b>\n"
        for cat, count in analytics["popular_categories"][:5]:
            text += f"{cat}: {count} бронирований\n"
        text += "\n"

    if analytics.get("avg_rating"):
        text += "<b>Средний рейтинг</b>\n"
        text += f"{analytics['avg_rating']:.1f}/5 ({analytics['rating_count']} отзывов)\n"

    await callback.message.answer(text, parse_mode="HTML")
    await callback.answer()
