"""Cart system - unified with single orders.

Simple cart that works exactly like single orders but with multiple items.
Creates ONE booking/order for all items in cart.
"""
from __future__ import annotations

import html
from typing import Any

from aiogram import F, Router, types
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.keyboards import main_menu_customer
from handlers.common.states import OrderDelivery
from localization import get_text

from .storage import CartItem, cart_storage

try:
    from logging_config import logger
except ImportError:
    import logging

    logger = logging.getLogger(__name__)


router = Router(name="cart")

# Module dependencies
db: Any = None
bot: Any = None


def setup_dependencies(database: Any, bot_instance: Any) -> None:
    """Setup module dependencies."""
    global db, bot
    db = database
    bot = bot_instance


def _esc(val: Any) -> str:
    """HTML-escape helper."""
    if val is None:
        return ""
    return html.escape(str(val))


# ===================== CART VIEW =====================


async def _show_cart_internal(
    event: types.Message | types.CallbackQuery, state: FSMContext, is_callback: bool = False
) -> None:
    """Internal cart display logic that handles both messages and callbacks."""
    if not db or not event.from_user:
        if is_callback and isinstance(event, types.CallbackQuery):
            await event.answer()
        return

    await state.clear()
    user_id = event.from_user.id
    lang = db.get_user_language(user_id)

    items = cart_storage.get_cart(user_id)

    if not items:
        empty_text = (
            "🛒 Корзина пуста\n\nДобавьте товары из каталога!"
            if lang == "ru"
            else "🛒 Savat bo'sh\n\nKatalogdan mahsulot qo'shing!"
        )
        kb = InlineKeyboardBuilder()
        kb.button(
            text="🔥 Горячие предложения" if lang == "ru" else "🔥 Issiq takliflar",
            callback_data="hot_offers",
        )

        if is_callback and isinstance(event, types.CallbackQuery):
            try:
                await event.message.edit_text(empty_text, reply_markup=kb.as_markup())
            except Exception:
                await event.message.answer(empty_text, reply_markup=kb.as_markup())
            await event.answer()
        else:
            await event.answer(empty_text, reply_markup=kb.as_markup())
        return

    # Build cart view
    currency = "so'm" if lang == "uz" else "сум"
    lines = [f"🛒 <b>{'Savat' if lang == 'uz' else 'Корзина'}</b>\n"]

    total = 0
    for i, item in enumerate(items, 1):
        subtotal = int(item.price * item.quantity)
        total += subtotal
        lines.append(f"\n<b>{i}. {_esc(item.title)}</b>")
        lines.append(f"   {item.quantity} × {int(item.price):,} = <b>{subtotal:,}</b> {currency}")
        lines.append(f"   🏪 {_esc(item.store_name)}")

    lines.append("\n" + "─" * 25)
    lines.append(f"💵 <b>{'JAMI' if lang == 'uz' else 'ИТОГО'}: {total:,} {currency}</b>")

    # Check delivery availability
    delivery_enabled = any(item.delivery_enabled for item in items)
    delivery_price = max(
        (item.delivery_price for item in items if item.delivery_enabled), default=0
    )

    if delivery_enabled:
        lines.append(
            f"\n🚚 {'Yetkazish' if lang == 'uz' else 'Доставка'}: +{delivery_price:,} {currency}"
        )

    text = "\n".join(lines)

    # Simplified cart keyboard - just item delete buttons + checkout options
    kb = InlineKeyboardBuilder()

    # Item delete buttons (one row per item)
    for i, item in enumerate(items, 1):
        title_short = item.title[:25] + "..." if len(item.title) > 25 else item.title
        kb.button(text=f"{i}. {title_short} ({item.quantity})", callback_data="cart_noop")
        kb.button(text="🗑", callback_data=f"cart_remove_{item.offer_id}")

    # Checkout options - directly on cart screen
    kb.button(
        text="🏪 Самовывоз" if lang == "ru" else "🏪 O'zim olaman",
        callback_data="cart_confirm_pickup",
    )
    if delivery_enabled:
        kb.button(
            text=f"🚚 Доставка (+{delivery_price:,})"
            if lang == "ru"
            else f"🚚 Yetkazish (+{delivery_price:,})",
            callback_data="cart_confirm_delivery",
        )

    # Clear cart button
    kb.button(
        text="🗑 Очистить" if lang == "ru" else "🗑 Tozalash",
        callback_data="cart_clear",
    )

    # Adjust: 2 buttons per item row + checkout buttons
    num_items = len(items)
    adjust_pattern = [2] * num_items  # 2 buttons per item row
    if delivery_enabled:
        adjust_pattern.extend([2, 1])  # pickup+delivery, then clear
    else:
        adjust_pattern.extend([1, 1])  # just pickup, then clear

    kb.adjust(*adjust_pattern)

    if is_callback and isinstance(event, types.CallbackQuery):
        try:
            await event.message.edit_text(text, parse_mode="HTML", reply_markup=kb.as_markup())
        except Exception:
            await event.message.answer(text, parse_mode="HTML", reply_markup=kb.as_markup())
        await event.answer()
    else:
        await event.answer(text, parse_mode="HTML", reply_markup=kb.as_markup())


