"""Customer booking handlers - create, view, cancel, rate bookings.

Premium UX v3 - Beautiful booking cards with photos and inline controls.
"""
from __future__ import annotations

import html
from typing import Any

from aiogram import F, Router, types
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.keyboards import cancel_keyboard, main_menu_customer
from handlers.common.states import BookOffer, OrderDelivery
from handlers.common.utils import is_main_menu_button
from localization import get_text
from logging_config import logger

from .utils import (
    calculate_total,
    can_proceed,
    format_booking_code,
    get_booking_field,
    get_offer_field,
    get_store_field,
    get_user_safe,
    safe_answer_or_send,
    safe_edit_reply_markup,
)

router = Router()

# Module dependencies (set via setup_dependencies)
db: Any = None
bot: Any = None
cache: Any = None
METRICS: dict = {}


def setup_dependencies(
    database: Any, bot_instance: Any, cache_manager: Any = None, metrics: dict = None
):
    """Setup module dependencies."""
    global db, bot, cache, METRICS
    db = database
    bot = bot_instance
    cache = cache_manager
    METRICS = metrics or {}


def _esc(val: Any) -> str:
    """HTML-escape helper."""
    if val is None:
        return ""
    return html.escape(str(val))


# ===================== PREMIUM UX v3: Beautiful booking cards =====================
# - New message with photo when booking
# - [−] [qty] [+] quantity controls
# - Radio-style delivery selection
# - Real-time total updates


def build_order_card_text(
    lang: str,
    title: str,
    price: int,
    quantity: int,
    store_name: str,
    delivery_enabled: bool,
    delivery_price: int,
    delivery_method: str | None,
    max_qty: int,
) -> str:
    """Build beautiful order card text with current selection."""
    currency = "so'm" if lang == "uz" else "сум"
    
    # Calculate totals
    subtotal = price * quantity
    delivery_cost = delivery_price if delivery_method == "delivery" else 0
    total = subtotal + delivery_cost
    
    # Header
    lines = [
        f"🛒 <b>{_esc(title)}</b>",
        "",
        f"━━━━━━━━━━━━━━━━━━",
    ]
    
    # Price info
    price_label = "Narxi" if lang == "uz" else "Цена"
    qty_label = "Miqdor" if lang == "uz" else "Количество"
    lines.append(f"💰 {price_label}: <b>{price:,}</b> {currency}")
    lines.append(f"📦 {qty_label}: <b>{quantity}</b> {'dona' if lang == 'uz' else 'шт'}")
    
    # Delivery section
    if delivery_enabled:
        lines.append("")
        delivery_label = "Yetkazish usuli" if lang == "uz" else "Способ получения"
        lines.append(f"🚚 <b>{delivery_label}:</b>")
        
        # Show current selection with radio buttons
        pickup_label = "O'zim olib ketaman" if lang == "uz" else "Самовывоз"
        delivery_label = f"Yetkazish (+{delivery_price:,} {currency})" if lang == "uz" else f"Доставка (+{delivery_price:,} {currency})"
        
        if delivery_method == "pickup":
            lines.append(f"   🔘 {pickup_label}")
            lines.append(f"   ⚪ {delivery_label}")
        elif delivery_method == "delivery":
            lines.append(f"   ⚪ {pickup_label}")
            lines.append(f"   🔘 {delivery_label}")
        else:
            lines.append(f"   ⚪ {pickup_label}")
            lines.append(f"   ⚪ {delivery_label}")
    
    # Totals
    lines.append("")
    lines.append(f"━━━━━━━━━━━━━━━━━━")
    
    subtotal_label = "Mahsulot" if lang == "uz" else "Товар"
    lines.append(f"📦 {subtotal_label}: {subtotal:,} {currency}")
    
    if delivery_method == "delivery" and delivery_cost > 0:
        delivery_cost_label = "Yetkazish" if lang == "uz" else "Доставка"
        lines.append(f"🚚 {delivery_cost_label}: +{delivery_cost:,} {currency}")
    
    total_label = "JAMI" if lang == "uz" else "ИТОГО"
    lines.append(f"💵 <b>{total_label}: {total:,} {currency}</b>")
    
    # Store info
    lines.append("")
    lines.append(f"🏪 {_esc(store_name)}")
    
    # Hint
    if not delivery_method and delivery_enabled:
        hint = "👇 Yetkazish usulini tanlang" if lang == "uz" else "👇 Выберите способ получения"
        lines.append("")
        lines.append(f"<i>{hint}</i>")
    
    return "\n".join(lines)


