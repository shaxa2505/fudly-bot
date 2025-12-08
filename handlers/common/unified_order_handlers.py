"""
Unified Order Handlers - Single entry point for order confirm/reject callbacks.

This module provides unified handlers for:
- order_confirm_{id} - Seller confirms order (both pickup and delivery)
- order_reject_{id} - Seller rejects order
- Backward compatibility with old patterns (partner_confirm_, partner_reject_)

All callbacks are routed here and use UnifiedOrderService for consistent
status updates and customer notifications.
"""
from __future__ import annotations

import re
from typing import Any

from aiogram import F, Router, types
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.services.unified_order_service import (
    OrderStatus,
    get_unified_order_service,
)
from handlers.common.states import CourierHandover
from handlers.common.utils import html_escape as _esc
from localization import get_text

# State filter alias for convenience
state_filter = StateFilter

try:
    from logging_config import logger
except ImportError:
    import logging

    logger = logging.getLogger(__name__)


router = Router(name="unified_order_handlers")

# Module dependencies
db: Any = None
bot: Any = None


def setup_dependencies(database: Any, bot_instance: Any) -> None:
    """Setup module dependencies."""
    global db, bot
    db = database
    bot = bot_instance


def _get_db():
    """Get database instance."""
    return db


def _get_store_field(store: Any, field: str, default: Any = None) -> Any:
    """Get field from store dict or object."""
    if isinstance(store, dict):
        return store.get(field, default)
    return getattr(store, field, default) if store else default


def _get_entity_field(entity: Any, field: str, default: Any = None) -> Any:
    """Get field from entity dict or tuple."""
    if isinstance(entity, dict):
        return entity.get(field, default)
    if hasattr(entity, field):
        return getattr(entity, field, default)
    return default


# =============================================================================
# UNIFIED CONFIRM/REJECT HANDLERS
# =============================================================================

# Regex patterns for all supported callback formats
# New format with explicit type: booking_confirm_{id}, order_confirm_{id}
# Legacy formats also supported for backward compatibility
CONFIRM_PATTERN = re.compile(
    r"^(booking_confirm_|order_confirm_|partner_confirm_order_|partner_confirm_|confirm_order_)(\d+)$"
)
REJECT_PATTERN = re.compile(
    r"^(booking_reject_|order_reject_|partner_reject_order_|partner_reject_|cancel_order_)(\d+)$"
)

# Mapping from callback prefix to entity type
PREFIX_TO_TYPE = {
    "booking_confirm_": "booking",
    "booking_reject_": "booking",
    "partner_confirm_": "booking",  # Legacy booking pattern
    "partner_reject_": "booking",  # Legacy booking pattern
    "order_confirm_": "order",
    "order_reject_": "order",
    "partner_confirm_order_": "order",  # Legacy order pattern
    "partner_reject_order_": "order",  # Legacy order pattern
    "confirm_order_": "order",
    "cancel_order_": "order",
}


def _determine_entity_type(prefix: str, entity_id: int, db_instance: Any) -> tuple[str, Any]:
    """
    Determine entity type from callback prefix.
    Falls back to checking both tables if prefix is ambiguous.

    Returns: (entity_type, entity) or ("unknown", None) if not found
    """
    # First try to determine from prefix
    suggested_type = PREFIX_TO_TYPE.get(prefix)

    if suggested_type == "booking":
        entity = db_instance.get_booking(entity_id)
        if entity:
            return ("booking", entity)
    elif suggested_type == "order":
        entity = db_instance.get_order(entity_id)
        if entity:
            return ("order", entity)

    # Fallback: check both tables (for generic patterns like order_confirm_)
    # This handles WebApp orders that might be bookings or orders
    entity = db_instance.get_order(entity_id)
    if entity:
        return ("order", entity)

    entity = db_instance.get_booking(entity_id)
    if entity:
        return ("booking", entity)

    return ("unknown", None)