@router.message(F.text.in_(["🛒 Корзина", "🛒 Savat"]))
async def show_cart(message: types.Message, state: FSMContext) -> None:
    """Show cart contents - main entry point from text message."""
    await _show_cart_internal(message, state, is_callback=False)


# ===================== CART ACTIONS =====================


@router.callback_query(F.data == "cart_clear")
async def cart_clear(callback: types.CallbackQuery) -> None:
    """Clear entire cart."""
    if not db or not callback.message:
        await callback.answer()
        return

    user_id = callback.from_user.id
    lang = db.get_user_language(user_id)

    cart_storage.clear_cart(user_id)

    text = "🗑 Корзина очищена" if lang == "ru" else "🗑 Savat tozalandi"

    try:
        await callback.message.edit_text(text, parse_mode="HTML")
    except Exception:
        pass

    await callback.answer()


@router.callback_query(F.data == "cart_checkout")
async def cart_checkout(callback: types.CallbackQuery, state: FSMContext) -> None:
    """Start checkout - show delivery/pickup choice (like single orders)."""
    if not db or not callback.message:
        await callback.answer()
        return

    user_id = callback.from_user.id
    lang = db.get_user_language(user_id)

    items = cart_storage.get_cart(user_id)
    if not items:
        await callback.answer("Корзина пуста" if lang == "ru" else "Savat bo'sh", show_alert=True)
        return

    # SMART NOTIFICATION: Check if any items are low in stock
    low_stock_warnings = []
    for item in items:
        # If item quantity is < 5 AND cart takes > 50% of available stock
        if item.max_quantity < 5 and item.quantity > (item.max_quantity * 0.5):
            low_stock_warnings.append(
                f"⚠️ {item.title}: осталось всего {item.max_quantity} {item.unit}"
                if lang == "ru"
                else f"⚠️ {item.title}: faqat {item.max_quantity} {item.unit} qoldi"
            )

    if low_stock_warnings:
        warning_text = "\n".join(low_stock_warnings)
        warning_text += "\n\n" + (
            "Товар заканчивается! Рекомендуем оформить заказ как можно скорее."
            if lang == "ru"
            else "Mahsulot tugayapti! Tezroq buyurtma berishni tavsiya qilamiz."
        )
        # Show warning but don't block checkout
        try:
            await callback.message.answer(warning_text, parse_mode="HTML")
        except Exception:
            pass

    # Check if user has phone
    user = db.get_user_model(user_id)
    if not user or not user.phone:
        from app.keyboards import phone_request_keyboard
        from handlers.common.states import Registration

        await callback.message.answer(
            "📱 Для оформления заказа укажите номер телефона"
            if lang == "ru"
            else "📱 Buyurtma berish uchun telefon raqamingizni kiriting",
            reply_markup=phone_request_keyboard(lang),
        )
        await state.update_data(pending_cart_checkout=True)
        await state.set_state(Registration.phone)
        await callback.answer()
        return

    # Check if all items from same store (for now)
    stores = {item.store_id for item in items}
    if len(stores) > 1:
        await callback.answer(
            "Можно оформить заказ только из одного магазина"
            if lang == "ru"
            else "Faqat bitta do'kondan buyurtma berish mumkin",
            show_alert=True,
        )
        return

    # Get store info
    store_id = items[0].store_id
    store = db.get_store(store_id)
    delivery_enabled = items[0].delivery_enabled
    delivery_price = items[0].delivery_price

    currency = "so'm" if lang == "uz" else "сум"
    total = int(sum(item.price * item.quantity for item in items))

    # Build checkout summary
    lines = [f"📋 <b>{'Buyurtma' if lang == 'uz' else 'Заказ'}</b>\n"]
    lines.append(f"🏪 {_esc(items[0].store_name)}\n")

    for item in items:
        subtotal = int(item.price * item.quantity)
        lines.append(f"• {_esc(item.title)} × {item.quantity} = {subtotal:,} {currency}")

    lines.append("\n" + "─" * 25)
    lines.append(f"💵 <b>{'Jami' if lang == 'uz' else 'Итого'}: {total:,} {currency}</b>")

    if delivery_enabled:
        lines.append(
            f"🚚 {'Yetkazish' if lang == 'uz' else 'Доставка'}: {delivery_price:,} {currency}"
        )

    text = "\n".join(lines)

    # Checkout keyboard
    kb = InlineKeyboardBuilder()

    if delivery_enabled:
        kb.button(
            text="🏪 Самовывоз" if lang == "ru" else "🏪 O'zim olib ketaman",
            callback_data="cart_confirm_pickup",
        )
        kb.button(
            text="🚚 Доставка" if lang == "ru" else "🚚 Yetkazish",
            callback_data="cart_confirm_delivery",
        )
        kb.adjust(2)
    else:
        kb.button(
            text="✅ Подтвердить" if lang == "ru" else "✅ Tasdiqlash",
            callback_data="cart_confirm_pickup",
        )

    kb.button(text="◀️ Назад" if lang == "ru" else "◀️ Orqaga", callback_data="back_to_cart")

    try:
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=kb.as_markup())
    except Exception:
        await callback.message.answer(text, parse_mode="HTML", reply_markup=kb.as_markup())

    await callback.answer()


