"""Booking management: view, cancel, rate bookings."""
from aiogram import F, Router, types
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.keyboards import main_menu_customer
from localization import get_text
from logging_config import logger

from handlers.bookings_utils import (
    _safe_answer_or_send,
    get_booking_field,
    get_offer_field,
    get_store_field,
)
from handlers.bookings_create import create_booking_final
from aiogram.fsm.context import FSMContext
from handlers.common_states.states import BookOffer

router = Router()

# Dependencies
db = None
bot = None


def setup_dependencies(database, bot_instance):
    """Setup module dependencies."""
    global db, bot
    db = database
    bot = bot_instance


@router.callback_query(
    F.data.in_(["bookings_active", "bookings_completed", "bookings_cancelled"])
)
async def filter_bookings(callback: types.CallbackQuery) -> None:
    """Filter bookings by status."""
    if not db:
        await callback.answer("System error", show_alert=True)
        return
        
    assert callback.from_user is not None
    lang = db.get_user_language(callback.from_user.id)
    
    status_map = {
        "bookings_active": "active",
        "bookings_completed": "completed", 
        "bookings_cancelled": "cancelled",
    }
    status = status_map.get(callback.data, "active")
    
    bookings = db.get_user_bookings_by_status(callback.from_user.id, status)
    
    if not bookings:
        await callback.answer(get_text(lang, f"no_{status}_bookings"), show_alert=True)
        return
    
    text = f"🛒 <b>{get_text(lang, 'bookings')} ({status})</b>\n\n"
    
    for booking in bookings[:10]:
        booking_id = get_booking_field(booking, 'booking_id')
        offer_title = booking[8] if len(booking) > 8 else "Товар"
        offer_price = booking[9] if len(booking) > 9 else 0
        quantity = get_booking_field(booking, 'quantity', 1)
        booking_code = get_booking_field(booking, 'code', '')
        created_at = get_booking_field(booking, 'created_at', '')
        
        total = int(offer_price * quantity)
        code_display = booking_code if booking_code else ''
        
        text += (f"🍽 <b>{offer_title}</b>\n"
                f"📦 {quantity} шт. × {int(offer_price):,} = {total:,} сум\n"
                f"🎫 <code>{code_display}</code>\n"
                f"📅 {created_at}\n\n")
    
    await _safe_answer_or_send(callback.message, callback.from_user.id, text, parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data.startswith("cancel_booking_"))
async def cancel_booking(callback: types.CallbackQuery) -> None:
    """Cancel booking."""
    if not db:
        await callback.answer("System error", show_alert=True)
        return
        
    assert callback.from_user is not None
    lang = db.get_user_language(callback.from_user.id)
    
    try:
        booking_id = int(callback.data.split("_")[-1])
    except (ValueError, IndexError):
        await callback.answer(get_text(lang, "error"), show_alert=True)
        return
    
    booking = db.get_booking(booking_id)
    if not booking:
        await callback.answer(get_text(lang, "booking_not_found"), show_alert=True)
        return
    
    success = db.cancel_booking(booking_id)
    if success:
        # Return quantity to offer
        offer_id = get_booking_field(booking, "offer_id")
        quantity = get_booking_field(booking, "quantity", 0)
        try:
            db.increment_offer_quantity_atomic(offer_id, int(quantity))
        except Exception as e:
            logger.error(f"Failed to increment offer quantity: {e}")
        
        await callback.answer(get_text(lang, "booking_cancelled"), show_alert=True)
        await filter_bookings(callback)
    else:
        await callback.answer(get_text(lang, "error"), show_alert=True)


@router.callback_query(F.data.startswith("cancel_booking_confirm_"))
async def cancel_booking_confirm(callback: types.CallbackQuery) -> None:
    """Ask user to confirm cancellation from the details view."""
    if not db:
        await callback.answer("System error", show_alert=True)
        return

    assert callback.from_user is not None
    lang = db.get_user_language(callback.from_user.id)
    try:
        booking_id = int(callback.data.rsplit("_", 1)[1])
    except (ValueError, IndexError):
        await callback.answer(get_text(lang, "error"), show_alert=True)
        return

    kb = InlineKeyboardBuilder()
    kb.button(text=("✅ Отменить" if lang == 'ru' else "✅ Bekor qilish"), callback_data=f"do_cancel_booking_{booking_id}")
    kb.button(text=("❌ Закрыть" if lang == 'ru' else "❌ Yopish"), callback_data="noop")
    kb.adjust(1)

    await _safe_answer_or_send(callback.message, callback.from_user.id, get_text(lang, "confirm_cancel") or ("Вы уверены?" if lang == 'ru' else "Haqiqatan bekor qilasizmi?"), reply_markup=kb.as_markup())
    await callback.answer()


