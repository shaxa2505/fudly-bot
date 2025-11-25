"""Customer booking handlers - create, view, cancel, rate bookings."""
from __future__ import annotations

import html
from typing import Any, Optional
from datetime import datetime, timedelta, timezone

from aiogram import F, Router, types
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.keyboards import cancel_keyboard, main_menu_customer
from localization import get_text
from logging_config import logger
from handlers.common_states.states import BookOffer

from .utils import (
    safe_answer_or_send,
    safe_edit_reply_markup,
    can_proceed,
    get_store_field,
    get_offer_field,
    get_booking_field,
    get_user_safe,
    format_booking_code,
    calculate_total,
)

router = Router()

# Module dependencies (set via setup_dependencies)
db: Any = None
bot: Any = None
cache: Any = None
METRICS: dict = {}


def setup_dependencies(database: Any, bot_instance: Any, cache_manager: Any = None, metrics: dict = None):
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


# ===================== BOOKING CREATION =====================

@router.callback_query(F.data.startswith("book_"))
async def book_offer_start(callback: types.CallbackQuery, state: FSMContext) -> None:
    """Start booking flow - ask for quantity."""
    if not db or not callback.message:
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
    quantity = get_offer_field(offer, "quantity", 0)
    if quantity <= 0:
        await callback.answer(get_text(lang, "no_offers"), show_alert=True)
        return
    
    # Save to state
    await state.update_data(
        offer_id=offer_id,
        max_quantity=quantity,
        offer_price=get_offer_field(offer, "discount_price", 0),
        offer_title=get_offer_field(offer, "title", "Товар"),
        store_id=get_offer_field(offer, "store_id"),
    )
    await state.set_state(BookOffer.quantity)
    
    # Ask for quantity
    if lang == "uz":
        text = f"📦 Nechta buyurtma qilmoqchisiz? (1-{quantity})"
    else:
        text = f"📦 Сколько хотите забронировать? (1-{quantity})"
    
    await callback.message.answer(text, reply_markup=cancel_keyboard(lang))
    await callback.answer()


@router.message(BookOffer.quantity)
async def book_offer_quantity(message: types.Message, state: FSMContext) -> None:
    """Process quantity input."""
    if not db:
        await message.answer("System error")
        return
    
    user_id = message.from_user.id
    lang = db.get_user_language(user_id)
    text = (message.text or "").strip()
    
    # Check cancel
    if text in ["❌ Отмена", "❌ Bekor qilish", "/cancel"]:
        await state.clear()
        await message.answer(
            get_text(lang, "action_cancelled"),
            reply_markup=main_menu_customer(lang)
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
            kb.button(text=f"🚚 Yetkazib berish ({delivery_price:,} so'm)", callback_data="delivery_choice")
        else:
            kb.button(text="🏪 Самовывоз", callback_data="pickup_choice")
            kb.button(text=f"🚚 Доставка ({delivery_price:,} сум)", callback_data="delivery_choice")
        kb.button(text="❌ " + ("Bekor qilish" if lang == "uz" else "Отмена"), callback_data="cancel_booking_flow")
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
    await state.update_data(delivery_option=0, delivery_cost=0)
    await safe_edit_reply_markup(callback.message)
    await create_booking(callback.message, state)
    await callback.answer()


@router.callback_query(F.data == "delivery_choice")
async def delivery_choice(callback: types.CallbackQuery, state: FSMContext) -> None:
    """User chose delivery - ask for address."""
    if not db:
        await callback.answer("System error", show_alert=True)
        return
    
    user_id = callback.from_user.id
    lang = db.get_user_language(user_id)
    
    data = await state.get_data()
    store_id = data.get("store_id")
    store = db.get_store(store_id) if store_id else None
    delivery_price = get_store_field(store, "delivery_price", 0)
    
    await state.update_data(delivery_option=1, delivery_cost=delivery_price)
    await state.set_state(BookOffer.delivery_address)
    
    await safe_edit_reply_markup(callback.message)
    
    if lang == "uz":
        text = "📍 Yetkazib berish manzilini kiriting:\n\nMasalan: Chilanzar tumani, 5-mavze, 10-uy"
    else:
        text = "📍 Введите адрес доставки:\n\nНапример: Чиланзарский район, 5-массив, дом 10"
    
    await callback.message.answer(text, reply_markup=cancel_keyboard(lang))
    await callback.answer()


@router.message(BookOffer.delivery_address)
async def book_delivery_address(message: types.Message, state: FSMContext) -> None:
    """Process delivery address."""
    if not db:
        await message.answer("System error")
        return
    
    user_id = message.from_user.id
    lang = db.get_user_language(user_id)
    text = (message.text or "").strip()
    
    # Check cancel
    if text in ["❌ Отмена", "❌ Bekor qilish", "/cancel"]:
        await state.clear()
        await message.answer(
            get_text(lang, "action_cancelled"),
            reply_markup=main_menu_customer(lang)
        )
        return
    
    if len(text) < 10:
        if lang == "uz":
            await message.answer("❌ Iltimos, to'liq manzilni kiriting (kamida 10 ta belgi)")
        else:
            await message.answer("❌ Укажите полный адрес (минимум 10 символов)")
        return
    
    await state.update_data(delivery_address=text)
    await create_booking(message, state)


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
        get_text(lang, "action_cancelled"),
        reply_markup=main_menu_customer(lang)
    )
    await callback.answer()