@router.callback_query(F.data.regexp(CONFIRM_PATTERN))
async def unified_confirm_handler(callback: types.CallbackQuery) -> None:
    """
    Unified handler for order confirmation.

    Supports callback patterns:
    - booking_confirm_{id} (explicit booking)
    - order_confirm_{id} (explicit order or generic)
    - partner_confirm_order_{id} (legacy orders)
    - partner_confirm_{id} (legacy bookings)
    - confirm_order_{id} (legacy)
    """
    if not callback.from_user or not callback.data:
        await callback.answer()
        return

    db_instance = _get_db()
    if not db_instance:
        await callback.answer("System error", show_alert=True)
        return

    order_service = get_unified_order_service()
    partner_id = callback.from_user.id
    lang = db_instance.get_user_language(partner_id)

    # Extract entity ID from callback
    match = CONFIRM_PATTERN.match(callback.data)
    if not match:
        await callback.answer("❌", show_alert=True)
        return

    prefix = match.group(1)
    entity_id = int(match.group(2))

    # Use smart entity type detection based on prefix
    entity_type, entity = _determine_entity_type(prefix, entity_id, db_instance)

    if not entity:
        msg = "Buyurtma topilmadi" if lang == "uz" else "Заказ не найден"
        await callback.answer(f"❌ {msg}", show_alert=True)
        return

    # Verify ownership
    store_id = _get_entity_field(entity, "store_id")
    if not store_id:
        # Try to get from offer for old bookings
        offer_id = _get_entity_field(entity, "offer_id")
        if offer_id:
            offer = db_instance.get_offer(offer_id)
            if offer:
                store_id = _get_entity_field(offer, "store_id")

    store = db_instance.get_store(store_id) if store_id else None
    owner_id = _get_store_field(store, "owner_id") if store else None

    if not owner_id or partner_id != owner_id:
        logger.warning(
            f"Ownership verification failed: partner={partner_id}, owner={owner_id}, "
            f"{entity_type}={entity_id}"
        )
        await callback.answer("❌", show_alert=True)
        return

    # Use UnifiedOrderService if available, otherwise fallback
    if order_service:
        success = await order_service.confirm_order(entity_id, entity_type)
    else:
        # Fallback: direct update
        try:
            if entity_type == "order":
                db_instance.update_order_status(entity_id, OrderStatus.PREPARING)
            else:
                db_instance.update_booking_status(entity_id, "confirmed")
            success = True
        except Exception as e:
            logger.error(f"Failed to confirm: {e}")
            success = False

    if not success:
        await callback.answer(get_text(lang, "error") or "Error", show_alert=True)
        return

    # Get order details for updated message
    from app.core.utils import get_offer_field
    from app.services.unified_order_service import NotificationTemplates

    # Build items list
    items = []
    order_type = "delivery" if entity_type == "order" else "pickup"
    delivery_address = None
    customer_name = None
    customer_phone = None
    total = 0
    delivery_price = 0

    if entity_type == "order":
        order_type_db = _get_entity_field(entity, "order_type", "delivery")
        if order_type_db:
            order_type = order_type_db
        delivery_address = _get_entity_field(entity, "delivery_address")

        # Get item info
        offer_id = _get_entity_field(entity, "offer_id")
        quantity = _get_entity_field(entity, "quantity", 1)
        if offer_id:
            offer = db_instance.get_offer(offer_id)
            if offer:
                title = get_offer_field(offer, "title", "Товар")
                price = get_offer_field(offer, "discount_price", 0)
                items.append({"title": title, "quantity": quantity, "price": price})
                total = price * quantity

        # Check cart items
        import json

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
            except Exception:
                pass

        delivery_price = (
            _get_store_field(store, "delivery_price", 0) if order_type == "delivery" else 0
        )
    else:
        # Booking (pickup)
        offer_id = _get_entity_field(entity, "offer_id")
        quantity = _get_entity_field(entity, "quantity", 1)
        if offer_id:
            offer = db_instance.get_offer(offer_id)
            if offer:
                title = get_offer_field(offer, "title", "Товар")
                price = get_offer_field(offer, "discount_price", 0)
                items.append({"title": title, "quantity": quantity, "price": price})
                total = price * quantity

    # Get customer info
    customer_id = _get_entity_field(entity, "user_id")
    if customer_id:
        customer = db_instance.get_user_model(customer_id)
        if customer:
            customer_name = customer.first_name
            customer_phone = customer.phone

    currency = "so'm" if lang == "uz" else "сум"

    # Build SINGLE updated message with new status and buttons
    seller_text = NotificationTemplates.seller_status_update(
        lang=lang,
        order_id=entity_id,
        status=OrderStatus.PREPARING,
        order_type=order_type,
        items=items,
        customer_name=customer_name,
        customer_phone=customer_phone,
        delivery_address=delivery_address,
        total=total,
        delivery_price=delivery_price,
        currency=currency,
    )

    # Build action buttons based on entity type and order type
    kb = InlineKeyboardBuilder()
    if entity_type == "booking":
        # For pickup - show "Выдано" button
        if lang == "uz":
            kb.button(text="✅ Topshirildi", callback_data=f"complete_booking_{entity_id}")
        else:
            kb.button(text="✅ Выдано", callback_data=f"complete_booking_{entity_id}")
    else:
        # For delivery - show "Готов к передаче" button (step 1 of courier handoff)
        if lang == "uz":
            kb.button(text="📦 Topshirishga tayyor", callback_data=f"order_ready_{entity_id}")
        else:
            kb.button(text="📦 Готов к передаче", callback_data=f"order_ready_{entity_id}")
    kb.adjust(1)

    # EDIT the existing message instead of sending new one
    try:
        if callback.message:
            if hasattr(callback.message, "caption") and callback.message.caption:
                await callback.message.edit_caption(
                    caption=seller_text,
                    parse_mode="HTML",
                    reply_markup=kb.as_markup(),
                )
            else:
                await callback.message.edit_text(
                    text=seller_text,
                    parse_mode="HTML",
                    reply_markup=kb.as_markup(),
                )
    except Exception as e:
        logger.warning(f"Failed to edit seller message: {e}")

    confirmed_msg = "Tasdiqlandi" if lang == "uz" else "Подтверждено"
    await callback.answer(f"✅ {confirmed_msg}")


