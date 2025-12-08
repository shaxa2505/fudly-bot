"""
Delivery order partner handlers - BATCH order confirmation/rejection by sellers.

Single order confirm/reject is handled by unified_order_handlers.py.
This file contains only:
- Batch confirm/reject (for cart orders)
- Customer cancellation
"""
from __future__ import annotations

import json
import os
from typing import Any

from aiogram import F, Router, types

from app.core.utils import get_offer_field, get_store_field
from database_protocol import DatabaseProtocol
from handlers.common.utils import html_escape as _esc
from logging_config import logger

router = Router()

ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))


def _get_order_field(order: Any, field: str, index: int = 0) -> Any:
    """Helper to get field from order dict or tuple."""
    if isinstance(order, dict):
        return order.get(field)
    return order[index] if len(order) > index else None


# =============================================================================
# NOTE: partner_confirm_order_ and partner_reject_order_ handlers REMOVED
# They are now handled by unified_order_handlers.py which provides:
# - Consistent status updates via UnifiedOrderService
# - Automatic customer notifications with progress bars
# - Live message editing to reduce spam
# =============================================================================


@router.callback_query(F.data.startswith("cancel_order_customer_"))
async def cancel_order_customer(
    callback: types.CallbackQuery, db: DatabaseProtocol, bot: Any
) -> None:
    """Customer cancels order."""
    if not callback.from_user:
        await callback.answer()
        return

    lang = db.get_user_language(callback.from_user.id)

    try:
        order_id = int(callback.data.split("_")[3])
    except (ValueError, IndexError):
        await callback.answer("❌", show_alert=True)
        return

    order = db.get_order(order_id)
    if not order:
        await callback.answer("❌", show_alert=True)
        return

    if _get_order_field(order, "user_id", 1) != callback.from_user.id:
        await callback.answer("❌", show_alert=True)
        return

    status = _get_order_field(order, "status", 3)
    if status not in ["pending", "confirmed"]:
        msg = "Buyurtma allaqachon qayta ishlangan" if lang == "uz" else "Заказ уже обработан"
        await callback.answer(f"❌ {msg}", show_alert=True)
        return

    db.update_order_status(order_id, "cancelled")

    # Restore quantity
    offer_id = _get_order_field(order, "offer_id", 2)
    quantity = _get_order_field(order, "quantity", 4)
    if offer_id:
        try:
            db.increment_offer_quantity_atomic(offer_id, int(quantity))
        except Exception:
            pass

    msg = "Bekor qilindi" if lang == "uz" else "Отменено"
    try:
        await callback.message.edit_text(callback.message.text + f"\n\n❌ {msg}", parse_mode="HTML")
    except Exception:
        pass

    # Notify seller
    store = db.get_store(_get_order_field(order, "store_id", 2))
    if store:
        owner_id = get_store_field(store, "owner_id")
        try:
            await bot.send_message(
                owner_id,
                f"ℹ️ Buyurtma #{order_id} bekor qilindi\n👤 {callback.from_user.first_name}",
                parse_mode="HTML",
            )
        except Exception:
            pass

    await callback.answer()


# =============================================================================
# BATCH CONFIRM/REJECT ORDERS (for cart deliveries)
# =============================================================================


@router.callback_query(F.data.startswith("partner_confirm_order_batch_"))
async def partner_confirm_order_batch(
    callback: types.CallbackQuery, db: DatabaseProtocol, bot: Any
) -> None:
    """Partner confirms multiple delivery orders at once (from cart)."""
    if not callback.from_user or not callback.data:
        await callback.answer()
        return

    partner_id = callback.from_user.id
    lang = db.get_user_language(partner_id)

    try:
        # Extract order IDs from callback data: "partner_confirm_order_batch_1,2,3"
        order_ids_str = callback.data.replace("partner_confirm_order_batch_", "")
        order_ids = [int(oid) for oid in order_ids_str.split(",")]
    except (ValueError, AttributeError):
        await callback.answer("❌", show_alert=True)
        return

    if not order_ids:
        await callback.answer("❌", show_alert=True)
        return

    # Confirm all orders
    confirmed_count = 0
    customer_notifications: dict = {}  # {customer_id: [order_infos]}

    for order_id in order_ids:
        try:
            order = db.get_order(order_id)
            if not order:
                continue

            # Verify ownership
            store_id = _get_order_field(order, "store_id", 2)
            store = db.get_store(store_id) if store_id else None
            owner_id = get_store_field(store, "owner_id") if store else None

            if partner_id != owner_id:
                continue

            # Update order status
            db.update_order_status(order_id, "preparing")
            confirmed_count += 1

            # Collect info for customer notification
            customer_id = _get_order_field(order, "user_id", 1)
            if customer_id:
                if customer_id not in customer_notifications:
                    customer_notifications[customer_id] = []

                offer_id = _get_order_field(order, "offer_id", 3)
                quantity = _get_order_field(order, "quantity", 4)
                address = _get_order_field(order, "delivery_address", 7)

                offer = db.get_offer(offer_id) if offer_id else None
                offer_title = get_offer_field(offer, "title", "Товар") if offer else "Товар"
                store_name = get_store_field(store, "name", "Магазин") if store else "Магазин"

                customer_notifications[customer_id].append(
                    {
                        "order_id": order_id,
                        "title": offer_title,
                        "quantity": quantity,
                        "store_name": store_name,
                        "address": address,
                    }
                )

        except Exception as e:
            logger.error(f"Failed to confirm order {order_id}: {e}")
            continue

    # Notify customers (grouped)
    for customer_id, orders_info in customer_notifications.items():
        try:
            cust_lang = db.get_user_language(customer_id)

            lines: list[str] = []
            if cust_lang == "uz":
                lines.append("🎉 <b>Barcha buyurtmalar qabul qilindi!</b>\n")
            else:
                lines.append("🎉 <b>Все заказы приняты!</b>\n")

            for info in orders_info:
                lines.append(f"📦 #{info['order_id']}")
                lines.append(f"🏪 {_esc(info['store_name'])}")
                lines.append(f"🛒 {_esc(info['title'])} × {info['quantity']}")
                lines.append(f"📍 {_esc(info['address'])}\n")

            if cust_lang == "uz":
                lines.append("🚚 <b>Yetkazib berish tashkil qilinmoqda!</b>")
            else:
                lines.append("🚚 <b>Доставка организуется!</b>")

            customer_msg = "\n".join(lines)
            await bot.send_message(customer_id, customer_msg, parse_mode="HTML")

        except Exception as e:
            logger.error(f"Failed to notify customer {customer_id}: {e}")

    # Update partner message
    try:
        if callback.message:
            await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass

    success_text = (
        f"✅ {confirmed_count} ta buyurtma qabul qilindi"
        if lang == "uz"
        else f"✅ Принято заказов: {confirmed_count}"
    )
    await callback.answer(success_text)