@router.callback_query(F.data.startswith("do_cancel_booking_"))
async def do_cancel_booking(callback: types.CallbackQuery) -> None:
    """Perform booking cancellation (user-confirmed)."""
    if not db:
        await callback.answer("System error", show_alert=True)
        return

    assert callback.from_user is not None
    lang = db.get_user_language(callback.from_user.id)
    try:
        booking_id = int(callback.data.rsplit("_", 1)[1])
    except (ValueError, IndexError):
        await callback.answer(get_text(lang, "error"), show_alert=True)
        return

    booking = db.get_booking(booking_id)
    if not booking:
        await callback.answer(get_text(lang, "booking_not_found"), show_alert=True)
        return

    success = db.cancel_booking(booking_id)
    if success:
        await _safe_answer_or_send(callback.message, callback.from_user.id, get_text(lang, "booking_cancelled"), reply_markup=main_menu_customer(lang))
        await callback.answer()
    else:
        await callback.answer(get_text(lang, "error"), show_alert=True)


@router.callback_query(F.data.startswith("partner_confirm_"))
async def partner_confirm(callback: types.CallbackQuery) -> None:
    """Partner confirms a pending booking; set status to 'confirmed' and notify customer."""
    if not db:
        await callback.answer("System error", show_alert=True)
        return

    assert callback.from_user is not None
    lang = db.get_user_language(callback.from_user.id)
    try:
        booking_id = int((callback.data or "").rsplit("_", 1)[-1])
    except (ValueError, IndexError):
        await callback.answer(get_text(lang, "error"), show_alert=True)
        return

    booking = db.get_booking(booking_id)
    if not booking:
        await callback.answer(get_text(lang, "booking_not_found"), show_alert=True)
        return

    try:
        db.update_booking_status(booking_id, 'confirmed')
    except Exception as e:
        logger.error(f"Failed to update booking status to confirmed: {e}")
        await callback.answer(get_text(lang, "error"), show_alert=True)
        return

    # Notify customer
    try:
        user_id = get_booking_field(booking, 'user_id')
        code = get_booking_field(booking, 'booking_code') or get_booking_field(booking, 'code') or str(booking_id)
        product_title = None
        offer = None
        offer_id = get_booking_field(booking, 'offer_id')
        if offer_id:
            offer = db.get_offer(offer_id)
            product_title = get_offer_field(offer, 'title', '')

        text = f"✅ {get_text('ru', 'booking_confirmed') if lang == 'ru' else get_text('uz', 'booking_confirmed') or 'Ваша бронь подтверждена'}\n\n"
        text += f"🎫 <code>{code}</code>\n"
        if product_title:
            text += f"📦 {product_title}\n"

        from bot import bot as global_bot
        await _safe_answer_or_send(None, user_id, text, parse_mode='HTML')
    except Exception as e:
        logger.error(f"Failed to notify customer after partner confirm: {e}")

    await callback.answer(get_text(lang, "partner_confirmed") or ("Подтверждено" if lang == 'ru' else "Tasdiqlandi"))


@router.callback_query(F.data.startswith("partner_reject_"))
async def partner_reject(callback: types.CallbackQuery) -> None:
    """Partner rejects a booking; cancel and notify customer."""
    if not db:
        await callback.answer("System error", show_alert=True)
        return

    assert callback.from_user is not None
    lang = db.get_user_language(callback.from_user.id)
    try:
        booking_id = int((callback.data or "").rsplit("_", 1)[-1])
    except (ValueError, IndexError):
        await callback.answer(get_text(lang, "error"), show_alert=True)
        return

    booking = db.get_booking(booking_id)
    if not booking:
        await callback.answer(get_text(lang, "booking_not_found"), show_alert=True)
        return

    try:
        success = db.cancel_booking(booking_id)
    except Exception as e:
        logger.error(f"Failed to cancel booking via partner_reject: {e}")
        await callback.answer(get_text(lang, "error"), show_alert=True)
        return

    if success:
        # Notify customer
        try:
            user_id = get_booking_field(booking, 'user_id')
            code = get_booking_field(booking, 'booking_code') or get_booking_field(booking, 'code') or str(booking_id)
            await _safe_answer_or_send(None, user_id, f"❌ {get_text('ru', 'booking_rejected') if lang == 'ru' else get_text('uz', 'booking_rejected') or 'Бронь отклонена'}\n\n🎫 <code>{code}</code>", parse_mode='HTML')
        except Exception as e:
            logger.error(f"Failed to notify customer after partner reject: {e}")

        await callback.answer(get_text(lang, "partner_rejected") or ("Отклонено" if lang == 'ru' else "Rad etildi"))
    else:
        await callback.answer(get_text(lang, "error"), show_alert=True)