@router.callback_query(F.data.regexp(REJECT_PATTERN))
async def unified_reject_handler(callback: types.CallbackQuery) -> None:
    """
    Unified handler for order rejection.

    Supports callback patterns:
    - order_reject_{id} (new unified)
    - booking_reject_{id} (explicit booking)
    - order_reject_{id} (explicit order or generic)
    - partner_reject_order_{id} (legacy orders)
    - partner_reject_{id} (legacy bookings)
    - cancel_order_{id} (legacy)
    """
    if not callback.from_user or not callback.data:
        await callback.answer()
        return

    db_instance = _get_db()
    if not db_instance:
        await callback.answer("System error", show_alert=True)
        return

    order_service = get_unified_order_service()
    partner_id = callback.from_user.id
    lang = db_instance.get_user_language(partner_id)

    # Extract entity ID from callback
    match = REJECT_PATTERN.match(callback.data)
    if not match:
        await callback.answer("❌", show_alert=True)
        return

    prefix = match.group(1)
    entity_id = int(match.group(2))

    # Use smart entity type detection based on prefix
    entity_type, entity = _determine_entity_type(prefix, entity_id, db_instance)

    if not entity:
        msg = "Buyurtma topilmadi" if lang == "uz" else "Заказ не найден"
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
    owner_id = _get_store_field(store, "owner_id") if store else None

    if not owner_id or partner_id != owner_id:
        logger.warning(
            f"Ownership verification failed in reject: partner={partner_id}, owner={owner_id}, "
            f"{entity_type}={entity_id}"
        )
        await callback.answer("❌", show_alert=True)
        return

    # Use UnifiedOrderService if available
    if order_service:
        success = await order_service.reject_order(entity_id, entity_type)
    else:
        # Fallback: direct update with quantity restoration
        try:
            if entity_type == "order":
                db_instance.update_order_status(entity_id, OrderStatus.REJECTED)
            else:
                db_instance.cancel_booking(entity_id)

            # Restore quantities
            await _restore_quantities_fallback(db_instance, entity, entity_type)
            success = True
        except Exception as e:
            logger.error(f"Failed to reject: {e}")
            success = False

    if not success:
        await callback.answer(get_text(lang, "error") or "Error", show_alert=True)
        return

    # Update seller's message
    try:
        if callback.message:
            rejected_text = "❌ <b>RAD ETILDI</b>" if lang == "uz" else "❌ <b>ОТКЛОНЕНО</b>"

            if hasattr(callback.message, "caption") and callback.message.caption:
                await callback.message.edit_caption(
                    caption=callback.message.caption + f"\n\n{rejected_text}",
                    parse_mode="HTML",
                )
            elif hasattr(callback.message, "text") and callback.message.text:
                await callback.message.edit_text(
                    text=callback.message.text + f"\n\n{rejected_text}",
                    parse_mode="HTML",
                )
    except Exception as e:
        logger.warning(f"Failed to update seller message: {e}")

    rejected_msg = "Rad etildi" if lang == "uz" else "Отклонено"
    await callback.answer(f"❌ {rejected_msg}")


