"""Partner booking handlers - confirm, reject, complete bookings."""
from __future__ import annotations

import html
from typing import Any

from aiogram import F, Router, types
from aiogram.fsm.context import FSMContext
from aiogram.types import BufferedInputFile
from aiogram.utils.keyboard import InlineKeyboardBuilder

from handlers.common.states import RateBooking
from localization import get_text
from logging_config import logger

from .utils import (
    format_booking_code,
    get_booking_field,
    get_offer_field,
    get_store_field,
    safe_answer_or_send,
    safe_edit_reply_markup,
)

# QR code generator
try:
    from app.core.qr_generator import generate_booking_qr

    QR_ENABLED = True
except ImportError:
    QR_ENABLED = False
    generate_booking_qr = None

router = Router()

# Module dependencies
db: Any = None
bot: Any = None
bot_username: str = "fudly_bot"  # Default, will be updated from bot.get_me()


def setup_dependencies(database: Any, bot_instance: Any):
    """Setup module dependencies."""
    global db, bot, bot_username
    db = database
    bot = bot_instance
    # Bot username will be fetched dynamically when generating QR
    logger.info(f"Partner module initialized, default bot_username: {bot_username}")


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
    offer_id = get_booking_field(booking, "offer_id")
    offer = db.get_offer(offer_id) if offer_id else None
    store_id = get_offer_field(offer, "store_id") if offer else None
    store = db.get_store(store_id) if store_id else None
    owner_id = get_store_field(store, "owner_id")

    if partner_id != owner_id:
        await callback.answer(get_text(lang, "error"), show_alert=True)
        return

    # Confirm booking
    try:
        db.update_booking_status(booking_id, "confirmed")
        db.mark_reminder_sent(booking_id)  # Prevent reminder spam
    except Exception as e:
        logger.error(f"Failed to confirm booking: {e}")
        await callback.answer(get_text(lang, "error"), show_alert=True)
        return

    # Notify customer - OPTIMIZED: single message with QR + all info
    customer_id = get_booking_field(booking, "user_id")
    code = get_booking_field(booking, "code")
    code_display = format_booking_code(code, booking_id)

    if customer_id:
        customer_lang = db.get_user_language(customer_id)
        store_name = get_store_field(store, "name", "Магазин")
        store_address = get_store_field(store, "address", "")

        # Compact single message with all info
        if customer_lang == "uz":
            customer_msg = (
                f"✅ <b>Broningiz tasdiqlandi!</b>\n\n"
                f"🏪 {_esc(store_name)}\n"
                f"📍 Manzil: {_esc(store_address)}\n\n"
                f"━━━━━━━━━━\n"
                f"🎫 <b>Bron kodi:</b>\n"
                f"<code>{code_display}</code>\n"
                f"━━━━━━━━━━\n\n"
                f"⚠️ Ushbu kodni yoki QR kodni sotuvchiga ko'rsating."
            )
        else:
            customer_msg = (
                f"✅ <b>Broningiz tasdiqlandi!</b>\n\n"
                f"🏪 {_esc(store_name)}\n"
                f"📍 Manzil: {_esc(store_address)}\n\n"
                f"━━━━━━━━━━\n"
                f"🎫 <b>Bron kodi:</b>\n"
                f"<code>{code_display}</code>\n"
                f"━━━━━━━━━━\n\n"
                f"⚠️ Ushbu kodni yoki QR kodni sotuvchiga ko'rsating."
            )

        try:
            # Single message with QR code - no separate messages
            qr_sent = False
            if QR_ENABLED and generate_booking_qr:
                try:
                    bot_info = await bot.get_me()
                    current_bot_username = bot_info.username or bot_username
                except Exception:
                    current_bot_username = bot_username

                qr_image = generate_booking_qr(
                    code or str(booking_id), booking_id, bot_username=current_bot_username
                )
                if qr_image:
                    try:
                        qr_file = BufferedInputFile(
                            qr_image.read(), filename=f"booking_{booking_id}_qr.png"
                        )
                        await bot.send_photo(
                            customer_id, qr_file, caption=customer_msg, parse_mode="HTML"
                        )
                        qr_sent = True
                    except Exception as qr_e:
                        logger.warning(f"Failed to send QR: {qr_e}")

            if not qr_sent:
                await bot.send_message(customer_id, customer_msg, parse_mode="HTML")

        except Exception as e:
            error_msg = str(e).lower()
            if "bot" in error_msg or "blocked" in error_msg or "deactivated" in error_msg:
                logger.warning(f"Cannot notify customer {customer_id}: {e}")
            else:
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
        text = f"✅ Bron #{booking_id} tasdiqlandi.\n📋 Mijoz kelganda 'Berildi' tugmasini bosing."
    else:
        text = f"✅ Бронь #{booking_id} подтверждена.\n📋 Нажмите 'Выдано' когда клиент заберёт."

    await safe_answer_or_send(
        callback.message, partner_id, text, bot=bot, reply_markup=kb.as_markup()
    )
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
    offer_id = get_booking_field(booking, "offer_id")
    offer = db.get_offer(offer_id) if offer_id else None
    store_id = get_offer_field(offer, "store_id") if offer else None
    store = db.get_store(store_id) if store_id else None
    owner_id = get_store_field(store, "owner_id")

    if partner_id != owner_id:
        await callback.answer(get_text(lang, "error"), show_alert=True)
        return

    # Cancel booking and restore quantity
    try:
        db.cancel_booking(booking_id)
        qty = get_booking_field(booking, "quantity", 1)
        db.increment_offer_quantity_atomic(offer_id, int(qty))
    except Exception as e:
        logger.error(f"Failed to reject booking: {e}")
        await callback.answer(get_text(lang, "error"), show_alert=True)
        return

    # Notify customer
    customer_id = get_booking_field(booking, "user_id")
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
    offer_id = get_booking_field(booking, "offer_id")
    offer = db.get_offer(offer_id) if offer_id else None
    store_id = get_offer_field(offer, "store_id") if offer else None
    store = db.get_store(store_id) if store_id else None
    owner_id = get_store_field(store, "owner_id")

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
    customer_id = get_booking_field(booking, "user_id")
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
            await bot.send_message(
                customer_id, customer_msg, parse_mode="HTML", reply_markup=kb.as_markup()
            )
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
    offer_id = get_booking_field(booking, "offer_id")
    offer = db.get_offer(offer_id) if offer_id else None
    store_id = get_offer_field(offer, "store_id") if offer else None
    store = db.get_store(store_id) if store_id else None
    owner_id = get_store_field(store, "owner_id")

    if partner_id != owner_id:
        await callback.answer(get_text(lang, "error"), show_alert=True)
        return

    # Cancel and restore
    try:
        db.cancel_booking(booking_id)
        qty = get_booking_field(booking, "quantity", 1)
        db.increment_offer_quantity_atomic(offer_id, int(qty))
    except Exception as e:
        logger.error(f"Failed to cancel booking: {e}")
        await callback.answer(get_text(lang, "error"), show_alert=True)
        return

    # Notify customer
    customer_id = get_booking_field(booking, "user_id")
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


