"""
Delivery order admin handlers - payment confirmation/rejection.

Extracted from delivery.py for maintainability.
"""
from __future__ import annotations

import os
from typing import Any

from aiogram import F, Router, types
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.core.utils import get_offer_field, get_store_field
from app.services.unified_order_service import (
    OrderStatus,
    get_unified_order_service,
    init_unified_order_service,
)
from database_protocol import DatabaseProtocol
from logging_config import logger

router = Router()

ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))

# Module dependencies (set via setup_dependencies)
_db: DatabaseProtocol | None = None
_bot: Any = None


def setup_dependencies(database: DatabaseProtocol, bot_instance: Any) -> None:
    """Setup module dependencies."""
    global _db, _bot
    _db = database
    _bot = bot_instance


def _get_order_field(order: Any, field: str, index: int = 0) -> Any:
    """Helper to get field from order dict or tuple."""
    if isinstance(order, dict):
        return order.get(field)
    return order[index] if len(order) > index else None


@router.callback_query(F.data.startswith("admin_confirm_payment_"))
async def admin_confirm_payment(
    callback: types.CallbackQuery, db: DatabaseProtocol, bot: Any
) -> None:
    """Admin confirms payment."""
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("❌", show_alert=True)
        return

    try:
        order_id = int(callback.data.split("_")[3])
    except (ValueError, IndexError):
        await callback.answer("❌", show_alert=True)
        return

    order = db.get_order(order_id)
    if not order:
        await callback.answer("❌ Buyurtma topilmadi", show_alert=True)
        return
    payment_status = _get_order_field(order, "payment_status", 0)
    if str(payment_status) not in ("proof_submitted", "awaiting_proof", "awaiting_admin_confirmation"):
        await callback.answer("⚠️ To'lov allaqachon ko'rib chiqilgan", show_alert=True)
        return

    skip_seller_notify = False
    order_service = get_unified_order_service()
    if not order_service and bot:
        order_service = init_unified_order_service(db, bot)
    if not order_service:
        await callback.answer("System error", show_alert=True)
        return

    await order_service.confirm_payment(order_id)
    skip_seller_notify = True

    # Get details
    store_id = _get_order_field(order, "store_id", 2)
    offer_id = _get_order_field(order, "offer_id", 3)
    quantity = _get_order_field(order, "quantity", 4)
    address = _get_order_field(order, "delivery_address", 7)
    customer_id = _get_order_field(order, "user_id", 1)
    payment_photo = _get_order_field(order, "payment_proof_photo_id", 10)
    
    # Get order_type to determine if this is delivery or pickup
    order_type = _get_order_field(order, "order_type", -1)  # Index -1 means use dict only
    if isinstance(order, dict):
        order_type = order.get("order_type", "delivery")  # Default to delivery for backward compat
    else:
        order_type = "delivery"  # Legacy orders without order_type field

    # Check if cart order by trying to get cart_items from dict
    if isinstance(order, dict):
        is_cart_order = order.get("is_cart_order", 0)
        cart_items_json = order.get("cart_items")
    else:
        is_cart_order = 0
        cart_items_json = None

    store = db.get_store(store_id)
    customer = db.get_user_model(customer_id)

    owner_id = get_store_field(store, "owner_id") if store else None
    delivery_price = _get_order_field(order, "delivery_price", None)
    if delivery_price is None:
        delivery_price = (
            get_store_field(store, "delivery_price", 0) if store and order_type == "delivery" else 0
        )
    delivery_price = int(delivery_price or 0)
    order_total_price = order.get("total_price") if isinstance(order, dict) else None

    customer_name = customer.first_name if customer else "—"
    customer_phone = customer.phone if customer else "—"

    # Build items list and calculate total
    if is_cart_order and cart_items_json:
        import json

        try:
            cart_items = (
                json.loads(cart_items_json) if isinstance(cart_items_json, str) else cart_items_json
            )
        except Exception:
            cart_items = []

        items_list = "\n".join([f"• {item['title']} × {item['quantity']}" for item in cart_items])
        total = int(order_total_price) if order_total_price is not None else (
            sum(item["price"] * item["quantity"] for item in cart_items) + delivery_price
        )
    else:
        # Single item order
        item_title = _get_order_field(order, "item_title", None)
        item_price = _get_order_field(order, "item_price", None)
        offer = None
        if not item_title or item_price is None:
            offer = db.get_offer(offer_id) if offer_id else None
        offer_title = item_title or (
            get_offer_field(offer, "title", "Товар") if offer else "Товар"
        )
        offer_price = (
            int(item_price)
            if item_price is not None
            else int(get_offer_field(offer, "discount_price", 0) if offer else 0)
        )
        quantity = int(quantity or 1)
        items_list = f"• {offer_title} × {quantity}"
        total = int(order_total_price) if order_total_price is not None else (
            (offer_price * quantity) + delivery_price
        )

    # Update admin message
    try:
        await callback.message.edit_caption(
            caption=callback.message.caption + "\n\n✅ <b>TASDIQLANDI</b>",
            parse_mode="HTML",
        )
    except Exception:
        pass

    # Notify seller with confirmation buttons
    if owner_id and not skip_seller_notify:
        seller_lang = db.get_user_language(owner_id)
        currency = "so'm" if seller_lang == "uz" else "сум"

        if seller_lang == "uz":
            # Build order type indicator
            order_type_text = "🏪 O'zi olib ketadi" if order_type == "pickup" else "🚚 Yetkazish"
            
            caption = (
                f"🔔 <b>Yangi buyurtma!</b>\n\n"
                f"📦 #{order_id} | {order_type_text} | ✅ To'langan\n"
                f"🛒 <b>Mahsulotlar:</b>\n{items_list}\n"
                f"💵 {total:,} {currency}\n"
            )
            
            # Show address ONLY for delivery orders
            if order_type == "delivery" and address:
                caption += f"📍 {address}\n"
            
            caption += (
                f"👤 {customer_name}\n"
                f"📱 <code>{customer_phone}</code>\n\n"
                f"⏳ <b>Buyurtmani tasdiqlang!</b>"
            )
            confirm_text = "✅ Qabul qilish"
            reject_text = "❌ Rad etish"
        else:
            # Build order type indicator
            order_type_text = "🏪 Самовывоз" if order_type == "pickup" else "🚚 Доставка"
            
            caption = (
                f"🔔 <b>Новый заказ!</b>\n\n"
                f"📦 #{order_id} | {order_type_text} | ✅ Оплачено\n"
                f"🛒 <b>Товары:</b>\n{items_list}\n"
                f"💵 {total:,} {currency}\n"
            )
            
            # Show address ONLY for delivery orders
            if order_type == "delivery" and address:
                caption += f"📍 {address}\n"
            
            caption += (
                f"👤 {customer_name}\n"
                f"📱 <code>{customer_phone}</code>\n\n"
                f"⏳ <b>Подтвердите заказ!</b>"
            )
            confirm_text = "✅ Принять"
            reject_text = "❌ Отклонить"

        # Partner confirmation keyboard
        partner_kb = InlineKeyboardBuilder()
        partner_kb.button(text=confirm_text, callback_data=f"order_confirm_{order_id}")
        partner_kb.button(text=reject_text, callback_data=f"order_reject_{order_id}")
        partner_kb.adjust(2)

        try:
            if payment_photo:
                await bot.send_photo(
                    owner_id,
                    photo=payment_photo,
                    caption=caption,
                    parse_mode="HTML",
                    reply_markup=partner_kb.as_markup(),
                )
            else:
                await bot.send_message(
                    owner_id, caption, parse_mode="HTML", reply_markup=partner_kb.as_markup()
                )
        except Exception as e:
            logger.error(f"Failed to notify seller: {e}")

    # Notify customer - payment confirmed, waiting for partner
    # Use UnifiedOrderService for live editing if customer_message_id exists
    if customer_id:
        cust_lang = db.get_user_language(customer_id)
        if cust_lang == "uz":
            text = f"✅ <b>To'lov tasdiqlandi!</b>\n\n📦 #{order_id}\n⏳ Sotuvchi tasdiqlashini kutamiz..."
        else:
            text = f"✅ <b>Оплата подтверждена!</b>\n\n📦 #{order_id}\n⏳ Ожидаем подтверждение продавца..."

        try:
            # Try to edit existing customer message first (caption -> text)
            existing_msg_id = order.get("customer_message_id") if isinstance(order, dict) else None
            edit_success = False

            if existing_msg_id:
                try:
                    await bot.edit_message_caption(
                        chat_id=customer_id,
                        message_id=existing_msg_id,
                        caption=text,
                        parse_mode="HTML",
                    )
                    edit_success = True
                    logger.info(f"Edited payment confirmation for order #{order_id}")
                except Exception:
                    try:
                        await bot.edit_message_text(
                            chat_id=customer_id,
                            message_id=existing_msg_id,
                            text=text,
                            parse_mode="HTML",
                        )
                        edit_success = True
                        logger.info(f"Edited payment confirmation for order #{order_id}")
                    except Exception:
                        pass

            if not edit_success:
                sent_msg = await bot.send_message(customer_id, text, parse_mode="HTML")
                if sent_msg and hasattr(db, "set_order_customer_message_id"):
                    try:
                        db.set_order_customer_message_id(order_id, sent_msg.message_id)
                        logger.info(
                            "Saved customer_message_id=%s for order#%s",
                            sent_msg.message_id,
                            order_id,
                        )
                    except Exception as save_err:
                        logger.warning(
                            "Failed to save customer_message_id for order %s: %s",
                            order_id,
                            save_err,
                        )
        except Exception as e:
            logger.error(f"Failed to notify customer: {e}")

    await callback.answer("✅ Tasdiqlandi!", show_alert=True)


