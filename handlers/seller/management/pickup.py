"""Pickup code verification handler."""
from __future__ import annotations

from aiogram import F, Router, types

from handlers.bookings.utils import safe_answer_or_send as _safe_answer_or_send
from logging_config import logger

from .utils import get_db, get_store_field

router = Router()


@router.message(F.text.startswith("/pickup "))
async def seller_check_pickup_code(message: types.Message) -> None:
    """Seller command to verify pickup code and mark booking as completed.

    Usage: /pickup CODE
    """
    db = get_db()

    # Ensure user is a seller with stores
    try:
        stores = db.get_user_stores(message.from_user.id) or []
        if not stores:
            await message.answer("⚠️ This command is for sellers only")
            return
    except Exception:
        await message.answer("⚠️ System error")
        return

    parts = message.text.split(None, 1)
    if len(parts) < 2:
        await message.answer("Usage: /pickup CODE")
        return

    code = parts[1].strip()
    try:
        booking = db.get_booking_by_code(code)
    except Exception as e:
        logger.error(f"Error fetching booking by code: {e}")
        await message.answer("⚠️ Error checking code")
        return

    if not booking:
        await message.answer("❌ Booking not found or already used")
        return

    # Validate that seller owns the store for this booking
    store_id = (
        booking.get("store_id")
        if isinstance(booking, dict)
        else (booking[1] if len(booking) > 1 else None)
    )
    owner_ok = False
    for s in stores:
        sid = get_store_field(s, "store_id")
        if sid == store_id:
            owner_ok = True
            break

    if not owner_ok:
        await message.answer("❌ You don't have permission to complete this booking")
        return

    try:
        booking_id = (
            booking.get("booking_id")
            if isinstance(booking, dict)
            else (booking[0] if len(booking) > 0 else None)
        )
        if booking_id is None:
            await message.answer("❌ Invalid booking record")
            return
        db.complete_booking(booking_id)
        await message.answer(f"✅ Booking {booking_id} marked as completed")
        # Notify customer optionally
        try:
            user_id = (
                booking.get("user_id")
                if isinstance(booking, dict)
                else (booking[2] if len(booking) > 2 else None)
            )
            if user_id:
                await _safe_answer_or_send(
                    None, user_id, f"🎉 Ваш заказ {booking_id} выдан. Спасибо!"
                )
        except Exception:
            pass
    except Exception as e:
        logger.error(f"Error completing booking by code: {e}")
        await message.answer("❌ Failed to complete booking")