@router.callback_query(F.data == "back_to_cart")
async def back_to_cart(callback: types.CallbackQuery, state: FSMContext) -> None:
    """Return to cart view."""
    if not callback.message or not callback.from_user:
        await callback.answer()
        return

    # Use _show_cart_internal directly with is_callback=True
    await _show_cart_internal(callback, state, is_callback=True)


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

    # Structured logging for cart order
    total_amount = (
        sum(item["price"] * item["quantity"] for item in cart_items_stored) + delivery_price
    )
    logger.info(
        f"ORDER_CREATED: id={order_id}, user={user_id}, type=delivery, "
        f"total={total_amount}, items={len(cart_items_stored)}, source=cart_card, pickup_code={pickup_code}"
    )

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
    # The keyboard is already shown to user, we just need an editable status message.
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


# ===================== BACK TO MENU =====================


@router.callback_query(F.data == "back_to_menu")
async def back_to_menu(callback: types.CallbackQuery, state: FSMContext) -> None:
    """Return to main menu."""
    if not db or not callback.message:
        await callback.answer()
        return

    await state.clear()  # Clear any ongoing state

    user_id = callback.from_user.id
    lang = db.get_user_language(user_id)

    cart_count = cart_storage.get_cart_count(user_id)

    text = "🏠 Главное меню" if lang == "ru" else "🏠 Asosiy menyu"

    await callback.message.answer(text, reply_markup=main_menu_customer(lang, cart_count))
    await callback.answer()


# ===================== CART CARD BUILDERS (simplified - only quantity, no delivery method) =====================


