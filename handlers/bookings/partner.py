"""Partner booking handlers - confirm, reject, complete bookings."""
from __future__ import annotations

from typing import Any

from aiogram import F, Router, types
from aiogram.fsm.context import FSMContext
from aiogram.types import BufferedInputFile
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.services.unified_order_service import (
    OrderStatus,
    get_unified_order_service,
    init_unified_order_service,
)
from handlers.common.states import RateBooking
from handlers.common.utils import can_manage_store, html_escape as _esc, resolve_offer_photo
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
bot_username: str = "fudlyuzbot"  # Default, will be updated from bot.get_me()
MAX_CAPTION_LENGTH = 1000


def setup_dependencies(database: Any, bot_instance: Any):
    """Setup module dependencies."""
    global db, bot, bot_username
    db = database
    bot = bot_instance
    # Bot username will be fetched dynamically when generating QR
    logger.info(f"Partner module initialized, default bot_username: {bot_username}")


def _t(lang: str, ru: str, uz: str) -> str:
    return ru if lang == "ru" else uz


def _lang_code(user: types.User | None) -> str:
    code = (user.language_code or "ru") if user else "ru"
    return "uz" if code.startswith("uz") else "ru"


def _service_unavailable(lang: str) -> str:
    return _t(lang, "Сервис временно недоступен. Попробуйте позже.", "Xizmat vaqtincha mavjud emas. Keyinroq urinib ko'ring.")


def _safe_caption(text: str) -> str:
    if len(text) <= MAX_CAPTION_LENGTH:
        return text
    return text[: MAX_CAPTION_LENGTH - 3] + "..."


# ===================== PARTNER CONFIRM/REJECT =====================
# NOTE: Handlers for partner_confirm_ and partner_reject_ patterns
# have been moved to handlers/common/unified_order_handlers.py
# which is registered before this router in bot.py
# This ensures all order/booking confirms/rejects go through UnifiedOrderService


# ===================== COMPLETE BOOKING =====================
# NOTE: complete_booking_ handler has been moved to unified_order_handlers.py
# to use UnifiedOrderService for consistent customer notifications


@router.callback_query(F.data.regexp(r"^partner_cancel_\d+$"))
async def partner_cancel_booking(callback: types.CallbackQuery) -> None:
    """Partner cancels an already confirmed booking."""
    if not db or not bot:
        lang_code = _lang_code(callback.from_user)
        await callback.answer(_service_unavailable(lang_code), show_alert=True)
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

    # Verify ownership - get store_id from booking directly (important for cart bookings)
    store_id = get_booking_field(booking, "store_id")
    if not store_id:
        # Fallback: try to get from offer
        offer_id = get_booking_field(booking, "offer_id")
        offer = db.get_offer(offer_id) if offer_id else None
        store_id = get_offer_field(offer, "store_id") if offer else None

    store = db.get_store(store_id) if store_id else None
    if not can_manage_store(db, store_id, partner_id, store=store):
        await callback.answer(get_text(lang, "no_access"), show_alert=True)
        return

    # Cancel and restore quantities (prefer unified service for consistency)
    try:
        order_service = get_unified_order_service()
        if order_service:
            ok = await order_service.update_status(
                entity_id=booking_id,
                entity_type="booking",
                new_status=OrderStatus.REJECTED,
                notify_customer=False,
                reject_reason="seller_cancel",
            )
            if not ok:
                order_service = None
        if not order_service:
            db.cancel_booking(booking_id)
    except Exception as e:
        logger.error(f"Failed to cancel booking: {e}")
        await callback.answer(get_text(lang, "error"), show_alert=True)
        return

    # Notify customer
    customer_id = get_booking_field(booking, "user_id")
    if customer_id:
        customer_lang = db.get_user_language(customer_id)

        customer_msg = _t(
            customer_lang,
            "К сожалению, продавец отменил вашу бронь.",
            "Afsuski, broningiz sotuvchi tomonidan bekor qilindi.",
        )

        try:
            offer_id = get_booking_field(booking, "offer_id")
            offer = db.get_offer(offer_id) if offer_id else None
            offer_photo = resolve_offer_photo(offer)
            if offer_photo:
                await bot.send_photo(
                    customer_id,
                    photo=offer_photo,
                    caption=_safe_caption(customer_msg),
                )
            else:
                await bot.send_message(customer_id, customer_msg)
        except Exception as e:
            logger.error(f"Failed to notify customer {customer_id}: {e}")

    await safe_edit_reply_markup(callback.message)

    text = _t(lang, f"Бронь #{booking_id} отменена.", f"Bron #{booking_id} bekor qilindi.")

    await safe_answer_or_send(callback.message, partner_id, text, bot=bot)
    await callback.answer()