def build_order_card_keyboard(
    lang: str,
    offer_id: int,
    store_id: int,
    quantity: int,
    max_qty: int,
    delivery_enabled: bool,
    delivery_method: str | None,
) -> InlineKeyboardBuilder:
    """Build order card keyboard with [−] [qty] [+] and delivery options."""
    kb = InlineKeyboardBuilder()
    
    # Row 1: Quantity controls [−] [qty] [+]
    minus_enabled = quantity > 1
    plus_enabled = quantity < max_qty
    
    minus_text = "➖" if minus_enabled else "⬜"
    plus_text = "➕" if plus_enabled else "⬜"
    
    kb.button(
        text=minus_text, 
        callback_data=f"pbook_qty_{offer_id}_{quantity - 1}" if minus_enabled else "pbook_noop"
    )
    kb.button(text=f"📦 {quantity}", callback_data="pbook_noop")
    kb.button(
        text=plus_text, 
        callback_data=f"pbook_qty_{offer_id}_{quantity + 1}" if plus_enabled else "pbook_noop"
    )
    
    # Row 2-3: Delivery options (if enabled)
    if delivery_enabled:
        pickup_text = "🏪 O'zim olib ketaman" if lang == "uz" else "🏪 Самовывоз"
        delivery_text = "🚚 Yetkazish" if lang == "uz" else "🚚 Доставка"
        
        # Add checkmarks for selected option
        if delivery_method == "pickup":
            pickup_text = "✓ " + pickup_text
        elif delivery_method == "delivery":
            delivery_text = "✓ " + delivery_text
        
        kb.button(text=pickup_text, callback_data=f"pbook_method_{offer_id}_pickup")
        kb.button(text=delivery_text, callback_data=f"pbook_method_{offer_id}_delivery")
    
    # Row 4: Confirm and Cancel
    if delivery_method or not delivery_enabled:
        confirm_text = "✅ Tasdiqlash" if lang == "uz" else "✅ Подтвердить"
        kb.button(text=confirm_text, callback_data=f"pbook_confirm_{offer_id}")
    
    cancel_text = "❌ Bekor" if lang == "uz" else "❌ Отмена"
    kb.button(text=cancel_text, callback_data=f"pbook_cancel_{offer_id}_{store_id}")
    
    # Layout
    if delivery_enabled:
        if delivery_method:
            kb.adjust(3, 2, 2)  # [−][qty][+], [pickup][delivery], [confirm][cancel]
        else:
            kb.adjust(3, 2, 1)  # [−][qty][+], [pickup][delivery], [cancel]
    else:
        kb.adjust(3, 2)  # [−][qty][+], [confirm][cancel]
    
    return kb


@router.callback_query(F.data.regexp(r"^book_\d+$"))
async def book_offer_start(callback: types.CallbackQuery, state: FSMContext) -> None:
    """Premium UX: Update current card with order controls (no new message)."""
    if not db or not bot or not callback.message:
        await callback.answer("System error", show_alert=True)
        return

    user_id = callback.from_user.id
    lang = db.get_user_language(user_id)

    # Rate limit check
    if not can_proceed(user_id, "book_start"):
        await callback.answer(get_text(lang, "too_many_requests"), show_alert=True)
        return

    # Parse offer_id
    try:
        offer_id = int(callback.data.split("_")[1])
    except (ValueError, IndexError):
        await callback.answer(get_text(lang, "error"), show_alert=True)
        return

    offer = db.get_offer(offer_id)
    if not offer:
        await callback.answer(get_text(lang, "offer_not_found"), show_alert=True)
        return

    # Check availability
    max_quantity = get_offer_field(offer, "quantity", 0)
    if max_quantity <= 0:
        await callback.answer(get_text(lang, "no_offers"), show_alert=True)
        return

    # Get offer details
    offer_price = get_offer_field(offer, "discount_price", 0)
    offer_title = get_offer_field(offer, "title", "Товар")
    store_id = get_offer_field(offer, "store_id")

    # Get store details
    store = db.get_store(store_id) if store_id else None
    store_name = get_store_field(store, "name", "Магазин")
    delivery_enabled = get_store_field(store, "delivery_enabled", 0) == 1
    delivery_price = get_store_field(store, "delivery_price", 0) if delivery_enabled else 0

    # Initial state: quantity=1, no delivery method selected
    initial_qty = 1
    initial_method = None if delivery_enabled else "pickup"

    # Save to state
    await state.update_data(
        offer_id=offer_id,
        max_quantity=max_quantity,
        offer_price=offer_price,
        offer_title=offer_title,
        store_id=store_id,
        store_name=store_name,
        delivery_enabled=delivery_enabled,
        delivery_price=delivery_price,
        selected_qty=initial_qty,
        selected_delivery=initial_method,
    )
    await state.set_state(BookOffer.quantity)

    # Build card text and keyboard
    text = build_order_card_text(
        lang, offer_title, offer_price, initial_qty, store_name,
        delivery_enabled, delivery_price, initial_method, max_quantity
    )
    kb = build_order_card_keyboard(
        lang, offer_id, store_id, initial_qty, max_quantity,
        delivery_enabled, initial_method
    )

    # Update EXISTING message (edit caption for photo, edit text for text)
    try:
        if callback.message.photo:
            await callback.message.edit_caption(
                caption=text,
                parse_mode="HTML",
                reply_markup=kb.as_markup()
            )
        else:
            await callback.message.edit_text(
                text,
                parse_mode="HTML",
                reply_markup=kb.as_markup()
            )
    except Exception as e:
        logger.warning(f"Failed to edit message: {e}")
    
    await callback.answer()


@router.callback_query(F.data == "pbook_noop")
async def pbook_noop(callback: types.CallbackQuery) -> None:
    """No-op for disabled buttons."""
    await callback.answer()


