"""Customer-side unified order handlers.

Contains callbacks where customers mark orders as received.
"""
from __future__ import annotations

import json
import os
import re
from datetime import datetime, timedelta
from typing import Any

from aiogram import F, Router, types
from aiogram.types import WebAppInfo
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.core.utils import UZB_TZ, get_uzb_time, to_uzb_datetime
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
OPEN_ORDER_PATTERN = r"^open_order_(\d+)$"
MAX_CAPTION_LENGTH = 1000


def _safe_caption(text: str) -> str:
    if len(text) <= MAX_CAPTION_LENGTH:
        return text
    return text[: MAX_CAPTION_LENGTH - 1] + "…"


def _format_ready_until(updated_at: Any | None) -> str | None:
    try:
        hours = int(os.environ.get("PICKUP_READY_EXPIRY_HOURS", "2"))
    except Exception:
        hours = 2
    if hours <= 0:
        return None

    base_time = to_uzb_datetime(updated_at) or get_uzb_time()
    ready_until = base_time + timedelta(hours=hours)
    return ready_until.strftime("%H:%M")


def _build_open_order_keyboard(lang: str, order_id: int) -> InlineKeyboardBuilder:
    kb = InlineKeyboardBuilder()
    webapp_url = os.getenv("WEBAPP_URL", "").strip()
    if webapp_url:
        kb.button(
            text=get_text(lang, "btn_open_order_app"),
            web_app=WebAppInfo(url=f"{webapp_url.rstrip('/')}/order/{order_id}"),
        )
    kb.button(text=get_text(lang, "btn_back_menu"), callback_data="back_to_menu")
    kb.adjust(1)
    return kb


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

    # Fallback: if service is unavailable, update the card here.
    if not order_service and callback.message:
        completed_text = NotificationTemplates.customer_status_update(
            lang=lang,
            order_id=order_id,
            status=OrderStatus.COMPLETED,
            order_type=order_type,
            store_name=store_name,
        )
        try:
            if getattr(callback.message, "caption", None):
                await callback.message.edit_caption(
                    caption=_safe_caption(completed_text),
                    parse_mode="HTML",
                )
            else:
                await callback.message.edit_text(
                    text=completed_text,
                    parse_mode="HTML",
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


async def open_order_handler(callback: types.CallbackQuery) -> None:
    """Fallback handler for opening an order when Mini App is unavailable."""
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
        order_id = int(callback.data.split("_")[-1])
    except ValueError:
        await callback.answer(get_text(lang, "error"), show_alert=True)
        return

    order = db_instance.get_order(order_id) if hasattr(db_instance, "get_order") else None
    booking = None
    if not order and hasattr(db_instance, "get_booking"):
        booking = db_instance.get_booking(order_id)
    if not order and not booking:
        await callback.answer(get_text(lang, "order_not_found"), show_alert=True)
        return

    if order:
        order_user_id = _get_entity_field(order, "user_id")
    else:
        order_user_id = _get_entity_field(booking, "user_id")
    if order_user_id != user_id:
        await callback.answer(get_text(lang, "error"), show_alert=True)
        return

    if order:
        status_raw = _get_entity_field(order, "order_status") or _get_entity_field(order, "status")
        status = OrderStatus.normalize(str(status_raw or "pending"))

        delivery_address = _get_entity_field(order, "delivery_address")
        order_type = _get_entity_field(order, "order_type") or (
            "delivery" if delivery_address else "pickup"
        )
        if order_type == "taxi":
            order_type = "delivery"

        store_id = _get_entity_field(order, "store_id")
        store = db_instance.get_store(store_id) if store_id else None
        store_name = _get_entity_field(store, "name", "") if store else ""
        store_address = _get_entity_field(store, "address", "") if store else ""

        total_price = int(_get_entity_field(order, "total_price") or 0)
        delivery_price = int(_get_entity_field(order, "delivery_price") or 0)
        if total_price <= 0:
            cart_items_json = _get_entity_field(order, "cart_items")
            if cart_items_json:
                try:
                    cart_items = (
                        json.loads(cart_items_json)
                        if isinstance(cart_items_json, str)
                        else cart_items_json
                    )
                except Exception:
                    cart_items = []
                if isinstance(cart_items, list):
                    total_price = sum(
                        int(item.get("price") or 0) * int(item.get("quantity") or 1)
                        for item in cart_items
                    )
            if total_price <= 0:
                qty = int(_get_entity_field(order, "quantity") or 1)
                price = int(_get_entity_field(order, "item_price") or 0)
                total_price = max(0, qty * price)

        updated_at = _get_entity_field(order, "updated_at")
        ready_until = (
            _format_ready_until(updated_at)
            if order_type == "pickup" and status == OrderStatus.READY
            else None
        )
        pickup_code = _get_entity_field(order, "pickup_code")
    else:
        status_raw = _get_entity_field(booking, "status") or _get_entity_field(booking, "order_status")
        status = OrderStatus.normalize(str(status_raw or "pending"))
        order_type = "pickup"
        delivery_address = None
        store_id = _get_entity_field(booking, "store_id")
        store = db_instance.get_store(store_id) if store_id else None
        store_name = _get_entity_field(store, "name", "") if store else ""
        store_address = _get_entity_field(store, "address", "") if store else ""
        qty = int(_get_entity_field(booking, "quantity") or 1)
        price = int(_get_entity_field(booking, "price") or 0)
        if price <= 0:
            offer_id = _get_entity_field(booking, "offer_id")
            if offer_id and hasattr(db_instance, "get_offer"):
                offer = db_instance.get_offer(offer_id)
                price = int(_get_entity_field(offer, "discount_price") or 0)
        total_price = max(0, qty * price)
        delivery_price = 0
        updated_at = _get_entity_field(booking, "updated_at")
        ready_until = (
            _format_ready_until(updated_at)
            if status == OrderStatus.READY
            else None
        )
        pickup_code = _get_entity_field(booking, "booking_code") or _get_entity_field(booking, "pickup_code")

    currency = get_text(lang, "currency")
    card = NotificationTemplates.customer_status_update(
        lang=lang,
        order_id=order_id,
        status=status,
        order_type=order_type,
        store_name=store_name,
        store_address=store_address,
        delivery_address=delivery_address,
        pickup_code=pickup_code,
        total=total_price,
        delivery_price=delivery_price,
        currency=currency,
        ready_until=ready_until,
    )

    kb = _build_open_order_keyboard(lang, order_id)

    try:
        if callback.message and getattr(callback.message, "caption", None):
            await callback.message.edit_caption(
                caption=_safe_caption(card),
                parse_mode="HTML",
                reply_markup=kb.as_markup(),
            )
        elif callback.message:
            await callback.message.edit_text(
                text=card,
                parse_mode="HTML",
                reply_markup=kb.as_markup(),
            )
    except Exception as e:
        logger.warning("Failed to render fallback order #%s: %s", order_id, e)

    await callback.answer()


def register(router: Router) -> None:
    """Register all customer-side unified order handlers on the router."""

    router.callback_query.register(
        customer_received_handler, F.data.regexp(CUSTOMER_RECEIVED_PATTERN)
    )
    router.callback_query.register(
        customer_received_handler, F.data.regexp(r"^order_received_(\d+)$")
    )
    router.callback_query.register(rate_order_handler, F.data.regexp(RATE_ORDER_PATTERN))
    router.callback_query.register(open_order_handler, F.data.regexp(OPEN_ORDER_PATTERN))
