"""Admin statistics handlers delegating to services."""
from __future__ import annotations

from aiogram import F, Router, types
from aiogram.filters import Command

from app.core.metrics import metrics
from app.keyboards import admin as admin_keyboards
from app.services.admin_service import AdminService
from app.templates import admin as admin_templates

router = Router(name="admin_stats")

# Module-level dependencies
admin_service: AdminService | None = None
logger = None


def setup(
    admin_svc: AdminService,
    log,
) -> None:
    """Setup admin stats with dependencies."""
    global admin_service, logger
    admin_service = admin_svc
    logger = log


@router.message(Command("stats"))
async def admin_stats_command(message: types.Message):
    """Full statistics dashboard for admin."""
    if not admin_service or not message.from_user:
        return
    if not admin_service.is_admin(message.from_user.id):
        await message.answer("⛔ Доступ запрещён")
        return

    try:
        # Get metrics summary
        summary = metrics.get_summary()

        # Get business stats
        user_stats = admin_service.get_user_stats()
        store_stats = admin_service.get_store_stats()
        offer_stats = admin_service.get_offer_stats()
        booking_stats = admin_service.get_booking_stats()

        # Calculate totals
        stores_total = store_stats.active + store_stats.pending + store_stats.rejected
        offers_total = offer_stats.active + offer_stats.inactive + offer_stats.deleted

        # Format dashboard
        text = (
            "📊 <b>Дашборд Fudly Bot</b>\n\n"
            "⏱ <b>Система:</b>\n"
            f"├ Uptime: {summary['uptime_hours']} ч\n"
            f"├ Запросов: {summary['total_requests']}\n"
            f"├ Ошибок: {summary['total_errors']}\n"
            f"├ Avg время: {summary['avg_request_duration_ms']} мс\n"
            f"└ P95 время: {summary['p95_request_duration_ms']} мс\n\n"
            "👥 <b>Пользователи:</b>\n"
            f"├ Всего: {user_stats.total}\n"
            f"├ Покупатели: {user_stats.customers}\n"
            f"├ Продавцы: {user_stats.sellers}\n"
            f"├ За неделю: {user_stats.week_users}\n"
            f"└ Сегодня: {user_stats.today_users}\n\n"
            "🏪 <b>Магазины:</b>\n"
            f"├ Всего: {stores_total}\n"
            f"├ Активных: {store_stats.active}\n"
            f"├ На модерации: {store_stats.pending}\n"
            f"└ Отклонённых: {store_stats.rejected}\n\n"
            "📦 <b>Товары:</b>\n"
            f"├ Всего: {offers_total}\n"
            f"├ Активных: {offer_stats.active}\n"
            f"├ Неактивных: {offer_stats.inactive}\n"
            f"└ Удалённых: {offer_stats.deleted}\n\n"
            "📋 <b>Бронирования:</b>\n"
            f"├ Всего: {booking_stats.total}\n"
            f"├ Ожидающих: {booking_stats.pending}\n"
            f"├ Завершённых: {booking_stats.completed}\n"
            f"├ Отменённых: {booking_stats.cancelled}\n"
            f"├ Сегодня: {booking_stats.today_bookings}\n"
            f"└ Выручка сегодня: {booking_stats.today_revenue:,.0f} сум\n\n"
            "🔗 <b>API Endpoints:</b>\n"
            "├ /health - проверка здоровья\n"
            "├ /metrics - Prometheus метрики\n"
            "└ /metrics/json - JSON метрики"
        )

        await message.answer(text, parse_mode="HTML")

    except Exception as exc:
        if logger:
            logger.error("Admin stats command error: %s", exc)
        await message.answer("❌ Ошибка получения статистики")