@router.callback_query(F.data.startswith("admin_reject_payment_"))
async def admin_reject_payment(
    callback: types.CallbackQuery, db: DatabaseProtocol, bot: Any
) -> None:
    """Admin rejects payment."""
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("❌", show_alert=True)
        return

    try:
        order_id = int(callback.data.split("_")[3])
    except (ValueError, IndexError):
        await callback.answer("❌", show_alert=True)
        return

    order = db.get_order(order_id)
    if not order:
        await callback.answer("❌", show_alert=True)
        return
    payment_status = _get_order_field(order, "payment_status", 0)
    if str(payment_status) not in ("proof_submitted", "awaiting_proof", "awaiting_admin_confirmation"):
        await callback.answer("⚠️ To'lov allaqachon ko'rib chiqilgan", show_alert=True)
        return

    db.update_payment_status(order_id, "rejected")
    # Keep order_status as fulfillment-only and allow customer to re-upload proof
    order_service = get_unified_order_service()
    if not order_service and bot:
        order_service = init_unified_order_service(db, bot)
    if order_service:
        await order_service.update_status(
            entity_id=order_id,
            entity_type="order",
            new_status=OrderStatus.PENDING,
            notify_customer=False,
        )
    else:
        logger.warning("UnifiedOrderService unavailable for payment rejection")

    customer_id = _get_order_field(order, "user_id", 1)

    # Update admin message
    try:
        await callback.message.edit_caption(
            caption=callback.message.caption + "\n\n❌ <b>RAD ETILDI</b>",
            parse_mode="HTML",
        )
    except Exception:
        pass

    # Notify customer
    if customer_id:
        cust_lang = db.get_user_language(customer_id)
        if cust_lang == "uz":
            text = (
                f"❌ <b>To'lov tasdiqlanmadi</b>\n\n📦 #{order_id}\nIltimos, chekni qayta yuboring."
            )
        else:
            text = (
                f"❌ <b>Оплата не подтверждена</b>\n\n📦 #{order_id}\nПожалуйста, отправьте чек ещё раз."
            )

        try:
            existing_msg_id = order.get("customer_message_id") if isinstance(order, dict) else None
            edit_success = False

            if existing_msg_id:
                try:
                    await bot.edit_message_caption(
                        chat_id=customer_id,
                        message_id=existing_msg_id,
                        caption=text,
                        parse_mode="HTML",
                    )
                    edit_success = True
                except Exception:
                    try:
                        await bot.edit_message_text(
                            chat_id=customer_id,
                            message_id=existing_msg_id,
                            text=text,
                            parse_mode="HTML",
                        )
                        edit_success = True
                    except Exception:
                        pass

            if not edit_success:
                sent_msg = await bot.send_message(customer_id, text, parse_mode="HTML")
                if sent_msg and hasattr(db, "set_order_customer_message_id"):
                    try:
                        db.set_order_customer_message_id(order_id, sent_msg.message_id)
                        logger.info(
                            "Saved customer_message_id=%s for order#%s",
                            sent_msg.message_id,
                            order_id,
                        )
                    except Exception as save_err:
                        logger.warning(
                            "Failed to save customer_message_id for order %s: %s",
                            order_id,
                            save_err,
                        )
        except Exception:
            pass

    await callback.answer("❌ Rad etildi", show_alert=True)