async def _restore_quantities_fallback(db_instance: Any, entity: Any, entity_type: str) -> None:
    """Restore offer quantities (fallback without order service)."""
    import json

    try:
        if isinstance(entity, dict):
            is_cart = entity.get("is_cart_order", 0) == 1 or entity.get("is_cart_booking", 0) == 1
            cart_items_json = entity.get("cart_items")
            offer_id = entity.get("offer_id")
            quantity = entity.get("quantity", 1)
        else:
            is_cart = (
                getattr(entity, "is_cart_order", 0) == 1
                or getattr(entity, "is_cart_booking", 0) == 1
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
                    except Exception:
                        pass
        elif offer_id:
            try:
                db_instance.increment_offer_quantity_atomic(offer_id, int(quantity))
            except Exception:
                pass

    except Exception as e:
        logger.error(f"Failed to restore quantities: {e}")


# =============================================================================
# ADDITIONAL STATUS UPDATE HANDLERS
# =============================================================================


@router.callback_query(F.data.regexp(r"^order_ready_(\d+)$"))
async def order_ready_handler(callback: types.CallbackQuery) -> None:
    """Mark order as ready for courier handoff - EDITS existing message."""
    if not callback.from_user or not callback.data:
        await callback.answer()
        return

    db_instance = _get_db()
    if not db_instance:
        await callback.answer("System error", show_alert=True)
        return

    order_service = get_unified_order_service()
    partner_id = callback.from_user.id
    lang = db_instance.get_user_language(partner_id)

    try:
        order_id = int(callback.data.split("_")[-1])
    except ValueError:
        await callback.answer("❌", show_alert=True)
        return

    order = db_instance.get_order(order_id)
    if not order:
        await callback.answer("❌", show_alert=True)
        return

    # Verify ownership
    store_id = _get_entity_field(order, "store_id")
    store = db_instance.get_store(store_id) if store_id else None
    owner_id = _get_store_field(store, "owner_id") if store else None

    if not owner_id or partner_id != owner_id:
        await callback.answer("❌", show_alert=True)
        return

    if order_service:
        success = await order_service.mark_ready(order_id, "order")
    else:
        try:
            db_instance.update_order_status(order_id, OrderStatus.READY)
            success = True
        except Exception:
            success = False

    if not success:
        await callback.answer("❌", show_alert=True)
        return

    # Build updated seller message with READY status
    import json

    from app.core.utils import get_offer_field
    from app.services.unified_order_service import NotificationTemplates

    # Get order details
    items = []
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

    # Check cart items
    cart_items_json = _get_entity_field(order, "cart_items")
    if cart_items_json:
        try:
            cart_items = (
                json.loads(cart_items_json) if isinstance(cart_items_json, str) else cart_items_json
            )
            items = cart_items
            total = sum(item.get("price", 0) * item.get("quantity", 1) for item in cart_items)
        except Exception:
            pass

    delivery_price = _get_store_field(store, "delivery_price", 0)

    # Get customer info
    customer_id = _get_entity_field(order, "user_id")
    customer_name = None
    customer_phone = None
    if customer_id:
        customer = db_instance.get_user_model(customer_id)
        if customer:
            customer_name = customer.first_name
            customer_phone = customer.phone

    currency = "so'm" if lang == "uz" else "сум"

    seller_text = NotificationTemplates.seller_status_update(
        lang=lang,
        order_id=order_id,
        status=OrderStatus.READY,
        order_type="delivery",
        items=items,
        customer_name=customer_name,
        customer_phone=customer_phone,
        delivery_address=delivery_address,
        total=total,
        delivery_price=delivery_price,
        currency=currency,
    )

    # Button to hand off to courier
    kb = InlineKeyboardBuilder()
    if lang == "uz":
        kb.button(text="🚚 Kuryerga topshirdim", callback_data=f"order_delivering_{order_id}")
    else:
        kb.button(text="🚚 Передал курьеру", callback_data=f"order_delivering_{order_id}")
    kb.adjust(1)

    # EDIT message
    try:
        if callback.message:
            if hasattr(callback.message, "caption") and callback.message.caption:
                await callback.message.edit_caption(
                    caption=seller_text,
                    parse_mode="HTML",
                    reply_markup=kb.as_markup(),
                )
            else:
                await callback.message.edit_text(
                    text=seller_text,
                    parse_mode="HTML",
                    reply_markup=kb.as_markup(),
                )
    except Exception as e:
        logger.warning(f"Failed to edit ready message: {e}")

    msg = "Tayyor!" if lang == "uz" else "Готово к передаче!"
    await callback.answer(f"📦 {msg}")


@router.callback_query(F.data.regexp(r"^order_delivering_(\d+)$"))
async def order_delivering_handler(callback: types.CallbackQuery, state: FSMContext) -> None:
    """Seller clicks "Передал курьеру" - ask for courier phone first."""
    if not callback.from_user or not callback.data:
        await callback.answer()
        return

    db_instance = _get_db()
    if not db_instance:
        await callback.answer("System error", show_alert=True)
        return

    partner_id = callback.from_user.id
    lang = db_instance.get_user_language(partner_id)

    try:
        order_id = int(callback.data.split("_")[-1])
    except ValueError:
        await callback.answer("❌", show_alert=True)
        return

    order = db_instance.get_order(order_id)
    if not order:
        await callback.answer("❌", show_alert=True)
        return

    # Verify ownership
    store_id = _get_entity_field(order, "store_id")
    store = db_instance.get_store(store_id) if store_id else None
    owner_id = _get_store_field(store, "owner_id") if store else None

    if not owner_id or partner_id != owner_id:
        await callback.answer("❌", show_alert=True)
        return

    # Save order_id in state and ask for courier phone
    from handlers.common.states import CourierHandover

    await state.set_state(CourierHandover.courier_phone)
    await state.update_data(
        order_id=order_id,
        seller_message_id=callback.message.message_id if callback.message else None,
        unified_flow=True,  # Flag to distinguish from order_management flow
    )

    # Ask for courier phone - add skip button
    kb = InlineKeyboardBuilder()
    skip_text = "⏩ O'tkazib yuborish" if lang == "uz" else "⏩ Пропустить"
    kb.button(text=skip_text, callback_data=f"skip_courier_phone_{order_id}")

    prompt = (
        "📱 Kuryer telefon raqamini kiriting:\n\n" "<i>Mijoz kuryer bilan bog'lanishi uchun</i>"
        if lang == "uz"
        else "📱 Введите телефон курьера:\n\n" "<i>Чтобы клиент мог связаться с курьером</i>"
    )

    try:
        await callback.message.answer(prompt, parse_mode="HTML", reply_markup=kb.as_markup())
    except Exception:
        pass

    await callback.answer()


@router.callback_query(F.data.regexp(r"^skip_courier_phone_(\d+)$"))
async def skip_courier_phone_handler(callback: types.CallbackQuery, state: FSMContext) -> None:
    """Skip courier phone entry and proceed with delivery."""
    if not callback.from_user or not callback.data:
        await callback.answer()
        return

    try:
        order_id = int(callback.data.split("_")[-1])
    except ValueError:
        await callback.answer("❌", show_alert=True)
        return

    # Process delivery without courier phone
    await _process_delivery_handover(callback, state, order_id, courier_phone=None)


@router.message(F.text, StateFilter(CourierHandover.courier_phone))
async def courier_phone_entered_handler(message: types.Message, state: FSMContext) -> None:
    """Process courier phone input (unified flow only)."""
    if not message.from_user or not message.text:
        return

    data = await state.get_data()
    order_id = data.get("order_id")

    # Only handle unified flow - let order_management handle legacy flow
    if not data.get("unified_flow"):
        return

    if not order_id:
        await state.clear()
        return

    # Clean phone number
    courier_phone = message.text.strip()

    # Basic validation - should contain digits
    digits_only = "".join(c for c in courier_phone if c.isdigit())
    if len(digits_only) < 7:
        db_instance = _get_db()
        lang = db_instance.get_user_language(message.from_user.id) if db_instance else "ru"
        error_text = (
            "❌ Noto'g'ri telefon raqami. Qaytadan kiriting:"
            if lang == "uz"
            else "❌ Неверный номер. Введите ещё раз:"
        )
        await message.answer(error_text)
        return

    # Process delivery with courier phone
    await _process_delivery_handover(message, state, order_id, courier_phone=courier_phone)


async def _process_delivery_handover(
    event: types.Message | types.CallbackQuery,
    state: FSMContext,
    order_id: int,
    courier_phone: str | None = None,
) -> None:
    """Process delivery handover to courier - updates status and notifies customer."""
    import json

    from app.core.utils import get_offer_field
    from app.services.unified_order_service import NotificationTemplates

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

    order = db_instance.get_order(order_id)
    if not order:
        return

    store_id = _get_entity_field(order, "store_id")
    store = db_instance.get_store(store_id) if store_id else None

    # Update order status with courier phone
    if order_service:
        success = await order_service.start_delivery(order_id, courier_phone=courier_phone)
    else:
        try:
            db_instance.update_order_status(order_id, OrderStatus.DELIVERING)
            success = True
        except Exception:
            success = False

    if not success:
        error_text = "❌ Xatolik yuz berdi" if lang == "uz" else "❌ Произошла ошибка"
        if isinstance(event, types.Message):
            await event.answer(error_text)
        else:
            await event.answer(error_text, show_alert=True)
        return

    # Build updated seller message with DELIVERING status
    items = []
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

    # Check cart items
    cart_items_json = _get_entity_field(order, "cart_items")
    if cart_items_json:
        try:
            cart_items = (
                json.loads(cart_items_json) if isinstance(cart_items_json, str) else cart_items_json
            )
            items = cart_items
            total = sum(item.get("price", 0) * item.get("quantity", 1) for item in cart_items)
        except Exception:
            pass

    delivery_price = _get_store_field(store, "delivery_price", 0) if store else 0

    # Get customer info
    customer_id = _get_entity_field(order, "user_id")
    customer_name = None
    customer_phone_info = None
    if customer_id:
        customer = db_instance.get_user_model(customer_id)
        if customer:
            customer_name = customer.first_name
            customer_phone_info = customer.phone

    currency = "so'm" if lang == "uz" else "сум"

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
    )

    # Add courier phone info to seller text
    if courier_phone:
        courier_label = "Kuryer" if lang == "uz" else "Курьер"
        seller_text += f"\n\n📞 {courier_label}: <code>{courier_phone}</code>"

    # Try to edit original seller message or send confirmation
    if isinstance(event, types.CallbackQuery) and event.message:
        try:
            if hasattr(event.message, "caption") and event.message.caption:
                await event.message.edit_caption(
                    caption=seller_text,
                    parse_mode="HTML",
                )
            else:
                await event.message.edit_text(
                    text=seller_text,
                    parse_mode="HTML",
                )
        except Exception as e:
            logger.warning(f"Failed to edit delivering message: {e}")

    # Send confirmation
    msg = "Kuryerga topshirildi" if lang == "uz" else "Передано курьеру"
    if isinstance(event, types.CallbackQuery):
        await event.answer(f"🚚 {msg}", show_alert=True)
    else:
        await event.answer(f"🚚 {msg}")
        # Delete phone prompt message
        try:
            await event.delete()
        except Exception:
            pass