@router.callback_query(F.data.startswith("pbook_qty_"))
async def pbook_change_qty(callback: types.CallbackQuery, state: FSMContext) -> None:
    """Premium UX: Change quantity and update card."""
    if not db or not bot or not callback.message:
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
    max_quantity = data.get("max_quantity", 1)

    if new_qty < 1 or new_qty > max_quantity:
        await callback.answer("❌", show_alert=True)
        return

    # Update state
    await state.update_data(selected_qty=new_qty)
    data = await state.get_data()

    # Rebuild card
    text = build_order_card_text(
        lang,
        data.get("offer_title", ""),
        data.get("offer_price", 0),
        new_qty,
        data.get("store_name", ""),
        data.get("delivery_enabled", False),
        data.get("delivery_price", 0),
        data.get("selected_delivery"),
        max_quantity
    )
    kb = build_order_card_keyboard(
        lang,
        offer_id,
        data.get("store_id", 0),
        new_qty,
        max_quantity,
        data.get("delivery_enabled", False),
        data.get("selected_delivery")
    )

    # Update message
    try:
        if callback.message.photo:
            await callback.message.edit_caption(caption=text, parse_mode="HTML", reply_markup=kb.as_markup())
        else:
            await callback.message.edit_text(text, parse_mode="HTML", reply_markup=kb.as_markup())
    except Exception:
        pass
    await callback.answer()


@router.callback_query(F.data.startswith("pbook_method_"))
async def pbook_select_method(callback: types.CallbackQuery, state: FSMContext) -> None:
    """Premium UX: Select delivery method and update card."""
    if not db or not bot or not callback.message:
        await callback.answer()
        return

    user_id = callback.from_user.id
    lang = db.get_user_language(user_id)

    try:
        parts = callback.data.split("_")
        offer_id = int(parts[2])
        method = parts[3]  # "pickup" or "delivery"
    except (ValueError, IndexError):
        await callback.answer("❌", show_alert=True)
        return

    # Update state
    await state.update_data(selected_delivery=method)
    data = await state.get_data()

    quantity = data.get("selected_qty", 1)
    max_quantity = data.get("max_quantity", 1)

    # Rebuild card
    text = build_order_card_text(
        lang,
        data.get("offer_title", ""),
        data.get("offer_price", 0),
        quantity,
        data.get("store_name", ""),
        data.get("delivery_enabled", False),
        data.get("delivery_price", 0),
        method,
        max_quantity
    )
    kb = build_order_card_keyboard(
        lang,
        offer_id,
        data.get("store_id", 0),
        quantity,
        max_quantity,
        data.get("delivery_enabled", False),
        method
    )

    # Update message
    try:
        if callback.message.photo:
            await callback.message.edit_caption(caption=text, parse_mode="HTML", reply_markup=kb.as_markup())
        else:
            await callback.message.edit_text(text, parse_mode="HTML", reply_markup=kb.as_markup())
    except Exception:
        pass
    await callback.answer()


@router.callback_query(F.data.startswith("pbook_cancel_"))
async def pbook_cancel(callback: types.CallbackQuery, state: FSMContext) -> None:
    """Cancel booking - restore original product card."""
    if not db or not callback.message:
        await callback.answer()
        return

    user_id = callback.from_user.id
    lang = db.get_user_language(user_id)

    try:
        parts = callback.data.split("_")
        offer_id = int(parts[2])
        store_id = int(parts[3])
    except (ValueError, IndexError):
        await callback.answer()
        return

    await state.clear()

    # Get offer and store
    offer = db.get_offer(offer_id)
    store = db.get_store(store_id) if store_id else None
    
    if not offer:
        await callback.answer()
        return

    # Build card text manually (more reliable than OfferDetails)
    currency = "so'm" if lang == "uz" else "сум"
    title = get_offer_field(offer, "title", "Товар")
    description = get_offer_field(offer, "description", "")
    original_price = get_offer_field(offer, "original_price", 0)
    discount_price = get_offer_field(offer, "discount_price", 0)
    quantity = get_offer_field(offer, "quantity", 0)
    unit = get_offer_field(offer, "unit", "шт" if lang == "ru" else "dona")
    expiry_date = get_offer_field(offer, "expiry_date")
    store_name = get_store_field(store, "name", "")
    store_address = get_store_field(store, "address", "")
    delivery_enabled = get_store_field(store, "delivery_enabled", 0) == 1
    delivery_price = get_store_field(store, "delivery_price", 0)
    min_order = get_store_field(store, "min_order_amount", 0)
    
    lines = [f"📦 <b>{_esc(title)}</b>"]
    
    if description:
        desc = description[:100] + "..." if len(description) > 100 else description
        lines.append(f"<i>{_esc(desc)}</i>")
    
    lines.append("")
    lines.append("─" * 25)
    
    # Price
    if original_price and discount_price:
        discount_pct = int((1 - discount_price / original_price) * 100) if original_price > 0 else 0
        lines.append(f"<s>{int(original_price):,}</s> → <b>{int(discount_price):,}</b> {currency} (-{discount_pct}%)")
    else:
        lines.append(f"💰 <b>{int(discount_price or 0):,}</b> {currency}")
    
    lines.append("─" * 25)
    lines.append("")
    
    # Stock
    stock_label = "Mavjud" if lang == "uz" else "В наличии"
    lines.append(f"📦 {stock_label}: <b>{quantity}</b> {unit}")
    
    # Expiry
    if expiry_date:
        expiry_label = "Yaroqlilik" if lang == "uz" else "Срок до"
        expiry_str = str(expiry_date)[:10]
        try:
            from datetime import datetime
            dt = datetime.strptime(expiry_str, "%Y-%m-%d")
            expiry_str = dt.strftime("%d.%m.%Y")
        except Exception:
            pass
        lines.append(f"📅 {expiry_label}: {expiry_str}")
    
    # Store
    lines.append("")
    if store_name:
        lines.append(f"🏪 {_esc(store_name)}")
    if store_address:
        lines.append(f"📍 {_esc(store_address)}")
    
    # Delivery
    if delivery_enabled:
        lines.append("")
        delivery_label = "Yetkazish" if lang == "uz" else "Доставка"
        lines.append(f"🚚 {delivery_label}: {int(delivery_price):,} {currency}")
        if min_order:
            min_label = "Min." if lang == "uz" else "Мин."
            lines.append(f"   {min_label}: {int(min_order):,} {currency}")
    
    text = "\n".join(lines)
    
    # Keyboard with back button
    from app.keyboards.offers import offer_details_with_back_keyboard
    kb = offer_details_with_back_keyboard(lang, offer_id, store_id, delivery_enabled)
    
    try:
        if callback.message.photo:
            await callback.message.edit_caption(caption=text, parse_mode="HTML", reply_markup=kb)
        else:
            await callback.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
    except Exception as e:
        logger.warning(f"Failed to edit message on cancel: {e}")
    
    await callback.answer()