async def create_booking(message: types.Message, state: FSMContext) -> None:
    """Create the final booking."""
    if not db or not bot:
        await message.answer("System error")
        return
    
    user_id = message.from_user.id
    lang = db.get_user_language(user_id)
    data = await state.get_data()
    
    offer_id = data.get("offer_id")
    quantity = data.get("quantity", 1)
    delivery_option = data.get("delivery_option", 0)
    delivery_address = data.get("delivery_address", "")
    delivery_cost = data.get("delivery_cost", 0)
    offer_price = data.get("offer_price", 0)
    offer_title = data.get("offer_title", "Товар")
    store_id = data.get("store_id")
    
    if not offer_id:
        await message.answer(get_text(lang, "error"))
        await state.clear()
        return
    
    # Create booking atomically
    try:
        ok, booking_id, code = db.create_booking_atomic(offer_id, user_id, quantity)
    except Exception as e:
        logger.error(f"Booking creation failed: {e}")
        ok, booking_id, code = False, None, None
    
    if not ok or not booking_id:
        if lang == "uz":
            await message.answer("❌ Afsuski, tanlangan miqdor mavjud emas.")
        else:
            await message.answer("❌ К сожалению, выбранное количество уже недоступно.")
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
    
    # Calculate total
    total = calculate_total(offer_price, quantity, delivery_cost if delivery_option == 1 else 0)
    code_display = format_booking_code(code, booking_id)
    
    # Notify customer
    if delivery_option == 1:
        if lang == "uz":
            customer_msg = (
                f"⏳ <b>Buyurtma yuborildi!</b>\n\n"
                f"🏪 {_esc(store_name)}\n"
                f"📦 {_esc(offer_title)} × {quantity}\n"
                f"🚚 Yetkazib berish: {_esc(delivery_address)}\n"
                f"💰 Jami: {total:,} so'm\n\n"
                f"⚠️ Sotuvchi tasdiqlagandan so'ng sizga xabar beramiz."
            )
        else:
            customer_msg = (
                f"⏳ <b>Заказ отправлен!</b>\n\n"
                f"🏪 {_esc(store_name)}\n"
                f"📦 {_esc(offer_title)} × {quantity}\n"
                f"🚚 Доставка: {_esc(delivery_address)}\n"
                f"💰 Итого: {total:,} сум\n\n"
                f"⚠️ Мы сообщим, когда продавец подтвердит заказ."
            )
    else:
        if lang == "uz":
            customer_msg = (
                f"⏳ <b>Bron yuborildi!</b>\n\n"
                f"🏪 {_esc(store_name)}\n"
                f"📦 {_esc(offer_title)} × {quantity}\n"
                f"📍 Manzil: {_esc(store_address)}\n"
                f"💰 Jami: {total:,} so'm\n\n"
                f"⚠️ Sotuvchi tasdiqlagandan so'ng bron kodi yuboriladi."
            )
        else:
            customer_msg = (
                f"⏳ <b>Бронь отправлена!</b>\n\n"
                f"🏪 {_esc(store_name)}\n"
                f"📦 {_esc(offer_title)} × {quantity}\n"
                f"📍 Адрес: {_esc(store_address)}\n"
                f"💰 Итого: {total:,} сум\n\n"
                f"⚠️ Код бронирования будет отправлен после подтверждения продавцом."
            )
    
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
            delivery_option=delivery_option,
            delivery_address=delivery_address,
        )