def build_cart_add_card_text(
    lang: str,
    title: str,
    price: float,
    quantity: int,
    store_name: str,
    max_qty: int,
    original_price: float = 0,
    description: str = "",
    expiry_date: str = "",
    store_address: str = "",
    unit: str = "шт",
) -> str:
    """Build simplified cart addition card text - only quantity selection."""
    text_parts = []

    # Title
    text_parts.append(f"🍱 <b>{title}</b>")
    if description:
        text_parts.append(f"<i>{description}</i>")

    text_parts.append("")

    # Price
    if original_price and original_price > price:
        discount_pct = int(((original_price - price) / original_price) * 100)
        text_parts.append(
            f"<s>{original_price:,.0f}</s> → <b>{price:,.0f} сум</b> <code>(-{discount_pct}%)</code>"
        )
    else:
        text_parts.append(f"💰 <b>{price:,.0f} сум</b>")

    # Quantity
    text_parts.append(
        f"📦 Количество: <b>{quantity} {unit}</b>"
        if lang == "ru"
        else f"📦 Miqdor: <b>{quantity} {unit}</b>"
    )

    # Stock
    stock_label = "В наличии" if lang == "ru" else "Omborda"
    text_parts.append(f"📊 {stock_label}: {max_qty} {unit}")

    # Expiry
    if expiry_date:
        expiry_label = "Годен до" if lang == "ru" else "Srok"
        text_parts.append(f"📅 {expiry_label}: {expiry_date}")

    text_parts.append("")

    # Store
    text_parts.append(f"🏪 <b>{store_name}</b>")
    if store_address:
        text_parts.append(f"📍 {store_address}")

    text_parts.append("")

    # Total
    total = price * quantity
    text_parts.append(
        f"💳 <b>ИТОГО: {total:,.0f} сум</b>"
        if lang == "ru"
        else f"💳 <b>JAMI: {total:,.0f} so'm</b>"
    )

    return "\n".join(text_parts)


def build_cart_add_card_keyboard(
    lang: str, offer_id: int, quantity: int, max_qty: int
) -> InlineKeyboardBuilder:
    """Build simplified cart addition keyboard - quantity buttons + add to cart button."""
    kb = InlineKeyboardBuilder()

    # Simple quantity control: [ - ] [qty] [ + ]
    minus_btn = "➖" if quantity > 1 else "▫️"
    plus_btn = "➕" if quantity < max_qty else "▫️"

    kb.button(
        text=minus_btn,
        callback_data=f"cart_qty_{offer_id}_{quantity - 1}" if quantity > 1 else "cart_noop",
    )
    kb.button(text=f"📦 {quantity}", callback_data="cart_noop")
    kb.button(
        text=plus_btn,
        callback_data=f"cart_qty_{offer_id}_{quantity + 1}" if quantity < max_qty else "cart_noop",
    )
    kb.adjust(3)

    # Add to cart button
    kb.button(
        text="✅ Добавить в корзину" if lang == "ru" else "✅ Savatga qo'shish",
        callback_data=f"cart_add_confirm_{offer_id}",
    )

    # Cancel button
    kb.button(
        text="❌ Отмена" if lang == "ru" else "❌ Bekor qilish",
        callback_data=f"cart_add_cancel_{offer_id}",
    )

    kb.adjust(3, 1, 1)

    return kb


# ===================== ADD TO CART (simplified - only quantity) =====================


