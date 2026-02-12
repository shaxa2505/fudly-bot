"""Seller-side unified order handlers.

Contains confirmation/rejection, status updates and courier handover
flows for orders. All callbacks are registered via
`register(router)`.
"""
from __future__ import annotations

import json
import re
from typing import Any

from aiogram import F, Router, types
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.domain.order import PaymentStatus
from app.services.unified_order_service import (
    NotificationTemplates,
    OrderStatus,
    get_unified_order_service,
    init_unified_order_service,
)
from handlers.common.states import CourierHandover
from handlers.common.utils import can_manage_store
from localization import get_text

from .common import _get_db, _get_entity_field, _get_store_field, logger

# Regex patterns for all supported callback formats
CONFIRM_PATTERN = re.compile(
    r"^(order_confirm_|partner_confirm_order_|confirm_order_)(\d+)$"
)
REJECT_PATTERN = re.compile(r"^(order_reject_|partner_reject_order_|cancel_order_)(\d+)$")

MAX_CAPTION_LENGTH = 1000


def _safe_caption(text: str) -> str:
    if len(text) <= MAX_CAPTION_LENGTH:
        return text
    return text[: MAX_CAPTION_LENGTH - 3] + "..."


def _transition_error_text(order_service: Any | None, lang: str) -> str:
    if order_service and hasattr(order_service, "get_last_status_error"):
        reason = order_service.get_last_status_error()
        if reason:
            return str(reason)
    return get_text(lang, "error") or "Error"


def _is_paid_online_order(entity: Any) -> bool:
    payment_method = _get_entity_field(entity, "payment_method")
    payment_status = _get_entity_field(entity, "payment_status")
    payment_proof_photo_id = _get_entity_field(entity, "payment_proof_photo_id")

    method_norm = PaymentStatus.normalize_method(payment_method)
    if method_norm not in ("click", "payme"):
        return False
    status_norm = PaymentStatus.normalize(
        payment_status,
        payment_method=payment_method,
        payment_proof_photo_id=payment_proof_photo_id,
    )
    return status_norm == PaymentStatus.CONFIRMED


def _is_unpaid_online_order(entity: Any) -> bool:
    payment_method = _get_entity_field(entity, "payment_method")
    payment_status = _get_entity_field(entity, "payment_status")
    payment_proof_photo_id = _get_entity_field(entity, "payment_proof_photo_id")

    method_norm = PaymentStatus.normalize_method(payment_method)
    if method_norm not in ("click", "payme"):
        return False

    status_norm = PaymentStatus.normalize(
        payment_status,
        payment_method=payment_method,
        payment_proof_photo_id=payment_proof_photo_id,
    )
    return status_norm != PaymentStatus.CONFIRMED


def _determine_entity_type(prefix: str, entity_id: int, db_instance: Any) -> tuple[str, Any]:
    """Determine entity type for order callbacks."""

    entity = db_instance.get_order(entity_id)
    if entity:
        return ("order", entity)

    return ("unknown", None)


async def _restore_quantities_fallback(db_instance: Any, entity: Any, entity_type: str) -> None:
    """Restore offer quantities (fallback when UnifiedOrderService is unavailable)."""

    try:
        if isinstance(entity, dict):
            is_cart = entity.get("is_cart_order", 0) == 1
            cart_items_json = entity.get("cart_items")
            offer_id = entity.get("offer_id")
            quantity = entity.get("quantity", 1)
        else:
            is_cart = (
                getattr(entity, "is_cart_order", 0) == 1
            )
            cart_items_json = getattr(entity, "cart_items", None)
            offer_id = getattr(entity, "offer_id", None)
            quantity = getattr(entity, "quantity", 1)

        if is_cart and cart_items_json:
            cart_items = (
                json.loads(cart_items_json) if isinstance(cart_items_json, str) else cart_items_json
            )
            for item in cart_items:
                item_offer_id = item.get("offer_id")
                item_qty = item.get("quantity", 1)
                if item_offer_id:
                    try:
                        db_instance.increment_offer_quantity_atomic(item_offer_id, int(item_qty))
                    except Exception as e:  # pragma: no cover - defensive logging
                        logger.warning(
                            "Failed to restore quantity for offer %s (qty=%s): %s",
                            item_offer_id,
                            item_qty,
                            e,
                        )
        elif offer_id:
            try:
                db_instance.increment_offer_quantity_atomic(offer_id, int(quantity))
            except Exception as e:  # pragma: no cover - defensive logging
                logger.warning(
                    "Failed to restore quantity for offer %s (qty=%s): %s",
                    offer_id,
                    quantity,
                    e,
                )

    except Exception as e:  # pragma: no cover - defensive logging
        logger.error(f"Failed to restore quantities: {e}")


# ============================================================================
# UNIFIED CONFIRM / REJECT
# ============================================================================


