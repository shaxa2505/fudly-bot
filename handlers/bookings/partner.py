"""Partner booking handlers - confirm, reject, complete bookings."""
from __future__ import annotations

import html
from typing import Any

from aiogram import F, Router, types
from aiogram.utils.keyboard import InlineKeyboardBuilder

from localization import get_text
from logging_config import logger

from .utils import (
    safe_answer_or_send,
    safe_edit_reply_markup,
    get_store_field,
    get_offer_field,
    get_booking_field,
    format_booking_code,
)

router = Router()

# Module dependencies
db: Any = None
bot: Any = None


def setup_dependencies(database: Any, bot_instance: Any):
    """Setup module dependencies."""
    global db, bot
    db = database
    bot = bot_instance


def _esc(val: Any) -> str:
    """HTML-escape helper."""
    if val is None:
        return ""
    return html.escape(str(val))


# ===================== PARTNER CONFIRM/REJECT =====================

@router.callback_query(F.data.regexp(r"^partner_confirm_\d+$"))
async def partner_confirm_booking(callback: types.CallbackQuery) -> None:
    """Partner confirms a booking."""
    if not db or not bot:
        await callback.answer("System error", show_alert=True)
        return
    
    partner_id = callback.from_user.id
    lang = db.get_user_language(partner_id)
    
    try:
        booking_id = int(callback.data.split("_")[-1])
    except ValueError:
        await callback.answer(get_text(lang, "error"), show_alert=True)
        return
    
    booking = db.get_booking(booking_id)
    if not booking:
        await callback.answer(get_text(lang, "booking_not_found"), show_alert=True)
        return
    
    # Verify ownership
    offer_id = get_booking_field(booking, 'offer_id')
    offer = db.get_offer(offer_id) if offer_id else None
    store_id = get_offer_field(offer, 'store_id') if offer else None
    store = db.get_store(store_id) if store_id else None
    owner_id = get_store_field(store, 'owner_id')
    
    if partner_id != owner_id:
        await callback.answer(get_text(lang, "error"), show_alert=True)
        return
    
    # Confirm booking
    try:
        db.update_booking_status(booking_id, 'confirmed')
        db.mark_reminder_sent(booking_id)  # Prevent reminder spam
    except Exception as e:
        logger.error(f"Failed to confirm booking: {e}")
        await callback.answer(get_text(lang, "error"), show_alert=True)
        return
    
    # Notify customer
    customer_id = get_booking_field(booking, 'user_id')
    code = get_booking_field(booking, 'code')
    code_display = format_booking_code(code, booking_id)
    
    if customer_id:
        customer_lang = db.get_user_language(customer_id)
        store_name = get_store_field(store, 'name', 'Магазин')
        store_address = get_store_field(store, 'address', '')
        
        if customer_lang == "uz":
            customer_msg = (
                f"✅ <b>Broningiz tasdiqlandi!</b>\n\n"
                f"🏪 {_esc(store_name)}\n"
                f"📍 Manzil: {_esc(store_address)}\n"
                f"🎫 Bron kodi: <code>{code_display}</code>\n\n"
                f"⚠️ Ushbu kodni sotuvchiga ko'rsating."
            )
        else:
            customer_msg = (
                f"✅ <b>Ваша бронь подтверждена!</b>\n\n"
                f"🏪 {_esc(store_name)}\n"
                f"📍 Адрес: {_esc(store_address)}\n"
                f"🎫 Код бронирования: <code>{code_display}</code>\n\n"
                f"⚠️ Покажите этот код продавцу при получении."
            )
        
        try:
            await bot.send_message(customer_id, customer_msg, parse_mode="HTML")
        except Exception as e:
            logger.error(f"Failed to notify customer {customer_id}: {e}")
    
    # Update partner's message
    await safe_edit_reply_markup(callback.message)
    
    # Add complete/cancel buttons
    kb = InlineKeyboardBuilder()
    if lang == "uz":
        kb.button(text="✅ Berildi", callback_data=f"complete_booking_{booking_id}")
        kb.button(text="❌ Bekor qilish", callback_data=f"partner_cancel_{booking_id}")
    else:
        kb.button(text="✅ Выдано", callback_data=f"complete_booking_{booking_id}")
        kb.button(text="❌ Отменить", callback_data=f"partner_cancel_{booking_id}")
    kb.adjust(2)
    
    if lang == "uz":
        text = f"✅ Bron #{booking_id} tasdiqlandi.\n\n📋 Mijoz kelganda 'Berildi' tugmasini bosing."
    else:
        text = f"✅ Бронь #{booking_id} подтверждена.\n\n📋 Нажмите 'Выдано' когда клиент заберёт заказ."
    
    await safe_answer_or_send(callback.message, partner_id, text, bot=bot, reply_markup=kb.as_markup())
    await callback.answer(get_text(lang, "booking_confirmed") or "Подтверждено")


