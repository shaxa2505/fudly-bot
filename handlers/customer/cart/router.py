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


@router.message(F.text.in_(["🛒 Корзина", "🛒 Savat"]))
async def show_cart(message: types.Message, state: FSMContext) -> None:
    """Show cart contents - main entry point."""
    if not db or not message.from_user:
        return

    await state.clear()
    user_id = message.from_user.id
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
            text="🔥 Горячие предложения" if lang == "ru" else "🔥 Ҳаракатли таклифлар",
            callback_data="hot_offers",
        )
        await message.answer(empty_text, reply_markup=kb.as_markup())
        return

    # Build cart view
    currency = "so'm" if lang == "uz" else "сум"
    lines = [f"🛒 <b>{'Savat' if lang == 'uz' else 'Корзина'}</b>\n"]

    total = 0
    for i, item in enumerate(items, 1):
        subtotal = item.price * item.quantity
        total += subtotal
        lines.append(f"\n<b>{i}. {_esc(item.title)}</b>")
        lines.append(f"   {item.quantity} × {item.price:,} = <b>{subtotal:,}</b> {currency}")
        lines.append(f"   🏪 {_esc(item.store_name)}")

    lines.append("\n" + "─" * 25)
    lines.append(f"💵 <b>{'JAMI' if lang == 'uz' else 'ИТОГО'}: {total:,} {currency}</b>")

    text = "\n".join(lines)

    # Cart keyboard
    kb = InlineKeyboardBuilder()
    kb.button(
        text="✅ Оформить заказ" if lang == "ru" else "✅ Buyurtma berish",
        callback_data="cart_checkout",
    )
    kb.button(
        text="🗑 Очистить корзину" if lang == "ru" else "🗑 Savatni tozalash",
        callback_data="cart_clear",
    )
    kb.adjust(1)

    await message.answer(text, parse_mode="HTML", reply_markup=kb.as_markup())


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
    total = sum(item.price * item.quantity for item in items)

    # Build checkout summary
    lines = [f"📋 <b>{'Buyurtma' if lang == 'uz' else 'Заказ'}</b>\n"]
    lines.append(f"🏪 {_esc(items[0].store_name)}\n")

    for item in items:
        subtotal = item.price * item.quantity
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

    # Simulate message to reuse show_cart logic
    from aiogram.types import Message

    fake_message = Message(
        message_id=callback.message.message_id,
        date=callback.message.date,
        chat=callback.message.chat,
        from_user=callback.from_user,
    )

    await show_cart(fake_message, state)
    await callback.answer()


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
        subtotal = item.price * item.quantity
        lines.append(f"• {_esc(item.title)} × {item.quantity} = {subtotal:,} {currency}")

    total = sum(item.price * item.quantity for item in items)
    lines.append(f"\n💵 <b>{'JAMI' if lang == 'uz' else 'ИТОГО'}: {total:,} {currency}</b>")

    text = "\n".join(lines)

    try:
        await callback.message.edit_text(text, parse_mode="HTML")
    except Exception:
        await callback.message.answer(text, parse_mode="HTML")

    # Notify partner - send ONE notification with all items
    try:
        store = db.get_store(store_id)
        if store:
            owner_id = store.get("owner_id") if isinstance(store, dict) else store[1]

            # Build partner notification
            partner_lines = [
                f"🛒 <b>{'Yangi savat broni!' if lang == 'uz' else 'Новое бронирование корзины!'}</b>\n"
            ]
            partner_lines.append(
                f"📋 {'Bron kodi' if lang == 'uz' else 'Код'}: <b>{booking_code}</b>"
            )
            partner_lines.append(
                f"👤 {'Mijoz' if lang == 'uz' else 'Клиент'}: {callback.from_user.first_name or 'User'}\n"
            )
            partner_lines.append(f"<b>{'Mahsulotlar' if lang == 'uz' else 'Товары'}:</b>")

            for item in items:
                subtotal = item.price * item.quantity
                partner_lines.append(
                    f"• {_esc(item.title)} × {item.quantity} = {subtotal:,} {currency}"
                )

            partner_lines.append(
                f"\n💵 <b>{'JAMI' if lang == 'uz' else 'ИТОГО'}: {total:,} {currency}</b>"
            )

            partner_text = "\n".join(partner_lines)

            # One button to confirm/reject entire cart booking
            kb = InlineKeyboardBuilder()
            kb.button(
                text="✅ Подтвердить" if lang == "ru" else "✅ Tasdiqlash",
                callback_data=f"partner_confirm_{booking_id}",
            )
            kb.button(
                text="❌ Отклонить" if lang == "ru" else "❌ Rad etish",
                callback_data=f"partner_reject_{booking_id}",
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
    """Start delivery address input for cart."""
    if not db or not callback.message:
        await callback.answer()
        return

    user_id = callback.from_user.id
    lang = db.get_user_language(user_id)

    items = cart_storage.get_cart(user_id)
    if not items:
        await callback.answer("Корзина пуста" if lang == "ru" else "Savat bo'sh", show_alert=True)
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
        store_id=items[0].store_id,
        delivery_price=items[0].delivery_price,
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
    """Process delivery address and create cart order."""
    if not db or not message.from_user or not message.text:
        return

    user_id = message.from_user.id
    lang = db.get_user_language(user_id)
    delivery_address = message.text.strip()

    data = await state.get_data()
    cart_items_stored = data.get("cart_items", [])
    store_id = data.get("store_id")
    delivery_price = data.get("delivery_price", 0)

    await state.clear()

    if not cart_items_stored or not store_id:
        await message.answer(
            "❌ Данные корзины потеряны" if lang == "ru" else "❌ Savat ma'lumotlari yo'qoldi"
        )
        return

    # Prepare cart_items for database (cart_items_stored is already list of dicts)
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
        delivery_address=delivery_address,
        delivery_price=delivery_price,
        payment_method="cash",
    )

    if not ok:
        error_text = (
            "❌ Не удалось создать заказ" if lang == "ru" else "❌ Buyurtma yaratib bo'lmadi"
        )
        if error_reason and "insufficient_stock" in error_reason:
            error_text = (
                "❌ Недостаточно товара на складе"
                if lang == "ru"
                else "❌ Omborda yetarli mahsulot yo'q"
            )

        await message.answer(error_text)
        return

    # Clear cart after successful order
    cart_storage.clear_cart(user_id)

    # Build success message
    currency = "so'm" if lang == "uz" else "сум"
    lines = [f"✅ <b>{'Buyurtma yaratildi!' if lang == 'uz' else 'Заказ создан!'}</b>\n"]
    lines.append(f"📋 {'Buyurtma kodi' if lang == 'uz' else 'Код заказа'}: <b>{pickup_code}</b>\n")
    lines.append(f"🏪 {_esc(cart_items_stored[0]['store_name'])}")
    lines.append(f"📍 {'Yetkazish' if lang == 'uz' else 'Доставка'}: {_esc(delivery_address)}\n")
    lines.append(f"<b>{'Mahsulotlar' if lang == 'uz' else 'Товары'}:</b>")

    total = 0
    for item in cart_items_stored:
        subtotal = item["price"] * item["quantity"]
        total += subtotal
        lines.append(f"• {_esc(item['title'])} × {item['quantity']} = {subtotal:,} {currency}")

    lines.append(f"🚚 {'Yetkazish' if lang == 'uz' else 'Доставка'}: {delivery_price:,} {currency}")
    total_with_delivery = total + delivery_price
    lines.append(
        f"\n💵 <b>{'JAMI' if lang == 'uz' else 'ИТОГО'}: {total_with_delivery:,} {currency}</b>"
    )

    text = "\n".join(lines)
    await message.answer(text, parse_mode="HTML")

    # Notify partner - send ONE notification with all items
    try:
        store = db.get_store(store_id)
        if store:
            owner_id = store.get("owner_id") if isinstance(store, dict) else store[1]

            # Build partner notification
            partner_lines = [
                f"🛒🚚 <b>{'Yangi savat buyurtmasi!' if lang == 'uz' else 'Новый заказ корзины!'}</b>\n"
            ]
            partner_lines.append(
                f"📋 {'Buyurtma kodi' if lang == 'uz' else 'Код'}: <b>{pickup_code}</b>"
            )
            partner_lines.append(
                f"👤 {'Mijoz' if lang == 'uz' else 'Клиент'}: {message.from_user.first_name or 'User'}"
            )
            partner_lines.append(
                f"📍 {'Manzil' if lang == 'uz' else 'Адрес'}: {_esc(delivery_address)}\n"
            )
            partner_lines.append(f"<b>{'Mahsulotlar' if lang == 'uz' else 'Товары'}:</b>")

            for item in cart_items_stored:
                subtotal = item["price"] * item["quantity"]
                partner_lines.append(
                    f"• {_esc(item['title'])} × {item['quantity']} = {subtotal:,} {currency}"
                )

            partner_lines.append(
                f"🚚 {'Yetkazish' if lang == 'uz' else 'Доставка'}: {delivery_price:,} {currency}"
            )
            partner_lines.append(
                f"\n💵 <b>{'JAMI' if lang == 'uz' else 'ИТОГО'}: {total_with_delivery:,} {currency}</b>"
            )

            partner_text = "\n".join(partner_lines)

            # One button to confirm/reject entire cart order (uses same handlers as regular orders)
            kb = InlineKeyboardBuilder()
            kb.button(
                text="✅ Подтвердить" if lang == "ru" else "✅ Tasdiqlash",
                callback_data=f"partner_confirm_order_{order_id}",
            )
            kb.button(
                text="❌ Отклонить" if lang == "ru" else "❌ Rad etish",
                callback_data=f"partner_reject_order_{order_id}",
            )
            kb.adjust(2)

            await message.bot.send_message(
                owner_id, partner_text, parse_mode="HTML", reply_markup=kb.as_markup()
            )
            logger.info(
                f"🛒 Sent cart order notification to partner {owner_id} for order {order_id}"
            )
    except Exception as e:
        logger.error(f"Failed to notify partner: {e}")


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
        f"📦 Количество: <b>{quantity} {unit}</b>" if lang == "ru" else f"📦 Miqdor: <b>{quantity} {unit}</b>"
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
        f"💳 <b>ИТОГО: {total:,.0f} сум</b>" if lang == "ru" else f"💳 <b>JAMI: {total:,.0f} so'm</b>"
    )

    return "\n".join(text_parts)


