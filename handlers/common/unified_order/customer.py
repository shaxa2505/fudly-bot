"""Customer-side unified order handlers.

Contains callbacks where customers mark orders as received.
"""
from __future__ import annotations

import re

from aiogram import F, Router, types
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.services.unified_order_service import (
    NotificationTemplates,
    OrderStatus,
    get_unified_order_service,
)
from localization import get_text

from .common import _get_db, _get_entity_field, _get_store_field, logger

# Public callback patterns used for customer "received" buttons.
# Having them as constants allows tests to verify that they
# actually match simple ids like "customer_received_123".
CUSTOMER_RECEIVED_PATTERN = r"^customer_received_(\d+)$"
RATE_ORDER_PATTERN = r"^rate_order_(\d+)_(\d+)$"
MAX_CAPTION_LENGTH = 1000


def _safe_caption(text: str) -> str:
    if len(text) <= MAX_CAPTION_LENGTH:
        return text
    return text[: MAX_CAPTION_LENGTH - 1] + "…"


async def customer_received_handler(callback: types.CallbackQuery) -> None:
    """Customer confirms they received a delivery order."""

    if not callback.from_user or not callback.data:
        await callback.answer()
        return

    db_instance = _get_db()
    if not db_instance:
        await callback.answer(get_text("ru", "system_error"), show_alert=True)
        return

    order_service = get_unified_order_service()
    customer_id = callback.from_user.id
    lang = db_instance.get_user_language(customer_id)

    try:
        order_id = int(callback.data.split("_")[-1])
    except ValueError:
        await callback.answer(get_text(lang, "error"), show_alert=True)
        return

    order = db_instance.get_order(order_id)
    if not order:
        await callback.answer(get_text(lang, "error"), show_alert=True)
        return

    order_user_id = _get_entity_field(order, "user_id")
    if order_user_id != customer_id:
        await callback.answer(get_text(lang, "error"), show_alert=True)
        return

    current_status = _get_entity_field(order, "order_status") or _get_entity_field(order, "status")
    logger.info("customer_received_handler: order #%s, current_status=%s", order_id, current_status)
    valid_statuses = (
        OrderStatus.DELIVERING,
        OrderStatus.PREPARING,
        OrderStatus.READY,
        "delivering",
        "preparing",
        "ready",
        "confirmed",
    )
    if current_status not in valid_statuses:
        logger.warning(
            "customer_received_handler: order #%s status %s not in %s",
            order_id,
            current_status,
            valid_statuses,
        )
        await callback.answer(get_text(lang, "order_already_completed"), show_alert=True)
        return

    if order_service:
        success = await order_service.complete_order(order_id, "order")
    else:
        try:
            db_instance.update_order_status(order_id, OrderStatus.COMPLETED)
            success = True
        except Exception:  # pragma: no cover
            success = False

    if not success:
        await callback.answer(get_text(lang, "error"), show_alert=True)
        return

    # Determine order type for proper completion template
    order_type = _get_entity_field(order, "order_type")
    if not order_type:
        # Fallback: infer from delivery_address presence
        delivery_address = _get_entity_field(order, "delivery_address")
        order_type = "delivery" if delivery_address else "pickup"

    store_id = _get_entity_field(order, "store_id")
    store = db_instance.get_store(store_id) if store_id else None
    store_name = _get_store_field(store, "name", "")

    completed_text = NotificationTemplates.customer_status_update(
        lang=lang,
        order_id=order_id,
        status=OrderStatus.COMPLETED,
        order_type=order_type,
        store_name=store_name,
    )

    kb = InlineKeyboardBuilder()
    for i in range(1, 6):
        kb.button(text="⭐" * i, callback_data=f"rate_order_{order_id}_{i}")
    kb.adjust(5)

    try:
        if callback.message:
            if getattr(callback.message, "caption", None):
                await callback.message.edit_caption(
                    caption=_safe_caption(completed_text),
                    parse_mode="HTML",
                    reply_markup=kb.as_markup(),
                )
            else:
                await callback.message.edit_text(
                    text=completed_text,
                    parse_mode="HTML",
                    reply_markup=kb.as_markup(),
                )
    except Exception as e:  # pragma: no cover
        logger.warning(f"Failed to edit customer received message: {e}")

    msg = get_text(lang, "order_completed_thanks")
    await callback.answer(f"✅ {msg}", show_alert=True)


async def rate_order_handler(callback: types.CallbackQuery) -> None:
    """Customer rates a delivery/pickup order."""
    if not callback.from_user or not callback.data:
        await callback.answer()
        return

    db_instance = _get_db()
    if not db_instance:
        await callback.answer(get_text("ru", "system_error"), show_alert=True)
        return

    user_id = callback.from_user.id
    lang = db_instance.get_user_language(user_id)

    try:
        parts = callback.data.split("_")
        order_id = int(parts[2])
        rating = int(parts[3])
    except (ValueError, IndexError):
        await callback.answer(get_text(lang, "error"), show_alert=True)
        return

    if rating < 1 or rating > 5:
        await callback.answer(get_text(lang, "error"), show_alert=True)
        return

    order = db_instance.get_order(order_id) if hasattr(db_instance, "get_order") else None
    if not order:
        await callback.answer(get_text(lang, "error"), show_alert=True)
        return

    order_user_id = _get_entity_field(order, "user_id")
    if order_user_id != user_id:
        await callback.answer(get_text(lang, "error"), show_alert=True)
        return

    if hasattr(db_instance, "has_rated_order") and db_instance.has_rated_order(order_id):
        already = get_text(lang, "already_rated")
        await callback.answer(already, show_alert=True)
        return

    store_id = _get_entity_field(order, "store_id")

    try:
        if hasattr(db_instance, "add_order_rating"):
            db_instance.add_order_rating(order_id, user_id, store_id, rating)
    except Exception as e:  # pragma: no cover - defensive
        logger.warning(f"Failed to save order rating: {e}")
        await callback.answer(get_text(lang, "error"), show_alert=True)
        return

    try:
        if callback.message:
            await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:  # pragma: no cover - defensive
        pass

    thanks_html = get_text(lang, "rating_saved")
    thanks_plain = re.sub(r"<[^>]+>", "", thanks_html)
    await callback.answer(thanks_plain, show_alert=True)


def register(router: Router) -> None:
    """Register all customer-side unified order handlers on the router."""

    router.callback_query.register(
        customer_received_handler, F.data.regexp(CUSTOMER_RECEIVED_PATTERN)
    )
    router.callback_query.register(
        customer_received_handler, F.data.regexp(r"^order_received_(\d+)$")
    )
    router.callback_query.register(rate_order_handler, F.data.regexp(RATE_ORDER_PATTERN))