@router.callback_query(F.data.regexp(r"^partner_reject_\d+$"))
async def partner_reject_booking(callback: types.CallbackQuery) -> None:
    """Partner rejects a booking."""
    if not db or not bot:
        await callback.answer("System error", show_alert=True)
        return
    
    partner_id = callback.from_user.id
    lang = db.get_user_language(partner_id)
    
    try:
        booking_id = int(callback.data.split("_")[-1])
    except ValueError:
        await callback.answer(get_text(lang, "error"), show_alert=True)
        return
    
    booking = db.get_booking(booking_id)
    if not booking:
        await callback.answer(get_text(lang, "booking_not_found"), show_alert=True)
        return
    
    # Verify ownership
    offer_id = get_booking_field(booking, 'offer_id')
    offer = db.get_offer(offer_id) if offer_id else None
    store_id = get_offer_field(offer, 'store_id') if offer else None
    store = db.get_store(store_id) if store_id else None
    owner_id = get_store_field(store, 'owner_id')
    
    if partner_id != owner_id:
        await callback.answer(get_text(lang, "error"), show_alert=True)
        return
    
    # Cancel booking and restore quantity
    try:
        db.cancel_booking(booking_id)
        qty = get_booking_field(booking, 'quantity', 1)
        db.increment_offer_quantity_atomic(offer_id, int(qty))
    except Exception as e:
        logger.error(f"Failed to reject booking: {e}")
        await callback.answer(get_text(lang, "error"), show_alert=True)
        return
    
    # Notify customer
    customer_id = get_booking_field(booking, 'user_id')
    if customer_id:
        customer_lang = db.get_user_language(customer_id)
        
        if customer_lang == "uz":
            customer_msg = "❌ Afsuski, broningiz sotuvchi tomonidan rad etildi."
        else:
            customer_msg = "❌ К сожалению, продавец отклонил вашу бронь."
        
        try:
            await bot.send_message(customer_id, customer_msg)
        except Exception as e:
            logger.error(f"Failed to notify customer {customer_id}: {e}")
    
    # Update partner's message
    await safe_edit_reply_markup(callback.message)
    
    if lang == "uz":
        text = f"❌ Bron #{booking_id} rad etildi."
    else:
        text = f"❌ Бронь #{booking_id} отклонена."
    
    await safe_answer_or_send(callback.message, partner_id, text, bot=bot)
    await callback.answer(get_text(lang, "booking_rejected") or "Отклонено")


# ===================== COMPLETE BOOKING =====================

@router.callback_query(F.data.regexp(r"^complete_booking_\d+$"))
async def complete_booking(callback: types.CallbackQuery) -> None:
    """Partner marks booking as completed (item handed to customer)."""
    if not db or not bot:
        await callback.answer("System error", show_alert=True)
        return
    
    partner_id = callback.from_user.id
    lang = db.get_user_language(partner_id)
    
    try:
        booking_id = int(callback.data.split("_")[-1])
    except ValueError:
        await callback.answer(get_text(lang, "error"), show_alert=True)
        return
    
    booking = db.get_booking(booking_id)
    if not booking:
        await callback.answer(get_text(lang, "booking_not_found"), show_alert=True)
        return
    
    # Verify ownership
    offer_id = get_booking_field(booking, 'offer_id')
    offer = db.get_offer(offer_id) if offer_id else None
    store_id = get_offer_field(offer, 'store_id') if offer else None
    store = db.get_store(store_id) if store_id else None
    owner_id = get_store_field(store, 'owner_id')
    
    if partner_id != owner_id:
        await callback.answer(get_text(lang, "error"), show_alert=True)
        return
    
    # Complete booking
    try:
        db.complete_booking(booking_id)
    except Exception as e:
        logger.error(f"Failed to complete booking: {e}")
        await callback.answer(get_text(lang, "error"), show_alert=True)
        return
    
    # Notify customer
    customer_id = get_booking_field(booking, 'user_id')
    if customer_id:
        customer_lang = db.get_user_language(customer_id)
        
        kb = InlineKeyboardBuilder()
        if customer_lang == "uz":
            customer_msg = "🎉 <b>Buyurtma topshirildi!</b>\n\nRahmat! Qanday bo'ldi? Baholang:"
            for i in range(1, 6):
                kb.button(text="⭐" * i, callback_data=f"rate_booking_{booking_id}_{i}")
        else:
            customer_msg = "🎉 <b>Заказ выдан!</b>\n\nСпасибо! Как вам? Оцените:"
            for i in range(1, 6):
                kb.button(text="⭐" * i, callback_data=f"rate_booking_{booking_id}_{i}")
        kb.adjust(5)
        
        try:
            await bot.send_message(customer_id, customer_msg, parse_mode="HTML", reply_markup=kb.as_markup())
        except Exception as e:
            logger.error(f"Failed to notify customer {customer_id}: {e}")
    
    # Update partner's message
    await safe_edit_reply_markup(callback.message)
    
    if lang == "uz":
        text = f"✅ Bron #{booking_id} yakunlandi!"
    else:
        text = f"✅ Бронь #{booking_id} завершена!"
    
    await safe_answer_or_send(callback.message, partner_id, text, bot=bot)
    await callback.answer(get_text(lang, "booking_completed") or "Завершено")


