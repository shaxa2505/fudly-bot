"""Partner booking handlers - confirm, reject, complete bookings."""
from __future__ import annotations

from typing import Any

from aiogram import F, Router, types
from aiogram.fsm.context import FSMContext
from aiogram.types import BufferedInputFile
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.services.unified_order_service import OrderStatus, get_unified_order_service
from handlers.common.states import RateBooking
from handlers.common.utils import html_escape as _esc
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

    # Verify ownership - get store_id from booking directly (important for cart bookings)
    store_id = get_booking_field(booking, "store_id")
    if not store_id:
        # Fallback: try to get from offer
        offer_id = get_booking_field(booking, "offer_id")
        offer = db.get_offer(offer_id) if offer_id else None
        store_id = get_offer_field(offer, "store_id") if offer else None

    store = db.get_store(store_id) if store_id else None
    owner_id = get_store_field(store, "owner_id") if store else None

    if not owner_id or partner_id != owner_id:
        await callback.answer(get_text(lang, "error"), show_alert=True)
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

            # Restore quantities - check if cart booking
            is_cart_booking = get_booking_field(booking, "is_cart_booking", 0)
            if is_cart_booking:
                import json

                cart_items_json = get_booking_field(booking, "cart_items")
                if cart_items_json:
                    try:
                        cart_items = (
                            json.loads(cart_items_json)
                            if isinstance(cart_items_json, str)
                            else cart_items_json
                        )
                        for item in cart_items:
                            item_offer_id = item.get("offer_id")
                            item_qty = item.get("quantity", 1)
                            if item_offer_id:
                                db.increment_offer_quantity_atomic(item_offer_id, int(item_qty))
                    except Exception as e:
                        logger.error(f"Failed to restore cart quantities in cancel: {e}")
            else:
                # Single item booking
                offer_id = get_booking_field(booking, "offer_id")
                qty = get_booking_field(booking, "quantity", 1)
                if offer_id:
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
        callback_data=f"add_review_{booking_id}",
    )
    kb.adjust(1)

    thanks = "Rahmat!" if lang == "uz" else "Спасибо!"
    try:
        await callback.message.edit_text(
            f"⭐ {thanks} Siz {rating} ball berdingiz."
            if lang == "uz"
            else f"⭐ {thanks} Вы поставили {rating} {'звезду' if rating == 1 else 'звезды' if rating < 5 else 'звёзд'}.",
            reply_markup=kb.as_markup(),
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


# ===================== BATCH CONFIRM/REJECT (for cart orders) =====================


@router.callback_query(F.data.startswith("partner_confirm_batch_"))
async def partner_confirm_batch_bookings(callback: types.CallbackQuery) -> None:
    """Partner confirms multiple bookings at once (from cart)."""
    if not db or not bot:
        await callback.answer("System error", show_alert=True)
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
    customer_notifications = {}  # {customer_id: [booking_infos]}
    order_service = get_unified_order_service()

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
            owner_id = get_store_field(store, "owner_id")

            if partner_id != owner_id:
                continue

            # Confirm booking
            if order_service:
                ok = await order_service.update_status(
                    entity_id=booking_id,
                    entity_type="booking",
                    new_status=OrderStatus.PREPARING,
                    notify_customer=False,
                )
            else:
                ok = True
                db.update_booking_status(booking_id, "preparing")

            if ok:
                db.mark_reminder_sent(booking_id)
                confirmed_count += 1
            else:
                continue

            # Collect info for customer notification
            customer_id = get_booking_field(booking, "user_id")
            if customer_id:
                if customer_id not in customer_notifications:
                    customer_notifications[customer_id] = []

                code = get_booking_field(booking, "code")
                code_display = format_booking_code(code, booking_id)
                store_name = get_store_field(store, "name", "Магазин")
                store_address = get_store_field(store, "address", "")

                customer_notifications[customer_id].append(
                    {
                        "code": code_display,
                        "store_name": store_name,
                        "store_address": store_address,
                    }
                )

        except Exception as e:
            logger.error(f"Failed to confirm booking {booking_id}: {e}")
            continue

    # Notify customers (grouped)
    for customer_id, bookings_info in customer_notifications.items():
        try:
            customer_lang = db.get_user_language(customer_id)

            lines = []
            if customer_lang == "uz":
                lines.append("✅ <b>Barcha bronlaringiz tasdiqlandi!</b>\n")
            else:
                lines.append("✅ <b>Все ваши брони подтверждены!</b>\n")

            for info in bookings_info:
                lines.append(f"🏪 {_esc(info['store_name'])}")
                if info["store_address"]:
                    lines.append(f"📍 {_esc(info['store_address'])}")
                lines.append(f"🎫 Kod: <code>{info['code']}</code>\n")

            if customer_lang == "uz":
                lines.append("⚠️ Kodni sotuvchiga ko'rsating.")
            else:
                lines.append("⚠️ Покажите код продавцу.")

            customer_msg = "\n".join(lines)
            await bot.send_message(customer_id, customer_msg, parse_mode="HTML")

        except Exception as e:
            logger.error(f"Failed to notify customer {customer_id}: {e}")

    # Update partner message
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass

    success_text = (
        f"✅ {confirmed_count} ta bron tasdiqlandi"
        if lang == "uz"
        else f"✅ Подтверждено броней: {confirmed_count}"
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
    customer_notifications = {}  # {customer_id: [store_names]}
    order_service = get_unified_order_service()

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
            owner_id = get_store_field(store, "owner_id")

            if partner_id != owner_id:
                continue

            # Reject booking
            if order_service:
                ok = await order_service.update_status(
                    entity_id=booking_id,
                    entity_type="booking",
                    new_status=OrderStatus.REJECTED,
                    notify_customer=False,
                )
            else:
                ok = True
                # Return quantity to offer
                quantity = get_booking_field(booking, "quantity", 1)
                if offer_id:
                    db.increment_offer_quantity_atomic(offer_id, quantity)
                db.update_booking_status(booking_id, "rejected")

            if not ok:
                continue

            rejected_count += 1

            # Collect info for customer notification
            customer_id = get_booking_field(booking, "user_id")
            if customer_id:
                if customer_id not in customer_notifications:
                    customer_notifications[customer_id] = []

                store_name = get_store_field(store, "name", "Магазин")
                customer_notifications[customer_id].append(store_name)

        except Exception as e:
            logger.error(f"Failed to reject booking {booking_id}: {e}")
            continue

    # Notify customers (grouped)
    for customer_id, store_names in customer_notifications.items():
        try:
            customer_lang = db.get_user_language(customer_id)

            if customer_lang == "uz":
                customer_msg = f"❌ Afsuski, {', '.join(store_names)} bronlaringiz rad etildi."
            else:
                customer_msg = f"❌ К сожалению, ваши брони в {', '.join(store_names)} отклонены."

            await bot.send_message(customer_id, customer_msg, parse_mode="HTML")

        except Exception as e:
            logger.error(f"Failed to notify customer {customer_id}: {e}")

    # Update partner message
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass

    reject_text = (
        f"❌ {rejected_count} ta bron rad etildi"
        if lang == "uz"
        else f"❌ Отклонено броней: {rejected_count}"
    )
    await callback.answer(reject_text)