async def unified_confirm_handler(callback: types.CallbackQuery) -> None:
    """Unified handler for order confirmation callbacks."""

    if not callback.from_user or not callback.data:
        await callback.answer()
        return

    db_instance = _get_db()
    if not db_instance:
        await callback.answer(get_text("ru", "system_error"), show_alert=True)
        return

    order_service = get_unified_order_service()
    if not order_service and callback.bot:
        order_service = init_unified_order_service(db_instance, callback.bot)
    partner_id = callback.from_user.id
    lang = db_instance.get_user_language(partner_id)

    match = CONFIRM_PATTERN.match(callback.data)
    if not match:
        await callback.answer(get_text(lang, "error"), show_alert=True)
        return

    prefix = match.group(1)
    entity_id = int(match.group(2))

    entity_type, entity = _determine_entity_type(prefix, entity_id, db_instance)
    if not entity:
        msg = get_text(lang, "order_not_found")
        await callback.answer(f"❌ {msg}", show_alert=True)
        return

    # Verify ownership
    store_id = _get_entity_field(entity, "store_id")
    if not store_id:
        offer_id = _get_entity_field(entity, "offer_id")
        if offer_id:
            offer = db_instance.get_offer(offer_id)
            if offer:
                store_id = _get_entity_field(offer, "store_id")

    store = db_instance.get_store(store_id) if store_id else None
    if not can_manage_store(db_instance, store_id, partner_id, store=store):
        logger.warning(
            "Ownership verification failed: partner=%s, owner=%s, %s=%s",
            partner_id,
            _get_store_field(store, "owner_id") if store else None,
            entity_type,
            entity_id,
        )
        await callback.answer(get_text(lang, "error"), show_alert=True)
        return

    # Determine order type early for correct status transition
    delivery_address: str | None = None
    order_type = "delivery"
    if entity_type == "order":
        delivery_address = _get_entity_field(entity, "delivery_address")
        order_type_db = _get_entity_field(entity, "order_type")
        if order_type_db:
            order_type = order_type_db
        else:
            order_type = "delivery" if delivery_address else "pickup"
    else:
        order_type = "pickup"
    if order_type == "taxi":
        order_type = "delivery"

    if entity_type == "order" and _is_unpaid_online_order(entity):
        await callback.answer(get_text(lang, "payment_not_confirmed"), show_alert=True)
        return

    target_status = OrderStatus.PREPARING

    # Use UnifiedOrderService if available, otherwise fallback
    if order_service:
        success = await order_service.confirm_order(entity_id, entity_type)
        if success:
            confirmed_msg = get_text(lang, "order_confirmed")
            await callback.answer(f"✅ {confirmed_msg}")
            return
    else:
        try:
            if entity_type == "order":
                db_instance.update_order_status(entity_id, target_status)
            else:
                db_instance.update_booking_status(entity_id, target_status)
            success = True
        except Exception as e:  # pragma: no cover - defensive logging
            logger.error(f"Failed to confirm: {e}")
            success = False

    if not success:
        await callback.answer(_transition_error_text(order_service, lang), show_alert=True)
        return

    # Build updated seller message
    from app.core.utils import get_offer_field

    items: list[dict] = []
    customer_name: str | None = None
    customer_phone: str | None = None
    total = 0
    delivery_price = 0

    if entity_type == "order":
        offer_id = _get_entity_field(entity, "offer_id")
        quantity = _get_entity_field(entity, "quantity", 1)
        if offer_id:
            offer = db_instance.get_offer(offer_id)
            if offer:
                title = get_offer_field(offer, "title", "Товар")
                price = get_offer_field(offer, "discount_price", 0)
                items.append({"title": title, "quantity": quantity, "price": price})
                total = price * quantity

        cart_items_json = _get_entity_field(entity, "cart_items")
        if cart_items_json:
            try:
                cart_items = (
                    json.loads(cart_items_json)
                    if isinstance(cart_items_json, str)
                    else cart_items_json
                )
                items = cart_items
                total = sum(item.get("price", 0) * item.get("quantity", 1) for item in cart_items)
            except Exception:  # pragma: no cover - defensive logging
                pass

        delivery_price = (
            _get_store_field(store, "delivery_price", 0) if order_type == "delivery" else 0
        )

    # Customer info
    customer_id = _get_entity_field(entity, "user_id")
    if customer_id:
        customer = db_instance.get_user_model(customer_id)
        if customer:
            customer_name = customer.first_name
            customer_phone = customer.phone

    currency = get_text(lang, "currency")
    payment_method = _get_entity_field(entity, "payment_method")
    payment_status = _get_entity_field(entity, "payment_status")
    payment_proof_photo_id = _get_entity_field(entity, "payment_proof_photo_id")

    seller_text = NotificationTemplates.seller_status_update(
        lang=lang,
        order_id=entity_id,
        status=target_status,
        order_type=order_type,
        items=items,
        customer_name=customer_name,
        customer_phone=customer_phone,
        delivery_address=delivery_address,
        total=total,
        delivery_price=delivery_price,
        currency=currency,
        payment_method=payment_method,
        payment_status=payment_status,
        payment_proof_photo_id=payment_proof_photo_id,
        created_at=_get_entity_field(entity, "created_at"),
    )

    kb = InlineKeyboardBuilder()
    if order_type != "delivery":
        kb.button(
            text=get_text(lang, "btn_ready_for_pickup"),
            callback_data=f"order_ready_{entity_id}",
        )
        kb.adjust(1)
    else:
        kb.button(
            text=get_text(lang, "btn_ready_for_delivery"),
            callback_data=f"order_ready_{entity_id}",
        )
        kb.adjust(1)

    try:
        if callback.message:
            if getattr(callback.message, "caption", None):
                await callback.message.edit_caption(
                    caption=_safe_caption(seller_text),
                    parse_mode="HTML",
                    reply_markup=kb.as_markup(),
                )
            else:
                await callback.message.edit_text(
                    text=seller_text,
                    parse_mode="HTML",
                    reply_markup=kb.as_markup(),
                )
    except Exception as e:  # pragma: no cover - defensive logging
        logger.warning(f"Failed to edit seller message: {e}")

    # NOTE: Customer notification is handled by UnifiedOrderService.confirm_order()
    # No need to send duplicate message here

    confirmed_msg = get_text(lang, "order_confirmed")
    await callback.answer(f"✅ {confirmed_msg}")