@router.callback_query(F.data.regexp(r"^customer_received_(\d+)$"))
async def customer_received_handler(callback: types.CallbackQuery) -> None:
    """Customer confirms they received the order - marks as COMPLETED."""
    if not callback.from_user or not callback.data:
        await callback.answer()
        return

    db_instance = _get_db()
    if not db_instance:
        await callback.answer("System error", show_alert=True)
        return

    order_service = get_unified_order_service()
    customer_id = callback.from_user.id
    lang = db_instance.get_user_language(customer_id)

    try:
        order_id = int(callback.data.split("_")[-1])
    except ValueError:
        await callback.answer("❌", show_alert=True)
        return

    order = db_instance.get_order(order_id)
    if not order:
        await callback.answer("❌", show_alert=True)
        return

    # Verify this is the customer's order
    order_user_id = _get_entity_field(order, "user_id")
    if order_user_id != customer_id:
        await callback.answer("❌", show_alert=True)
        return

    # Check order status is DELIVERING
    current_status = _get_entity_field(order, "status")
    if current_status != OrderStatus.DELIVERING:
        msg = "Buyurtma allaqachon yakunlangan" if lang == "uz" else "Заказ уже завершён"
        await callback.answer(msg, show_alert=True)
        return

    # Complete the order
    if order_service:
        success = await order_service.complete_order(order_id, "order")
    else:
        try:
            db_instance.update_order_status(order_id, OrderStatus.COMPLETED)
            success = True
        except Exception:
            success = False

    if not success:
        await callback.answer("❌", show_alert=True)
        return

    # Update customer message with completed status + rating buttons
    from app.services.unified_order_service import NotificationTemplates

    store_id = _get_entity_field(order, "store_id")
    store = db_instance.get_store(store_id) if store_id else None
    store_name = _get_store_field(store, "name", "")

    completed_text = NotificationTemplates.customer_status_update(
        lang=lang,
        order_id=order_id,
        status=OrderStatus.COMPLETED,
        order_type="delivery",
        store_name=store_name,
    )

    # Add rating buttons
    kb = InlineKeyboardBuilder()
    for i in range(1, 6):
        kb.button(text="⭐" * i, callback_data=f"rate_order_{order_id}_{i}")
    kb.adjust(5)

    try:
        if callback.message:
            if hasattr(callback.message, "caption") and callback.message.caption:
                await callback.message.edit_caption(
                    caption=completed_text,
                    parse_mode="HTML",
                    reply_markup=kb.as_markup(),
                )
            else:
                await callback.message.edit_text(
                    text=completed_text,
                    parse_mode="HTML",
                    reply_markup=kb.as_markup(),
                )
    except Exception as e:
        logger.warning(f"Failed to edit customer received message: {e}")

    msg = "Rahmat! Buyurtma yakunlandi" if lang == "uz" else "Спасибо! Заказ завершён"
    await callback.answer(f"✅ {msg}", show_alert=True)