@router.message(F.text == "📊 Dashboard")
async def admin_dashboard_button(message: types.Message):
    """Handle Dashboard button in admin menu."""
    if not admin_service or not message.from_user:
        return
    if not admin_service.is_admin(message.from_user.id):
        await message.answer("⛔ Доступ запрещён")
        return

    try:
        # Get metrics summary
        summary = metrics.get_summary()

        # Get business stats
        user_stats = admin_service.get_user_stats()
        store_stats = admin_service.get_store_stats()
        offer_stats = admin_service.get_offer_stats()
        booking_stats = admin_service.get_booking_stats()

        # Calculate totals
        stores_total = store_stats.active + store_stats.pending + store_stats.rejected
        offers_total = offer_stats.active + offer_stats.inactive + offer_stats.deleted

        # Format dashboard
        text = (
            "📊 <b>Дашборд Fudly Bot</b>\n\n"
            "⏱ <b>Система:</b>\n"
            f"├ Uptime: {summary['uptime_hours']} ч\n"
            f"├ Запросов: {summary['total_requests']}\n"
            f"├ Ошибок: {summary['total_errors']}\n"
            f"├ Avg время: {summary['avg_request_duration_ms']} мс\n"
            f"└ P95 время: {summary['p95_request_duration_ms']} мс\n\n"
            "👥 <b>Пользователи:</b>\n"
            f"├ Всего: {user_stats.total}\n"
            f"├ Покупатели: {user_stats.customers}\n"
            f"├ Продавцы: {user_stats.sellers}\n"
            f"├ За неделю: {user_stats.week_users}\n"
            f"└ Сегодня: {user_stats.today_users}\n\n"
            "🏪 <b>Магазины:</b>\n"
            f"├ Всего: {stores_total}\n"
            f"├ Активных: {store_stats.active}\n"
            f"├ На модерации: {store_stats.pending}\n"
            f"└ Отклонённых: {store_stats.rejected}\n\n"
            "📦 <b>Товары:</b>\n"
            f"├ Всего: {offers_total}\n"
            f"├ Активных: {offer_stats.active}\n"
            f"├ Неактивных: {offer_stats.inactive}\n"
            f"└ Удалённых: {offer_stats.deleted}\n\n"
            "📋 <b>Бронирования:</b>\n"
            f"├ Всего: {booking_stats.total}\n"
            f"├ Ожидающих: {booking_stats.pending}\n"
            f"├ Завершённых: {booking_stats.completed}\n"
            f"├ Отменённых: {booking_stats.cancelled}\n"
            f"├ Сегодня: {booking_stats.today_bookings}\n"
            f"└ Выручка сегодня: {booking_stats.today_revenue:,.0f} сум\n\n"
            "🔗 <b>API Endpoints:</b>\n"
            "├ /health - проверка здоровья\n"
            "├ /metrics - Prometheus метрики\n"
            "└ /metrics/json - JSON метрики"
        )

        await message.answer(text, parse_mode="HTML")

    except Exception as exc:
        if logger:
            logger.error("Admin dashboard button error: %s", exc)
        await message.answer("❌ Ошибка получения дашборда")


@router.message(F.text == "👥 Пользователи")
async def admin_users(message: types.Message):
    if not admin_service or not admin_service.is_admin(message.from_user.id):
        return
    try:
        stats = admin_service.get_user_stats()
        text = admin_templates.render_user_stats(stats)
        keyboard = admin_keyboards.admin_users_keyboard()
        await message.answer(text, parse_mode="HTML", reply_markup=keyboard)
    except Exception as exc:
        if logger:
            logger.error("Admin users stats error: %s", exc)


@router.message(F.text == "🏪 Магазины")
async def admin_stores(message: types.Message):
    if not admin_service or not admin_service.is_admin(message.from_user.id):
        return
    try:
        stats = admin_service.get_store_stats()
        text = admin_templates.render_store_stats(stats)
        keyboard = admin_keyboards.admin_stores_keyboard(stats.pending)
        await message.answer(text, parse_mode="HTML", reply_markup=keyboard)
    except Exception as exc:
        if logger:
            logger.error("Admin stores stats error: %s", exc)


@router.message(F.text == "📦 Товары")
async def admin_offers(message: types.Message):
    if not admin_service or not admin_service.is_admin(message.from_user.id):
        return
    try:
        stats = admin_service.get_offer_stats()
        text = admin_templates.render_offer_stats(stats)
        keyboard = admin_keyboards.admin_offers_keyboard()
        await message.answer(text, parse_mode="HTML", reply_markup=keyboard)
    except Exception as exc:
        if logger:
            logger.error("Admin offers stats error: %s", exc)


@router.message(F.text == "📋 Бронирования")
async def admin_bookings(message: types.Message):
    if not admin_service or not admin_service.is_admin(message.from_user.id):
        return
    try:
        stats = admin_service.get_booking_stats()
        text = admin_templates.render_booking_stats(stats)
        keyboard = admin_keyboards.admin_bookings_keyboard()
        await message.answer(text, parse_mode="HTML", reply_markup=keyboard)
    except Exception as exc:
        if logger:
            logger.error("Admin bookings stats error: %s", exc)