async def unified_reject_handler(callback: types.CallbackQuery) -> None:
    """Unified handler for order rejection callbacks."""

    if not callback.from_user or not callback.data:
        await callback.answer()
        return

    db_instance = _get_db()
    if not db_instance:
        await callback.answer(get_text("ru", "system_error"), show_alert=True)
        return

    order_service = get_unified_order_service()
    if not order_service and callback.bot:
        order_service = init_unified_order_service(db_instance, callback.bot)
    partner_id = callback.from_user.id
    lang = db_instance.get_user_language(partner_id)

    match = REJECT_PATTERN.match(callback.data)
    if not match:
        await callback.answer(get_text(lang, "error"), show_alert=True)
        return

    prefix = match.group(1)
    entity_id = int(match.group(2))

    entity_type, entity = _determine_entity_type(prefix, entity_id, db_instance)
    if not entity:
        msg = get_text(lang, "order_not_found")
        await callback.answer(f"❌ {msg}", show_alert=True)
        return

    store_id = _get_entity_field(entity, "store_id")
    if not store_id:
        offer_id = _get_entity_field(entity, "offer_id")
        if offer_id:
            offer = db_instance.get_offer(offer_id)
            if offer:
                store_id = _get_entity_field(offer, "store_id")

    store = db_instance.get_store(store_id) if store_id else None
    if not can_manage_store(db_instance, store_id, partner_id, store=store):
        logger.warning(
            "Ownership verification failed in reject: partner=%s, owner=%s, %s=%s",
            partner_id,
            _get_store_field(store, "owner_id") if store else None,
            entity_type,
            entity_id,
        )
        await callback.answer(get_text(lang, "error"), show_alert=True)
        return

    if entity_type == "order" and _is_paid_online_order(entity):
        await callback.answer(get_text(lang, "paid_click_reject_blocked"), show_alert=True)
        return

    if order_service:
        success = await order_service.reject_order(entity_id, entity_type)
        if success:
            rejected_msg = get_text(lang, "order_rejected")
            await callback.answer(f"❌ {rejected_msg}")
            return
    else:
        try:
            db_instance.update_order_status(entity_id, OrderStatus.REJECTED)

            await _restore_quantities_fallback(db_instance, entity, entity_type)
            success = True
        except Exception as e:  # pragma: no cover - defensive logging
            logger.error(f"Failed to reject: {e}")
            success = False

    if not success:
        await callback.answer(_transition_error_text(order_service, lang), show_alert=True)
        return

    # NOTE: Customer notification is handled by UnifiedOrderService.reject_order()
    # No need to send duplicate message here

    # Update seller's message
    rejected_text = get_text(lang, "order_rejected_bold")
    try:
        if callback.message:
            if getattr(callback.message, "caption", None):
                await callback.message.edit_caption(
                    caption=_safe_caption(f"{callback.message.caption}\n\n{rejected_text}"),
                    parse_mode="HTML",
                )
            elif getattr(callback.message, "text", None):
                await callback.message.edit_text(
                    text=f"{callback.message.text}\n\n{rejected_text}",
                    parse_mode="HTML",
                )
    except Exception as e:  # pragma: no cover - defensive logging
        logger.warning(f"Failed to update seller message: {e}")

    rejected_msg = get_text(lang, "order_rejected")
    await callback.answer(f"❌ {rejected_msg}")


# ============================================================================
# ADDITIONAL STATUS UPDATE HANDLERS
# ============================================================================