# ===================== RATING (OPTIMIZED - single message) =====================


@router.callback_query(F.data.regexp(r"^rate_booking_\d+_\d+$"))
async def rate_booking(callback: types.CallbackQuery, state: FSMContext) -> None:
    """Customer rates - save immediately, show optional review inline."""
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

    if get_booking_field(booking, "user_id") != user_id:
        await callback.answer(get_text(lang, "error"), show_alert=True)
        return

    # Save rating immediately (without review)
    offer_id = get_booking_field(booking, "offer_id")
    offer = db.get_offer(offer_id) if offer_id else None
    store_id = get_offer_field(offer, "store_id") if offer else None

    try:
        db.add_rating(booking_id, user_id, store_id, rating, None)
    except Exception as e:
        logger.error(f"Failed to save rating: {e}")

    # Update the SAME message with thanks + optional review prompt
    stars = "⭐" * rating
    kb = InlineKeyboardBuilder()
    kb.button(
        text="📝 Sharh qoldirish" if lang == "uz" else "📝 Оставить отзыв",
        callback_data=f"add_review_{booking_id}"
    )
    kb.adjust(1)

    thanks = "Rahmat!" if lang == "uz" else "Спасибо!"
    try:
        await callback.message.edit_text(
            f"⭐ {thanks} Siz {rating} ball berdingiz." if lang == "uz" else f"⭐ {thanks} Вы поставили {rating} {'звезду' if rating == 1 else 'звезды' if rating < 5 else 'звёзд'}.",
            reply_markup=kb.as_markup()
        )
    except Exception:
        pass

    await callback.answer(f"{stars} {thanks}")