@router.callback_query(F.data.startswith("pbook_confirm_"))
async def pbook_confirm(callback: types.CallbackQuery, state: FSMContext) -> None:
    """Confirm order - create booking or start delivery flow."""
    if not db or not bot or not callback.message:
        await callback.answer("System error", show_alert=True)
        return

    user_id = callback.from_user.id
    lang = db.get_user_language(user_id)
    data = await state.get_data()

    selected_delivery = data.get("selected_delivery")

    if not selected_delivery:
        msg = "Avval olish usulini tanlang" if lang == "uz" else "Сначала выберите способ получения"
        await callback.answer(msg, show_alert=True)
        return

    offer_id = data.get("offer_id")
    quantity = data.get("selected_qty", 1)
    store_id = data.get("store_id")
    offer_price = data.get("offer_price", 0)
    offer_title = data.get("offer_title", "Товар")

    # Check minimum order for delivery
    if selected_delivery == "delivery":
        store = db.get_store(store_id) if store_id else None
        min_order = get_store_field(store, "min_order_amount", 0)
        order_total = offer_price * quantity

        if min_order > 0 and order_total < min_order:
            currency = "so'm" if lang == "uz" else "сум"
            msg = (
                f"❌ Min. buyurtma: {min_order:,} {currency}"
                if lang == "uz"
                else f"❌ Мин. заказ: {min_order:,} {currency}"
            )
            await callback.answer(msg, show_alert=True)
            return

    # Show processing status in the card (no keyboard)
    currency = "so'm" if lang == "uz" else "сум"
    total = offer_price * quantity
    processing_text = (
        f"⏳ <b>Bron yuborilmoqda...</b>\n\n"
        f"🛒 {_esc(offer_title)} × {quantity}\n"
        f"💵 {total:,} {currency}"
        if lang == "uz" else
        f"⏳ <b>Оформляем бронь...</b>\n\n"
        f"🛒 {_esc(offer_title)} × {quantity}\n"
        f"💵 {total:,} {currency}"
    )
    
    try:
        if callback.message.photo:
            await callback.message.edit_caption(caption=processing_text, parse_mode="HTML", reply_markup=None)
        else:
            await callback.message.edit_text(processing_text, parse_mode="HTML", reply_markup=None)
    except Exception:
        pass

    if selected_delivery == "delivery":
        # Switch to delivery flow - ask for address
        await state.clear()
        await state.update_data(
            offer_id=offer_id,
            store_id=store_id,
            quantity=quantity,
        )
        await state.set_state(OrderDelivery.address)

        if lang == "uz":
            text = "📍 Yetkazib berish manzilini kiriting:\n\nMasalan: Chilanzar tumani, 5-mavze, 10-uy"
        else:
            text = "📍 Введите адрес доставки:\n\nНапример: Чиланзарский район, 5-массив, дом 10"

        await bot.send_message(user_id, text, reply_markup=cancel_keyboard(lang))
    else:
        # Pickup - create booking directly
        await state.update_data(quantity=quantity, delivery_option=0, delivery_cost=0)

        # Create booking (will send notification in same chat)
        await create_booking(callback.message, state, real_user_id=user_id)

    await callback.answer()


# ===================== LEGACY HANDLERS (kept for compatibility) =====================