async def order_ready_handler(callback: types.CallbackQuery) -> None:
    """Mark order as ready for courier handoff and edit seller message."""

    if not callback.from_user or not callback.data:
        await callback.answer()
        return

    db_instance = _get_db()
    if not db_instance:
        await callback.answer(get_text("ru", "system_error"), show_alert=True)
        return

    order_service = get_unified_order_service()
    if not order_service and callback.bot:
        order_service = init_unified_order_service(db_instance, callback.bot)
    partner_id = callback.from_user.id
    lang = db_instance.get_user_language(partner_id)

    try:
        order_id = int(callback.data.split("_")[-1])
    except ValueError:
        await callback.answer(get_text(lang, "error"), show_alert=True)
        return

    order = db_instance.get_order(order_id)
    if not order:
        await callback.answer(get_text(lang, "error"), show_alert=True)
        return

    order_type = _get_entity_field(order, "order_type")
    if not order_type:
        delivery_address = _get_entity_field(order, "delivery_address")
        order_type = "delivery" if delivery_address else "pickup"
    is_delivery = order_type in ("delivery", "taxi")

    store_id = _get_entity_field(order, "store_id")
    store = db_instance.get_store(store_id) if store_id else None
    if not can_manage_store(db_instance, store_id, partner_id, store=store):
        await callback.answer(get_text(lang, "error"), show_alert=True)
        return

    if _is_unpaid_online_order(order):
        await callback.answer(get_text(lang, "payment_not_confirmed"), show_alert=True)
        return

    if order_service:
        success = await order_service.mark_ready(order_id, "order")
        if success:
            msg = get_text(lang, "order_ready_success") if is_delivery else get_text(lang, "status_ready")
            await callback.answer(f"✅ {msg}")
            return
    else:
        try:
            db_instance.update_order_status(order_id, OrderStatus.READY)
            success = True
        except Exception:  # pragma: no cover
            success = False

    if not success:
        await callback.answer(_transition_error_text(order_service, lang), show_alert=True)
        return

    from app.core.utils import get_offer_field

    items: list[dict] = []
    delivery_address = _get_entity_field(order, "delivery_address")
    total = 0

    offer_id = _get_entity_field(order, "offer_id")
    quantity = _get_entity_field(order, "quantity", 1)
    if offer_id:
        offer = db_instance.get_offer(offer_id)
        if offer:
            title = get_offer_field(offer, "title", "Товар")
            price = get_offer_field(offer, "discount_price", 0)
            items.append({"title": title, "quantity": quantity, "price": price})
            total = price * quantity

    cart_items_json = _get_entity_field(order, "cart_items")
    if cart_items_json:
        try:
            cart_items = (
                json.loads(cart_items_json) if isinstance(cart_items_json, str) else cart_items_json
            )
            items = cart_items
            total = sum(item.get("price", 0) * item.get("quantity", 1) for item in cart_items)
        except Exception as e:  # pragma: no cover
            logger.warning(
                "Failed to save seller_message_id for order %s: %s",
                order_id,
                e,
            )

    delivery_price = _get_store_field(store, "delivery_price", 0) if is_delivery else 0

    customer_id = _get_entity_field(order, "user_id")
    customer_name = None
    customer_phone = None
    if customer_id:
        customer = db_instance.get_user_model(customer_id)
        if customer:
            customer_name = customer.first_name
            customer_phone = customer.phone

    currency = get_text(lang, "currency")
    payment_method = _get_entity_field(order, "payment_method")
    payment_status = _get_entity_field(order, "payment_status")
    payment_proof_photo_id = _get_entity_field(order, "payment_proof_photo_id")

    seller_text = NotificationTemplates.seller_status_update(
        lang=lang,
        order_id=order_id,
        status=OrderStatus.READY,
        order_type="delivery" if is_delivery else "pickup",
        items=items,
        customer_name=customer_name,
        customer_phone=customer_phone,
        delivery_address=delivery_address if is_delivery else None,
        total=total,
        delivery_price=delivery_price,
        currency=currency,
        payment_method=payment_method,
        payment_status=payment_status,
        payment_proof_photo_id=payment_proof_photo_id,
        created_at=_get_entity_field(order, "created_at"),
    )

    kb = InlineKeyboardBuilder()
    if is_delivery:
        kb.button(
            text=get_text(lang, "btn_enter_courier_phone"),
            callback_data=f"order_delivering_{order_id}",
        )
        kb.button(
            text=get_text(lang, "btn_skip"),
            callback_data=f"skip_courier_phone_{order_id}",
        )
        kb.adjust(2)
    else:
        kb.button(
            text=get_text(lang, "btn_mark_issued"),
            callback_data=f"order_complete_{order_id}",
        )
        kb.adjust(1)

    try:
        if callback.message:
            if getattr(callback.message, "caption", None):
                await callback.message.edit_caption(
                    caption=_safe_caption(seller_text),
                    parse_mode="HTML",
                    reply_markup=kb.as_markup(),
                )
            else:
                await callback.message.edit_text(
                    text=seller_text,
                    parse_mode="HTML",
                    reply_markup=kb.as_markup(),
                )
    except Exception as e:  # pragma: no cover
        logger.warning(f"Failed to edit ready message: {e}")
    if is_delivery:
        msg = get_text(lang, "order_ready_success")
        await callback.answer(f"✅ {msg}")
    else:
        msg = get_text(lang, "status_ready")
        await callback.answer(f"✅ {msg}")