@router.callback_query(F.data.regexp(r"^order_complete_(\d+)$"))
async def order_complete_handler(callback: types.CallbackQuery) -> None:
    """Mark order as completed - EDITS existing message."""
    if not callback.from_user or not callback.data:
        await callback.answer()
        return

    db_instance = _get_db()
    if not db_instance:
        await callback.answer("System error", show_alert=True)
        return

    order_service = get_unified_order_service()
    partner_id = callback.from_user.id
    lang = db_instance.get_user_language(partner_id)

    try:
        order_id = int(callback.data.split("_")[-1])
    except ValueError:
        await callback.answer("❌", show_alert=True)
        return

    order = db_instance.get_order(order_id)
    if not order:
        await callback.answer("❌", show_alert=True)
        return

    # Verify ownership
    store_id = _get_entity_field(order, "store_id")
    store = db_instance.get_store(store_id) if store_id else None
    owner_id = _get_store_field(store, "owner_id") if store else None

    if not owner_id or partner_id != owner_id:
        await callback.answer("❌", show_alert=True)
        return

    if order_service:
        success = await order_service.complete_order(order_id, "order")
    else:
        try:
            db_instance.update_order_status(order_id, OrderStatus.COMPLETED)
            success = True
        except Exception:
            success = False

    if not success:
        await callback.answer("❌", show_alert=True)
        return

    # Build COMPLETED message
    import json

    from app.core.utils import get_offer_field
    from app.services.unified_order_service import NotificationTemplates

    items = []
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
        except Exception:
            pass

    delivery_price = _get_store_field(store, "delivery_price", 0)

    customer_id = _get_entity_field(order, "user_id")
    customer_name = None
    customer_phone = None
    if customer_id:
        customer = db_instance.get_user_model(customer_id)
        if customer:
            customer_name = customer.first_name
            customer_phone = customer.phone

    currency = "so'm" if lang == "uz" else "сум"

    seller_text = NotificationTemplates.seller_status_update(
        lang=lang,
        order_id=order_id,
        status=OrderStatus.COMPLETED,
        order_type="delivery",
        items=items,
        customer_name=customer_name,
        customer_phone=customer_phone,
        delivery_address=delivery_address,
        total=total,
        delivery_price=delivery_price,
        currency=currency,
    )

    # EDIT message - no buttons for completed
    try:
        if callback.message:
            if hasattr(callback.message, "caption") and callback.message.caption:
                await callback.message.edit_caption(
                    caption=seller_text,
                    parse_mode="HTML",
                )
            else:
                await callback.message.edit_text(
                    text=seller_text,
                    parse_mode="HTML",
                )
    except Exception as e:
        logger.warning(f"Failed to edit complete message: {e}")

    msg = "Bajarildi!" if lang == "uz" else "Выполнено!"
    await callback.answer(f"🎉 {msg}")


