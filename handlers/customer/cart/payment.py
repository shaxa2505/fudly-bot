"""Payment handlers for cart orders (Click and card flows)."""
from __future__ import annotations

from typing import Any

from aiogram import F, Router, types
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.services.unified_order_service import OrderItem, OrderResult, get_unified_order_service
from handlers.common.states import OrderDelivery

from .common import db, bot, esc


class IsCartOrderFilter:
    """Filter that checks if current FSM state data has is_cart_order=True."""

    async def __call__(self, message: types.Message, state: FSMContext) -> bool:  # type: ignore[override]
        data = await state.get_data()
        return data.get("is_cart_order", False)


async def _cart_switch_to_card_payment(
    message: types.Message,
    state: FSMContext,
    data: dict[str, Any],
    order_id: int,
    lang: str,
) -> None:
    msg = (
        "⚠️ Click ishlamayapti. Karta orqali to'lang."
        if lang == "uz"
        else "⚠️ Click недоступен. Оплатите картой."
    )
    await message.answer(msg)

    await state.update_data(order_id=order_id, payment_method="card")
    await state.set_state(OrderDelivery.payment_proof)
    await _cart_show_card_payment_details(message, state, lang)


async def _cart_show_card_payment_details(
    message: types.Message, state: FSMContext, lang: str
) -> None:
    data = await state.get_data()
    store_id = data.get("store_id")
    cart_items_stored = data.get("cart_items", [])
    delivery_price = data.get("delivery_price", 0)

    payment_card = None
    try:
        payment_card = db.get_payment_card(store_id)
    except Exception:
        pass

    if not payment_card:
        try:
            payment_card = db.get_platform_payment_card()
        except Exception:
            pass

    if not payment_card:
        payment_card = {"card_number": "8600 1234 5678 9012", "card_holder": "FUDLY"}

    if isinstance(payment_card, dict):
        card_number = payment_card.get("card_number", "")
        card_holder = payment_card.get("card_holder", "—")
    elif isinstance(payment_card, (tuple, list)) and len(payment_card) > 1:
        card_number = payment_card[1]
        card_holder = payment_card[2] if len(payment_card) > 2 else "—"
    else:
        card_number = str(payment_card)
        card_holder = "—"

    total = sum(item["price"] * item["quantity"] for item in cart_items_stored)
    total_with_delivery = total + delivery_price

    currency = "so'm" if lang == "uz" else "сум"

    if lang == "uz":
        text = (
            f"💳 <b>Kartaga o'tkazing:</b>\n\n"
            f"💰 Summa: <b>{total_with_delivery:,} {currency}</b>\n"
            f"💳 Karta: <code>{card_number}</code>\n"
            f"👤 {card_holder}\n\n"
            f"📸 <i>Chek skrinshotini yuboring</i>"
        )
    else:
        text = (
            f"💳 <b>Переведите на карту:</b>\n\n"
            f"💰 Сумма: <b>{total_with_delivery:,} {currency}</b>\n"
            f"💳 Карта: <code>{card_number}</code>\n"
            f"👤 {card_holder}\n\n"
            f"📸 <i>Отправьте скриншот чека</i>"
        )

    kb = InlineKeyboardBuilder()
    cancel_text = "❌ Bekor" if lang == "uz" else "❌ Отмена"
    kb.button(text=cancel_text, callback_data="cart_cancel_payment")

    await message.answer(text, parse_mode="HTML", reply_markup=kb.as_markup())


