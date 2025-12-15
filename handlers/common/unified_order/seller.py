"""Seller-side unified order handlers.

Contains confirmation/rejection, status updates and courier handover
flows for both orders and bookings. All callbacks are registered via
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

from app.services.unified_order_service import (
    OrderStatus,
    get_unified_order_service,
    NotificationTemplates,
)
from handlers.common.states import CourierHandover
from handlers.common.utils import html_escape as _esc
from localization import get_text

from .common import _get_db, _get_store_field, _get_entity_field, logger


# Regex patterns for all supported callback formats
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
    """Determine entity type from callback prefix, with DB fallbacks."""

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
    entity = db_instance.get_order(entity_id)
    if entity:
        return ("order", entity)

    entity = db_instance.get_booking(entity_id)
    if entity:
        return ("booking", entity)

    return ("unknown", None)


async def _restore_quantities_fallback(db_instance: Any, entity: Any, entity_type: str) -> None:
    """Restore offer quantities (fallback when UnifiedOrderService is unavailable)."""

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
                    except Exception:  # pragma: no cover - non-critical logging
                        pass
        elif offer_id:
            try:
                db_instance.increment_offer_quantity_atomic(offer_id, int(quantity))
            except Exception:  # pragma: no cover - non-critical logging
                pass

    except Exception as e:  # pragma: no cover - defensive logging
        logger.error(f"Failed to restore quantities: {e}")


# ============================================================================
# UNIFIED CONFIRM / REJECT
# ============================================================================


async def unified_confirm_handler(callback: types.CallbackQuery) -> None:
    """Unified handler for order/booking confirmation callbacks."""

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

    match = CONFIRM_PATTERN.match(callback.data)
    if not match:
        await callback.answer("❌", show_alert=True)
        return

    prefix = match.group(1)
    entity_id = int(match.group(2))

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
            "Ownership verification failed: partner=%s, owner=%s, %s=%s",
            partner_id,
            owner_id,
            entity_type,
            entity_id,
        )
        await callback.answer("❌", show_alert=True)
        return

    # Use UnifiedOrderService if available, otherwise fallback
    if order_service:
        success = await order_service.confirm_order(entity_id, entity_type)
    else:
        try:
            if entity_type == "order":
                db_instance.update_order_status(entity_id, OrderStatus.PREPARING)
            else:
                db_instance.update_booking_status(entity_id, "confirmed")
            success = True
        except Exception as e:  # pragma: no cover - defensive logging
            logger.error(f"Failed to confirm: {e}")
            success = False

    if not success:
        await callback.answer(get_text(lang, "error") or "Error", show_alert=True)
        return

    # Build updated seller message
    from app.core.utils import get_offer_field

    items: list[dict] = []
    order_type = "delivery" if entity_type == "order" else "pickup"
    delivery_address: str | None = None
    customer_name: str | None = None
    customer_phone: str | None = None
    total = 0
    delivery_price = 0

    if entity_type == "order":
        order_type_db = _get_entity_field(entity, "order_type", "delivery")
        if order_type_db:
            order_type = order_type_db
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
                total = sum(
                    item.get("price", 0) * item.get("quantity", 1) for item in cart_items
                )
            except Exception:  # pragma: no cover - defensive logging
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

    # Customer info
    customer_id = _get_entity_field(entity, "user_id")
    if customer_id:
        customer = db_instance.get_user_model(customer_id)
        if customer:
            customer_name = customer.first_name
            customer_phone = customer.phone

    currency = "so'm" if lang == "uz" else "сум"

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

    # Add a short next-step hint so sellers clearly understand
    # what to do after confirmation for each flow.
    if entity_type == "booking":
        if lang == "uz":
            hint = (
                "\n\n<i>Mijoz kelganda mahsulotni topshiring va “Topshirildi” "
                "tugmasini bosing.</i>"
            )
        else:
            hint = (
                "\n\n<i>Когда клиент придёт, выдайте товар и нажмите "
                "«Выдано».</i>"
            )
        seller_text += hint
    elif entity_type == "order" and order_type != "delivery":
        # Pickup order created через orders: сразу ждём фактической выдачи.
        if lang == "uz":
            hint = (
                "\n\n<i>Mijoz buyurtmani olganda “Topshirildi” tugmasini bosing.</i>"
            )
        else:
            hint = (
                "\n\n<i>Когда клиент заберёт заказ, нажмите «Выдано».</i>"
            )
        seller_text += hint
    else:
        # Delivery flow: сначала готовим, потом передаём курьеру.
        if lang == "uz":
            hint = (
                "\n\n<i>Buyurtma tayyor bo'lganda “Topshirishga tayyor” "
                "tugmasini bosing.</i>"
            )
        else:
            hint = (
                "\n\n<i>Когда заказ будет готов, нажмите «Готов к передаче».</i>"
            )
        seller_text += hint

    kb = InlineKeyboardBuilder()
    if entity_type == "booking":
        # Classic pickup booking flow: after подтверждения сразу ждём выдачи
        if lang == "uz":
            kb.button(text="✅ Topshirildi", callback_data=f"complete_booking_{entity_id}")
        else:
            kb.button(text="✅ Выдано", callback_data=f"complete_booking_{entity_id}")
    elif entity_type == "order" and order_type != "delivery":
        # Pickup‑заказ, оформленный через orders: не показываем этапы доставки,
        # сразу даём кнопку "выдано" как для брони.
        if lang == "uz":
            kb.button(text="✅ Topshirildi", callback_data=f"order_complete_{entity_id}")
        else:
            kb.button(text="✅ Выдано", callback_data=f"order_complete_{entity_id}")
    else:
        # Настоящая доставка: сначала "готов к передаче", затем курьер и т.д.
        if lang == "uz":
            kb.button(text="📦 Topshirishga tayyor", callback_data=f"order_ready_{entity_id}")
        else:
            kb.button(text="📦 Готов к передаче", callback_data=f"order_ready_{entity_id}")
    kb.adjust(1)

    try:
        if callback.message:
            if getattr(callback.message, "caption", None):
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
    except Exception as e:  # pragma: no cover - defensive logging
        logger.warning(f"Failed to edit seller message: {e}")

    # Notify customer about confirmation
    customer_id = _get_entity_field(entity, "user_id")
    if customer_id and callback.bot:
        try:
            customer_lang = db_instance.get_user_language(customer_id)
            if customer_lang == "uz":
                customer_msg = (
                    f"✅ <b>Buyurtmangiz qabul qilindi!</b>\n\n"
                    f"📦 Buyurtma #{entity_id}\n"
                )
                if entity_type == "order" and order_type == "delivery":
                    customer_msg += "\n🚚 Tayyor bo'lganda xabar beramiz!"
                else:
                    customer_msg += "\n🏪 Tayyor bo'lganda olib ketishingiz mumkin!"
            else:
                customer_msg = (
                    f"✅ <b>Ваш заказ подтвержден!</b>\n\n"
                    f"📦 Заказ #{entity_id}\n"
                )
                if entity_type == "order" and order_type == "delivery":
                    customer_msg += "\n🚚 Сообщим, когда будет готов!"
                else:
                    customer_msg += "\n🏪 Можете забрать, когда будет готов!"
            
            await callback.bot.send_message(
                chat_id=customer_id,
                text=customer_msg,
                parse_mode="HTML"
            )
        except Exception as e:
            logger.warning(f"Failed to notify customer: {e}")

    confirmed_msg = "Tasdiqlandi" if lang == "uz" else "Подтверждено"
    await callback.answer(f"✅ {confirmed_msg}")


async def unified_reject_handler(callback: types.CallbackQuery) -> None:
    """Unified handler for order/booking rejection callbacks."""

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

    match = REJECT_PATTERN.match(callback.data)
    if not match:
        await callback.answer("❌", show_alert=True)
        return

    prefix = match.group(1)
    entity_id = int(match.group(2))

    entity_type, entity = _determine_entity_type(prefix, entity_id, db_instance)
    if not entity:
        msg = "Buyurtma topilmadi" if lang == "uz" else "Заказ не найден"
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
    owner_id = _get_store_field(store, "owner_id") if store else None

    if not owner_id or partner_id != owner_id:
        logger.warning(
            "Ownership verification failed in reject: partner=%s, owner=%s, %s=%s",
            partner_id,
            owner_id,
            entity_type,
            entity_id,
        )
        await callback.answer("❌", show_alert=True)
        return

    if order_service:
        success = await order_service.reject_order(entity_id, entity_type)
    else:
        try:
            if entity_type == "order":
                db_instance.update_order_status(entity_id, OrderStatus.REJECTED)
            else:
                db_instance.cancel_booking(entity_id)

            await _restore_quantities_fallback(db_instance, entity, entity_type)
            success = True
        except Exception as e:  # pragma: no cover - defensive logging
            logger.error(f"Failed to reject: {e}")
            success = False

    if not success:
        await callback.answer(get_text(lang, "error") or "Error", show_alert=True)
        return

    # Notify customer about rejection
    customer_id = _get_entity_field(entity, "user_id")
    if customer_id and callback.bot:
        try:
            customer_lang = db_instance.get_user_language(customer_id)
            if customer_lang == "uz":
                customer_msg = (
                    f"❌ <b>Buyurtma rad etildi</b>\n\n"
                    f"📦 Buyurtma #{entity_id}\n\n"
                    f"Afsuski, do'kon buyurtmani qabul qila olmadi.\n"
                    f"Iltimos, boshqa mahsulotlarni ko'rib chiqing."
                )
            else:
                customer_msg = (
                    f"❌ <b>Заказ отклонен</b>\n\n"
                    f"📦 Заказ #{entity_id}\n\n"
                    f"К сожалению, заведение не смогло принять заказ.\n"
                    f"Пожалуйста, посмотрите другие предложения."
                )
            
            await callback.bot.send_message(
                chat_id=customer_id,
                text=customer_msg,
                parse_mode="HTML"
            )
        except Exception as e:
            logger.warning(f"Failed to notify customer about rejection: {e}")

    # Update seller's message
    try:
        if callback.message:
            rejected_text = "❌ <b>RAD ETILDI</b>" if lang == "uz" else "❌ <b>ОТКЛОНЕНО</b>"

            if getattr(callback.message, "caption", None):
                await callback.message.edit_caption(
                    caption=f"{callback.message.caption}\n\n{rejected_text}",
                    parse_mode="HTML",
                )
            elif getattr(callback.message, "text", None):
                await callback.message.edit_text(
                    text=f"{callback.message.text}\n\n{rejected_text}",
                    parse_mode="HTML",
                )
    except Exception as e:  # pragma: no cover - defensive logging
        logger.warning(f"Failed to update seller message: {e}")

    rejected_msg = "Rad etildi" if lang == "uz" else "Отклонено"
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

    # Only delivery orders should go through the courier flow.
    order_type = _get_entity_field(order, "order_type", "delivery")
    if order_type != "delivery":
        await callback.answer("❌", show_alert=True)
        return

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
        except Exception:  # pragma: no cover
            success = False

    if not success:
        await callback.answer("❌", show_alert=True)
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
        except Exception:  # pragma: no cover
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

    kb = InlineKeyboardBuilder()
    if lang == "uz":
        kb.button(text="🚚 Kuryerga topshirdim", callback_data=f"order_delivering_{order_id}")
    else:
        kb.button(text="🚚 Передал курьеру", callback_data=f"order_delivering_{order_id}")
    kb.adjust(1)

    try:
        if callback.message:
            if getattr(callback.message, "caption", None):
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
    except Exception as e:  # pragma: no cover
        logger.warning(f"Failed to edit ready message: {e}")

    msg = "Tayyor!" if lang == "uz" else "Готово к передаче!"
    await callback.answer(f"📦 {msg}")


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

    store_id = _get_entity_field(order, "store_id")
    store = db_instance.get_store(store_id) if store_id else None
    owner_id = _get_store_field(store, "owner_id") if store else None

    if not owner_id or partner_id != owner_id:
        await callback.answer("❌", show_alert=True)
        return

    await state.set_state(CourierHandover.courier_phone)
    await state.update_data(
        order_id=order_id,
        seller_message_id=callback.message.message_id if callback.message else None,
        unified_flow=True,
    )

    kb = InlineKeyboardBuilder()
    skip_text = "⏩ O'tkazib yuborish" if lang == "uz" else "⏩ Пропустить"
    kb.button(text=skip_text, callback_data=f"skip_courier_phone_{order_id}")

    prompt = (
        "📱 Kuryer telefon raqamini kiriting:\n\n<i>Mijoz kuryer bilan bog'lanishi uchun</i>"
        if lang == "uz"
        else "📱 Введите телефон курьера:\n\n<i>Чтобы клиент мог связаться с курьером</i>"
    )

    try:
        await callback.message.answer(prompt, parse_mode="HTML", reply_markup=kb.as_markup())
    except Exception:  # pragma: no cover
        pass

    await callback.answer()


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
        error_text = (
            "❌ Noto'g'ri telefon raqami. Qaytadan kiriting:"
            if lang == "uz"
            else "❌ Неверный номер. Введите ещё раз:"
        )
        await message.answer(error_text)
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

    order = db_instance.get_order(order_id)
    if not order:
        return

    order_type = _get_entity_field(order, "order_type", "delivery")
    if order_type != "delivery":
        # Safety guard: pickup orders should not hit courier flow
        return

    store_id = _get_entity_field(order, "store_id")
    store = db_instance.get_store(store_id) if store_id else None

    if order_service:
        success = await order_service.start_delivery(order_id, courier_phone=courier_phone)
    else:
        try:
            db_instance.update_order_status(order_id, OrderStatus.DELIVERING)
            success = True
        except Exception:  # pragma: no cover
            success = False

    if not success:
        error_text = "❌ Xatolik yuz berdi" if lang == "uz" else "❌ Произошла ошибка"
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

    if courier_phone:
        courier_label = "Kuryer" if lang == "uz" else "Курьер"
        seller_text += f"\n\n📞 {courier_label}: <code>{courier_phone}</code>"

    if isinstance(event, types.CallbackQuery) and event.message:
        try:
            if getattr(event.message, "caption", None):
                await event.message.edit_caption(
                    caption=seller_text,
                    parse_mode="HTML",
                )
            else:
                await event.message.edit_text(
                    text=seller_text,
                    parse_mode="HTML",
                )
        except Exception as e:  # pragma: no cover
            logger.warning(f"Failed to edit delivering message: {e}")

    msg = "Kuryerga topshirildi" if lang == "uz" else "Передано курьеру"
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
        except Exception:  # pragma: no cover
            success = False

    if not success:
        await callback.answer("❌", show_alert=True)
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
        except Exception:  # pragma: no cover
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

    # Respect actual order_type from DB so pickup orders don't
    # render as delivery in seller/status templates.
    order_type = _get_entity_field(order, "order_type", "delivery")

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
    )

    try:
        if callback.message:
            if getattr(callback.message, "caption", None):
                await callback.message.edit_caption(
                    caption=seller_text,
                    parse_mode="HTML",
                )
            else:
                await callback.message.edit_text(
                    text=seller_text,
                    parse_mode="HTML",
                )
    except Exception as e:  # pragma: no cover
        logger.warning(f"Failed to edit complete message: {e}")

    msg = "Bajarildi!" if lang == "uz" else "Выполнено!"
    await callback.answer(f"🎉 {msg}")


async def complete_booking_handler(callback: types.CallbackQuery) -> None:
    """Mark pickup booking as completed (item handed to customer)."""

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

    if order_service:
        success = await order_service.complete_order(booking_id, "booking")
    else:
        try:
            db_instance.complete_booking(booking_id)
            success = True
        except Exception as e:  # pragma: no cover
            logger.error(f"Failed to complete booking: {e}")
            success = False

    if not success:
        await callback.answer("❌", show_alert=True)
        return

    try:
        complete_text = "✅ <b>TOPSHIRILDI</b>" if lang == "uz" else "✅ <b>ВЫДАНО</b>"
        if callback.message and getattr(callback.message, "text", None):
            await callback.message.edit_text(
                text=f"{callback.message.text}\n\n{complete_text}",
                parse_mode="HTML",
            )
    except Exception:  # pragma: no cover
        pass

    if lang == "uz":
        text = f"✅ Bron #{booking_id} yakunlandi!"
    else:
        text = f"✅ Бронь #{booking_id} завершена!"

    try:
        if callback.message:
            await callback.message.answer(text)
    except Exception:  # pragma: no cover
        pass

    msg = "Yakunlandi!" if lang == "uz" else "Завершено!"
    await callback.answer(f"🎉 {msg}")


async def order_cancel_seller_handler(callback: types.CallbackQuery) -> None:
    """Seller cancels order or booking after confirmation."""

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

    entity = db_instance.get_order(entity_id)
    entity_type = "order"
    if not entity:
        entity = db_instance.get_booking(entity_id)
        entity_type = "booking"

    if not entity:
        await callback.answer("❌", show_alert=True)
        return

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
        except Exception:  # pragma: no cover
            success = False

    if not success:
        await callback.answer("❌", show_alert=True)
        return

    try:
        cancel_text = "❌ <b>BEKOR QILINDI</b>" if lang == "uz" else "❌ <b>ОТМЕНЕНО</b>"
        if callback.message and getattr(callback.message, "text", None):
            await callback.message.edit_text(
                text=f"{callback.message.text}\n\n{cancel_text}",
                parse_mode="HTML",
            )
    except Exception:  # pragma: no cover
        pass

    msg = "Bekor qilindi" if lang == "uz" else "Отменено"
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
        skip_courier_phone_handler, F.data.regexp(r"^skip_courier_phone_(\d+)$")
    )

    router.message.register(
        courier_phone_entered_handler,
        F.text,
        StateFilter(CourierHandover.courier_phone),
    )

    router.callback_query.register(
        order_complete_handler, F.data.regexp(r"^order_complete_(\d+)$")
    )
    router.callback_query.register(
        complete_booking_handler, F.data.regexp(r"^complete_booking_(\d+)$")
    )
    router.callback_query.register(
        order_cancel_seller_handler, F.data.regexp(r"^order_cancel_seller_(\d+)$")
    )