@router.callback_query(F.data.regexp(r"^complete_booking_(\d+)$"))
async def complete_booking_handler(callback: types.CallbackQuery) -> None:
    """
    Mark pickup booking as completed (item handed to customer).
    Uses UnifiedOrderService for consistent notifications.
    """
    if not callback.from_user or not callback.data:
        await callback.answer()
        return

    db_instance = _get_db()
    if not db_instance:
        await callback.answer("System error", show_alert=True)
        return

    order_service = get_unified_order_service()
    partner_id = callback.from_user.id
    lang = db_instance.get_user_language(partner_id)

    try:
        booking_id = int(callback.data.split("_")[-1])
    except ValueError:
        await callback.answer("❌", show_alert=True)
        return

    booking = db_instance.get_booking(booking_id)
    if not booking:
        msg = "Bron topilmadi" if lang == "uz" else "Бронь не найдена"
        await callback.answer(f"❌ {msg}", show_alert=True)
        return

    # Verify ownership
    store_id = _get_entity_field(booking, "store_id")
    if not store_id:
        offer_id = _get_entity_field(booking, "offer_id")
        if offer_id:
            offer = db_instance.get_offer(offer_id)
            if offer:
                store_id = _get_entity_field(offer, "store_id")

    store = db_instance.get_store(store_id) if store_id else None
    owner_id = _get_store_field(store, "owner_id") if store else None

    if not owner_id or partner_id != owner_id:
        await callback.answer("❌", show_alert=True)
        return

    # Use UnifiedOrderService for completion with proper customer notification
    if order_service:
        success = await order_service.complete_order(booking_id, "booking")
    else:
        # Fallback
        try:
            db_instance.complete_booking(booking_id)
            success = True
        except Exception as e:
            logger.error(f"Failed to complete booking: {e}")
            success = False

    if not success:
        await callback.answer("❌", show_alert=True)
        return

    # Update seller message
    try:
        complete_text = "✅ <b>TOPSHIRILDI</b>" if lang == "uz" else "✅ <b>ВЫДАНО</b>"
        if callback.message and callback.message.text:
            await callback.message.edit_text(
                text=callback.message.text + f"\n\n{complete_text}",
                parse_mode="HTML",
            )
    except Exception:
        pass

    if lang == "uz":
        text = f"✅ Bron #{booking_id} yakunlandi!"
    else:
        text = f"✅ Бронь #{booking_id} завершена!"

    try:
        await callback.message.answer(text)
    except Exception:
        pass

    msg = "Yakunlandi!" if lang == "uz" else "Завершено!"
    await callback.answer(f"🎉 {msg}")