@router.message(BookOffer.quantity)
async def book_offer_quantity(message: types.Message, state: FSMContext) -> None:
    """Process quantity input."""
    if not db:
        await message.answer("System error")
        return

    user_id = message.from_user.id
    lang = db.get_user_language(user_id)
    text = (message.text or "").strip()

    # Check if user pressed main menu button - clear state and let other handlers process
    if is_main_menu_button(text):
        await state.clear()
        return

    # Check cancel - accept all variants
    if (
        text in ["❌ Отмена", "❌ Bekor qilish", "/cancel", "Отмена", "Bekor qilish"]
        or "отмена" in text.lower()
        or "bekor" in text.lower()
    ):
        await state.clear()
        await message.answer(
            get_text(lang, "action_cancelled"), reply_markup=main_menu_customer(lang)
        )
        return

    # Validate quantity
    data = await state.get_data()
    max_qty = data.get("max_quantity", 1)

    try:
        quantity = int(text)
        if quantity < 1 or quantity > max_qty:
            raise ValueError("Invalid quantity")
    except ValueError:
        if lang == "uz":
            await message.answer(f"❌ Iltimos, 1 dan {max_qty} gacha raqam kiriting")
        else:
            await message.answer(f"❌ Введите число от 1 до {max_qty}")
        return

    await state.update_data(quantity=quantity)

    # Check if store has delivery
    store_id = data.get("store_id")
    store = db.get_store(store_id) if store_id else None
    delivery_enabled = get_store_field(store, "delivery_enabled", 0) == 1

    if delivery_enabled:
        # Ask for delivery choice
        await state.set_state(BookOffer.delivery_choice)

        delivery_price = get_store_field(store, "delivery_price", 0)

        kb = InlineKeyboardBuilder()
        if lang == "uz":
            kb.button(text="🏪 O'zim olib ketaman", callback_data="pickup_choice")
            kb.button(
                text=f"🚚 Yetkazib berish ({delivery_price:,} so'm)",
                callback_data="delivery_choice",
            )
        else:
            kb.button(text="🏪 Самовывоз", callback_data="pickup_choice")
            kb.button(text=f"🚚 Доставка ({delivery_price:,} сум)", callback_data="delivery_choice")
        kb.button(
            text="❌ " + ("Bekor qilish" if lang == "uz" else "Отмена"),
            callback_data="cancel_booking_flow",
        )
        kb.adjust(2, 1)

        if lang == "uz":
            text = "📦 Yetkazib berish usulini tanlang:"
        else:
            text = "📦 Выберите способ получения:"

        await message.answer(text, reply_markup=kb.as_markup())
    else:
        # No delivery - go straight to booking
        await state.update_data(delivery_option=0, delivery_cost=0)
        await create_booking(message, state)


@router.callback_query(F.data == "pickup_choice")
async def pickup_choice(callback: types.CallbackQuery, state: FSMContext) -> None:
    """User chose pickup."""
    user_id = callback.from_user.id  # Real user ID from callback
    await state.update_data(delivery_option=0, delivery_cost=0)
    await safe_edit_reply_markup(callback.message)
    await create_booking(callback.message, state, real_user_id=user_id)
    await callback.answer()


@router.callback_query(F.data == "delivery_choice")
async def delivery_choice(callback: types.CallbackQuery, state: FSMContext) -> None:
    """User chose delivery - redirect to OrderDelivery flow."""
    if not db:
        await callback.answer("System error", show_alert=True)
        return

    user_id = callback.from_user.id
    lang = db.get_user_language(user_id)

    # Get data from BookOffer state
    data = await state.get_data()
    offer_id = data.get("offer_id")
    quantity = data.get("quantity", 1)
    store_id = data.get("store_id")
    offer_price = data.get("offer_price", 0)

    # CHECK MIN_ORDER_AMOUNT before allowing delivery
    store = db.get_store(store_id) if store_id else None
    min_order_amount = get_store_field(store, "min_order_amount", 0)
    order_total = offer_price * quantity

    if min_order_amount > 0 and order_total < min_order_amount:
        currency = "сум" if lang == "ru" else "so'm"
        if lang == "uz":
            msg = (
                f"❌ Yetkazib berish uchun minimal buyurtma: {min_order_amount:,} {currency}\n"
                f"Sizning buyurtmangiz: {order_total:,} {currency}\n\n"
                f"Iltimos, miqdorni oshiring yoki olib ketishni tanlang."
            )
        else:
            msg = (
                f"❌ Минимальная сумма для доставки: {min_order_amount:,} {currency}\n"
                f"Ваш заказ: {order_total:,} {currency}\n\n"
                f"Пожалуйста, увеличьте количество или выберите самовывоз."
            )
        await callback.answer(msg, show_alert=True)
        return

    # Transfer to OrderDelivery state (orders.py handles delivery with payment)
    await state.clear()
    await state.update_data(
        offer_id=offer_id,
        store_id=store_id,
        quantity=quantity,
    )
    await state.set_state(OrderDelivery.address)

    await safe_edit_reply_markup(callback.message)

    if lang == "uz":
        text = "📍 Yetkazib berish manzilini kiriting:\n\nMasalan: Chilanzar tumani, 5-mavze, 10-uy"
    else:
        text = "📍 Введите адрес доставки:\n\nНапример: Чиланзарский район, 5-массив, дом 10"

    await callback.message.answer(text, reply_markup=cancel_keyboard(lang))
    await callback.answer()


# NOTE: BookOffer.delivery_address handler removed - delivery now uses OrderDelivery flow
# from handlers/orders.py which handles address -> payment -> order creation


@router.callback_query(F.data == "cancel_booking_flow")
async def cancel_booking_flow(callback: types.CallbackQuery, state: FSMContext) -> None:
    """Cancel booking flow."""
    if not db:
        await callback.answer("System error", show_alert=True)
        return

    user_id = callback.from_user.id
    lang = db.get_user_language(user_id)

    await state.clear()
    await safe_edit_reply_markup(callback.message)
    await callback.message.answer(
        get_text(lang, "action_cancelled"), reply_markup=main_menu_customer(lang)
    )
    await callback.answer()