# ===================== RATING (OPTIMIZED - single message) =====================


@router.callback_query(F.data.regexp(r"^rate_booking_\d+_\d+$"))
async def rate_booking(callback: types.CallbackQuery, state: FSMContext) -> None:
    """Customer rates - save immediately, show optional review inline."""
    if not db:
        lang_code = _lang_code(callback.from_user)
        await callback.answer(_service_unavailable(lang_code), show_alert=True)
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
    kb = InlineKeyboardBuilder()
    kb.button(
        text=_t(lang, "Оставить отзыв", "Sharh qoldirish"),
        callback_data=f"add_review_{booking_id}",
    )
    kb.adjust(1)

    thanks = _t(lang, "Спасибо!", "Rahmat!")
    rating_word = "звезду" if rating == 1 else "звезды" if rating < 5 else "звёзд"
    try:
        await callback.message.edit_text(
            f"{thanks} Siz {rating} ball berdingiz."
            if lang == "uz"
            else f"{thanks} Вы поставили {rating} {rating_word}.",
            reply_markup=kb.as_markup(),
        )
    except Exception:
        pass

    await callback.answer(thanks)


@router.callback_query(F.data.regexp(r"^add_review_\d+$"))
async def add_review_prompt(callback: types.CallbackQuery, state: FSMContext) -> None:
    """User wants to add optional text review."""
    if not db:
        lang_code = _lang_code(callback.from_user)
        await callback.answer(_service_unavailable(lang_code), show_alert=True)
        return

    user_id = callback.from_user.id
    lang = db.get_user_language(user_id)

    try:
        booking_id = int(callback.data.split("_")[-1])
    except (ValueError, IndexError):
        await callback.answer(get_text(lang, "error"), show_alert=True)
        return

    await state.update_data(booking_id=booking_id)
    await state.set_state(RateBooking.review_text)

    prompt = "Sharh yozing:" if lang == "uz" else "Напишите отзыв:"
    try:
        await callback.message.edit_text(prompt)
    except Exception:
        pass
    await callback.answer()


@router.message(RateBooking.review_text)
async def process_review_text(message: types.Message, state: FSMContext) -> None:
    """Process the text review from customer."""
    if not db or not bot:
        lang_code = _lang_code(message.from_user)
        await message.answer(_service_unavailable(lang_code))
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

    thanks = _t(lang, "Спасибо! Отзыв сохранён.", "Rahmat! Sharh saqlandi.")
    from app.keyboards import main_menu_customer

    await message.answer(thanks, reply_markup=main_menu_customer(lang, user_id=user_id))


@router.callback_query(F.data.regexp(r"^skip_review_\d+$"))
async def skip_review(callback: types.CallbackQuery, state: FSMContext) -> None:
    """Skip text review and save rating only."""
    if not db or not bot:
        lang_code = _lang_code(callback.from_user)
        await callback.answer(_service_unavailable(lang_code), show_alert=True)
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

    rating_word = "звезду" if rating == 1 else "звезды" if rating < 5 else "звёзд"
    text = (
        f"Rahmat! Siz {rating} ball berdingiz."
        if lang == "uz"
        else f"Спасибо! Вы поставили {rating} {rating_word}."
    )

    await safe_answer_or_send(callback.message, user_id, text, bot=bot)
    await callback.answer(_t(lang, "Спасибо за оценку!", "Baholaganingiz uchun rahmat!"))


# ===================== BATCH CONFIRM/REJECT (for cart orders) =====================