@router.callback_query(F.data.regexp(r"^add_review_\d+$"))
async def add_review_prompt(callback: types.CallbackQuery, state: FSMContext) -> None:
    """User wants to add optional text review."""
    if not db:
        await callback.answer("Error", show_alert=True)
        return

    user_id = callback.from_user.id
    lang = db.get_user_language(user_id)

    try:
        booking_id = int(callback.data.split("_")[-1])
    except (ValueError, IndexError):
        await callback.answer("Error", show_alert=True)
        return

    await state.update_data(booking_id=booking_id)
    await state.set_state(RateBooking.review_text)

    prompt = "Sharh yozing:" if lang == "uz" else "Напишите отзыв:"
    try:
        await callback.message.edit_text(f"📝 {prompt}")
    except Exception:
        pass
    await callback.answer()


@router.message(RateBooking.review_text)
async def process_review_text(message: types.Message, state: FSMContext) -> None:
    """Process the text review from customer."""
    if not db or not bot:
        await message.answer("System error")
        return

    user_id = message.from_user.id
    lang = db.get_user_language(user_id)
    review_text = (message.text or "").strip()[:500]  # Limit

    data = await state.get_data()
    booking_id = data.get("booking_id")

    if not booking_id:
        await state.clear()
        return

    # Update rating with review text
    try:
        db.update_rating_review(booking_id, user_id, review_text)
    except Exception as e:
        logger.error(f"Failed to update review: {e}")

    await state.clear()

    thanks = "Rahmat! Sharh saqlandi." if lang == "uz" else "Спасибо! Отзыв сохранён."
    from app.keyboards import main_menu_customer
    await message.answer(f"✅ {thanks}", reply_markup=main_menu_customer(lang))


@router.callback_query(F.data.regexp(r"^skip_review_\d+$"))
async def skip_review(callback: types.CallbackQuery, state: FSMContext) -> None:
    """Skip text review and save rating only."""
    if not db or not bot:
        await callback.answer("System error", show_alert=True)
        return

    user_id = callback.from_user.id
    lang = db.get_user_language(user_id)

    # Get saved data
    data = await state.get_data()
    booking_id = data.get("booking_id")
    rating = data.get("rating")

    if not booking_id or not rating:
        await state.clear()
        await callback.answer(get_text(lang, "error"), show_alert=True)
        return

    # Save rating without comment
    booking = db.get_booking(booking_id)
    if not booking:
        await state.clear()
        await callback.answer(get_text(lang, "booking_not_found"), show_alert=True)
        return

    offer_id = get_booking_field(booking, "offer_id")
    offer = db.get_offer(offer_id) if offer_id else None
    store_id = get_offer_field(offer, "store_id") if offer else None

    try:
        db.add_rating(booking_id, user_id, store_id, rating)
    except Exception as e:
        logger.error(f"Failed to save rating: {e}")
        await state.clear()
        await callback.answer(get_text(lang, "error"), show_alert=True)
        return

    await state.clear()
    await safe_edit_reply_markup(callback.message)

    if lang == "uz":
        text = f"⭐ Rahmat! Siz {rating} ball berdingiz."
    else:
        text = f"⭐ Спасибо! Вы поставили {rating} {'звезду' if rating == 1 else 'звезды' if rating < 5 else 'звёзд'}."

    await safe_answer_or_send(callback.message, user_id, text, bot=bot)
    await callback.answer(get_text(lang, "rating_saved") or "Оценка сохранена")