async def create_booking(
    message: types.Message, state: FSMContext, real_user_id: int | None = None
) -> None:
    """Create the final booking."""
    if not db or not bot:
        await message.answer("System error")
        return

    # Use provided user_id or fallback to message.from_user.id
    # Important: when called from callback, message.from_user is the BOT, not the user!
    user_id = real_user_id if real_user_id else message.from_user.id
    lang = db.get_user_language(user_id)
    data = await state.get_data()

    offer_id = data.get("offer_id")
    quantity = data.get("quantity", 1)
    offer_price = data.get("offer_price", 0)
    offer_title = data.get("offer_title", "Товар")
    store_id = data.get("store_id")

    if not offer_id:
        await message.answer(get_text(lang, "error"))
        await state.clear()
        return

    # Pre-check: verify offer still available before atomic booking
    offer = db.get_offer(offer_id)
    if not offer:
        await message.answer(get_text(lang, "offer_not_found") or "❌ Предложение не найдено")
        await state.clear()
        return

    offer_status = get_offer_field(offer, "status", "inactive")
    offer_qty = get_offer_field(offer, "quantity", 0)

    if offer_status != "active":
        if lang == "uz":
            await message.answer("❌ Bu taklif hozirda mavjud emas. Boshqa taklif tanlang.")
        else:
            await message.answer("❌ Это предложение сейчас недоступно. Выберите другое.")
        await state.clear()
        return

    if offer_qty < quantity:
        if lang == "uz":
            await message.answer(f"❌ Faqat {offer_qty} dona qolgan. Miqdorni kamaytiring.")
        else:
            await message.answer(f"❌ Осталось только {offer_qty} шт. Уменьшите количество.")
        await state.clear()
        return

    # Create booking atomically
    error_reason = None
    try:
        result = db.create_booking_atomic(offer_id, user_id, quantity)
        # Handle both 3-tuple and 4-tuple returns for backward compatibility
        if len(result) == 4:
            ok, booking_id, code, error_reason = result
        else:
            ok, booking_id, code = result
    except Exception as e:
        logger.error(f"Booking creation failed: {e}")
        ok, booking_id, code, error_reason = False, None, None, f"exception:{e}"

    if not ok or not booking_id:
        # Log for debugging with reason
        logger.warning(
            f"create_booking_atomic returned False: offer_id={offer_id}, user_id={user_id}, qty={quantity}, reason={error_reason}"
        )

        # Show specific error message based on reason
        if error_reason and error_reason.startswith("booking_limit:"):
            count = error_reason.split(":")[1]
            error_msg_uz = f"❌ Sizda allaqachon {count} ta faol bron bor (limit: 3)"
            error_msg_ru = f"❌ У вас уже {count} активных бронирований (лимит: 3)"
        elif error_reason and error_reason.startswith("offer_not_found"):
            error_msg_uz = "❌ Taklif topilmadi yoki faol emas"
            error_msg_ru = "❌ Предложение не найдено или неактивно"
        elif error_reason and error_reason.startswith("insufficient_qty:"):
            qty = error_reason.split(":")[1]
            error_msg_uz = f"❌ Yetarli miqdor yo'q. Qolgan: {qty} dona"
            error_msg_ru = f"❌ Недостаточно товара. Осталось: {qty} шт"
        elif error_reason and error_reason.startswith("offer_inactive:"):
            error_msg_uz = "❌ Taklif hozirda faol emas"
            error_msg_ru = "❌ Предложение сейчас неактивно"
        elif error_reason and error_reason.startswith("exception:"):
            error_msg_uz = f"❌ Xatolik yuz berdi: {error_reason}"
            error_msg_ru = f"❌ Произошла ошибка: {error_reason}"
        else:
            error_msg_uz = (
                "❌ Bronlash amalga oshmadi.\n\n"
                "Mumkin sabablar:\n"
                "• Sizda allaqachon 3 ta faol bron bor\n"
                "• Mahsulot allaqachon sotib olingan"
            )
            error_msg_ru = (
                "❌ Не удалось создать бронь.\n\n"
                "Возможные причины:\n"
                "• У вас уже есть 3 активных бронирования\n"
                "• Товар уже забронирован другим покупателем"
            )

        if lang == "uz":
            await message.answer(error_msg_uz)
        else:
            await message.answer(error_msg_ru)
        await state.clear()
        return

    # Update metrics
    if METRICS:
        METRICS["bookings_created"] = METRICS.get("bookings_created", 0) + 1

    logger.info(f"✅ Booking created: id={booking_id}, code={code}, user={user_id}")

    await state.clear()

    # Get store info
    store = db.get_store(store_id) if store_id else None
    store_name = get_store_field(store, "name", "Магазин")
    store_address = get_store_field(store, "address", "")
    owner_id = get_store_field(store, "owner_id")

    # Calculate total (no delivery cost for pickup)
    total = calculate_total(offer_price, quantity, 0)
    currency = "so'm" if lang == "uz" else "сум"

    # Beautiful customer notification with photo
    if lang == "uz":
        customer_msg = (
            f"✅ <b>BRON YUBORILDI!</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n\n"
            f"🛒 <b>{_esc(offer_title)}</b>\n"
            f"📦 Miqdor: <b>{quantity}</b> dona\n"
            f"💰 Jami: <b>{total:,}</b> {currency}\n\n"
            f"🏪 {_esc(store_name)}\n"
            f"📍 {_esc(store_address)}\n\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"⏳ <i>Sotuvchi tasdig'ini kutmoqda...</i>\n"
            f"━━━━━━━━━━━━━━━━━━\n\n"
            f"💡 Tasdiqlangandan so'ng sizga bron kodi va QR kod yuboriladi."
        )
    else:
        customer_msg = (
            f"✅ <b>БРОНЬ ОТПРАВЛЕНА!</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n\n"
            f"🛒 <b>{_esc(offer_title)}</b>\n"
            f"📦 Количество: <b>{quantity}</b> шт\n"
            f"💰 Итого: <b>{total:,}</b> {currency}\n\n"
            f"🏪 {_esc(store_name)}\n"
            f"📍 {_esc(store_address)}\n\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"⏳ <i>Ожидаем подтверждения продавца...</i>\n"
            f"━━━━━━━━━━━━━━━━━━\n\n"
            f"💡 После подтверждения вы получите код бронирования и QR-код."
        )

    # Try to send with photo for beautiful notification
    offer_photo = get_offer_field(offer, "photo") if offer else None
    if offer_photo:
        try:
            await bot.send_photo(
                user_id,
                photo=offer_photo,
                caption=customer_msg,
                parse_mode="HTML",
                reply_markup=main_menu_customer(lang)
            )
        except Exception:
            await message.answer(customer_msg, parse_mode="HTML", reply_markup=main_menu_customer(lang))
    else:
        await message.answer(customer_msg, parse_mode="HTML", reply_markup=main_menu_customer(lang))

    # Notify partner
    if owner_id:
        await notify_partner_new_booking(
            owner_id=owner_id,
            booking_id=booking_id,
            offer_title=offer_title,
            quantity=quantity,
            total=total,
            customer_id=user_id,
            customer_name=message.from_user.first_name,
            offer_photo=offer_photo,
        )