async def order_delivering_handler(callback: types.CallbackQuery, state: FSMContext) -> None:
    """Seller clicks "Передал курьеру" - ask for courier phone first."""

    if not callback.from_user or not callback.data:
        await callback.answer()
        return

    db_instance = _get_db()
    if not db_instance:
        await callback.answer(get_text("ru", "system_error"), show_alert=True)
        return

    partner_id = callback.from_user.id
    lang = db_instance.get_user_language(partner_id)

    try:
        order_id = int(callback.data.split("_")[-1])
    except ValueError:
        await callback.answer(get_text(lang, "error"), show_alert=True)
        return

    order = db_instance.get_order(order_id)
    if not order:
        await callback.answer(get_text(lang, "error"), show_alert=True)
        return

    store_id = _get_entity_field(order, "store_id")
    store = db_instance.get_store(store_id) if store_id else None
    if not can_manage_store(db_instance, store_id, partner_id, store=store):
        await callback.answer(get_text(lang, "error"), show_alert=True)
        return

    if _is_unpaid_online_order(order):
        await callback.answer(get_text(lang, "payment_not_confirmed"), show_alert=True)
        return

    order_type = _get_entity_field(order, "order_type", "delivery")
    if order_type not in ("delivery", "taxi"):
        await callback.answer(get_text(lang, "courier_not_needed_pickup"), show_alert=True)
        return

    await state.set_state(CourierHandover.courier_phone)
    await state.update_data(
        order_id=order_id,
        seller_message_id=callback.message.message_id if callback.message else None,
        unified_flow=True,
    )

    kb = InlineKeyboardBuilder()
    kb.button(text=get_text(lang, "btn_skip"), callback_data=f"skip_courier_phone_{order_id}")

    prompt = get_text(lang, "courier_phone_prompt")

    # Update the existing order card instead of sending a new one
    try:
        if callback.message:
            if getattr(callback.message, "caption", None):
                await callback.message.edit_caption(
                    caption=_safe_caption(f"{callback.message.caption}\n\n{prompt}"),
                    parse_mode="HTML",
                    reply_markup=kb.as_markup(),
                )
            else:
                await callback.message.edit_text(
                    text=f"{(callback.message.text or '').strip()}\n\n{prompt}".strip(),
                    parse_mode="HTML",
                    reply_markup=kb.as_markup(),
                )
        elif callback.bot and callback.from_user:
            await callback.bot.send_message(
                callback.from_user.id,
                prompt,
                parse_mode="HTML",
                reply_markup=kb.as_markup(),
            )
    except Exception:  # pragma: no cover
        try:
            if callback.message:
                await callback.message.answer(
                    prompt, parse_mode="HTML", reply_markup=kb.as_markup()
                )
            elif callback.bot and callback.from_user:
                await callback.bot.send_message(
                    callback.from_user.id,
                    prompt,
                    parse_mode="HTML",
                    reply_markup=kb.as_markup(),
                )
        except Exception as e:
            logger.warning("Failed to send courier phone prompt: %s", e)

    await callback.answer()


async def skip_courier_phone_handler(callback: types.CallbackQuery, state: FSMContext) -> None:
    """Skip courier phone entry and proceed with delivery."""

    if not callback.from_user or not callback.data:
        await callback.answer()
        return

    db_instance = _get_db()
    lang = db_instance.get_user_language(callback.from_user.id) if db_instance else "ru"

    try:
        order_id = int(callback.data.split("_")[-1])
    except ValueError:
        await callback.answer(get_text(lang, "error"), show_alert=True)
        return

    await _process_delivery_handover(callback, state, order_id, courier_phone=None)


async def courier_phone_entered_handler(message: types.Message, state: FSMContext) -> None:
    """Process courier phone input (unified flow only)."""

    if not message.from_user or not message.text:
        return

    data = await state.get_data()
    order_id = data.get("order_id")

    if not data.get("unified_flow"):
        return

    if not order_id:
        await state.clear()
        return

    courier_phone = message.text.strip()

    digits_only = "".join(c for c in courier_phone if c.isdigit())
    if len(digits_only) < 7:
        db_instance = _get_db()
        lang = db_instance.get_user_language(message.from_user.id) if db_instance else "ru"
        await message.answer(get_text(lang, "courier_phone_invalid"))
        return

    await _process_delivery_handover(message, state, order_id, courier_phone=courier_phone)