@router.callback_query(F.data.startswith("booking_details_"))
async def booking_details(callback: types.CallbackQuery) -> None:
    """Show booking details."""
    if not db:
        await callback.answer("System error", show_alert=True)
        return
        
    assert callback.from_user is not None
    lang = db.get_user_language(callback.from_user.id)
    
    try:
        booking_id = int(callback.data.split("_")[-1])
    except (ValueError, IndexError):
        await callback.answer(get_text(lang, "error"), show_alert=True)
        return
    
    booking = db.get_booking(booking_id)
    if not booking:
        await callback.answer(get_text(lang, "booking_not_found"), show_alert=True)
        return
    
    # Extract booking details
    offer_id = get_booking_field(booking, "offer_id")
    quantity = get_booking_field(booking, "quantity", 1)
    code = get_booking_field(booking, "code", "")
    created_at = get_booking_field(booking, "created_at", "")
    
    offer = db.get_offer(offer_id) if offer_id else None
    if offer:
        offer_title = get_offer_field(offer, "title", "Товар")
        offer_price = get_offer_field(offer, "discount_price", 0)
        store_name = get_offer_field(offer, "store_name", "Магазин")
        offer_address = get_offer_field(offer, "address", "")
    else:
        offer_title = "Товар"
        offer_price = 0
        store_name = "Магазин" 
        offer_address = ""
    
    if not offer_address and offer:
        store_id = get_offer_field(offer, "store_id")
        if store_id:
            store = db.get_store(store_id)
            if store:
                offer_address = get_store_field(store, "address", "")
    
    if not offer_address:
        offer_address = "Адрес не указан" if lang == 'ru' else "Manzil ko'rsatilmagan"
    
    total = int(offer_price * quantity)
    currency = "сум" if lang == 'ru' else "so'm"
    code_display = code if code else str(booking_id)
    
    text = (f"🏪 <b>{store_name}</b>\n\n"
           f"<b>{offer_title.upper()}</b>\n\n"
           f"💵 <b>Цена за ед.:</b> {int(offer_price):,} {currency}\n"
           f"💰 <b>Сумма:</b> {total:,} {currency}\n"
           f"📍 <b>Адрес получения:</b> {offer_address}\n\n"
           f"🎫 <code>{code_display}</code>\n"
           f"📅 {created_at}")
    
    kb = InlineKeyboardBuilder()
    kb.button(text="❌ Отменить" if lang == 'ru' else "❌ Bekor qilish", 
             callback_data=f"cancel_booking_confirm_{booking_id}")
    kb.button(text="❌ Закрыть" if lang == 'ru' else "❌ Yopish", 
             callback_data="noop")
    kb.adjust(1)
    
    await _safe_answer_or_send(callback.message, callback.from_user.id, text, 
                              parse_mode="HTML", reply_markup=kb.as_markup())
    await callback.answer()


@router.callback_query(F.data.startswith("select_pickup_"))
async def select_pickup_callback(callback: types.CallbackQuery, state: FSMContext) -> None:
    """Handle user selecting a pickup slot from the inline keyboard."""
    if not db:
        await callback.answer("System error", show_alert=True)
        return

    assert callback.from_user is not None
    lang = db.get_user_language(callback.from_user.id)

    try:
        epoch = int(callback.data.rsplit("_", 1)[1])
    except (ValueError, IndexError):
        await callback.answer(get_text(lang, "error"), show_alert=True)
        return

    from datetime import datetime, timezone
    # Convert epoch to iso string
    dt = datetime.fromtimestamp(epoch)
    pickup_time_iso = dt.isoformat()

    try:
        # Save to state and proceed with final booking creation
        # DO NOT clear the state before calling create_booking_final — it needs to read the saved data.
        await state.update_data(pickup_time=pickup_time_iso)
        # Call create_booking_final using the callback message as the origin
        await create_booking_final(callback.message, state)
    except Exception as e:
        logger.error(f"Error handling pickup selection: {e}")
        await callback.answer(get_text(lang, "error"), show_alert=True)
        return

    await callback.answer()


@router.callback_query(F.data.startswith("noop"))
async def noop_callback(callback: types.CallbackQuery) -> None:
    """No-op callback."""
    try:
        await callback.answer()
    except Exception:
        pass
__all__ = [
    "filter_bookings",
    "cancel_booking",
    "cancel_booking_confirm",
    "do_cancel_booking",
    "partner_confirm",
    "partner_reject",
    "booking_details",
    "noop_callback",
    "setup_dependencies",
]