@router.callback_query(F.data.startswith("partner_confirm_batch_"))
async def partner_confirm_batch_bookings(callback: types.CallbackQuery) -> None:
    """Partner confirms multiple bookings at once (from cart)."""
    if not db or not bot:
        lang_code = _lang_code(callback.from_user)
        await callback.answer(_service_unavailable(lang_code), show_alert=True)
        return

    partner_id = callback.from_user.id
    lang = db.get_user_language(partner_id)

    try:
        # Extract booking IDs from callback data: "partner_confirm_batch_1,2,3"
        booking_ids_str = callback.data.replace("partner_confirm_batch_", "")
        booking_ids = [int(bid) for bid in booking_ids_str.split(",")]
    except (ValueError, AttributeError):
        await callback.answer(get_text(lang, "error"), show_alert=True)
        return

    if not booking_ids:
        await callback.answer(get_text(lang, "error"), show_alert=True)
        return

    # Confirm all bookings
    confirmed_count = 0
    customer_notifications: dict[int, dict[str, Any]] = {}  # {customer_id: {bookings, photo}}
    order_service = get_unified_order_service()
    if not order_service and bot:
        order_service = init_unified_order_service(db, bot)
    if not order_service:
        await callback.answer(_service_unavailable(lang), show_alert=True)
        return

    for booking_id in booking_ids:
        try:
            booking = db.get_booking(booking_id)
            if not booking:
                continue

            # Verify ownership
            offer_id = get_booking_field(booking, "offer_id")
            offer = db.get_offer(offer_id) if offer_id else None
            store_id = get_offer_field(offer, "store_id") if offer else None
            store = db.get_store(store_id) if store_id else None
            if not can_manage_store(db, store_id, partner_id, store=store):
                continue

            # Confirm booking
            ok = await order_service.update_status(
                entity_id=booking_id,
                entity_type="booking",
                new_status=OrderStatus.READY,
                notify_customer=False,
            )

            if ok:
                db.mark_reminder_sent(booking_id)
                confirmed_count += 1
            else:
                continue

            # Collect info for customer notification
            customer_id = get_booking_field(booking, "user_id")
            if customer_id:
                if customer_id not in customer_notifications:
                    customer_notifications[customer_id] = {"bookings": [], "photo": None}

                code = get_booking_field(booking, "code")
                code_display = format_booking_code(code, booking_id)
                store_name = get_store_field(store, "name", "Магазин")
                store_address = get_store_field(store, "address", "")

                customer_notifications[customer_id]["bookings"].append(
                    {
                        "code": code_display,
                        "store_name": store_name,
                        "store_address": store_address,
                    }
                )
                if not customer_notifications[customer_id]["photo"]:
                    customer_notifications[customer_id]["photo"] = resolve_offer_photo(offer)

        except Exception as e:
            logger.error(f"Failed to confirm booking {booking_id}: {e}")
            continue

    # Notify customers (grouped)
    for customer_id, payload in customer_notifications.items():
        try:
            customer_lang = db.get_user_language(customer_id)

            lines = []
            lines.append(
                _t(
                    customer_lang,
                    "<b>Все ваши брони подтверждены</b>\n",
                    "<b>Barcha bronlaringiz tasdiqlandi</b>\n",
                )
            )

            store_label = _t(customer_lang, "Магазин", "Do'kon")
            address_label = _t(customer_lang, "Адрес", "Manzil")
            code_label = _t(customer_lang, "Код", "Kod")

            bookings_info = payload.get("bookings", [])
            for info in bookings_info:
                lines.append(f"{store_label}: {_esc(info['store_name'])}")
                if info["store_address"]:
                    lines.append(f"{address_label}: {_esc(info['store_address'])}")
                lines.append(f"{code_label}: <code>{info['code']}</code>\n")

            lines.append(
                _t(customer_lang, "Покажите код продавцу.", "Kodni sotuvchiga ko'rsating.")
            )

            customer_msg = "\n".join(lines)
            offer_photo = payload.get("photo")
            if offer_photo:
                try:
                    await bot.send_photo(
                        customer_id,
                        photo=offer_photo,
                        caption=_safe_caption(customer_msg),
                        parse_mode="HTML",
                    )
                except Exception:
                    await bot.send_message(customer_id, customer_msg, parse_mode="HTML")
            else:
                await bot.send_message(customer_id, customer_msg, parse_mode="HTML")

        except Exception as e:
            logger.error(f"Failed to notify customer {customer_id}: {e}")

    # Update partner message
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass

    success_text = (
        f"{confirmed_count} ta bron tasdiqlandi"
        if lang == "uz"
        else f"Подтверждено броней: {confirmed_count}"
    )
    await callback.answer(success_text)