async def _process_delivery_handover(
    event: types.Message | types.CallbackQuery,
    state: FSMContext,
    order_id: int,
    courier_phone: str | None = None,
) -> None:
    """Process delivery handover to courier - updates status and notifies customer."""

    from app.core.utils import get_offer_field

    db_instance = _get_db()
    if not db_instance:
        return

    data = await state.get_data()
    seller_message_id = data.get("seller_message_id")

    await state.clear()

    user_id = event.from_user.id if event.from_user else None
    if not user_id:
        return

    lang = db_instance.get_user_language(user_id)
    order_service = get_unified_order_service()
    if not order_service and getattr(event, "bot", None):
        order_service = init_unified_order_service(db_instance, event.bot)

    order = db_instance.get_order(order_id)
    if not order:
        return

    if _is_unpaid_online_order(order):
        message = get_text(lang, "payment_not_confirmed")
        if isinstance(event, types.Message):
            await event.answer(message)
        else:
            await event.answer(message, show_alert=True)
        return

    order_type = _get_entity_field(order, "order_type", "delivery")
    if order_type not in ("delivery", "taxi"):
        # Safety guard: pickup orders should not hit courier flow
        return

    store_id = _get_entity_field(order, "store_id")
    store = db_instance.get_store(store_id) if store_id else None

    if seller_message_id and hasattr(db_instance, "set_order_seller_message_id"):
        try:
            db_instance.set_order_seller_message_id(order_id, int(seller_message_id))
        except Exception:  # pragma: no cover
            pass

    if order_service:
        success = await order_service.start_delivery(order_id, courier_phone=courier_phone)
        if success:
            msg = get_text(lang, "courier_handover_done")
            if isinstance(event, types.CallbackQuery):
                await event.answer(f"🚚 {msg}", show_alert=True)
            else:
                await event.answer(f"🚚 {msg}")
                try:
                    await event.delete()
                except Exception:  # pragma: no cover
                    pass
            return
    else:
        try:
            db_instance.update_order_status(order_id, OrderStatus.DELIVERING)
            success = True
        except Exception:  # pragma: no cover
            success = False

    if not success:
        error_text = _transition_error_text(order_service, lang)
        if isinstance(event, types.Message):
            await event.answer(error_text)
        else:
            await event.answer(error_text, show_alert=True)
        return

    items: list[dict] = []
    delivery_address = _get_entity_field(order, "delivery_address")
    total = 0

    offer_id = _get_entity_field(order, "offer_id")
    quantity = _get_entity_field(order, "quantity", 1)
    if offer_id:
        offer = db_instance.get_offer(offer_id)
        if offer:
            title = get_offer_field(offer, "title", "Товар")
            price = get_offer_field(offer, "discount_price", 0)
            items.append({"title": title, "quantity": quantity, "price": price})
            total = price * quantity

    cart_items_json = _get_entity_field(order, "cart_items")
    if cart_items_json:
        try:
            cart_items = (
                json.loads(cart_items_json) if isinstance(cart_items_json, str) else cart_items_json
            )
            items = cart_items
            total = sum(item.get("price", 0) * item.get("quantity", 1) for item in cart_items)
        except Exception:  # pragma: no cover
            pass

    delivery_price = _get_store_field(store, "delivery_price", 0) if store else 0

    customer_id = _get_entity_field(order, "user_id")
    customer_name = None
    customer_phone_info = None
    if customer_id:
        customer = db_instance.get_user_model(customer_id)
        if customer:
            customer_name = customer.first_name
            customer_phone_info = customer.phone

    currency = get_text(lang, "currency")
    payment_method = _get_entity_field(order, "payment_method")
    payment_status = _get_entity_field(order, "payment_status")
    payment_proof_photo_id = _get_entity_field(order, "payment_proof_photo_id")

    seller_text = NotificationTemplates.seller_status_update(
        lang=lang,
        order_id=order_id,
        status=OrderStatus.DELIVERING,
        order_type="delivery",
        items=items,
        customer_name=customer_name,
        customer_phone=customer_phone_info,
        delivery_address=delivery_address,
        total=total,
        delivery_price=delivery_price,
        currency=currency,
        payment_method=payment_method,
        payment_status=payment_status,
        payment_proof_photo_id=payment_proof_photo_id,
        created_at=_get_entity_field(order, "created_at"),
    )

    safe_caption = _safe_caption(seller_text)
    edited = False
    if seller_message_id and getattr(event, "bot", None) and user_id:
        try:
            await event.bot.edit_message_caption(
                chat_id=user_id,
                message_id=seller_message_id,
                caption=safe_caption,
                parse_mode="HTML",
            )
            edited = True
        except Exception:
            try:
                await event.bot.edit_message_text(
                    chat_id=user_id,
                    message_id=seller_message_id,
                    text=seller_text,
                    parse_mode="HTML",
                )
                edited = True
            except Exception as e:  # pragma: no cover
                logger.warning(f"Failed to edit delivering message: {e}")

    if not edited and isinstance(event, types.CallbackQuery) and event.message:
        try:
            if getattr(event.message, "caption", None):
                await event.message.edit_caption(
                    caption=safe_caption,
                    parse_mode="HTML",
                )
            else:
                await event.message.edit_text(
                    text=seller_text,
                    parse_mode="HTML",
                )
        except Exception as e:  # pragma: no cover
            logger.warning(f"Failed to edit delivering message: {e}")

    msg = get_text(lang, "courier_handover_done")
    if isinstance(event, types.CallbackQuery):
        await event.answer(f"🚚 {msg}", show_alert=True)
    else:
        await event.answer(f"🚚 {msg}")
        try:
            await event.delete()
        except Exception:  # pragma: no cover
            pass