@router.callback_query(F.data.startswith("add_to_cart_"))
async def add_to_cart_start(callback: types.CallbackQuery, state: FSMContext) -> None:
    """Show simplified cart addition card - only quantity selection, no delivery method."""
    if not db or not callback.message or not callback.data:
        await callback.answer()
        return

    user_id = callback.from_user.id
    lang = db.get_user_language(user_id)

    try:
        offer_id = int(callback.data.split("_")[-1])
    except (ValueError, IndexError):
        await callback.answer("❌", show_alert=True)
        return

    # Get offer details
    offer = db.get_offer(offer_id)
    if not offer:
        await callback.answer(
            "Товар не найден" if lang == "ru" else "Mahsulot topilmadi", show_alert=True
        )
        return

    def get_field(data: Any, key: str, default: Any = None) -> Any:
        if isinstance(data, dict):
            return data.get(key, default)
        return default

    max_qty = get_field(offer, "quantity", 0)
    if max_qty <= 0:
        await callback.answer(
            "Товар закончился" if lang == "ru" else "Mahsulot tugadi", show_alert=True
        )
        return

    price = get_field(offer, "discount_price", 0)
    original_price = get_field(offer, "original_price", 0)
    title = get_field(offer, "title", "Товар")
    description = get_field(offer, "description", "")
    unit = get_field(offer, "unit", "шт")
    expiry_date = get_field(offer, "expiry_date", "")
    store_id = get_field(offer, "store_id")
    offer_photo = get_field(offer, "photo", None)

    store = db.get_store(store_id) if store_id else None
    store_name = get_field(store, "name", "")
    store_address = get_field(store, "address", "")
    delivery_enabled = get_field(store, "delivery_enabled", 0) == 1
    delivery_price = get_field(store, "delivery_price", 0)

    # Initial quantity=1
    initial_qty = 1

    # Save to state
    await state.update_data(
        offer_id=offer_id,
        max_quantity=max_qty,
        offer_price=price,
        original_price=original_price,
        offer_title=title,
        offer_description=description,
        offer_unit=unit,
        expiry_date=str(expiry_date) if expiry_date else "",
        store_id=store_id,
        store_name=store_name,
        store_address=store_address,
        delivery_enabled=delivery_enabled,
        delivery_price=delivery_price,
        selected_qty=initial_qty,
        offer_photo=offer_photo,
    )

    # Build simplified cart card
    text = build_cart_add_card_text(
        lang,
        title,
        price,
        initial_qty,
        store_name,
        max_qty,
        original_price=original_price,
        description=description,
        expiry_date=str(expiry_date) if expiry_date else "",
        store_address=store_address,
        unit=unit,
    )

    kb = build_cart_add_card_keyboard(lang, offer_id, initial_qty, max_qty)

    # Update existing message
    try:
        if callback.message.photo:
            await callback.message.edit_caption(
                caption=text, parse_mode="HTML", reply_markup=kb.as_markup()
            )
        else:
            await callback.message.edit_text(text, parse_mode="HTML", reply_markup=kb.as_markup())
        await callback.answer()
    except Exception as e:
        logger.warning(f"Failed to edit message in add_to_cart_start: {e}")
        await callback.answer("❌", show_alert=True)


# ===================== CART QUANTITY HANDLERS (simplified - only quantity) =====================


@router.callback_query(F.data.startswith("cart_qty_"))
async def cart_update_quantity(callback: types.CallbackQuery, state: FSMContext) -> None:
    """Update quantity in cart addition card."""
    if not db or not callback.message:
        await callback.answer()
        return

    user_id = callback.from_user.id
    lang = db.get_user_language(user_id)

    try:
        parts = callback.data.split("_")
        offer_id = int(parts[2])
        new_qty = int(parts[3])
    except (ValueError, IndexError):
        await callback.answer("❌", show_alert=True)
        return

    data = await state.get_data()
    max_qty = data.get("max_quantity", 1)

    if new_qty < 1 or new_qty > max_qty:
        await callback.answer()
        return

    # Update quantity in state
    await state.update_data(selected_qty=new_qty)

    # Rebuild simplified cart card
    text = build_cart_add_card_text(
        lang,
        data.get("offer_title", ""),
        data.get("offer_price", 0),
        new_qty,
        data.get("store_name", ""),
        max_qty,
        original_price=data.get("original_price", 0),
        description=data.get("offer_description", ""),
        expiry_date=data.get("expiry_date", ""),
        store_address=data.get("store_address", ""),
        unit=data.get("offer_unit", ""),
    )

    kb = build_cart_add_card_keyboard(lang, offer_id, new_qty, max_qty)

    try:
        if callback.message.photo:
            await callback.message.edit_caption(
                caption=text, parse_mode="HTML", reply_markup=kb.as_markup()
            )
        else:
            await callback.message.edit_text(text, parse_mode="HTML", reply_markup=kb.as_markup())
    except Exception:
        pass

    await callback.answer()


