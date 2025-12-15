"""Customer handler for uploading payment proof from Telegram bot.

Since file picker in Telegram WebApp doesn't work reliably, users can upload
payment proof directly through bot by clicking button in order history.
"""
from __future__ import annotations

from typing import Any

from aiogram import F, Router, types
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import BufferedInputFile
from aiogram.utils.keyboard import InlineKeyboardBuilder

from localization import get_text

try:
    from logging_config import logger
except ImportError:
    import logging
    logger = logging.getLogger(__name__)


router = Router(name="customer_payment_proof")

# Module dependencies
db: Any | None = None
bot_instance: Any | None = None


class PaymentProofStates(StatesGroup):
    """FSM states for payment proof upload."""
    waiting_for_photo = State()


def setup(database: Any, bot: Any = None) -> None:
    """Setup module dependencies."""
    global db, bot_instance
    db = database
    bot_instance = bot
    logger.info("✅ Customer payment proof handler initialized")


@router.callback_query(F.data.startswith("upload_proof_"))
async def start_upload_proof(callback: types.CallbackQuery, state: FSMContext) -> None:
    """User clicked button to upload payment proof for specific order."""
    if not callback.from_user:
        return
    
    try:
        order_id = int(callback.data.split("_")[-1])
        user_id = callback.from_user.id
        
        # Verify order belongs to user
        if not db or not hasattr(db, "get_order"):
            await callback.answer("❌ Xatolik / Ошибка", show_alert=True)
            return
        
        order = db.get_order(order_id)
        if not order:
            await callback.answer("❌ Buyurtma topilmadi / Заказ не найден", show_alert=True)
            return
        
        order_user_id = order.get("user_id") if isinstance(order, dict) else getattr(order, "user_id", None)
        if order_user_id != user_id:
            await callback.answer("❌ Bu buyurtma sizniki emas / Это не ваш заказ", show_alert=True)
            return
        
        # Check order status
        order_status = order.get("order_status") if isinstance(order, dict) else getattr(order, "order_status", None)
        if order_status not in ["awaiting_payment", "awaiting_admin_confirmation"]:
            lang = db.get_user_language(user_id) if hasattr(db, "get_user_language") else "ru"
            msg = "Bu buyurtma uchun to'lov kerak emas" if lang == "uz" else "Для этого заказа не требуется оплата"
            await callback.answer(f"⚠️ {msg}", show_alert=True)
            return
        
        # Save order_id in FSM and ask for photo
        await state.update_data(order_id=order_id)
        await state.set_state(PaymentProofStates.waiting_for_photo)
        
        lang = db.get_user_language(user_id) if hasattr(db, "get_user_language") else "ru"
        
        if lang == "uz":
            msg = (
                f"📸 <b>To'lov chekini yuklash</b>\n\n"
                f"Buyurtma #{order_id} uchun to'lov chekini yuboring.\n\n"
                f"To'lovni amalga oshirganingizdan keyin, chekni suratga olib bu yerga yuboring."
            )
        else:
            msg = (
                f"📸 <b>Загрузка чека об оплате</b>\n\n"
                f"Отправьте чек об оплате для заказа #{order_id}.\n\n"
                f"После совершения оплаты сфотографируйте чек и отправьте его сюда."
            )
        
        # Add cancel button
        kb = InlineKeyboardBuilder()
        cancel_text = "❌ Bekor qilish" if lang == "uz" else "❌ Отменить"
        kb.button(text=cancel_text, callback_data="cancel_upload")
        
        await callback.message.answer(msg, reply_markup=kb.as_markup(), parse_mode="HTML")
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Error starting payment proof upload: {e}")
        await callback.answer("❌ Xatolik / Ошибка", show_alert=True)


@router.callback_query(F.data == "cancel_upload")
async def cancel_upload(callback: types.CallbackQuery, state: FSMContext) -> None:
    """Cancel payment proof upload."""
    await state.clear()
    
    user_id = callback.from_user.id if callback.from_user else None
    lang = db.get_user_language(user_id) if db and hasattr(db, "get_user_language") and user_id else "ru"
    
    msg = "Bekor qilindi" if lang == "uz" else "Отменено"
    await callback.answer(f"❌ {msg}")
    
    if callback.message:
        try:
            await callback.message.delete()
        except Exception:
            pass