# ============================================================================
# COMPLETION / CANCELLATION
# ============================================================================


async def order_complete_handler(callback: types.CallbackQuery) -> None:
    """Mark order as completed and update seller message."""

    if not callback.from_user or not callback.data:
        await callback.answer()
        return

    db_instance = _get_db()
    if not db_instance:
        await callback.answer(get_text("ru", "system_error"), show_alert=True)
        return

    order_service = get_unified_order_service()
    if not order_service and callback.bot:
        order_service = init_unified_order_service(db_instance, callback.bot)
    partner_id = callback.from_user.id
    lang = db_instance.get_user_language(partner_id)

    try:
        order_id = int(callback.data.split("_")[-1])
    except ValueError:
        await callback.answer(get_text(lang, "error"), show_alert=True)
        return

    entity = db_instance.get_order(order_id)
    entity_type = "order"
    if not entity and hasattr(db_instance, "get_booking"):
        booking = db_instance.get_booking(order_id)
        if booking:
            entity = booking
            entity_type = "booking"
    if not entity:
        await callback.answer(get_text(lang, "error"), show_alert=True)
        return

    store_id = _get_entity_field(entity, "store_id")
    if not store_id:
        offer_id = _get_entity_field(entity, "offer_id")
        if offer_id:
            offer = db_instance.get_offer(offer_id)
            if offer:
                store_id = _get_entity_field(offer, "store_id")
    store = db_instance.get_store(store_id) if store_id else None
    if not can_manage_store(db_instance, store_id, partner_id, store=store):
        await callback.answer(get_text(lang, "error"), show_alert=True)
        return

    if order_service:
        success = await order_service.complete_order(order_id, entity_type)
        if success:
            msg = get_text(lang, "order_completed_seller")
            await callback.answer(f"🎉 {msg}")
            return
    else:
        try:
            if entity_type == "order":
                db_instance.update_order_status(order_id, OrderStatus.COMPLETED)
            else:
                db_instance.update_booking_status(order_id, OrderStatus.COMPLETED)
            success = True
        except Exception:  # pragma: no cover
            success = False

    if not success:
        await callback.answer(_transition_error_text(order_service, lang), show_alert=True)
        return

    from app.core.utils import get_offer_field

    items: list[dict] = []
    delivery_address = None
    total = 0
    delivery_price = 0
    order_type = "pickup"

    if entity_type == "order":
        delivery_address = _get_entity_field(entity, "delivery_address")

        offer_id = _get_entity_field(entity, "offer_id")
        quantity = _get_entity_field(entity, "quantity", 1)
        if offer_id:
            offer = db_instance.get_offer(offer_id)
            if offer:
                title = get_offer_field(offer, "title", "Товар")
                price = get_offer_field(offer, "discount_price", 0)
                items.append({"title": title, "quantity": quantity, "price": price})
                total = price * quantity

        cart_items_json = _get_entity_field(entity, "cart_items")
        if cart_items_json:
            try:
                cart_items = (
                    json.loads(cart_items_json)
                    if isinstance(cart_items_json, str)
                    else cart_items_json
                )
                items = cart_items
                total = sum(item.get("price", 0) * item.get("quantity", 1) for item in cart_items)
            except Exception:  # pragma: no cover
                pass

        delivery_price = _get_store_field(store, "delivery_price", 0)
        # Respect actual order_type from DB so pickup orders don't
        # render as delivery in seller/status templates.
        order_type = _get_entity_field(entity, "order_type", "delivery")
    else:
        # Booking (pickup by default)
        is_cart_booking = _get_entity_field(entity, "is_cart_booking", 0) == 1
        cart_items_json = _get_entity_field(entity, "cart_items")
        if is_cart_booking and cart_items_json:
            try:
                cart_items = (
                    json.loads(cart_items_json)
                    if isinstance(cart_items_json, str)
                    else cart_items_json
                )
                items = cart_items
                total = sum(item.get("price", 0) * item.get("quantity", 1) for item in cart_items)
            except Exception:  # pragma: no cover
                pass
        else:
            offer_id = _get_entity_field(entity, "offer_id")
            quantity = _get_entity_field(entity, "quantity", 1)
            if offer_id:
                offer = db_instance.get_offer(offer_id)
                if offer:
                    title = get_offer_field(offer, "title", "Товар")
                    price = get_offer_field(offer, "discount_price", 0)
                    items.append({"title": title, "quantity": quantity, "price": price})
                    total = price * quantity

    customer_id = _get_entity_field(entity, "user_id")
    customer_name = None
    customer_phone = None
    if customer_id:
        customer = db_instance.get_user_model(customer_id)
        if customer:
            customer_name = customer.first_name
            customer_phone = customer.phone

    currency = get_text(lang, "currency")
    payment_method = _get_entity_field(entity, "payment_method")
    payment_status = _get_entity_field(entity, "payment_status")
    payment_proof_photo_id = _get_entity_field(entity, "payment_proof_photo_id")

    seller_text = NotificationTemplates.seller_status_update(
        lang=lang,
        order_id=order_id,
        status=OrderStatus.COMPLETED,
        order_type=order_type,
        items=items,
        customer_name=customer_name,
        customer_phone=customer_phone,
        delivery_address=delivery_address,
        total=total,
        delivery_price=delivery_price,
        currency=currency,
        payment_method=payment_method,
        payment_status=payment_status,
        payment_proof_photo_id=payment_proof_photo_id,
        created_at=_get_entity_field(entity, "created_at"),
    )

    try:
        if callback.message:
            if getattr(callback.message, "caption", None):
                await callback.message.edit_caption(
                    caption=_safe_caption(seller_text),
                    parse_mode="HTML",
                )
            else:
                await callback.message.edit_text(
                    text=seller_text,
                    parse_mode="HTML",
                )
    except Exception as e:  # pragma: no cover
        logger.warning(f"Failed to edit complete message: {e}")

    msg = get_text(lang, "order_completed_seller")
    await callback.answer(f"🎉 {msg}")


