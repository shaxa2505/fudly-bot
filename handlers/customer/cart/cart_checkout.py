"""
Cart checkout and payment handlers.

Extracted from cart/router.py for maintainability.
Handles: pickup confirmation, delivery confirmation, address, payment methods.
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from aiogram import F, Router, types
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder

from handlers.common.utils import html_escape as _esc

if TYPE_CHECKING:
    from aiogram import Bot

logger = logging.getLogger(__name__)

# Will be initialized from main router
router = Router(name="cart_checkout")
db = None
bot: Bot | None = None

# Import cart storage
# Import FSM states
from handlers.customer.orders.delivery import OrderDelivery

from .storage import cart_storage


def init_checkout(database, bot_instance: Bot) -> None:
    """Initialize checkout handlers with database and bot instance."""
    global db, bot
    db = database
    bot = bot_instance


# ===================== PICKUP CONFIRMATION =====================


@router.callback_query(F.data == "cart_confirm_pickup")
async def cart_confirm_pickup(callback: types.CallbackQuery) -> None:
    """Confirm pickup for cart - create ONE booking with all items."""
    if not db or not callback.message:
        await callback.answer()
        return

    user_id = callback.from_user.id
    lang = db.get_user_language(user_id)

    items = cart_storage.get_cart(user_id)
    if not items:
        await callback.answer("Корзина пуста" if lang == "ru" else "Savat bo'sh", show_alert=True)
        return

    store_id = items[0].store_id

    # Prepare cart_items for database
    cart_items_data = [
        {
            "offer_id": item.offer_id,
            "quantity": item.quantity,
            "price": item.price,
            "title": item.title,
            "unit": item.unit,
        }
        for item in items
    ]

    # Create ONE booking with all items
    ok, booking_id, booking_code, error_reason = db.create_cart_booking_atomic(
        user_id=user_id,
        store_id=store_id,
        cart_items=cart_items_data,
        pickup_time=None,
    )

    if not ok:
        error_text = (
            "❌ Не удалось создать бронирование" if lang == "ru" else "❌ Bron yaratib bo'lmadi"
        )
        if error_reason and "insufficient_stock" in error_reason:
            error_text = (
                "❌ Недостаточно товара на складе"
                if lang == "ru"
                else "❌ Omborda yetarli mahsulot yo'q"
            )
        elif error_reason and "booking_limit" in error_reason:
            error_text = (
                "❌ Достигнут лимит активных бронирований"
                if lang == "ru"
                else "❌ Faol bronlar limiti tugadi"
            )

        await callback.answer(error_text, show_alert=True)
        return

    # Clear cart after successful booking
    cart_storage.clear_cart(user_id)

    # Build success message
    currency = "so'm" if lang == "uz" else "сум"
    lines = [f"✅ <b>{'Bron yaratildi!' if lang == 'uz' else 'Бронирование создано!'}</b>\n"]
    lines.append(
        f"📋 {'Bron kodi' if lang == 'uz' else 'Код бронирования'}: <b>{booking_code}</b>\n"
    )
    lines.append(f"🏪 {_esc(items[0].store_name)}")
    lines.append(f"📍 {_esc(items[0].store_address)}\n")
    lines.append(f"<b>{'Mahsulotlar' if lang == 'uz' else 'Товары'}:</b>")

    for item in items:
        subtotal = int(item.price * item.quantity)
        lines.append(f"• {_esc(item.title)} × {item.quantity} = {subtotal:,} {currency}")

    total = int(sum(item.price * item.quantity for item in items))
    lines.append(f"\n💵 <b>{'JAMI' if lang == 'uz' else 'ИТОГО'}: {total:,} {currency}</b>")

    text = "\n".join(lines)

    # Send/edit customer notification and save message_id for live editing
    customer_message_id = None
    try:
        await callback.message.edit_text(text, parse_mode="HTML")
        customer_message_id = callback.message.message_id
    except Exception:
        sent_msg = await callback.message.answer(text, parse_mode="HTML")
        customer_message_id = sent_msg.message_id

    # Save message_id for live status updates
    if customer_message_id and booking_id and hasattr(db, "set_booking_customer_message_id"):
        try:
            db.set_booking_customer_message_id(booking_id, customer_message_id)
            logger.info(
                f"Saved customer_message_id={customer_message_id} for cart booking #{booking_id}"
            )
        except Exception as e:
            logger.warning(f"Failed to save customer_message_id: {e}")

    # Notify partner - send ONE notification with all items (UNIFIED format)
    try:
        store = db.get_store(store_id)
        if store:
            owner_id = store.get("owner_id") if isinstance(store, dict) else store[1]

            # Get customer info for unified notification
            customer = db.get_user(user_id) if hasattr(db, "get_user") else None
            customer_name = callback.from_user.first_name or "Клиент"
            customer_phone = "Не указан"
            customer_username = None
            if customer:
                if isinstance(customer, dict):
                    customer_phone = customer.get("phone") or "Не указан"
                    customer_username = customer.get("username")
                else:
                    customer_phone = getattr(customer, "phone", None) or "Не указан"
                    customer_username = getattr(customer, "username", None)

            contact_info = f"@{customer_username}" if customer_username else customer_phone

            # Build UNIFIED partner notification (same format as tez buyurtma)
            if lang == "uz":
                partner_lines = [
                    "🔔 <b>YANGI BRON!</b>",
                    "━━━━━━━━━━━━━━━━━━",
                    "",
                    f"🎫 Kod: <b>{booking_code}</b>",
                    "🏪 O'zi olib ketadi",
                    "",
                    "👤 <b>Xaridor:</b>",
                    f"   Ism: {_esc(customer_name)}",
                    f"   📱 <code>{_esc(customer_phone)}</code>",
                    f"   💬 {_esc(contact_info)}",
                    "",
                    "<b>Mahsulotlar:</b>",
                ]
            else:
                partner_lines = [
                    "🔔 <b>НОВАЯ БРОНЬ!</b>",
                    "━━━━━━━━━━━━━━━━━━",
                    "",
                    f"🎫 Код: <b>{booking_code}</b>",
                    "🏪 Самовывоз",
                    "",
                    "👤 <b>Покупатель:</b>",
                    f"   Имя: {_esc(customer_name)}",
                    f"   📱 <code>{_esc(customer_phone)}</code>",
                    f"   💬 {_esc(contact_info)}",
                    "",
                    "<b>Товары:</b>",
                ]

            for item in items:
                subtotal = int(item.price * item.quantity)
                partner_lines.append(
                    f"• {_esc(item.title)} × {item.quantity} = {subtotal:,} {currency}"
                )

            partner_lines.extend(
                [
                    "",
                    "━━━━━━━━━━━━━━━━━━",
                    f"💰 <b>{'JAMI' if lang == 'uz' else 'ИТОГО'}: {total:,} {currency}</b>",
                    "━━━━━━━━━━━━━━━━━━",
                ]
            )

            partner_text = "\n".join(partner_lines)

            # One button to confirm/reject entire cart booking
            # Use explicit booking_ prefix since this is pickup BOOKING
            kb = InlineKeyboardBuilder()
            kb.button(
                text="✅ Tasdiqlash" if lang == "uz" else "✅ Подтвердить",
                callback_data=f"booking_confirm_{booking_id}",
            )
            kb.button(
                text="❌ Rad etish" if lang == "uz" else "❌ Отклонить",
                callback_data=f"booking_reject_{booking_id}",
            )
            kb.adjust(2)

            await callback.bot.send_message(
                owner_id, partner_text, parse_mode="HTML", reply_markup=kb.as_markup()
            )
            logger.info(
                f"🛒 Sent cart booking notification to partner {owner_id} for booking {booking_id}"
            )
    except Exception as e:
        logger.error(f"Failed to notify partner: {e}")

    await callback.answer("✅")


# ===================== DELIVERY CONFIRMATION =====================


@router.callback_query(F.data == "cart_confirm_delivery")
async def cart_confirm_delivery(callback: types.CallbackQuery, state: FSMContext) -> None:
    """Start delivery flow for cart - with min order check."""
    if not db or not callback.message:
        await callback.answer()
        return

    user_id = callback.from_user.id
    lang = db.get_user_language(user_id)

    items = cart_storage.get_cart(user_id)
    if not items:
        await callback.answer("Корзина пуста" if lang == "ru" else "Savat bo'sh", show_alert=True)
        return

    store_id = items[0].store_id
    delivery_price = items[0].delivery_price

    # Calculate total
    total = int(sum(item.price * item.quantity for item in items))

    # CHECK MIN_ORDER_AMOUNT before allowing delivery
    store = db.get_store(store_id)
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

    # Save cart to state (convert CartItem objects to dicts for JSON serialization)
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
        is_cart_order=True,  # Flag to identify cart orders
    )

    await state.set_state(OrderDelivery.address)

    text = "📍 Введите адрес доставки:" if lang == "ru" else "📍 Yetkazish manzilini kiriting:"

    try:
        await callback.message.edit_text(text, parse_mode="HTML")
    except Exception:
        await callback.message.answer(text, parse_mode="HTML")

    await callback.answer()


@router.message(OrderDelivery.address)
async def cart_process_delivery_address(message: types.Message, state: FSMContext) -> None:
    """Process delivery address for cart - same flow as regular orders."""
    if not db or not message.from_user or not message.text:
        return

    user_id = message.from_user.id
    lang = db.get_user_language(user_id)
    delivery_address = message.text.strip()

    data = await state.get_data()
    is_cart_order = data.get("is_cart_order", False)

    # Only handle cart orders in this handler
    if not is_cart_order:
        return

    cart_items_stored = data.get("cart_items", [])
    store_id = data.get("store_id")
    delivery_price = data.get("delivery_price", 0)

    if not cart_items_stored or not store_id:
        await message.answer(
            "❌ Данные корзины потеряны" if lang == "ru" else "❌ Savat ma'lumotlari yo'qoldi"
        )
        await state.clear()
        return

    # Validate address length
    if len(delivery_address) < 10:
        msg = "❌ Manzil juda qisqa" if lang == "uz" else "❌ Адрес слишком короткий"
        await message.answer(msg)
        return

    # Save address
    await state.update_data(address=delivery_address)

    # Save as last address for user
    try:
        db.save_delivery_address(user_id, delivery_address)
    except Exception as e:
        logger.warning(f"Could not save address: {e}")

    await state.set_state(OrderDelivery.payment_method_select)

    # Build payment selection message
    currency = "so'm" if lang == "uz" else "сум"
    total = sum(item["price"] * item["quantity"] for item in cart_items_stored)
    total_with_delivery = total + delivery_price

    lines = []
    lines.append(f"<b>{'Mahsulotlar' if lang == 'uz' else 'Товары'}:</b>")
    for item in cart_items_stored:
        subtotal = item["price"] * item["quantity"]
        lines.append(f"• {_esc(item['title'])} × {item['quantity']} = {subtotal:,} {currency}")

    lines.append(
        f"\n🚚 {'Yetkazish' if lang == 'uz' else 'Доставка'}: {delivery_price:,} {currency}"
    )
    lines.append(
        f"💵 <b>{'JAMI' if lang == 'uz' else 'ИТОГО'}: {total_with_delivery:,} {currency}</b>\n"
    )
    lines.append(f"📍 {'Manzil' if lang == 'uz' else 'Адрес'}: {_esc(delivery_address)}\n")
    payment_prompt = "To'lov usulini tanlang:" if lang == "uz" else "Выберите способ оплаты:"
    lines.append(payment_prompt)

    text = "\n".join(lines)

    # Payment buttons - same as regular orders
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
        text="🔙 Ortga" if lang == "uz" else "🔙 Назад",
        callback_data="cart_back_to_address",
    )
    kb.adjust(2, 1)

    await message.answer(text, parse_mode="HTML", reply_markup=kb.as_markup())


# ===================== CART PAYMENT HANDLERS =====================


@router.callback_query(F.data.startswith("cart_pay_click_"))
async def cart_pay_click(callback: types.CallbackQuery, state: FSMContext) -> None:
    """Process Click payment for cart."""
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

    if not cart_items_stored or not store_id:
        await callback.answer("❌ Ошибка" if lang == "ru" else "❌ Xatolik", show_alert=True)
        return

    # Prepare cart_items for database
    cart_items_data = [
        {
            "offer_id": item["offer_id"],
            "quantity": item["quantity"],
            "price": item["price"],
            "title": item["title"],
            "unit": item["unit"],
        }
        for item in cart_items_stored
    ]

    # Create ONE order with all items
    ok, order_id, pickup_code, error_reason = db.create_cart_order_atomic(
        user_id=user_id,
        store_id=store_id,
        cart_items=cart_items_data,
        delivery_address=address,
        delivery_price=delivery_price,
        payment_method="click",
    )

    if not ok:
        error_text = (
            "❌ Не удалось создать заказ" if lang == "ru" else "❌ Buyurtma yaratib bo'lmadi"
        )
        await callback.answer(error_text, show_alert=True)
        return

    # Clear cart
    cart_storage.clear_cart(user_id)

    # Send Click invoice
    from handlers.customer.payments import send_payment_invoice_for_booking

    try:
        await callback.message.delete()

        total = sum(item["price"] * item["quantity"] for item in cart_items_stored)
        # Use first item title + " и др." if multiple
        title_text = cart_items_stored[0]["title"]
        if len(cart_items_stored) > 1:
            title_text += " и др."

        invoice_msg = await send_payment_invoice_for_booking(
            user_id=user_id,
            booking_id=order_id,
            offer_title=title_text,
            quantity=1,  # Already in total
            unit_price=total,
            delivery_cost=delivery_price,
        )

        if invoice_msg:
            logger.info(f"✅ Click invoice sent for cart order {order_id}")
            await state.clear()
        else:
            # Fallback to card
            await _cart_switch_to_card_payment(callback.message, state, data, order_id, lang)
    except Exception as e:
        logger.error(f"Click invoice error for cart: {e}")
        await _cart_switch_to_card_payment(callback.message, state, data, order_id, lang)

    await callback.answer()


async def _cart_switch_to_card_payment(message, state, data, order_id, lang):
    """Switch to card payment when Click fails for cart."""
    msg = (
        "⚠️ Click ishlamayapti. Karta orqali to'lang."
        if lang == "uz"
        else "⚠️ Click недоступен. Оплатите картой."
    )
    await message.answer(msg)

    await state.update_data(order_id=order_id, payment_method="card")
    await state.set_state(OrderDelivery.payment_proof)
    await _cart_show_card_payment_details(message, state, lang)


@router.callback_query(F.data.startswith("cart_pay_card_"))
async def cart_pay_card(callback: types.CallbackQuery, state: FSMContext) -> None:
    """Process card payment for cart - show card details."""
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

    if not cart_items_stored or not store_id:
        await callback.answer("❌ Ошибка" if lang == "ru" else "❌ Xatolik", show_alert=True)
        return

    # Prepare cart_items for database
    cart_items_data = [
        {
            "offer_id": item["offer_id"],
            "quantity": item["quantity"],
            "price": item["price"],
            "title": item["title"],
            "unit": item["unit"],
        }
        for item in cart_items_stored
    ]

    # Create ONE order with all items
    ok, order_id, pickup_code, error_reason = db.create_cart_order_atomic(
        user_id=user_id,
        store_id=store_id,
        cart_items=cart_items_data,
        delivery_address=address,
        delivery_price=delivery_price,
        payment_method="card",
    )

    if not ok:
        error_text = (
            "❌ Не удалось создать заказ" if lang == "ru" else "❌ Buyurtma yaratib bo'lmadi"
        )
        await callback.answer(error_text, show_alert=True)
        return

    # Clear cart
    cart_storage.clear_cart(user_id)

    await state.update_data(order_id=order_id, payment_method="card")
    await state.set_state(OrderDelivery.payment_proof)

    await callback.message.delete()
    await _cart_show_card_payment_details(callback.message, state, lang)
    await callback.answer()


async def _cart_show_card_payment_details(
    message: types.Message, state: FSMContext, lang: str
) -> None:
    """Show card payment details for cart order."""
    data = await state.get_data()
    store_id = data.get("store_id")
    cart_items_stored = data.get("cart_items", [])
    delivery_price = data.get("delivery_price", 0)

    # Get payment card
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
        payment_card = {
            "card_number": "8600 1234 5678 9012",
            "card_holder": "FUDLY",
        }

    # Extract card details
    if isinstance(payment_card, dict):
        card_number = payment_card.get("card_number", "")
        card_holder = payment_card.get("card_holder", "—")
    elif isinstance(payment_card, (tuple, list)) and len(payment_card) > 1:
        card_number = payment_card[1]
        card_holder = payment_card[2] if len(payment_card) > 2 else "—"
    else:
        card_number = str(payment_card)
        card_holder = "—"

    # Calculate total
    total = sum(item["price"] * item["quantity"] for item in cart_items_stored)
    total_with_delivery = total + delivery_price

    currency = "so'm" if lang == "uz" else "сум"

    # Compact payment message
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

    # Cancel button
    kb = InlineKeyboardBuilder()
    cancel_text = "❌ Bekor" if lang == "uz" else "❌ Отмена"
    kb.button(text=cancel_text, callback_data="cart_cancel_payment")

    await message.answer(text, parse_mode="HTML", reply_markup=kb.as_markup())


class IsCartOrderFilter:
    """Filter that checks if current FSM state data has is_cart_order=True."""

    async def __call__(self, message: types.Message, state: FSMContext) -> bool:
        data = await state.get_data()
        return data.get("is_cart_order", False)


@router.message(OrderDelivery.payment_proof, F.photo, IsCartOrderFilter())
async def cart_payment_proof(message: types.Message, state: FSMContext) -> None:
    """Process payment screenshot for cart order."""
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
        msg = "❌ Ma'lumotlar yo'qoldi" if lang == "uz" else "❌ Данные потеряны"
        await message.answer(msg)
        await state.clear()
        return

    photo_id = message.photo[-1].file_id

    # Update payment status
    db.update_payment_status(order_id, "pending", photo_id)

    await state.clear()

    # Get store info
    store = db.get_store(store_id)
    from handlers.bookings.utils import get_store_field

    store_name = get_store_field(store, "name", "Магазин")
    owner_id = get_store_field(store, "owner_id")

    customer = db.get_user_model(user_id)
    customer_phone = customer.phone if customer else "—"

    total = sum(item["price"] * item["quantity"] for item in cart_items_stored)
    total_with_delivery = total + delivery_price
    currency = "so'm" if lang == "uz" else "сум"

    # Notify ADMIN
    from bot import ADMIN_ID

    if ADMIN_ID > 0:
        kb = InlineKeyboardBuilder()
        kb.button(text="✅ Tasdiqlash", callback_data=f"admin_confirm_payment_{order_id}")
        kb.button(text="❌ Rad etish", callback_data=f"admin_reject_payment_{order_id}")
        kb.adjust(2)

        # Build items list for admin
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
        except Exception as e:
            logger.error(f"Failed to notify admin: {e}")

    # Confirm to customer
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

    from app.keyboards import main_menu_customer

    # IMPORTANT: Don't use reply_markup here! Messages with ReplyKeyboard can't be edited later.
    sent_msg = await message.answer(confirm_text, parse_mode="HTML")

    # Save message_id for live status updates
    if sent_msg and order_id and hasattr(db, "set_order_customer_message_id"):
        try:
            db.set_order_customer_message_id(order_id, sent_msg.message_id)
            logger.info(
                f"Saved customer_message_id={sent_msg.message_id} for cart order #{order_id}"
            )
        except Exception as e:
            logger.warning(f"Failed to save customer_message_id: {e}")


@router.callback_query(F.data == "cart_cancel_payment")
async def cart_cancel_payment(callback: types.CallbackQuery, state: FSMContext) -> None:
    """Cancel payment and return to cart."""
    if not db or not callback.message:
        await callback.answer()
        return

    user_id = callback.from_user.id
    lang = db.get_user_language(user_id)

    await state.clear()

    msg = "❌ Buyurtma bekor qilindi" if lang == "uz" else "❌ Заказ отменён"

    from app.keyboards import main_menu_customer

    await callback.message.answer(msg, reply_markup=main_menu_customer(lang))
    await callback.answer()


@router.callback_query(F.data == "cart_back_to_address")
async def cart_back_to_address(callback: types.CallbackQuery, state: FSMContext) -> None:
    """Go back to address input."""
    if not db or not callback.message:
        await callback.answer()
        return

    user_id = callback.from_user.id
    lang = db.get_user_language(user_id)

    await state.set_state(OrderDelivery.address)

    text = "📍 Введите адрес доставки:" if lang == "ru" else "📍 Yetkazish manzilini kiriting:"

    try:
        await callback.message.edit_text(text, parse_mode="HTML")
    except Exception:
        await callback.message.answer(text, parse_mode="HTML")

    await callback.answer()