def build_cart_add_card_keyboard(
    lang: str, offer_id: int, quantity: int, max_qty: int
) -> InlineKeyboardBuilder:
    """Build simplified cart addition keyboard - only quantity buttons + add to cart button."""
    kb = InlineKeyboardBuilder()

    # Quantity buttons
    if max_qty <= 5:
        # Show all quantities as buttons
        for q in range(1, max_qty + 1):
            btn_text = f"📦 {q}" if q == quantity else str(q)
            kb.button(text=btn_text, callback_data=f"cart_qty_{offer_id}_{q}")
        kb.adjust(min(max_qty, 5))
    else:
        # Show -/+/value buttons
        minus_btn = "−" if quantity > 1 else "•"
        plus_btn = "+" if quantity < max_qty else "•"

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

    kb.adjust(1)

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

    await state.clear()

    cart_count = cart_storage.get_cart_count(user_id)

    text = (
        f"✅ Добавлено в корзину!\n\n🛒 В корзине: {cart_count} товар(ов)"
        if lang == "ru"
        else f"✅ Savatga qo'shildi!\n\n🛒 Savatda: {cart_count} ta mahsulot"
    )

    kb = InlineKeyboardBuilder()
    kb.button(
        text="🛒 Перейти в корзину" if lang == "ru" else "🛒 Savatga o'tish",
        callback_data="view_cart",
    )
    kb.button(
        text="🔙 Продолжить покупки" if lang == "ru" else "🔙 Xaridni davom ettirish",
        callback_data="back_to_menu",
    )
    kb.adjust(1)

    try:
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=kb.as_markup())
    except Exception:
        await callback.message.answer(text, parse_mode="HTML", reply_markup=kb.as_markup())

    await callback.answer("✅")


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


@router.callback_query(F.data == "view_cart")
async def view_cart_callback(callback: types.CallbackQuery, state: FSMContext) -> None:
    """View cart from callback."""
    if not callback.message or not callback.from_user:
        await callback.answer()
        return

    # Create fake message to reuse show_cart
    from aiogram.types import Message

    fake_message = Message(
        message_id=callback.message.message_id,
        date=callback.message.date,
        chat=callback.message.chat,
        from_user=callback.from_user,
    )

    await show_cart(fake_message, state)
    await callback.answer()
