"""Delivery flow for cart orders (address collection and validation)."""
from __future__ import annotations

from aiogram import F, Router, types
from aiogram.exceptions import SkipHandler
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder

from handlers.common.states import OrderDelivery

from .common import esc
from . import common


def register(router: Router) -> None:
    """Register delivery-related handlers for cart orders."""

    @router.callback_query(F.data == "cart_confirm_delivery")
    async def cart_confirm_delivery(callback: types.CallbackQuery, state: FSMContext) -> None:
        if not common.db or not callback.message:
            await callback.answer()
            return

        user_id = callback.from_user.id
        lang = common.db.get_user_language(user_id)

        from .storage import cart_storage

        items = cart_storage.get_cart(user_id)
        if not items:
            await callback.answer(
                "Корзина пуста" if lang == "ru" else "Savat bo'sh", show_alert=True
            )
            return

        store_id = items[0].store_id
        delivery_price = items[0].delivery_price

        total = int(sum(item.price * item.quantity for item in items))

        store = common.db.get_store(store_id)
        if store:
            from handlers.bookings.utils import get_store_field

            min_order_amount = get_store_field(store, "min_order_amount", 0)

            if min_order_amount > 0 and total < min_order_amount:
                currency = "so'm" if lang == "uz" else "сум"
                if lang == "uz":
                    msg = (
                        f"❌ Yetkazib berish uchun minimal buyurtma: {min_order_amount:,} {currency}\n"
                        f"Sizning buyurtmangiz: {total:,} {currency}\n\n"
                        f"Iltimos, ko'proq mahsulot qo'shing yoki olib ketishni tanlang."
                    )
                else:
                    msg = (
                        f"❌ Минимальная сумма для доставки: {min_order_amount:,} {currency}\n"
                        f"Ваш заказ: {total:,} {currency}\n\n"
                        f"Пожалуйста, добавьте ещё товары или выберите самовывоз."
                    )
                await callback.answer(msg, show_alert=True)
                return

        cart_items_dict = [
            {
                "offer_id": item.offer_id,
                "store_id": item.store_id,
                "title": item.title,
                "price": item.price,
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

        text = (
            "📍 Введите адрес доставки:"
            if lang == "ru"
            else "📍 Yetkazish manzilini kiriting:"
        )

        try:
            await callback.message.edit_text(text, parse_mode="HTML")
        except Exception:
            await callback.message.answer(text, parse_mode="HTML")

        await callback.answer()

    @router.message(OrderDelivery.address)
    async def cart_process_delivery_address(message: types.Message, state: FSMContext) -> None:
        if not common.db or not message.from_user or not message.text:
            return

        user_id = message.from_user.id
        lang = common.db.get_user_language(user_id)
        delivery_address = message.text.strip()

        data = await state.get_data()
        is_cart_order = data.get("is_cart_order", False)

        # If this is not a cart delivery flow, let other handlers process it
        if not is_cart_order:
            raise SkipHandler()

        cart_items_stored = data.get("cart_items", [])
        store_id = data.get("store_id")
        delivery_price = data.get("delivery_price", 0)

        if not cart_items_stored or not store_id:
            await message.answer(
                "❌ Данные корзины потеряны"
                if lang == "ru"
                else "❌ Savat ma'lumotlari yo'qoldi"
            )
            await state.clear()
            return

        if len(delivery_address) < 10:
            msg = "❌ Manzil juda qisqa" if lang == "uz" else "❌ Адрес слишком короткий"
            await message.answer(msg)
            return

        await state.update_data(address=delivery_address)

        try:
            common.db.save_delivery_address(user_id, delivery_address)
        except Exception as e:  # pragma: no cover - defensive logging
            from logging_config import logger

            logger.warning(f"Could not save address: {e}")

        await state.set_state(OrderDelivery.payment_method_select)

        currency = "so'm" if lang == "uz" else "сум"
        total = sum(item["price"] * item["quantity"] for item in cart_items_stored)
        total_with_delivery = total + delivery_price

        lines: list[str] = []
        lines.append(f"<b>{'Mahsulotlar' if lang == 'uz' else 'Товары'}:</b>")
        for item in cart_items_stored:
            subtotal = item["price"] * item["quantity"]
            lines.append(
                f"• {esc(item['title'])} × {item['quantity']} = {subtotal:,} {currency}"
            )

        lines.append(
            f"\n🚚 {'Yetkazish' if lang == 'uz' else 'Доставка'}: {delivery_price:,} {currency}"
        )
        lines.append(
            f"💵 <b>{'JAMI' if lang == 'uz' else 'ИТОГО'}: {total_with_delivery:,} {currency}</b>\n"
        )
        lines.append(
            f"📍 {'Manzil' if lang == 'uz' else 'Адрес'}: {esc(delivery_address)}\n"
        )
        payment_prompt = (
            "To'lov usulini tanlang:"
            if lang == "uz"
            else "Выберите способ оплаты:"
        )
        lines.append(payment_prompt)

        text = "\n".join(lines)

        kb = InlineKeyboardBuilder()
        kb.button(
            text="💳 Click" if lang == "uz" else "💳 Click",
            callback_data=f"cart_pay_click_{store_id}",
        )
        kb.button(
            text="💳 Karta" if lang == "uz" else "💳 Карта",
            callback_data=f"cart_pay_card_{store_id}",
        )
        kb.button(
            text="⬅️ Назад" if lang == "ru" else "⬅️ Orqaga",
            callback_data="cart_back_to_address",
        )
        kb.adjust(2, 1)

        await message.answer(text, parse_mode="HTML", reply_markup=kb.as_markup())

    @router.callback_query(F.data == "cart_back_to_address")
    async def cart_back_to_address(callback: types.CallbackQuery, state: FSMContext) -> None:
        if not common.db or not callback.message:
            await callback.answer()
            return

        user_id = callback.from_user.id
        lang = common.db.get_user_language(user_id)

        text = (
            "📍 Введите адрес доставки:"
            if lang == "ru"
            else "📍 Yetkazish manzilini kiriting:"
        )

        try:
            await callback.message.edit_text(text, parse_mode="HTML")
        except Exception:
            await callback.message.answer(text, parse_mode="HTML")

        await state.set_state(OrderDelivery.address)
        await callback.answer()