def register(router: Router) -> None:
    """Register payment-related handlers for cart orders."""

    @router.callback_query(F.data.startswith("cart_pay_click_"))
    async def cart_pay_click(callback: types.CallbackQuery, state: FSMContext) -> None:
        if not db or not callback.message:
            await callback.answer()
            return

        user_id = callback.from_user.id
        lang = db.get_user_language(user_id)

        data = await state.get_data()
        cart_items_stored = data.get("cart_items", [])
        store_id = data.get("store_id")
        delivery_price = data.get("delivery_price", 0)
        address = data.get("address", "")

        if not cart_items_stored or not store_id or not address:
            await callback.answer(
                "❌ Ошибка" if lang == "ru" else "❌ Xatolik", show_alert=True
            )
            return

        order_service = get_unified_order_service()
        if not order_service:
            await callback.answer(
                (
                    "❌ Система заказов недоступна"
                    if lang == "ru"
                    else "❌ Buyurtma xizmati mavjud emas"
                ),
                show_alert=True,
            )
            return

        order_items: list[OrderItem] = []
        for item in cart_items_stored:
            order_items.append(
                OrderItem(
                    offer_id=int(item["offer_id"]),
                    store_id=int(item["store_id"]),
                    title=str(item["title"]),
                    price=int(item["price"]),
                    original_price=int(item["price"]),
                    quantity=int(item["quantity"]),
                    store_name=str(item.get("store_name", "")),
                    store_address="",
                    delivery_price=int(delivery_price),
                )
            )

        try:
            result: OrderResult = await order_service.create_order(
                user_id=user_id,
                items=order_items,
                order_type="delivery",
                delivery_address=address,
                payment_method="click",
                notify_customer=True,
                notify_sellers=True,
            )
        except Exception as e:  # pragma: no cover - defensive logging
            from logging_config import logger

            logger.error(f"Failed to create unified delivery order from cart (click): {e}")
            await callback.answer(
                (
                    "❌ Не удалось создать заказ"
                    if lang == "ru"
                    else "❌ Buyurtma yaratib bo'lmadi"
                ),
                show_alert=True,
            )
            return

        if not result.success or not result.order_ids:
            msg = result.error_message or (
                "❌ Не удалось создать заказ"
                if lang == "ru"
                else "❌ Buyurtma yaratib bo'lmadi"
            )
            await callback.answer(msg, show_alert=True)
            return

        order_id = result.order_ids[0]

        from .storage import cart_storage

        cart_storage.clear_cart(user_id)

        from handlers.customer.payments import send_payment_invoice_for_booking

        try:
            await callback.message.delete()

            total = sum(item["price"] * item["quantity"] for item in cart_items_stored)
            title_text = cart_items_stored[0]["title"]
            if len(cart_items_stored) > 1:
                title_text += " и др."

            invoice_msg = await send_payment_invoice_for_booking(
                user_id=user_id,
                booking_id=order_id,
                offer_title=title_text,
                quantity=1,
                unit_price=total,
                delivery_cost=delivery_price,
            )

            if invoice_msg:
                from logging_config import logger

                logger.info(f"✅ Click invoice sent for cart order {order_id}")
                await state.clear()
            else:
                await _cart_switch_to_card_payment(
                    callback.message, state, data, order_id, lang
                )
        except Exception as e:  # pragma: no cover - defensive logging
            from logging_config import logger

            logger.error(f"Click invoice error for cart: {e}")
            await _cart_switch_to_card_payment(callback.message, state, data, order_id, lang)

        await callback.answer()

    @router.callback_query(F.data.startswith("cart_pay_card_"))
    async def cart_pay_card(callback: types.CallbackQuery, state: FSMContext) -> None:
        if not db or not callback.message:
            await callback.answer()
            return

        user_id = callback.from_user.id
        lang = db.get_user_language(user_id)

        data = await state.get_data()
        cart_items_stored = data.get("cart_items", [])
        store_id = data.get("store_id")
        delivery_price = data.get("delivery_price", 0)
        address = data.get("address", "")

        if not cart_items_stored or not store_id or not address:
            await callback.answer(
                "❌ Ошибка" if lang == "ru" else "❌ Xatolik", show_alert=True
            )
            return

        order_service = get_unified_order_service()
        if not order_service:
            await callback.answer(
                (
                    "❌ Система заказов недоступна"
                    if lang == "ru"
                    else "❌ Buyurtma xizmati mavjud emas"
                ),
                show_alert=True,
            )
            return

        order_items: list[OrderItem] = []
        for item in cart_items_stored:
            order_items.append(
                OrderItem(
                    offer_id=int(item["offer_id"]),
                    store_id=int(item["store_id"]),
                    title=str(item["title"]),
                    price=int(item["price"]),
                    original_price=int(item["price"]),
                    quantity=int(item["quantity"]),
                    store_name=str(item.get("store_name", "")),
                    store_address="",
                    delivery_price=int(delivery_price),
                )
            )

        try:
            result: OrderResult = await order_service.create_order(
                user_id=user_id,
                items=order_items,
                order_type="delivery",
                delivery_address=address,
                payment_method="card",
                notify_customer=True,
                notify_sellers=True,
            )
        except Exception as e:  # pragma: no cover - defensive logging
            from logging_config import logger

            logger.error(f"Failed to create unified delivery order from cart (card): {e}")
            await callback.answer(
                (
                    "❌ Не удалось создать заказ"
                    if lang == "ru"
                    else "❌ Buyurtma yaratib bo'lmadi"
                ),
                show_alert=True,
            )
            return

        if not result.success or not result.order_ids:
            msg = result.error_message or (
                "❌ Не удалось создать заказ"
                if lang == "ru"
                else "❌ Buyurtma yaratib bo'lmadi"
            )
            await callback.answer(msg, show_alert=True)
            return

        order_id = result.order_ids[0]

        from .storage import cart_storage

        cart_storage.clear_cart(user_id)

        await state.update_data(order_id=order_id, payment_method="card")
        await state.set_state(OrderDelivery.payment_proof)

        await callback.message.delete()
        await _cart_show_card_payment_details(callback.message, state, lang)
        await callback.answer()

    @router.message(OrderDelivery.payment_proof, F.photo, IsCartOrderFilter())
    async def cart_payment_proof(message: types.Message, state: FSMContext) -> None:
        if not db or not bot or not message.from_user:
            return

        user_id = message.from_user.id
        lang = db.get_user_language(user_id)
        data = await state.get_data()

        order_id = data.get("order_id")
        cart_items_stored = data.get("cart_items", [])
        store_id = data.get("store_id")
        delivery_price = data.get("delivery_price", 0)
        address = data.get("address", "")

        if not order_id or not cart_items_stored:
            msg = (
                "❌ Ma'lumotlar yo'qoldi" if lang == "uz" else "❌ Данные потеряны"
            )
            await message.answer(msg)
            await state.clear()
            return

        photo_id = message.photo[-1].file_id

        db.update_payment_status(order_id, "pending", photo_id)

        await state.clear()

        store = db.get_store(store_id)
        from handlers.bookings.utils import get_store_field

        store_name = get_store_field(store, "name", "Магазин")
        owner_id = get_store_field(store, "owner_id")

        customer = db.get_user_model(user_id)
        customer_phone = customer.phone if customer else "—"

        total = sum(item["price"] * item["quantity"] for item in cart_items_stored)
        total_with_delivery = total + delivery_price
        currency = "so'm" if lang == "uz" else "сум"

        from bot import ADMIN_ID

        if ADMIN_ID > 0:
            kb = InlineKeyboardBuilder()
            kb.button(
                text="✅ Tasdiqlash", callback_data=f"admin_confirm_payment_{order_id}"
            )
            kb.button(
                text="❌ Rad etish", callback_data=f"admin_reject_payment_{order_id}"
            )
            kb.adjust(2)

            items_text = "\n".join(
                [f"• {item['title']} × {item['quantity']}" for item in cart_items_stored]
            )

            try:
                await bot.send_photo(
                    chat_id=ADMIN_ID,
                    photo=photo_id,
                    caption=(
                        f"💳 <b>Yangi chek (Savat)!</b>\n\n"
                        f"📦 #{order_id} | {store_name}\n"
                        f"🛒 {items_text}\n"
                        f"💵 {total_with_delivery:,} {currency}\n"
                        f"📍 {address}\n"
                        f"👤 {message.from_user.first_name}\n"
                        f"📱 <code>{customer_phone}</code>"
                    ),
                    parse_mode="HTML",
                    reply_markup=kb.as_markup(),
                )
            except Exception as e:  # pragma: no cover - defensive logging
                from logging_config import logger

                logger.error(f"Failed to notify admin: {e}")

        if lang == "uz":
            confirm_text = (
                f"✅ <b>Buyurtma qabul qilindi!</b>\n\n"
                f"📦 #{order_id}\n"
                f"💵 {total_with_delivery:,} {currency}\n"
                f"📍 {address}\n\n"
                f"⏳ To'lov tasdiqlanishi kutilmoqda..."
            )
        else:
            confirm_text = (
                f"✅ <b>Заказ принят!</b>\n\n"
                f"📦 #{order_id}\n"
                f"💵 {total_with_delivery:,} {currency}\n"
                f"📍 {address}\n\n"
                f"⏳ Ожидаем подтверждения оплаты..."
            )

        sent_msg = await message.answer(confirm_text, parse_mode="HTML")

        if sent_msg and order_id and hasattr(db, "set_order_customer_message_id"):
            from logging_config import logger

            try:
                db.set_order_customer_message_id(order_id, sent_msg.message_id)
                logger.info(
                    "Saved customer_message_id=%s for cart order #%s",
                    sent_msg.message_id,
                    order_id,
                )
            except Exception as e:  # pragma: no cover - defensive logging
                logger.warning(f"Failed to save customer_message_id: {e}")

    @router.callback_query(F.data == "cart_cancel_payment")
    async def cart_cancel_payment(callback: types.CallbackQuery, state: FSMContext) -> None:
        if not callback.message or not callback.from_user:
            await callback.answer()
            return

        user_id = callback.from_user.id
        lang = db.get_user_language(user_id) if db else "ru"

        msg = (
            "❌ To'lov bekor qilindi" if lang == "uz" else "❌ Оплата отменена"
        )
        await callback.message.answer(msg)
        await state.clear()
        await callback.answer()