@router.callback_query(F.data.startswith("cart_add_confirm_"))
async def cart_add_confirm(callback: types.CallbackQuery, state: FSMContext) -> None:
    """Confirm adding to cart - simplified, no delivery method selection."""
    if not db or not callback.message:
        await callback.answer()
        return

    user_id = callback.from_user.id
    lang = db.get_user_language(user_id)

    data = await state.get_data()

    # Get all data
    offer_id = data.get("offer_id")
    quantity = data.get("selected_qty", 1)
    store_id = data.get("store_id")
    offer_title = data.get("offer_title", "")
    offer_price = data.get("offer_price", 0)
    original_price = data.get("original_price", 0)
    max_qty = data.get("max_quantity", 1)
    store_name = data.get("store_name", "")
    store_address = data.get("store_address", "")
    delivery_enabled = data.get("delivery_enabled", False)
    delivery_price = data.get("delivery_price", 0)
    offer_photo = data.get("offer_photo")
    offer_unit = data.get("offer_unit", "шт")
    expiry_date = data.get("expiry_date", "")

    # Add to cart
    cart_storage.add_item(
        user_id=user_id,
        offer_id=offer_id,
        store_id=store_id,
        title=offer_title,
        price=offer_price,
        quantity=quantity,
        original_price=original_price,
        max_quantity=max_qty,
        store_name=store_name,
        store_address=store_address,
        photo=offer_photo,
        unit=offer_unit,
        expiry_date=expiry_date,
        delivery_enabled=delivery_enabled,
        delivery_price=delivery_price,
    )

    cart_count = cart_storage.get_cart_count(user_id)

    # Show popup notification
    added_text = "Добавлено!" if lang == "ru" else "Qo'shildi!"
    popup_text = (
        f"✅ {added_text} В корзине: {cart_count} шт"
        if lang == "ru"
        else f"✅ {added_text} Savatda: {cart_count} ta"
    )
    await callback.answer(popup_text, show_alert=False)

    # Save page info before clearing state
    last_page = data.get("hot_offers_page", 0)
    source = data.get("source", "hot")

    await state.clear()

    # Show the offers list again (edit current message)
    # Import service to get offers
    from app.keyboards import offers as offer_keyboards
    from app.services.offer_service import OfferService
    from app.templates import offers as offer_templates
    from handlers.common.utils import normalize_city
    from handlers.customer.offers.browse import BrowseOffers

    user = db.get_user_model(user_id)
    city = user.city if user else "Ташкент"
    search_city = normalize_city(city)

    offer_service = OfferService(db)
    ITEMS_PER_PAGE = 5

    try:
        result = offer_service.list_hot_offers(
            search_city, limit=ITEMS_PER_PAGE, offset=last_page * ITEMS_PER_PAGE
        )

        if result.items:
            # Set state for offer browsing
            await state.set_state(BrowseOffers.offer_list)
            await state.update_data(
                offer_list=[offer.id for offer in result.items],
                hot_offers_page=last_page,
            )

            total_pages = (result.total + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE
            currency = "so'm" if lang == "uz" else "сум"

            header_title = "АКЦИИ ДО -70%" if lang == "ru" else "CHEGIRMALAR -70% GACHA"
            page_label = "Стр." if lang == "ru" else "Sah."
            text = f"🔥 <b>{header_title}</b>\n"
            text += f"📍 {city} | {page_label} {last_page + 1}/{total_pages}\n"
            text += "━" * 24 + "\n\n"

            for idx, offer in enumerate(result.items, start=1):
                title = offer.title
                if title.startswith("Пример:"):
                    title = title[7:].strip()
                title = title[:22] + ".." if len(title) > 22 else title

                if offer.original_price and offer.discount_price and offer.original_price > 0:
                    discount_pct = round((1 - offer.discount_price / offer.original_price) * 100)
                else:
                    discount_pct = 0

                text += f"<b>{idx}.</b> {_esc(title)}\n"
                text += f"   💰 <s>{int(offer.original_price):,}</s> → <b>{int(offer.discount_price):,}</b> {currency}"
                if discount_pct > 0:
                    text += f" <b>(-{discount_pct}%)</b>"
                text += f"\n   🏪 {_esc(offer.store_name)}\n\n"

            select_hint = (
                "👆 Выберите номер товара:" if lang == "ru" else "👆 Mahsulot raqamini tanlang:"
            )
            text += select_hint

            kb = offer_keyboards.hot_offers_compact_keyboard(
                lang, result.items, last_page, total_pages
            )

            try:
                await callback.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
            except Exception:
                await callback.message.delete()
                await callback.message.answer(text, parse_mode="HTML", reply_markup=kb)
        else:
            # No offers - just delete message
            try:
                await callback.message.delete()
            except Exception:
                pass
    except Exception as e:
        logger.error(f"Error showing offers after add to cart: {e}")
        try:
            await callback.message.delete()
        except Exception:
            pass


@router.callback_query(F.data.startswith("cart_add_cancel_"))
async def cart_add_cancel(callback: types.CallbackQuery, state: FSMContext) -> None:
    """Cancel cart addition."""
    if not callback.message:
        await callback.answer()
        return

    await state.clear()

    try:
        await callback.message.delete()
    except Exception:
        pass

    await callback.answer()


@router.callback_query(F.data == "cart_noop")
async def cart_noop(callback: types.CallbackQuery) -> None:
    """No-op handler for disabled buttons."""
    await callback.answer()


# ===================== CART EDITING HANDLERS =====================


@router.callback_query(F.data.startswith("cart_qty_inc_"))
async def cart_quantity_increase(callback: types.CallbackQuery, state: FSMContext) -> None:
    """Increase item quantity in cart."""
    if not db or not callback.message:
        await callback.answer()
        return

    user_id = callback.from_user.id
    lang = db.get_user_language(user_id)

    try:
        offer_id = int(callback.data.split("_")[-1])
    except (ValueError, IndexError):
        await callback.answer("❌ Ошибка" if lang == "ru" else "❌ Xatolik", show_alert=True)
        return

    # Get current item
    items = cart_storage.get_cart(user_id)
    item = next((i for i in items if i.offer_id == offer_id), None)

    if not item:
        await callback.answer(
            "❌ Товар не найден" if lang == "ru" else "❌ Mahsulot topilmadi", show_alert=True
        )
        return

    # Check max quantity
    if item.quantity >= item.max_quantity:
        await callback.answer(
            f"⚠️ Максимум: {item.max_quantity}"
            if lang == "ru"
            else f"⚠️ Maksimal: {item.max_quantity}",
            show_alert=True,
        )
        return

    # Increase quantity
    cart_storage.update_quantity(user_id, offer_id, item.quantity + 1)

    # Refresh cart display
    await _show_cart_internal(callback, state, is_callback=True)


@router.callback_query(F.data.startswith("cart_qty_dec_"))
async def cart_quantity_decrease(callback: types.CallbackQuery, state: FSMContext) -> None:
    """Decrease item quantity in cart."""
    if not db or not callback.message:
        await callback.answer()
        return

    user_id = callback.from_user.id
    lang = db.get_user_language(user_id)

    try:
        offer_id = int(callback.data.split("_")[-1])
    except (ValueError, IndexError):
        await callback.answer("❌ Ошибка" if lang == "ru" else "❌ Xatolik", show_alert=True)
        return

    # Get current item
    items = cart_storage.get_cart(user_id)
    item = next((i for i in items if i.offer_id == offer_id), None)

    if not item:
        await callback.answer(
            "❌ Товар не найден" if lang == "ru" else "❌ Mahsulot topilmadi", show_alert=True
        )
        return

    # Decrease or remove
    if item.quantity <= 1:
        cart_storage.remove_item(user_id, offer_id)
    else:
        cart_storage.update_quantity(user_id, offer_id, item.quantity - 1)

    # Refresh cart display
    await _show_cart_internal(callback, state, is_callback=True)


@router.callback_query(F.data.startswith("cart_remove_"))
async def cart_remove_item(callback: types.CallbackQuery, state: FSMContext) -> None:
    """Remove item from cart."""
    if not db or not callback.message:
        await callback.answer()
        return

    user_id = callback.from_user.id
    lang = db.get_user_language(user_id)

    try:
        offer_id = int(callback.data.split("_")[-1])
    except (ValueError, IndexError):
        await callback.answer("❌ Ошибка" if lang == "ru" else "❌ Xatolik", show_alert=True)
        return

    cart_storage.remove_item(user_id, offer_id)

    # Refresh cart display
    await _show_cart_internal(callback, state, is_callback=True)


@router.callback_query(F.data.startswith("continue_shopping_"))
async def continue_shopping(callback: types.CallbackQuery, state: FSMContext) -> None:
    """Return to store offers list after adding to cart."""
    if not db or not callback.message or not callback.data:
        await callback.answer()
        return

    try:
        store_id = int(callback.data.split("_")[-1])
    except (ValueError, IndexError):
        await callback.answer()
        return

    user_id = callback.from_user.id
    lang = db.get_user_language(user_id)

    # Get store and offers
    store = db.get_store(store_id)
    if not store:
        await callback.answer(
            "Магазин не найден" if lang == "ru" else "Do'kon topilmadi", show_alert=True
        )
        return

    from handlers.bookings.utils import get_store_field

    store_name = get_store_field(store, "name", "Магазин")

    # Get active offers
    offers = db.get_active_offers(store_id)
    if not offers:
        await callback.answer(
            "Нет доступных товаров" if lang == "ru" else "Mahsulotlar yo'q", show_alert=True
        )
        return

    # Build offers list with pagination
    from aiogram.utils.keyboard import InlineKeyboardBuilder

    text_lines = []
    text_lines.append(f"🏪 <b>{_esc(store_name)}</b>\n")
    text_lines.append(f"{'Mahsulotlar:' if lang == 'uz' else 'Товары:'}\n")

    # Show first 5 offers
    ITEMS_PER_PAGE = 5
    page = 0
    start_idx = page * ITEMS_PER_PAGE
    end_idx = start_idx + ITEMS_PER_PAGE
    page_offers = (
        offers[start_idx:end_idx] if isinstance(offers, list) else list(offers)[start_idx:end_idx]
    )

    for i, offer in enumerate(page_offers, start=start_idx + 1):
        from handlers.bookings.utils import get_offer_field

        title = get_offer_field(offer, "title", "Товар")
        price = get_offer_field(offer, "discount_price", 0)
        qty = get_offer_field(offer, "quantity", 0)

        text_lines.append(f"{i}. {_esc(title)} - {price:,} сум (в наличии: {qty})")

    text = "\n".join(text_lines)

    # Build keyboard with offer buttons
    kb = InlineKeyboardBuilder()

    for offer in page_offers:
        offer_id = get_offer_field(offer, "id", 0) or get_offer_field(offer, "offer_id", 0)
        title = get_offer_field(offer, "title", "Товар")

        kb.button(
            text=f"📦 {title[:30]}{'...' if len(title) > 30 else ''}",
            callback_data=f"view_offer_{offer_id}",
        )

    kb.adjust(1)

    # Add pagination if needed
    total_offers = len(offers) if isinstance(offers, list) else offers
    total_pages = (total_offers + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE

    if total_pages > 1:
        nav_buttons = []
        if page > 0:
            nav_buttons.append(
                ("◀️ Назад" if lang == "ru" else "◀️ Orqaga", f"store_page_{store_id}_{page - 1}")
            )
        nav_buttons.append((f"📄 {page + 1}/{total_pages}", "noop"))
        if page < total_pages - 1:
            nav_buttons.append(
                ("Вперед ▶️" if lang == "ru" else "Oldinga ▶️", f"store_page_{store_id}_{page + 1}")
            )

        for btn_text, btn_data in nav_buttons:
            kb.button(text=btn_text, callback_data=btn_data)
        kb.adjust(1, *([len(nav_buttons)] if len(nav_buttons) > 1 else [1]))

    # Cart button
    cart_count = cart_storage.get_cart_count(user_id)
    if cart_count > 0:
        kb.button(
            text=f"🛒 Корзина ({cart_count})" if lang == "ru" else f"🛒 Savat ({cart_count})",
            callback_data="view_cart",
        )
        kb.adjust(1)

    # Back button
    kb.button(
        text="🔙 Назад" if lang == "ru" else "🔙 Orqaga",
        callback_data="back_to_menu",
    )

    try:
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=kb.as_markup())
    except Exception:
        await callback.message.answer(text, parse_mode="HTML", reply_markup=kb.as_markup())

    await callback.answer()


@router.callback_query(F.data == "view_cart")
async def view_cart_callback(callback: types.CallbackQuery, state: FSMContext) -> None:
    """View cart from callback."""
    if not callback.message or not callback.from_user:
        await callback.answer()
        return

    await _show_cart_internal(callback, state, is_callback=True)
