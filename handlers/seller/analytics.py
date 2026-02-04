"""Seller analytics handlers."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from aiogram import F, Router, types
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.core.utils import get_store_field
from database_protocol import DatabaseProtocol
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
            "?????????",
            "Analitika",
            "?? ?????????",
            "?? Analitika",
        }
    )
)
async def show_analytics(message: types.Message) -> None:
    """Show analytics menu for seller."""
    if not db:
        await message.answer("System error")
        return

    lang = db.get_user_language(message.from_user.id)
    user = db.get_user_model(message.from_user.id)

    if (user.role if user else "customer") != "seller":
        await message.answer(get_text(lang, "not_seller"))
        return

    stores = db.get_user_accessible_stores(message.from_user.id)

    if not stores:
        await message.answer(get_text(lang, "no_stores"))
        return

    keyboard = InlineKeyboardBuilder()
    for store in stores:
        # Dict-compatible access
        store_id = store.get("store_id") if isinstance(store, dict) else store[0]
        store_name = store.get("name") if isinstance(store, dict) else store[2]
        label = "Аналитика" if lang == "ru" else "Analitika"
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

    analytics = db.get_store_analytics(store_id)
    store = db.get_store(store_id)

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


@router.message(
    F.text.in_(
        {
            get_text("ru", "today_stats"),
            get_text("uz", "today_stats"),
            "Сегодня",
            "Bugun",
        }
    )
)
async def partner_today_stats(message: types.Message, state: FSMContext) -> None:
    """Компактная статистика партнёра за сегодня"""
    # Clear any active FSM state
    await state.clear()
    
    if not db:
        await message.answer("System error")
        return

    lang = db.get_user_language(message.from_user.id)

    # Проверяем наличие магазинов (это главный критерий партнёра)
    stores = db.get_user_accessible_stores(message.from_user.id)
    if not stores:
        await message.answer(get_text(lang, "no_stores"))
        return

    with db.get_connection() as conn:
        cursor = conn.cursor()

        # Собираем ID всех магазинов партнёра
        store_ids = [get_store_field(store, "store_id") for store in stores]
        placeholders = ",".join(["%s"] * len(store_ids))

        # Статистика за сегодня
        today = datetime.now().strftime("%Y-%m-%d")

        # Заказы за сегодня
        query1 = f"""
            SELECT COUNT(*), SUM(b.quantity), SUM(o.discount_price * b.quantity)
            FROM bookings b
            JOIN offers o ON b.offer_id = o.offer_id
            WHERE o.store_id IN ({placeholders})
            AND DATE(b.created_at) = %s
            AND b.status != 'cancelled'
        """
        cursor.execute(query1, (*store_ids, today))

        orders_count, items_sold, revenue = cursor.fetchone()
        orders_count = orders_count or 0
        items_sold = int(items_sold or 0)
        revenue = int(revenue or 0)

        # Активные товары
        query2 = f"""
            SELECT COUNT(*)
            FROM offers
            WHERE store_id IN ({placeholders})
            AND status = 'active'
        """
        cursor.execute(query2, tuple(store_ids))
        active_offers = cursor.fetchone()[0]

        # ТОП товар
        query3 = f"""
            SELECT o.title, COUNT(*) as cnt
            FROM bookings b
            JOIN offers o ON b.offer_id = o.offer_id
            WHERE o.store_id IN ({placeholders})
            AND DATE(b.created_at) = %s
            AND b.status != 'cancelled'
            GROUP BY o.title
            ORDER BY cnt DESC
            LIMIT 1
        """
        cursor.execute(query3, (*store_ids, today))

        top_item = cursor.fetchone()
        if top_item:
            top_item_label = "Top mahsulot" if lang == "uz" else "Топ товар"
            orders_label = "buyurtma" if lang == "uz" else "заказов"
            top_item_text = f"\n{top_item_label}: {top_item[0]} ({top_item[1]} {orders_label})"
        else:
            top_item_text = ""

    # Localized compact summary (RU / UZ)
    if lang == "uz":
        currency = "so'm"
        text = (
            "<b>Bugungi statistika</b>\n\n"
            f"Tushum: {revenue:,} {currency}\n"
            f"Sotilgan mahsulotlar: {items_sold} ta\n"
            f"Buyurtmalar: {orders_count}\n"
            f"Faol mahsulotlar: {active_offers}{top_item_text}\n\n"
            f"Yangilandi: {datetime.now().strftime('%H:%M')}"
        )
    else:
        currency = "сум"
        text = (
            "<b>Статистика за сегодня</b>\n\n"
            f"Выручка: {revenue:,} {currency}\n"
            f"Товаров продано: {items_sold} шт\n"
            f"Заказов: {orders_count}\n"
            f"Активных товаров: {active_offers}{top_item_text}\n\n"
            f"Обновлено: {datetime.now().strftime('%H:%M')}"
        )

    await message.answer(text, parse_mode="HTML")
