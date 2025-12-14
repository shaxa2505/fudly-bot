from __future__ import annotations
from aiogram import Router, types, F
from datetime import datetime, time
from zoneinfo import ZoneInfo
from decimal import Decimal

from app.services.stats import get_partner_stats, Period

router = Router()

# Module-level dependencies
db = None


def setup_dependencies(database, bot_instance):
    """Setup dependencies for seller stats handler."""
    global db
    db = database


def _get_today_period(tz: str) -> Period:
    now = datetime.now(ZoneInfo(tz))
    start = datetime.combine(now.date(), time.min, tzinfo=ZoneInfo(tz))
    end = now
    return Period(start=start, end=end, tz=tz)


def _format_money(value: Decimal) -> str:
    return f"{value:,.0f}".replace(",", " ")


def _render_partner_stats_card(stats) -> str:
    t = stats.totals
    avg_ticket = t.avg_ticket if t.avg_ticket is not None else Decimal(0)
    return (
        "📊 СТАТИСТИКА СЕГОДНЯ\n"
        f"💰 Выручка: {_format_money(t.revenue)} сум\n"
        f"📦 Товаров продано: {t.items_sold} шт\n"
        f"🧾 Заказов: {t.orders}\n"
        f"📇 Активных товаров: {t.active_products}\n"
        f"🔹 Средний чек: {_format_money(avg_ticket)} сум\n"
        f"↩️ Возвраты: {_format_money(t.refunds_amount)} сум / {t.refunds_count}\n"
        f"\nОбновлено: {stats.period.end.strftime('%H:%M')}"
    )


@router.message(F.text == "📊 Сегодня")
async def partner_stats_today(message: types.Message):
    """Handle partner stats button: '📊 Сегодня'."""
    if not message.from_user or not db:
        return
    user_id = message.from_user.id
    # Use Asia/Tashkent as default TZ; TODO: fetch from user profile/city
    tz = "Asia/Tashkent"
    period = _get_today_period(tz)
    # Partner ID = user_id; store_id optional
    partner_id = user_id
    store_id = None
    stats = get_partner_stats(db=db, partner_id=partner_id, period=period, tz=tz, store_id=store_id)
    text = _render_partner_stats_card(stats)
    await message.answer(text)
