"""Admin handlers for delivery order payment confirmation.

When Mini App user creates DELIVERY order with CARD payment:
1. User uploads payment proof photo
2. Photo sent to ADMIN with confirmation buttons
3. Admin confirms/rejects payment
4. If confirmed → notify seller via unified_order_service
5. If rejected → notify customer, restore quantities
"""
from __future__ import annotations

from typing import Any

from aiogram import F, Router, types
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.services.unified_order_service import get_unified_order_service
from localization import get_text

try:
    from logging_config import logger
except ImportError:
    import logging
    logger = logging.getLogger(__name__)


router = Router(name="admin_delivery_orders")

# Module dependencies
db: Any | None = None


def setup(database: Any) -> None:
    """Setup module dependencies."""
    global db
    db = database
    logger.info("✅ Admin delivery orders handler initialized")


@router.callback_query(F.data.startswith("admin_confirm_payment_"))
async def admin_confirm_payment(callback: types.CallbackQuery) -> None:
    """Admin confirms payment proof for delivery order.
    
    Flow:
    1. Update order status from awaiting_admin_confirmation → pending
    2. Notify seller via unified_order_service
    3. Seller receives order with confirmation buttons
    """
    if not callback.message or not callback.from_user:
        return
    
    try:
        order_id = int(callback.data.split("_")[-1])
        logger.info(f"Admin {callback.from_user.id} confirming payment for order #{order_id}")
        
        # Get order details
        if not db or not hasattr(db, "get_order"):
            await callback.answer("❌ Database error", show_alert=True)
            return
        
        order = db.get_order(order_id)
        if not order:
            await callback.answer("❌ Order not found", show_alert=True)
            return
        
        # Get order data
        if isinstance(order, dict):
            user_id = order.get("user_id")
            store_id = order.get("store_id")
            delivery_address = order.get("delivery_address")
            order_status = order.get("order_status")
        else:
            user_id = getattr(order, "user_id", None)
            store_id = getattr(order, "store_id", None)
            delivery_address = getattr(order, "delivery_address", None)
            order_status = getattr(order, "order_status", None)
        
        # Check if already processed
        if order_status not in ["awaiting_payment", "awaiting_admin_confirmation"]:
            await callback.answer(f"⚠️ Order already processed (status: {order_status})", show_alert=True)
            return
        
        # Update status to pending (approved, waiting for seller)
        if hasattr(db, "update_order_status"):
            db.update_order_status(order_id, "pending")
        if hasattr(db, "update_payment_status"):
            db.update_payment_status(order_id, "confirmed")
        
        # Get store and seller info
        store = db.get_store(store_id) if hasattr(db, "get_store") and store_id else None
        if not store:
            await callback.answer("❌ Store not found", show_alert=True)
            return
        
        if isinstance(store, dict):
            seller_id = store.get("owner_id") or store.get("user_id")
            store_name = store.get("name", "")
        else:
            seller_id = getattr(store, "owner_id", None) or getattr(store, "user_id", None)
            store_name = getattr(store, "name", "")
        
        if not seller_id:
            await callback.answer("❌ Seller not found", show_alert=True)
            return
        
        # Get seller language
        seller_lang = db.get_user_language(seller_id) if hasattr(db, "get_user_language") else "ru"
        
        # Get user info
        user = db.get_user(user_id) if hasattr(db, "get_user") and user_id else None
        customer_name = ""
        customer_phone = ""
        if user:
            if isinstance(user, dict):
                customer_name = user.get("first_name", "")
                customer_phone = user.get("phone", "")
            else:
                customer_name = getattr(user, "first_name", "")
                customer_phone = getattr(user, "phone", "")
        
        # Build seller notification
        if seller_lang == "uz":
            seller_msg = (
                f"🔔 <b>YANGI BUYURTMA!</b>\n"
                f"━━━━━━━━━━━━━━━━━━\n\n"
                f"📦 #{order_id} | 🚚 Yetkazish\n\n"
                f"👤 {customer_name or 'Mijoz'}\n"
            )
            if customer_phone:
                seller_msg += f"📱 <code>{customer_phone}</code>\n"
            if delivery_address:
                seller_msg += f"📍 {delivery_address}\n"
            seller_msg += "\n💳 <b>To'lov admin tomonidan tasdiqlangan</b>\n\n"
            seller_msg += "⏳ <b>Buyurtmani tasdiqlang!</b>"
            
            confirm_text = "✅ Qabul qilish"
            reject_text = "❌ Rad etish"
        else:
            seller_msg = (
                f"🔔 <b>НОВЫЙ ЗАКАЗ!</b>\n"
                f"━━━━━━━━━━━━━━━━━━\n\n"
                f"📦 #{order_id} | 🚚 Доставка\n\n"
                f"👤 {customer_name or 'Клиент'}\n"
            )
            if customer_phone:
                seller_msg += f"📱 <code>{customer_phone}</code>\n"
            if delivery_address:
                seller_msg += f"📍 {delivery_address}\n"
            seller_msg += "\n💳 <b>Оплата подтверждена администратором</b>\n\n"
            seller_msg += "⏳ <b>Подтвердите заказ!</b>"
            
            confirm_text = "✅ Принять"
            reject_text = "❌ Отклонить"
        
        # Build keyboard
        kb = InlineKeyboardBuilder()
        kb.button(text=confirm_text, callback_data=f"order_confirm_{order_id}")
        kb.button(text=reject_text, callback_data=f"order_reject_{order_id}")
        kb.adjust(2)
        
        # Send to seller
        if callback.bot:
            await callback.bot.send_message(
                chat_id=seller_id,
                text=seller_msg,
                parse_mode="HTML",
                reply_markup=kb.as_markup(),
            )
        
        # Notify customer
        customer_lang = db.get_user_language(user_id) if hasattr(db, "get_user_language") and user_id else "ru"
        if customer_lang == "uz":
            customer_msg = (
                f"✅ <b>To'lov tasdiqlandi!</b>\n\n"
                f"📦 Buyurtma #{order_id}\n"
                f"🏪 {store_name}\n\n"
                f"Do'kon tasdiqini kuting (5-10 daqiqa)\n"
                f"✨ Tayyorlanganda xabar beramiz!"
            )
        else:
            customer_msg = (
                f"✅ <b>Оплата подтверждена!</b>\n\n"
                f"📦 Заказ #{order_id}\n"
                f"🏪 {store_name}\n\n"
                f"Ожидайте подтверждения от заведения (5-10 минут)\n"
                f"✨ Мы напишем, когда заказ будет готов!"
            )
        
        if callback.bot and user_id:
            await callback.bot.send_message(
                chat_id=user_id,
                text=customer_msg,
                parse_mode="HTML",
            )
        
        # Update admin message
        await callback.message.edit_caption(
            caption=callback.message.caption + "\n\n✅ <b>ОПЛАТА ПОДТВЕРЖДЕНА</b>\n"
                    f"👨‍💼 Администратор: {callback.from_user.first_name}",
            parse_mode="HTML",
        )
        await callback.answer("✅ Оплата подтверждена, заказ отправлен продавцу")
        
        logger.info(f"Order #{order_id} payment confirmed by admin, sent to seller {seller_id}")
        
    except Exception as e:
        logger.error(f"Error confirming payment: {e}")
        await callback.answer("❌ Ошибка подтверждения", show_alert=True)