async def notify_partner_new_booking(
    owner_id: int,
    booking_id: int,
    offer_title: str,
    quantity: int,
    total: int,
    customer_id: int,
    customer_name: str,
    offer_photo: str | None = None,
) -> None:
    """Send beautiful booking notification to partner with photo (pickup only)."""
    if not db or not bot:
        return

    partner_lang = db.get_user_language(owner_id)
    customer = get_user_safe(db, customer_id)

    # Use get_user_field for dict/model compatible access
    from .utils import get_user_field

    customer_phone = get_user_field(customer, "phone") or "Не указан"
    customer_username = get_user_field(customer, "username")

    # Contact info
    contact_info = f"@{customer_username}" if customer_username else customer_phone
    currency = "so'm" if partner_lang == "uz" else "сум"

    # Build beautiful notification card
    if partner_lang == "uz":
        text = (
            f"🔔 <b>YANGI BRON!</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n\n"
            f"🛒 <b>{_esc(offer_title)}</b>\n"
            f"📦 Miqdor: <b>{quantity}</b> dona\n"
            f"💰 Jami: <b>{total:,}</b> {currency}\n\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"👤 <b>Xaridor:</b>\n"
            f"   Ism: {_esc(customer_name)}\n"
            f"   📱 <code>{_esc(customer_phone)}</code>\n"
            f"   💬 {_esc(contact_info)}\n\n"
            f"🏪 <b>O'zi olib ketadi</b>\n"
            f"━━━━━━━━━━━━━━━━━━"
        )
        confirm_text = "✅ Tasdiqlash"
        reject_text = "❌ Rad etish"
    else:
        text = (
            f"🔔 <b>НОВАЯ БРОНЬ!</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n\n"
            f"🛒 <b>{_esc(offer_title)}</b>\n"
            f"📦 Количество: <b>{quantity}</b> шт\n"
            f"💰 Итого: <b>{total:,}</b> {currency}\n\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"👤 <b>Покупатель:</b>\n"
            f"   Имя: {_esc(customer_name)}\n"
            f"   📱 <code>{_esc(customer_phone)}</code>\n"
            f"   💬 {_esc(contact_info)}\n\n"
            f"🏪 <b>Самовывоз</b>\n"
            f"━━━━━━━━━━━━━━━━━━"
        )
        confirm_text = "✅ Подтвердить"
        reject_text = "❌ Отклонить"

    kb = InlineKeyboardBuilder()
    kb.button(text=confirm_text, callback_data=f"partner_confirm_{booking_id}")
    kb.button(text=reject_text, callback_data=f"partner_reject_{booking_id}")
    kb.adjust(2)

    try:
        # Try to send with photo first for beautiful card
        if offer_photo:
            try:
                await bot.send_photo(
                    owner_id,
                    photo=offer_photo,
                    caption=text,
                    parse_mode="HTML",
                    reply_markup=kb.as_markup(),
                )
                return
            except Exception as photo_err:
                logger.warning(f"Failed to send photo to partner: {photo_err}")

        # Fallback to text only
        await bot.send_message(owner_id, text, parse_mode="HTML", reply_markup=kb.as_markup())
    except Exception as e:
        logger.error(f"Failed to notify partner {owner_id}: {e}")