@router.callback_query(F.data.regexp(r"^order_cancel_seller_(\d+)$"))
async def order_cancel_seller_handler(callback: types.CallbackQuery) -> None:
    """Seller cancels order after confirmation."""
    if not callback.from_user or not callback.data:
        await callback.answer()
        return

    db_instance = _get_db()
    if not db_instance:
        await callback.answer("System error", show_alert=True)
        return

    order_service = get_unified_order_service()
    partner_id = callback.from_user.id
    lang = db_instance.get_user_language(partner_id)

    try:
        entity_id = int(callback.data.split("_")[-1])
    except ValueError:
        await callback.answer("❌", show_alert=True)
        return

    # Try order first, then booking
    entity = db_instance.get_order(entity_id)
    entity_type = "order"
    if not entity:
        entity = db_instance.get_booking(entity_id)
        entity_type = "booking"

    if not entity:
        await callback.answer("❌", show_alert=True)
        return

    # Verify ownership
    store_id = _get_entity_field(entity, "store_id")
    store = db_instance.get_store(store_id) if store_id else None
    owner_id = _get_store_field(store, "owner_id") if store else None

    if not owner_id or partner_id != owner_id:
        await callback.answer("❌", show_alert=True)
        return

    if order_service:
        success = await order_service.reject_order(entity_id, entity_type, "Отменено продавцом")
    else:
        try:
            if entity_type == "order":
                db_instance.update_order_status(entity_id, OrderStatus.CANCELLED)
            else:
                db_instance.cancel_booking(entity_id)
            await _restore_quantities_fallback(db_instance, entity, entity_type)
            success = True
        except Exception:
            success = False

    if not success:
        await callback.answer("❌", show_alert=True)
        return

    # Update message
    try:
        cancel_text = "❌ <b>BEKOR QILINDI</b>" if lang == "uz" else "❌ <b>ОТМЕНЕНО</b>"
        if callback.message and callback.message.text:
            await callback.message.edit_text(
                text=callback.message.text + f"\n\n{cancel_text}",
                parse_mode="HTML",
            )
    except Exception:
        pass

    msg = "Bekor qilindi" if lang == "uz" else "Отменено"
    await callback.answer(f"❌ {msg}")