async def notify_partner_new_booking(
    owner_id: int,
    booking_id: int,
    offer_title: str,
    quantity: int,
    total: int,
    customer_id: int,
    customer_name: str,
    delivery_option: int = 0,
    delivery_address: str = "",
) -> None:
    """Send new booking notification to partner."""
    if not db or not bot:
        return
    
    partner_lang = db.get_user_language(owner_id)
    customer = get_user_safe(db, customer_id)
    customer_phone = getattr(customer, 'phone', None) or "Не указан"
    
    # Build notification
    delivery_info = ""
    if delivery_option == 1:
        if partner_lang == "uz":
            delivery_info = f"\n🚚 <b>Yetkazib berish:</b> {_esc(delivery_address)}"
        else:
            delivery_info = f"\n🚚 <b>Доставка:</b> {_esc(delivery_address)}"
    
    if partner_lang == "uz":
        text = (
            f"🔔 <b>Yangi buyurtma!</b>\n\n"
            f"📦 {_esc(offer_title)} × {quantity}\n"
            f"💰 {total:,} so'm\n"
            f"👤 {_esc(customer_name)}\n"
            f"📱 <code>{_esc(customer_phone)}</code>"
            f"{delivery_info}"
        )
        confirm_text = "✅ Tasdiqlash"
        reject_text = "❌ Rad etish"
    else:
        text = (
            f"🔔 <b>Новый заказ!</b>\n\n"
            f"📦 {_esc(offer_title)} × {quantity}\n"
            f"💰 {total:,} сум\n"
            f"👤 {_esc(customer_name)}\n"
            f"📱 <code>{_esc(customer_phone)}</code>"
            f"{delivery_info}"
        )
        confirm_text = "✅ Подтвердить"
        reject_text = "❌ Отклонить"
    
    kb = InlineKeyboardBuilder()
    kb.button(text=confirm_text, callback_data=f"partner_confirm_{booking_id}")
    kb.button(text=reject_text, callback_data=f"partner_reject_{booking_id}")
    kb.adjust(2)
    
    try:
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
            get_text(lang, f"no_{status}_bookings") or "Нет бронирований",
            show_alert=True
        )
        return
    
    # Build list
    if lang == "uz":
        text = f"📋 <b>Bronlar ({status})</b>\n\n"
    else:
        text = f"📋 <b>Бронирования ({status})</b>\n\n"
    
    for booking in bookings[:10]:
        b_id = get_booking_field(booking, 'booking_id')
        code = get_booking_field(booking, 'code')
        qty = get_booking_field(booking, 'quantity', 1)
        created = get_booking_field(booking, 'created_at', '')
        
        # Get joined offer info (usually at positions 8+)
        offer_title = booking[8] if isinstance(booking, (list, tuple)) and len(booking) > 8 else "Товар"
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
    if get_booking_field(booking, 'user_id') != user_id:
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
    if get_booking_field(booking, 'user_id') != user_id:
        await callback.answer(get_text(lang, "error"), show_alert=True)
        return
    
    # Cancel and restore quantity
    success = db.cancel_booking(booking_id)
    if success:
        # Restore offer quantity
        offer_id = get_booking_field(booking, 'offer_id')
        qty = get_booking_field(booking, 'quantity', 1)
        try:
            db.increment_offer_quantity_atomic(offer_id, int(qty))
        except Exception as e:
            logger.error(f"Failed to restore quantity: {e}")
        
        await callback.answer(
            get_text(lang, "booking_cancelled") or "Бронирование отменено",
            show_alert=True
        )
        await safe_edit_reply_markup(callback.message)
    else:
        await callback.answer(get_text(lang, "error"), show_alert=True)


@router.callback_query(F.data == "noop")
async def noop_handler(callback: types.CallbackQuery) -> None:
    """No-operation handler for closing dialogs."""
    await callback.answer()
