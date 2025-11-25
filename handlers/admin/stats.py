"""Admin statistics handlers delegating to services."""
from __future__ import annotations

from aiogram import Router, F, types

from app.services.admin_service import AdminService
from app.templates import admin as admin_templates
from app.keyboards import admin as admin_keyboards

router = Router(name='admin_stats')

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