@router.message(PaymentProofStates.waiting_for_photo, F.photo)
async def receive_payment_proof(message: types.Message, state: FSMContext) -> None:
    """User sent photo as payment proof."""
    if not message.from_user or not message.photo:
        return
    
    try:
        user_id = message.from_user.id
        data = await state.get_data()
        order_id = data.get("order_id")
        
        if not order_id:
            await message.answer("❌ Xatolik: buyurtma topilmadi / Ошибка: заказ не найден")
            await state.clear()
            return
        
        # Get order
        if not db or not hasattr(db, "get_order"):
            await message.answer("❌ Xatolik / Ошибка")
            await state.clear()
            return
        
        order = db.get_order(order_id)
        if not order:
            await message.answer("❌ Buyurtma topilmadi / Заказ не найден")
            await state.clear()
            return
        
        # Get order details
        if isinstance(order, dict):
            order_user_id = order.get("user_id")
            store_id = order.get("store_id")
            delivery_address = order.get("delivery_address")
            total_price = order.get("total_price", 0)
        else:
            order_user_id = getattr(order, "user_id", None)
            store_id = getattr(order, "store_id", None)
            delivery_address = getattr(order, "delivery_address", None)
            total_price = getattr(order, "total_price", 0)
        
        # Verify user
        if order_user_id != user_id:
            await message.answer("❌ Bu buyurtma sizniki emas / Это не ваш заказ")
            await state.clear()
            return
        
        # Get user info
        user = db.get_user(user_id) if hasattr(db, "get_user") else None
        customer_name = ""
        customer_phone = ""
        if user:
            if isinstance(user, dict):
                customer_name = user.get("full_name") or user.get("username") or f"User {user_id}"
                customer_phone = user.get("phone_number") or ""
            else:
                customer_name = getattr(user, "full_name", None) or getattr(user, "username", None) or f"User {user_id}"
                customer_phone = getattr(user, "phone_number", "") or ""
        
        # Get store name
        store_name = "Магазин"
        if hasattr(db, "get_store"):
            store = db.get_store(store_id)
            if store:
                store_name = store.get("name") if isinstance(store, dict) else getattr(store, "name", "Магазин")
        
        # Update order status
        if hasattr(db, "update_order_status"):
            db.update_order_status(order_id, "awaiting_admin_confirmation")
        
        # Get admin IDs
        admin_ids = []
        if hasattr(db, "get_all_users"):
            users = db.get_all_users()
            for u in users:
                role = u.get("role") if isinstance(u, dict) else getattr(u, "role", None)
                u_id = u.get("user_id") if isinstance(u, dict) else getattr(u, "user_id", None)
                if role == "admin" and u_id:
                    admin_ids.append(u_id)
        
        # Send to all admins
        if not admin_ids:
            logger.warning("No admin users found in database")
            await message.answer("⚠️ Adminlar topilmadi / Администраторы не найдены")
            await state.clear()
            return
        
        # Build admin message
        admin_msg = (
            f"💳 <b>Новый платёж на подтверждение</b>\n\n"
            f"📦 Заказ #{order_id}\n"
            f"👤 Клиент: {customer_name}\n"
        )
        if customer_phone:
            admin_msg += f"📱 Телефон: {customer_phone}\n"
        admin_msg += (
            f"🏪 Магазин: {store_name}\n"
            f"💰 Сумма: {int(total_price):,} сум\n"
        )
        if delivery_address:
            admin_msg += f"📍 Адрес: {delivery_address}\n"
        
        # Create admin keyboard
        kb = InlineKeyboardBuilder()
        kb.button(text="✅ Подтвердить", callback_data=f"admin_confirm_payment_{order_id}")
        kb.button(text="❌ Отклонить", callback_data=f"admin_reject_payment_{order_id}")
        kb.adjust(2)
        
        # Send photo to all admins
        photo = message.photo[-1]
        sent_count = 0
        for admin_id in admin_ids:
            try:
                await message.bot.send_photo(
                    chat_id=admin_id,
                    photo=photo.file_id,
                    caption=admin_msg,
                    reply_markup=kb.as_markup(),
                    parse_mode="HTML"
                )
                sent_count += 1
            except Exception as e:
                logger.warning(f"Failed to send payment proof to admin {admin_id}: {e}")
        
        # Notify user
        lang = db.get_user_language(user_id) if hasattr(db, "get_user_language") else "ru"
        if lang == "uz":
            success_msg = (
                f"✅ <b>Chek yuborildi!</b>\n\n"
                f"Buyurtma #{order_id} uchun to'lov cheki adminlarga yuborildi.\n"
                f"Tez orada tasdiqlash haqida xabar beramiz."
            )
        else:
            success_msg = (
                f"✅ <b>Чек отправлен!</b>\n\n"
                f"Чек об оплате для заказа #{order_id} отправлен администраторам.\n"
                f"Скоро мы сообщим о подтверждении."
            )
        
        await message.answer(success_msg, parse_mode="HTML")
        await state.clear()
        
        logger.info(f"Payment proof for order #{order_id} sent to {sent_count} admins")
        
    except Exception as e:
        logger.error(f"Error processing payment proof: {e}")
        await message.answer("❌ Xatolik / Ошибка")
        await state.clear()


@router.message(PaymentProofStates.waiting_for_photo)
async def wrong_content_type(message: types.Message, state: FSMContext) -> None:
    """User sent something other than photo."""
    if not message.from_user:
        return
    
    user_id = message.from_user.id
    lang = db.get_user_language(user_id) if db and hasattr(db, "get_user_language") else "ru"
    
    if lang == "uz":
        msg = "❌ Iltimos, faqat rasm yuboring.\n\nTo'lov cheki rasmini yuboring yoki /cancel bosing."
    else:
        msg = "❌ Пожалуйста, отправьте только фото.\n\nОтправьте фото чека об оплате или нажмите /cancel."
    
    await message.answer(msg)