@router.callback_query(F.data.startswith("partner_reject_batch_"))
async def partner_reject_batch_bookings(callback: types.CallbackQuery) -> None:
    """Partner rejects multiple bookings at once (from cart)."""
    if not db or not bot:
        await callback.answer("System error", show_alert=True)
        return

    partner_id = callback.from_user.id
    lang = db.get_user_language(partner_id)

    try:
        # Extract booking IDs from callback data: "partner_reject_batch_1,2,3"
        booking_ids_str = callback.data.replace("partner_reject_batch_", "")
        booking_ids = [int(bid) for bid in booking_ids_str.split(",")]
    except (ValueError, AttributeError):
        await callback.answer(get_text(lang, "error"), show_alert=True)
        return

    if not booking_ids:
        await callback.answer(get_text(lang, "error"), show_alert=True)
        return

    # Reject all bookings and restore quantities
    rejected_count = 0
    customer_notifications: dict[int, dict[str, Any]] = {}  # {customer_id: {stores, photo}}
    order_service = get_unified_order_service()
    if not order_service and bot:
        order_service = init_unified_order_service(db, bot)
    if not order_service:
        await callback.answer("System error", show_alert=True)
        return

    for booking_id in booking_ids:
        try:
            booking = db.get_booking(booking_id)
            if not booking:
                continue

            # Verify ownership
            offer_id = get_booking_field(booking, "offer_id")
            offer = db.get_offer(offer_id) if offer_id else None
            store_id = get_offer_field(offer, "store_id") if offer else None
            store = db.get_store(store_id) if store_id else None
            if not can_manage_store(db, store_id, partner_id, store=store):
                continue

            # Reject booking
            ok = await order_service.update_status(
                entity_id=booking_id,
                entity_type="booking",
                new_status=OrderStatus.REJECTED,
                notify_customer=False,
            )

            if not ok:
                continue

            rejected_count += 1

            # Collect info for customer notification
            customer_id = get_booking_field(booking, "user_id")
            if customer_id:
                if customer_id not in customer_notifications:
                    customer_notifications[customer_id] = {"stores": [], "photo": None}

                store_name = get_store_field(store, "name", "Магазин")
                customer_notifications[customer_id]["stores"].append(store_name)
                if not customer_notifications[customer_id]["photo"]:
                    customer_notifications[customer_id]["photo"] = resolve_offer_photo(offer)

        except Exception as e:
            logger.error(f"Failed to reject booking {booking_id}: {e}")
            continue

    # Notify customers (grouped)
    for customer_id, payload in customer_notifications.items():
        try:
            customer_lang = db.get_user_language(customer_id)

            store_names = payload.get("stores", [])
            customer_msg = _t(
                customer_lang,
                f"К сожалению, ваши брони в {', '.join(store_names)} отклонены.",
                f"Afsuski, {', '.join(store_names)} bronlaringiz rad etildi.",
            )

            offer_photo = payload.get("photo")
            if offer_photo:
                try:
                    await bot.send_photo(
                        customer_id,
                        photo=offer_photo,
                        caption=_safe_caption(customer_msg),
                        parse_mode="HTML",
                    )
                except Exception:
                    await bot.send_message(customer_id, customer_msg, parse_mode="HTML")
            else:
                await bot.send_message(customer_id, customer_msg, parse_mode="HTML")

        except Exception as e:
            logger.error(f"Failed to notify customer {customer_id}: {e}")

    # Update partner message
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass

    reject_text = (
        f"{rejected_count} ta bron rad etildi"
        if lang == "uz"
        else f"Отклонено броней: {rejected_count}"
    )
    await callback.answer(reject_text)