@router.callback_query(F.data.regexp(r"^partner_cancel_\d+$"))
async def partner_cancel_booking(callback: types.CallbackQuery) -> None:
    """Partner cancels an already confirmed booking."""
    if not db or not bot:
        await callback.answer("System error", show_alert=True)
        return
    
    partner_id = callback.from_user.id
    lang = db.get_user_language(partner_id)
    
    try:
        booking_id = int(callback.data.split("_")[-1])
    except ValueError:
        await callback.answer(get_text(lang, "error"), show_alert=True)
        return
    
    booking = db.get_booking(booking_id)
    if not booking:
        await callback.answer(get_text(lang, "booking_not_found"), show_alert=True)
        return
    
    # Verify ownership
    offer_id = get_booking_field(booking, 'offer_id')
    offer = db.get_offer(offer_id) if offer_id else None
    store_id = get_offer_field(offer, 'store_id') if offer else None
    store = db.get_store(store_id) if store_id else None
    owner_id = get_store_field(store, 'owner_id')
    
    if partner_id != owner_id:
        await callback.answer(get_text(lang, "error"), show_alert=True)
        return
    
    # Cancel and restore
    try:
        db.cancel_booking(booking_id)
        qty = get_booking_field(booking, 'quantity', 1)
        db.increment_offer_quantity_atomic(offer_id, int(qty))
    except Exception as e:
        logger.error(f"Failed to cancel booking: {e}")
        await callback.answer(get_text(lang, "error"), show_alert=True)
        return
    
    # Notify customer
    customer_id = get_booking_field(booking, 'user_id')
    if customer_id:
        customer_lang = db.get_user_language(customer_id)
        
        if customer_lang == "uz":
            customer_msg = "❌ Afsuski, broningiz sotuvchi tomonidan bekor qilindi."
        else:
            customer_msg = "❌ К сожалению, продавец отменил вашу бронь."
        
        try:
            await bot.send_message(customer_id, customer_msg)
        except Exception as e:
            logger.error(f"Failed to notify customer {customer_id}: {e}")
    
    await safe_edit_reply_markup(callback.message)
    
    if lang == "uz":
        text = f"❌ Bron #{booking_id} bekor qilindi."
    else:
        text = f"❌ Бронь #{booking_id} отменена."
    
    await safe_answer_or_send(callback.message, partner_id, text, bot=bot)
    await callback.answer()


# ===================== RATING =====================

@router.callback_query(F.data.regexp(r"^rate_booking_\d+_\d+$"))
async def rate_booking(callback: types.CallbackQuery) -> None:
    """Customer rates a completed booking."""
    if not db:
        await callback.answer("System error", show_alert=True)
        return
    
    user_id = callback.from_user.id
    lang = db.get_user_language(user_id)
    
    try:
        parts = callback.data.split("_")
        booking_id = int(parts[2])
        rating = int(parts[3])
    except (ValueError, IndexError):
        await callback.answer(get_text(lang, "error"), show_alert=True)
        return
    
    if rating < 1 or rating > 5:
        await callback.answer(get_text(lang, "error"), show_alert=True)
        return
    
    booking = db.get_booking(booking_id)
    if not booking:
        await callback.answer(get_text(lang, "booking_not_found"), show_alert=True)
        return
    
    # Verify it's the customer
    if get_booking_field(booking, 'user_id') != user_id:
        await callback.answer(get_text(lang, "error"), show_alert=True)
        return
    
    # Save rating
    offer_id = get_booking_field(booking, 'offer_id')
    offer = db.get_offer(offer_id) if offer_id else None
    store_id = get_offer_field(offer, 'store_id') if offer else None
    
    try:
        db.add_rating(booking_id, user_id, store_id, rating)
    except Exception as e:
        logger.error(f"Failed to save rating: {e}")
        await callback.answer(get_text(lang, "error"), show_alert=True)
        return
    
    await safe_edit_reply_markup(callback.message)
    
    if lang == "uz":
        text = f"⭐ Rahmat! Siz {rating} ball berdingiz."
    else:
        text = f"⭐ Спасибо! Вы поставили {rating} {'звезду' if rating == 1 else 'звезды' if rating < 5 else 'звёзд'}."
    
    await safe_answer_or_send(callback.message, user_id, text, bot=bot)
    await callback.answer(get_text(lang, "rating_saved") or "Оценка сохранена")
