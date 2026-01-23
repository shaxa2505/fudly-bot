from __future__ import annotations

import os

from aiogram import F, Router, types
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.services.unified_order_service import (
    OrderItem,
    get_unified_order_service,
)
from localization import get_text

from .common import esc
from . import common


ENABLE_TELEGRAM_PAYMENTS = (
    os.getenv("ENABLE_TELEGRAM_PAYMENTS", "0").strip().lower() in {"1", "true", "yes"}
)


def register(router: Router) -> None:
    """Register payment-related handlers for cart orders."""

    @router.callback_query(F.data == "cart_pay_click")
    async def cart_pay_click(callback: types.CallbackQuery, state: FSMContext) -> None:
        if not common.db or not callback.message:
            await callback.answer()
            return

        # Import lazily to avoid circular imports
        from handlers.customer import payments as telegram_payments

        user_id = callback.from_user.id
        lang = common.db.get_user_language(user_id)

        if not ENABLE_TELEGRAM_PAYMENTS or not telegram_payments.PROVIDER_TOKEN:
            await callback.answer(get_text(lang, "cart_payment_click_unavailable"), show_alert=True)
            return

        data = await state.get_data()
        cart_items_stored = data.get("cart_items", [])
        store_id = data.get("store_id")
        address = data.get("address", "")
        delivery_price = data.get("delivery_price", 0)

        if not cart_items_stored or not store_id or not address:
            await state.clear()
            await callback.answer(get_text(lang, "cart_payment_data_missing"), show_alert=True)
            return

        order_service = get_unified_order_service()
        if not order_service:
            await callback.answer(get_text(lang, "system_error"), show_alert=True)
            return

        order_items: list[OrderItem] = []
        for item in cart_items_stored:
            order_items.append(
                OrderItem(
                    offer_id=int(item["offer_id"]),
                    store_id=int(item["store_id"]),
                    title=str(item["title"]),
                    price=int(item["price"]),
                    original_price=int(item.get("original_price") or item["price"]),
                    quantity=int(item["quantity"]),
                    store_name=str(item.get("store_name", "")),
                    store_address="",
                    photo=item.get("photo") or item.get("photo_id"),
                    delivery_price=int(delivery_price),
                )
            )

        try:
            result = await order_service.create_order(
                user_id=user_id,
                items=order_items,
                order_type="delivery",
                delivery_address=address,
                payment_method="click",
                notify_customer=False,
                notify_sellers=False,
            )
        except Exception as e:
            from logging_config import logger

            logger.error(f"Failed to create cart order for Click: {e}")
            await callback.answer(get_text(lang, "system_error"), show_alert=True)
            return

        if not result.success or not result.order_ids:
            await callback.answer(
                get_text(lang, "cart_payment_order_failed"),
                show_alert=True,
            )
            return

        order_id = result.order_ids[0]

        items_for_invoice = [
            {
                "title": item["title"],
                "price": int(item["price"]),
                "quantity": int(item["quantity"]),
            }
            for item in cart_items_stored
        ]

        store_name = str(cart_items_stored[0].get("store_name", ""))

        try:
            await telegram_payments.create_order_invoice(
                chat_id=user_id,
                order_id=int(order_id),
                items=items_for_invoice,
                delivery_cost=int(delivery_price),
                store_name=store_name,
            )
        except Exception as e:
            from logging_config import logger

            logger.error(f"Failed to send Telegram invoice for cart order #{order_id}: {e}")
            await callback.answer(get_text(lang, "system_error"), show_alert=True)
            return

        from .storage import cart_storage

        cart_storage.clear_cart(user_id)

        try:
            common.db.save_delivery_address(user_id, address)
        except Exception:
            pass

        try:
            await callback.message.edit_reply_markup(reply_markup=None)
        except Exception:
            pass

        await state.clear()

        notify_text = (
            "Счёт отправлен. Нажмите «Оплатить» в сообщении выше."
            if lang != "uz"
            else "Hisob yuborildi. Yuqoridagi xabarda «To'lash» tugmasini bosing."
        )
        try:
            await callback.message.answer(notify_text)
        except Exception:
            pass

        await callback.answer()

    @router.callback_query(F.data == "cart_back_to_payment")
    async def cart_back_to_payment(callback: types.CallbackQuery, state: FSMContext) -> None:
        """Go back from card details to payment method selection for cart orders."""
        if not common.db or not callback.message:
            await callback.answer()
            return

        user_id = callback.from_user.id
        lang = common.db.get_user_language(user_id)

        data = await state.get_data()
        cart_items_stored = data.get("cart_items", [])
        store_id = data.get("store_id")
        delivery_price = data.get("delivery_price", 0)
        address = data.get("address", "")

        if not cart_items_stored or not store_id or not address:
            await state.clear()
            await callback.answer(get_text(lang, "cart_payment_data_missing"), show_alert=True)
            return

        currency = "so'm" if lang == "uz" else "сум"
        total = sum(int(item["price"]) * int(item["quantity"]) for item in cart_items_stored)
        total_with_delivery = total + int(delivery_price)

        safe_address = esc(address)
        text = (
            f"<b>{get_text(lang, 'cart_payment_select_title')}</b>\n\n"
            f"{get_text(lang, 'cart_payment_amount_label')}: <b>{total_with_delivery:,} {currency}</b>\n"
            f"{get_text(lang, 'cart_delivery_address_label')}: {safe_address}"
        )

        kb = InlineKeyboardBuilder()
        kb.button(
            text=get_text(lang, "cart_delivery_payment_click"),
            callback_data="cart_pay_click",
        )
        kb.button(
            text=get_text(lang, "cart_delivery_back_button"),
            callback_data="cart_back_to_address",
        )
        kb.button(
            text=get_text(lang, "cart_payment_cancel_button"),
            callback_data="cart_cancel_payment",
        )
        kb.adjust(1, 2)

        try:
            await callback.message.edit_text(text, parse_mode="HTML", reply_markup=kb.as_markup())
        except Exception:
            await callback.message.answer(text, parse_mode="HTML", reply_markup=kb.as_markup())

        await callback.answer()

    @router.callback_query(F.data == "cart_cancel_payment")
    async def cart_cancel_payment(callback: types.CallbackQuery, state: FSMContext) -> None:
        if not callback.message or not callback.from_user:
            await callback.answer()
            return

        user_id = callback.from_user.id
        lang = common.db.get_user_language(user_id) if common.db else "ru"

        await callback.message.answer(get_text(lang, "cart_payment_canceled"))
        await state.clear()
        await callback.answer()
