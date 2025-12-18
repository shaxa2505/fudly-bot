"""Pickup code verification handler."""
from __future__ import annotations

from aiogram import F, Router, types

from app.services.unified_order_service import get_unified_order_service, init_unified_order_service
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
        stores = db.get_user_accessible_stores(message.from_user.id) or []
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

    entity_type = "booking"
    entity = None

    try:
        # Prefer unified pickup orders by pickup_code (v24+)
        if hasattr(db, "get_order_by_pickup_code"):
            entity = db.get_order_by_pickup_code(code)
            if isinstance(entity, dict) and (entity.get("order_type") or "pickup") == "pickup":
                entity_type = "order"
            else:
                entity = None

        if not entity:
            entity = db.get_booking_by_code(code)
    except Exception as e:
        logger.error(f"Error fetching by code: {e}")
        await message.answer("⚠️ Error checking code")
        return

    if not entity:
        await message.answer("❌ Booking/order not found or already used")
        return

    # Validate that seller owns the store for this booking
    store_id = entity.get("store_id") if (entity_type == "order" and isinstance(entity, dict)) else (
        entity.get("store_id")
        if isinstance(entity, dict)
        else (entity[1] if len(entity) > 1 else None)
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
        entity_id = (
            entity.get("order_id")
            if entity_type == "order" and isinstance(entity, dict)
            else (
                entity.get("booking_id")
                if isinstance(entity, dict)
                else (entity[0] if len(entity) > 0 else None)
            )
        )
        if entity_id is None:
            await message.answer("❌ Invalid record")
            return

        unified = get_unified_order_service() or init_unified_order_service(db, message.bot)
        await unified.complete_order(int(entity_id), entity_type)  # type: ignore[arg-type]

        await message.answer(
            f"✅ {'Order' if entity_type == 'order' else 'Booking'} {entity_id} marked as completed"
        )
    except Exception as e:
        logger.error(f"Error completing booking by code: {e}")
        await message.answer("❌ Failed to complete booking")