async def order_cancel_seller_handler(callback: types.CallbackQuery) -> None:
    """Seller cancels order after confirmation."""

    if not callback.from_user or not callback.data:
        await callback.answer()
        return

    db_instance = _get_db()
    if not db_instance:
        await callback.answer(get_text("ru", "system_error"), show_alert=True)
        return

    order_service = get_unified_order_service()
    if not order_service and callback.bot:
        order_service = init_unified_order_service(db_instance, callback.bot)
    partner_id = callback.from_user.id
    lang = db_instance.get_user_language(partner_id)

    try:
        entity_id = int(callback.data.split("_")[-1])
    except ValueError:
        await callback.answer(get_text(lang, "error"), show_alert=True)
        return
    entity = db_instance.get_order(entity_id)
    entity_type = "order"

    if not entity:
        await callback.answer(get_text(lang, "error"), show_alert=True)
        return

    store_id = _get_entity_field(entity, "store_id")
    store = db_instance.get_store(store_id) if store_id else None
    if not can_manage_store(db_instance, store_id, partner_id, store=store):
        await callback.answer(get_text(lang, "error"), show_alert=True)
        return

    if _is_paid_online_order(entity):
        await callback.answer(get_text(lang, "paid_click_reject_blocked"), show_alert=True)
        return

    if order_service:
        success = await order_service.reject_order(entity_id, entity_type, "Отменено продавцом")
    else:
        try:
            db_instance.update_order_status(entity_id, OrderStatus.CANCELLED)
            await _restore_quantities_fallback(db_instance, entity, entity_type)
            success = True
        except Exception:  # pragma: no cover
            success = False

    if not success:
        await callback.answer(_transition_error_text(order_service, lang), show_alert=True)
        return

    try:
        cancel_text = get_text(lang, "order_cancelled_bold")
        if callback.message and getattr(callback.message, "text", None):
            await callback.message.edit_text(
                text=f"{callback.message.text}\n\n{cancel_text}",
                parse_mode="HTML",
            )
    except Exception:  # pragma: no cover
        pass

    msg = get_text(lang, "order_cancelled")
    await callback.answer(f"❌ {msg}")


def register(router: Router) -> None:
    """Register all seller-side unified order handlers on the router."""

    router.callback_query.register(unified_confirm_handler, F.data.regexp(CONFIRM_PATTERN))
    router.callback_query.register(unified_reject_handler, F.data.regexp(REJECT_PATTERN))

    router.callback_query.register(order_ready_handler, F.data.regexp(r"^order_ready_(\d+)$"))
    router.callback_query.register(
        order_delivering_handler, F.data.regexp(r"^order_delivering_(\d+)$")
    )
    router.callback_query.register(
        order_delivering_handler, F.data.regexp(r"^handover_courier_(\d+)$")
    )
    router.callback_query.register(
        skip_courier_phone_handler, F.data.regexp(r"^skip_courier_phone_(\d+)$")
    )

    router.message.register(
        courier_phone_entered_handler,
        F.text,
        StateFilter(CourierHandover.courier_phone),
    )

    router.callback_query.register(order_complete_handler, F.data.regexp(r"^order_complete_(\d+)$"))
    router.callback_query.register(
        order_cancel_seller_handler, F.data.regexp(r"^order_cancel_seller_(\d+)$")
    )