@router.callback_query(F.data.startswith("admin_reject_payment_"))
async def admin_reject_payment(callback: types.CallbackQuery) -> None:
    """Admin rejects payment proof for delivery order.
    
    Flow:
    1. Update order status → rejected
    2. Notify customer
    3. Restore offer quantities
    """
    if not callback.message or not callback.from_user:
        return
    
    try:
        order_id = int(callback.data.split("_")[-1])
        logger.info(f"Admin {callback.from_user.id} rejecting payment for order #{order_id}")
        
        # Get order
        if not db or not hasattr(db, "get_order"):
            await callback.answer("❌ Database error", show_alert=True)
            return
        
        order = db.get_order(order_id)
        if not order:
            await callback.answer("❌ Order not found", show_alert=True)
            return
        
        if isinstance(order, dict):
            user_id = order.get("user_id")
            order_status = order.get("order_status")
        else:
            user_id = getattr(order, "user_id", None)
            order_status = getattr(order, "order_status", None)
        
        # Check if already processed
        if order_status not in ["awaiting_payment", "awaiting_admin_confirmation"]:
            await callback.answer(f"⚠️ Order already processed (status: {order_status})", show_alert=True)
            return
        
        # Update status to rejected
        order_service = get_unified_order_service()
        if order_service:
            await order_service.update_status(
                entity_id=order_id,
                entity_type="order",
                new_status="rejected",
                notify_customer=False,  # We'll send custom message
                reject_reason="Платёж не подтверждён администратором",
            )
        elif hasattr(db, "update_order_status"):
            db.update_order_status(order_id, "rejected")
        if hasattr(db, "update_payment_status"):
            db.update_payment_status(order_id, "rejected")
        
        # Notify customer
        customer_lang = db.get_user_language(user_id) if hasattr(db, "get_user_language") and user_id else "ru"
        if customer_lang == "uz":
            customer_msg = (
                f"😔 <b>To'lov tasdiqlanmadi</b>\n\n"
                f"📦 Buyurtma #{order_id}\n\n"
                f"To'lov cheki tasdiqlanmadi.\n"
                f"Iltimos, qo'llab-quvvatlash bilan bog'laning."
            )
        else:
            customer_msg = (
                f"😔 <b>Оплата не подтверждена</b>\n\n"
                f"📦 Заказ #{order_id}\n\n"
                f"К сожалению, платёж не подтверждён.\n"
                f"Пожалуйста, свяжитесь с поддержкой."
            )
        
        if callback.bot and user_id:
            await callback.bot.send_message(
                chat_id=user_id,
                text=customer_msg,
                parse_mode="HTML",
            )
        
        # Update admin message
        await callback.message.edit_caption(
            caption=callback.message.caption + "\n\n❌ <b>ОПЛАТА ОТКЛОНЕНА</b>\n"
                    f"👨‍💼 Администратор: {callback.from_user.first_name}",
            parse_mode="HTML",
        )
        await callback.answer("❌ Оплата отклонена, клиент уведомлён")
        
        logger.info(f"Order #{order_id} payment rejected by admin")
        
    except Exception as e:
        logger.error(f"Error rejecting payment: {e}")
        await callback.answer("❌ Ошибка отклонения", show_alert=True)
