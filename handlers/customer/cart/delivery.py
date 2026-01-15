from __future__ import annotations

from aiogram import F, Router, types
from aiogram.filters import BaseFilter
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder

from handlers.common.states import OrderDelivery
from localization import get_text

from .common import esc
from . import common


class IsCartOrder(BaseFilter):
    """Filter messages for which current FSM data indicates cart delivery flow."""

    async def __call__(self, message: types.Message, state: FSMContext) -> bool:  # type: ignore[override]
        data = await state.get_data()
        return bool(data.get("is_cart_order"))


def register(router: Router) -> None:
    """Register delivery-related handlers for cart orders."""

    @router.callback_query(F.data == "cart_confirm_delivery")
    async def cart_confirm_delivery(callback: types.CallbackQuery, state: FSMContext) -> None:
        if not common.db or not callback.message:
            await callback.answer()
            return

        user_id = callback.from_user.id
        lang = common.db.get_user_language(user_id)
        updates, changed = common.refresh_cart_items(user_id, lang)
        if updates:
            warning_text = get_text(lang, "cart_updated_notice") + "\n" + "\n".join(updates)
            await callback.message.answer(warning_text, parse_mode="HTML")
        if changed:
            from .view import show_cart

            await show_cart(callback, state, is_callback=True)
            await callback.answer()
            return

        from .storage import cart_storage

        items = cart_storage.get_cart(user_id)
        if not items:
            await callback.answer(get_text(lang, "cart_empty_alert"), show_alert=True)
            return

        store_id = items[0].store_id
        delivery_enabled = any(item.delivery_enabled for item in items)
        if not delivery_enabled:
            await callback.answer(get_text(lang, "cart_delivery_unavailable"), show_alert=True)
            return
        delivery_price = max(
            (item.delivery_price for item in items if item.delivery_enabled), default=0
        )

        total = int(sum(item.price * item.quantity for item in items))

        store = common.db.get_store(store_id)
        if store:
            from handlers.bookings.utils import get_store_field

            min_order_amount = get_store_field(store, "min_order_amount", 0)

            if min_order_amount > 0 and total < min_order_amount:
                currency = "so'm" if lang == "uz" else "сум"
                msg = get_text(
                    lang,
                    "cart_delivery_min_order",
                    min=f"{min_order_amount:,}",
                    total=f"{total:,}",
                    currency=currency,
                )
                await callback.answer(msg, show_alert=True)
                return

        cart_items_dict = [
            {
                "offer_id": item.offer_id,
                "store_id": item.store_id,
                "title": item.title,
                "price": item.price,
                "original_price": item.original_price,
                "quantity": item.quantity,
                "unit": item.unit,
                "store_name": item.store_name,
            }
            for item in items
        ]
        await state.update_data(
            cart_items=cart_items_dict,
            store_id=store_id,
            delivery_price=delivery_price,
            is_cart_order=True,
        )

        await state.set_state(OrderDelivery.address)

        text = get_text(lang, "cart_delivery_address_prompt")
        kb = InlineKeyboardBuilder()
        kb.button(text=get_text(lang, "cart_delivery_back_button"), callback_data="back_to_cart")

        try:
            await callback.message.edit_text(text, parse_mode="HTML", reply_markup=kb.as_markup())
        except Exception:
            await callback.message.answer(text, parse_mode="HTML", reply_markup=kb.as_markup())

        await callback.answer()

    @router.message(OrderDelivery.address, IsCartOrder())
    async def cart_process_delivery_address(message: types.Message, state: FSMContext) -> None:
        if not common.db or not message.from_user or not message.text:
            return

        user_id = message.from_user.id
        lang = common.db.get_user_language(user_id)
        delivery_address = message.text.strip()

        data = await state.get_data()

        cart_items_stored = data.get("cart_items", [])
        store_id = data.get("store_id")
        delivery_price = data.get("delivery_price", 0)

        if not cart_items_stored or not store_id:
            await message.answer(get_text(lang, "cart_delivery_data_lost"))
            await state.clear()
            return

        if len(delivery_address) < 10:
            await message.answer(get_text(lang, "cart_delivery_address_too_short"))
            return

        await state.update_data(address=delivery_address)

        await state.set_state(OrderDelivery.payment_method_select)

        currency = "so'm" if lang == "uz" else "сум"
        total = sum(item["price"] * item["quantity"] for item in cart_items_stored)
        total_with_delivery = total + delivery_price

        lines: list[str] = [f"<b>{get_text(lang, 'cart_delivery_products_title')}:</b>"]
        for item in cart_items_stored:
            subtotal = item['price'] * item['quantity']
            lines.append(f"- {esc(item['title'])} x {item['quantity']} = {subtotal:,} {currency}")

        lines.append("")
        lines.append(f"{get_text(lang, 'cart_delivery_label')}: {delivery_price:,} {currency}")
        lines.append(
            f"<b>{get_text(lang, 'cart_grand_total_label')}: {total_with_delivery:,} {currency}</b>"
        )
        lines.append("")
        lines.append(
            f"{get_text(lang, 'cart_delivery_address_label')}: {esc(delivery_address)}"
        )
        lines.append("")
        lines.append(get_text(lang, 'cart_delivery_payment_prompt'))

        text = "\n".join(lines)

        kb = InlineKeyboardBuilder()
        kb.button(
            text=get_text(lang, "cart_delivery_payment_card"),
            callback_data=f"cart_pay_card_{store_id}",
        )
        kb.button(
            text=get_text(lang, "cart_delivery_back_button"),
            callback_data="cart_back_to_address",
        )
        kb.adjust(1, 1)

        await message.answer(text, parse_mode="HTML", reply_markup=kb.as_markup())

    @router.callback_query(F.data == "cart_back_to_address")
    async def cart_back_to_address(callback: types.CallbackQuery, state: FSMContext) -> None:
        if not common.db or not callback.message:
            await callback.answer()
            return

        user_id = callback.from_user.id
        lang = common.db.get_user_language(user_id)

        text = get_text(lang, "cart_delivery_address_prompt")
        kb = InlineKeyboardBuilder()
        kb.button(text=get_text(lang, "cart_delivery_back_button"), callback_data="back_to_cart")

        try:
            await callback.message.edit_text(text, parse_mode="HTML", reply_markup=kb.as_markup())
        except Exception:
            await callback.message.answer(text, parse_mode="HTML", reply_markup=kb.as_markup())

        await state.set_state(OrderDelivery.address)
        await callback.answer()
