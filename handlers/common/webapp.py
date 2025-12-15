"""
Mini App (WebApp) handlers for Telegram.
"""
from __future__ import annotations

import logging
import os
from typing import Any

from aiogram import F, Router, types
from aiogram.types import InlineKeyboardMarkup, WebAppInfo
from aiogram.utils.keyboard import InlineKeyboardBuilder

logger = logging.getLogger(__name__)

router = Router(name="webapp")

# URL вашего Mini App (из переменных окружения или дефолтный)
WEBAPP_URL = os.getenv("WEBAPP_URL", "https://fudly-webapp.vercel.app")
# Partner Panel на Railway (раздаётся вместе с API)
PARTNER_PANEL_URL = os.getenv("PARTNER_PANEL_URL", "https://fudly-bot-production.up.railway.app/partner-panel")


def get_partner_panel_url() -> str:
    """Get partner panel Mini App URL.

    Partner Panel is hosted on Vercel for reliability.
    Can be overridden via PARTNER_PANEL_URL environment variable.
    """
    return PARTNER_PANEL_URL


def webapp_keyboard(lang: str = "ru") -> InlineKeyboardMarkup:
    """Keyboard with Mini App button."""
    builder = InlineKeyboardBuilder()

    builder.button(
        text="🛒 Открыть магазин" if lang == "ru" else "🛒 Do'konni ochish",
        web_app=WebAppInfo(url=WEBAPP_URL),
    )

    return builder.as_markup()


def main_menu_with_webapp(lang: str = "ru") -> InlineKeyboardMarkup:
    """Main menu with Mini App button."""
    builder = InlineKeyboardBuilder()

    # Mini App button
    builder.button(
        text="🛍️ Каталог товаров" if lang == "ru" else "🛍️ Mahsulotlar katalogi",
        web_app=WebAppInfo(url=WEBAPP_URL),
    )

    # Other quick actions
    builder.button(
        text="🔥 Акции" if lang == "ru" else "🔥 Aksiyalar",
        callback_data="hot_offers",
    )
    builder.button(
        text="🏪 Магазины" if lang == "ru" else "🏪 Do'konlar",
        callback_data="establishments_list",
    )

    builder.adjust(1, 2)
    return builder.as_markup()


@router.message(F.text.in_(["🛍️ Каталог", "🛍️ Katalog", "📱 Mini App"]))
async def open_webapp_button(message: types.Message, db: Any) -> None:
    """Send Mini App button."""
    if not message.from_user:
        return

    user_id = message.from_user.id
    lang = db.get_user_language(user_id) if db else "ru"

    text = (
        "🛍️ <b>Откройте каталог товаров</b>\n\n"
        "Нажмите кнопку ниже, чтобы открыть удобный каталог "
        "со всеми акциями и скидками!"
        if lang == "ru"
        else "🛍️ <b>Mahsulotlar katalogini oching</b>\n\n"
        "Barcha aksiya va chegirmalar bilan qulay katalogni "
        "ochish uchun quyidagi tugmani bosing!"
    )

    await message.answer(text, parse_mode="HTML", reply_markup=webapp_keyboard(lang))


@router.callback_query(F.data == "open_webapp")
async def open_webapp_callback(callback: types.CallbackQuery, db: Any) -> None:
    """Handle open webapp callback."""
    if not callback.message or not callback.from_user:
        return

    user_id = callback.from_user.id
    lang = db.get_user_language(user_id) if db else "ru"

    await callback.message.answer(
        "👇 Нажмите кнопку чтобы открыть каталог"
        if lang == "ru"
        else "👇 Katalogni ochish uchun tugmani bosing",
        reply_markup=webapp_keyboard(lang),
    )
    await callback.answer()


@router.message(F.web_app_data)
async def handle_webapp_data(message: types.Message, db: Any) -> None:
    """
    Handle data received from Mini App.

    When user completes order in Mini App, we receive data here.
    """
    if not message.web_app_data or not message.from_user:
        return

    import json

    user_id = message.from_user.id
    lang = db.get_user_language(user_id) if db else "ru"

    try:
        data = json.loads(message.web_app_data.data)

        # Handle different actions from Mini App
        action = data.get("action")

        if action == "order":
            # User placed an order from Mini App
            order_items = data.get("items", [])
            total = data.get("total", 0)

            # Log order details
            logger.info(f"Order received: {len(order_items)} items, total: {total}")

            await message.answer(
                f"✅ Заказ получен! Сумма: {total} сум"
                if lang == "ru"
                else f"✅ Buyurtma qabul qilindi! Summa: {total} so'm"
            )

        elif action == "add_to_cart":
            cart_offer_id = data.get("offer_id")
            cart_quantity = data.get("quantity", 1)

            # Log cart addition
            logger.info(f"Add to cart: offer={cart_offer_id}, qty={cart_quantity}")

            await message.answer(
                "✅ Добавлено в корзину!" if lang == "ru" else "✅ Savatga qo'shildi!"
            )

    except json.JSONDecodeError:
        await message.answer("❌ Ошибка данных" if lang == "ru" else "❌ Ma'lumot xatosi")