@router.callback_query(F.data.startswith("partner_reject_order_batch_"))
async def partner_reject_order_batch(
    callback: types.CallbackQuery, db: DatabaseProtocol, bot: Any
) -> None:
    """Partner rejects multiple delivery orders at once (from cart)."""
    if not callback.from_user or not callback.data:
        await callback.answer()
        return

    partner_id = callback.from_user.id
    lang = db.get_user_language(partner_id)

    try:
        # Extract order IDs from callback data: "partner_reject_order_batch_1,2,3"
        order_ids_str = callback.data.replace("partner_reject_order_batch_", "")
        order_ids = [int(oid) for oid in order_ids_str.split(",")]
    except (ValueError, AttributeError):
        await callback.answer("❌", show_alert=True)
        return

    if not order_ids:
        await callback.answer("❌", show_alert=True)
        return

    # Reject all orders and restore quantities
    rejected_count = 0
    customer_notifications: dict = {}  # {customer_id: [store_names]}

    for order_id in order_ids:
        try:
            order = db.get_order(order_id)
            if not order:
                continue

            # Verify ownership
            store_id = _get_order_field(order, "store_id", 2)
            store = db.get_store(store_id) if store_id else None
            owner_id = get_store_field(store, "owner_id") if store else None

            if partner_id != owner_id:
                continue

            # Update order status
            db.update_order_status(order_id, "rejected")

            # Restore quantity
            offer_id = _get_order_field(order, "offer_id", 3)
            quantity = _get_order_field(order, "quantity", 4)
            if offer_id:
                try:
                    db.increment_offer_quantity_atomic(offer_id, int(quantity))
                except Exception:
                    pass

            rejected_count += 1

            # Collect info for customer notification
            customer_id = _get_order_field(order, "user_id", 1)
            if customer_id:
                if customer_id not in customer_notifications:
                    customer_notifications[customer_id] = []

                store_name = get_store_field(store, "name", "Магазин") if store else "Магазин"
                customer_notifications[customer_id].append(store_name)

            # Notify admin about rejection
            if ADMIN_ID > 0:
                try:
                    await bot.send_message(
                        ADMIN_ID,
                        f"⚠️ Заказ #{order_id} отклонён продавцом\n💰 Требуется возврат средств",
                        parse_mode="HTML",
                    )
                except Exception:
                    pass

        except Exception as e:
            logger.error(f"Failed to reject order {order_id}: {e}")
            continue

    # Notify customers (grouped)
    for customer_id, store_names in customer_notifications.items():
        try:
            cust_lang = db.get_user_language(customer_id)

            if cust_lang == "uz":
                customer_msg = f"😔 <b>Buyurtmalar rad etildi</b>\n\n🏪 {', '.join(store_names)}\n\n💰 Pul qaytariladi."
            else:
                customer_msg = f"😔 <b>Заказы отклонены</b>\n\n🏪 {', '.join(store_names)}\n\n💰 Деньги будут возвращены."

            await bot.send_message(customer_id, customer_msg, parse_mode="HTML")

        except Exception as e:
            logger.error(f"Failed to notify customer {customer_id}: {e}")

    # Update partner message
    try:
        if callback.message:
            await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass

    reject_text = (
        f"❌ {rejected_count} ta buyurtma rad etildi"
        if lang == "uz"
        else f"❌ Отклонено заказов: {rejected_count}"
    )
    await callback.answer(reject_text)
