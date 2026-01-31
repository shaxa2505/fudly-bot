from __future__ import annotations

from aiogram import F, Router, types
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.core.order_math import calc_items_total, calc_total_price
from app.integrations.payment_service import get_payment_service
from app.services.unified_order_service import (
    OrderItem,
    get_unified_order_service,
)
from localization import get_text

from .common import esc
from . import common


def register(router: Router) -> None:
    """Register payment-related handlers for cart orders."""

    @router.callback_query(F.data == "cart_pay_click")
    async def cart_pay_click(callback: types.CallbackQuery, state: FSMContext) -> None:
        if not common.db or not callback.message:
            await callback.answer()
            return

        user_id = callback.from_user.id
        lang = common.db.get_user_language(user_id)

        data = await state.get_data()
        if data.get("cart_payment_in_progress"):
            await callback.answer(get_text(lang, "cart_confirm_in_progress"), show_alert=True)
            return
        await state.update_data(cart_payment_in_progress=True)

        cart_items_stored = data.get("cart_items", [])
        store_id = data.get("store_id")
        address = data.get("address", "")
        delivery_price = data.get("delivery_price", 0)

        if not cart_items_stored or not store_id or not address:
            await state.clear()
            await callback.answer(get_text(lang, "cart_payment_data_missing"), show_alert=True)
            return

        payment_service = get_payment_service()
        if hasattr(payment_service, "set_database"):
            payment_service.set_database(common.db)

        credentials = None
        try:
            credentials = payment_service.get_store_credentials(int(store_id), "click")
        except Exception:
            credentials = None

        if not credentials and not payment_service.click_enabled:
            await state.update_data(cart_payment_in_progress=False)
            await callback.answer(get_text(lang, "cart_payment_click_unavailable"), show_alert=True)
            return

        order_service = get_unified_order_service()
        if not order_service:
            await state.update_data(cart_payment_in_progress=False)
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
            await state.update_data(cart_payment_in_progress=False)
            await callback.answer(get_text(lang, "system_error"), show_alert=True)
            return

        if not result.success or not result.order_ids:
            await state.update_data(cart_payment_in_progress=False)
            await callback.answer(
                get_text(lang, "cart_payment_order_failed"),
                show_alert=True,
            )
            return

        order_id = result.order_ids[0]
        await state.update_data(order_id=order_id)
        order_total = None
        try:
            if hasattr(common.db, "get_order"):
                order_row = common.db.get_order(int(order_id))
                if order_row:
                    order_total = int(order_row.get("total_price") or 0)
        except Exception:
            order_total = None

        if not order_total:
            items_total = calc_items_total(cart_items_stored)
            order_total = calc_total_price(items_total, int(delivery_price or 0))

        return_url = None
        try:
            import os

            webapp_url = os.getenv("WEBAPP_URL", "").strip()
            if webapp_url:
                return_url = f"{webapp_url.rstrip('/')}/order/{order_id}/details"
        except Exception:
            return_url = None

        try:
            payment_url = payment_service.generate_click_url(
                order_id=int(order_id),
                amount=int(order_total),
                return_url=return_url,
                user_id=int(user_id),
                store_id=int(store_id),
            )
        except Exception as e:
            from logging_config import logger

            logger.error(f"Failed to generate Click link for cart order #{order_id}: {e}")
            try:
                await order_service.cancel_order(int(order_id), "order")
            except Exception:
                pass
            await state.update_data(cart_payment_in_progress=False)
            await callback.answer(get_text(lang, "cart_payment_click_unavailable"), show_alert=True)
            return

        kb = InlineKeyboardBuilder()
        kb.button(text=get_text(lang, "cart_delivery_payment_click"), url=payment_url)

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

        notify_text = get_text(lang, "cart_payment_click_prompt")
        try:
            await callback.message.answer(notify_text, reply_markup=kb.as_markup())
        except Exception:
            pass

        await callback.answer()

    @router.callback_query(F.data == "cart_back_to_payment")
    async def cart_back_to_payment(callback: types.CallbackQuery, state: FSMContext) -> None:
        """Go back to payment method selection for cart orders."""
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
        total = calc_items_total(cart_items_stored)
        total_with_delivery = calc_total_price(total, int(delivery_price or 0))

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