# ===================== VIEW BOOKINGS =====================


@router.callback_query(F.data.in_(["bookings_active", "bookings_completed", "bookings_cancelled"]))
async def filter_bookings(callback: types.CallbackQuery) -> None:
    """Show filtered bookings list."""
    if not db:
        await callback.answer("System error", show_alert=True)
        return

    user_id = callback.from_user.id
    lang = db.get_user_language(user_id)

    status_map = {
        "bookings_active": "active",
        "bookings_completed": "completed",
        "bookings_cancelled": "cancelled",
    }
    status = status_map.get(callback.data, "active")

    bookings = db.get_user_bookings_by_status(user_id, status)

    if not bookings:
        await callback.answer(
            get_text(lang, f"no_{status}_bookings") or "Нет бронирований", show_alert=True
        )
        return

    # Build list
    if lang == "uz":
        text = f"📋 <b>Bronlar ({status})</b>\n\n"
    else:
        text = f"📋 <b>Бронирования ({status})</b>\n\n"

    for booking in bookings[:10]:
        b_id = get_booking_field(booking, "booking_id")
        code = get_booking_field(booking, "code")
        qty = get_booking_field(booking, "quantity", 1)
        created = get_booking_field(booking, "created_at", "")

        # Get joined offer info (usually at positions 8+)
        offer_title = (
            booking[8] if isinstance(booking, (list, tuple)) and len(booking) > 8 else "Товар"
        )
        offer_price = booking[9] if isinstance(booking, (list, tuple)) and len(booking) > 9 else 0

        total = int(offer_price * qty)
        code_display = format_booking_code(code, b_id)

        text += (
            f"🍽 <b>{_esc(offer_title)}</b>\n"
            f"📦 {qty} × {int(offer_price):,} = {total:,}\n"
            f"🎫 <code>{code_display}</code>\n"
            f"📅 {created}\n\n"
        )

    await safe_answer_or_send(callback.message, user_id, text, bot=bot, parse_mode="HTML")
    await callback.answer()


# ===================== CANCEL BOOKING =====================


@router.callback_query(F.data.regexp(r"^cancel_booking_\d+$"))
async def cancel_booking_confirm(callback: types.CallbackQuery) -> None:
    """Ask for cancellation confirmation."""
    if not db:
        await callback.answer("System error", show_alert=True)
        return

    user_id = callback.from_user.id
    lang = db.get_user_language(user_id)

    try:
        booking_id = int(callback.data.split("_")[-1])
    except ValueError:
        await callback.answer(get_text(lang, "error"), show_alert=True)
        return

    booking = db.get_booking(booking_id)
    if not booking:
        await callback.answer(get_text(lang, "booking_not_found"), show_alert=True)
        return

    # Check ownership
    if get_booking_field(booking, "user_id") != user_id:
        await callback.answer(get_text(lang, "error"), show_alert=True)
        return

    kb = InlineKeyboardBuilder()
    if lang == "uz":
        kb.button(text="✅ Ha, bekor qilish", callback_data=f"confirm_cancel_{booking_id}")
        kb.button(text="❌ Yo'q", callback_data="noop")
        text = "❓ Bronni bekor qilmoqchimisiz?"
    else:
        kb.button(text="✅ Да, отменить", callback_data=f"confirm_cancel_{booking_id}")
        kb.button(text="❌ Нет", callback_data="noop")
        text = "❓ Вы уверены, что хотите отменить бронирование?"
    kb.adjust(2)

    await safe_answer_or_send(callback.message, user_id, text, bot=bot, reply_markup=kb.as_markup())
    await callback.answer()


@router.callback_query(F.data.regexp(r"^confirm_cancel_\d+$"))
async def confirm_cancel_booking(callback: types.CallbackQuery) -> None:
    """Execute booking cancellation."""
    if not db:
        await callback.answer("System error", show_alert=True)
        return

    user_id = callback.from_user.id
    lang = db.get_user_language(user_id)

    try:
        booking_id = int(callback.data.split("_")[-1])
    except ValueError:
        await callback.answer(get_text(lang, "error"), show_alert=True)
        return

    booking = db.get_booking(booking_id)
    if not booking:
        await callback.answer(get_text(lang, "booking_not_found"), show_alert=True)
        return

    # Check ownership
    if get_booking_field(booking, "user_id") != user_id:
        await callback.answer(get_text(lang, "error"), show_alert=True)
        return

    # Cancel and restore quantity
    success = db.cancel_booking(booking_id)
    if success:
        # Restore offer quantity
        offer_id = get_booking_field(booking, "offer_id")
        qty = get_booking_field(booking, "quantity", 1)
        try:
            db.increment_offer_quantity_atomic(offer_id, int(qty))
        except Exception as e:
            logger.error(f"Failed to restore quantity: {e}")

        await callback.answer(
            get_text(lang, "booking_cancelled") or "Бронирование отменено", show_alert=True
        )
        await safe_edit_reply_markup(callback.message)
    else:
        await callback.answer(get_text(lang, "error"), show_alert=True)


@router.callback_query(F.data == "noop")
async def noop_handler(callback: types.CallbackQuery) -> None:
    """No-operation handler for closing dialogs."""
    await callback.answer()
