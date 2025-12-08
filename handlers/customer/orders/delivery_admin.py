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
from database_protocol import DatabaseProtocol
from logging_config import logger

router = Router()

ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))


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

    db.update_payment_status(order_id, "confirmed")
    db.update_order_status(order_id, "confirmed")

    # Get details
    store_id = _get_order_field(order, "store_id", 2)
    offer_id = _get_order_field(order, "offer_id", 3)
    quantity = _get_order_field(order, "quantity", 4)
    address = _get_order_field(order, "delivery_address", 7)
    customer_id = _get_order_field(order, "user_id", 1)
    payment_photo = _get_order_field(order, "payment_proof_photo_id", 10)

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
    delivery_price = get_store_field(store, "delivery_price", 0) if store else 0

    customer_name = customer.first_name if customer else "—"
    customer_phone = customer.phone if customer else "—"

    # Build items list and calculate total
    if is_cart_order and cart_items_json:
        import json

        try:
            cart_items = (
                json.loads(cart_items_json)
                if isinstance(cart_items_json, str)
                else cart_items_json
            )
        except Exception:
            cart_items = []

        items_list = "\n".join(
            [f"• {item['title']} × {item['quantity']}" for item in cart_items]
        )
        total = (
            sum(item["price"] * item["quantity"] for item in cart_items) + delivery_price
        )
    else:
        # Single item order
        offer = db.get_offer(offer_id)
        offer_title = get_offer_field(offer, "title", "Товар") if offer else "Товар"
        offer_price = get_offer_field(offer, "discount_price", 0) if offer else 0
        items_list = f"• {offer_title} × {quantity}"
        total = (offer_price * quantity) + delivery_price

    # Update admin message
    try:
        await callback.message.edit_caption(
            caption=callback.message.caption + "\n\n✅ <b>TASDIQLANDI</b>",
            parse_mode="HTML",
        )
    except Exception:
        pass

    # Notify seller with confirmation buttons
    if owner_id:
        seller_lang = db.get_user_language(owner_id)
        currency = "so'm" if seller_lang == "uz" else "сум"

        if seller_lang == "uz":
            caption = (
                f"🔔 <b>Yangi buyurtma!</b>\n\n"
                f"📦 #{order_id} | ✅ To'langan\n"
                f"🛒 <b>Mahsulotlar:</b>\n{items_list}\n"
                f"💵 {total:,} {currency}\n"
                f"📍 {address}\n"
                f"👤 {customer_name}\n"
                f"📱 <code>{customer_phone}</code>\n\n"
                f"⏳ <b>Buyurtmani tasdiqlang!</b>"
            )
            confirm_text = "✅ Qabul qilish"
            reject_text = "❌ Rad etish"
        else:
            caption = (
                f"🔔 <b>Новый заказ!</b>\n\n"
                f"📦 #{order_id} | ✅ Оплачено\n"
                f"🛒 <b>Товары:</b>\n{items_list}\n"
                f"💵 {total:,} {currency}\n"
                f"📍 {address}\n"
                f"👤 {customer_name}\n"
                f"📱 <code>{customer_phone}</code>\n\n"
                f"⏳ <b>Подтвердите заказ!</b>"
            )
            confirm_text = "✅ Принять"
            reject_text = "❌ Отклонить"

        # Partner confirmation keyboard
        partner_kb = InlineKeyboardBuilder()
        partner_kb.button(
            text=confirm_text, callback_data=f"partner_confirm_order_{order_id}"
        )
        partner_kb.button(
            text=reject_text, callback_data=f"partner_reject_order_{order_id}"
        )
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
    if customer_id:
        cust_lang = db.get_user_language(customer_id)
        if cust_lang == "uz":
            text = f"✅ <b>To'lov tasdiqlandi!</b>\n\n📦 #{order_id}\n⏳ Sotuvchi tasdiqlashini kutamiz..."
        else:
            text = f"✅ <b>Оплата подтверждена!</b>\n\n📦 #{order_id}\n⏳ Ожидаем подтверждение продавца..."

        try:
            await bot.send_message(customer_id, text, parse_mode="HTML")
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

    db.update_payment_status(order_id, "rejected")
    db.update_order_status(order_id, "cancelled")

    # Restore quantity
    offer_id = _get_order_field(order, "offer_id", 3)
    quantity = _get_order_field(order, "quantity", 4)
    customer_id = _get_order_field(order, "user_id", 1)

    if offer_id:
        try:
            db.increment_offer_quantity_atomic(offer_id, int(quantity))
        except Exception:
            pass

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
                f"❌ <b>To'lov tasdiqlanmadi</b>\n\n📦 #{order_id}\nIltimos, qayta urinib ko'ring."
            )
        else:
            text = (
                f"❌ <b>Оплата не подтверждена</b>\n\n📦 #{order_id}\nПожалуйста, попробуйте снова."
            )

        try:
            await bot.send_message(customer_id, text, parse_mode="HTML")
        except Exception:
            pass

    await callback.answer("❌ Rad etildi", show_alert=True)
