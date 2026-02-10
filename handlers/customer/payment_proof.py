"""Customer handler for uploading payment proof from Telegram bot.

Since file picker in Telegram WebApp doesn't work reliably, users can upload
payment proof directly through bot by clicking button in order history.
"""
from __future__ import annotations

import os
from typing import Any

from aiogram import F, Router, types
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import BufferedInputFile
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.application.orders.submit_payment_proof import submit_payment_proof
from app.domain.order import OrderStatus, PaymentStatus
from app.infra.db.orders_repo import OrdersRepository
from app.interfaces.bot.presenters.payment_proof_messages import (
    build_admin_payment_proof_caption,
    build_admin_payment_proof_keyboard,
)
from app.services.unified_order_service import get_unified_order_service, init_unified_order_service
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


def _t(lang: str, ru: str, uz: str) -> str:
    return ru if lang == "ru" else uz


def _lang_code(user: types.User | None) -> str:
    code = (user.language_code or "ru") if user else "ru"
    return "uz" if code.startswith("uz") else "ru"


def _service_unavailable(lang: str) -> str:
    return _t(
        lang,
        "Сервис временно недоступен. Попробуйте позже.",
        "Xizmat vaqtincha mavjud emas. Keyinroq urinib ko'ring.",
    )


class PaymentProofStates(StatesGroup):
    """FSM states for payment proof upload."""

    waiting_for_photo = State()


def setup(database: Any, bot: Any = None) -> None:
    """Setup module dependencies."""
    global db, bot_instance
    db = database
    bot_instance = bot
    logger.info("Customer payment proof handler initialized")


@router.callback_query(F.data.startswith("upload_proof_"))
async def start_upload_proof(callback: types.CallbackQuery, state: FSMContext) -> None:
    """User clicked button to upload payment proof for specific order."""
    if not callback.from_user:
        return

    try:
        order_id = int(callback.data.split("_")[-1])
        user_id = callback.from_user.id
        lang = (
            db.get_user_language(user_id)
            if db and hasattr(db, "get_user_language")
            else _lang_code(callback.from_user)
        )

        # Verify order belongs to user
        if not db or not hasattr(db, "get_order"):
            await callback.answer(_service_unavailable(lang), show_alert=True)
            return

        order = db.get_order(order_id)
        if not order:
            await callback.answer(_t(lang, "Заказ не найден.", "Buyurtma topilmadi."), show_alert=True)
            return

        order_user_id = (
            order.get("user_id") if isinstance(order, dict) else getattr(order, "user_id", None)
        )
        if order_user_id != user_id:
            await callback.answer(_t(lang, "Это не ваш заказ.", "Bu buyurtma sizniki emas."), show_alert=True)
            return

        payment_method = (
            order.get("payment_method")
            if isinstance(order, dict)
            else getattr(order, "payment_method", None)
        )
        payment_status_raw = (
            order.get("payment_status")
            if isinstance(order, dict)
            else getattr(order, "payment_status", None)
        )
        payment_proof_photo_id = (
            order.get("payment_proof_photo_id")
            if isinstance(order, dict)
            else getattr(order, "payment_proof_photo_id", None)
        )

        payment_status = PaymentStatus.normalize(
            payment_status_raw,
            payment_method=payment_method,
            payment_proof_photo_id=payment_proof_photo_id,
        )

        if payment_status == PaymentStatus.PROOF_SUBMITTED:
            msg = _t(
                lang,
                "Чек уже отправлен. Ожидайте подтверждения.",
                "Chek allaqachon yuborilgan. Tasdiqlanishini kuting.",
            )
            await callback.answer(msg, show_alert=True)
            return

        if payment_status == PaymentStatus.CONFIRMED:
            msg = _t(lang, "Оплата уже подтверждена.", "To'lov allaqachon tasdiqlangan.")
            await callback.answer(msg, show_alert=True)
            return

        if payment_status == PaymentStatus.NOT_REQUIRED:
            msg = _t(
                lang,
                "Для этого заказа не требуется оплата.",
                "Bu buyurtma uchun to'lov kerak emas.",
            )
            await callback.answer(msg, show_alert=True)
            return

        if payment_status not in (PaymentStatus.AWAITING_PROOF, PaymentStatus.REJECTED):
            msg = _t(
                lang,
                "Для этого заказа не требуется отправлять чек.",
                "Bu buyurtma uchun chek yuborish kerak emas.",
            )
            await callback.answer(msg, show_alert=True)
            return

        # Save order_id in FSM and ask for photo
        await state.update_data(order_id=order_id)
        await state.set_state(PaymentProofStates.waiting_for_photo)

        if lang == "uz":
            msg = (
                f"<b>To'lov cheki</b>\n\n"
                f"Buyurtma #{order_id}\n"
                f"To'lov chekini suratga olib shu yerga yuboring."
            )
        else:
            msg = (
                f"<b>Чек об оплате</b>\n\n"
                f"Заказ #{order_id}\n"
                f"Сфотографируйте чек и отправьте его сюда."
            )

        # Add cancel button
        kb = InlineKeyboardBuilder()
        cancel_text = "Bekor qilish" if lang == "uz" else "Отменить"
        kb.button(text=cancel_text, callback_data="cancel_upload")

        await callback.message.answer(msg, reply_markup=kb.as_markup(), parse_mode="HTML")
        await callback.answer()

    except Exception as e:
        logger.error(f"Error starting payment proof upload: {e}")
        await callback.answer(_service_unavailable(_lang_code(callback.from_user)), show_alert=True)


@router.callback_query(F.data == "cancel_upload")
async def cancel_upload(callback: types.CallbackQuery, state: FSMContext) -> None:
    """Cancel payment proof upload."""
    await state.clear()

    user_id = callback.from_user.id if callback.from_user else None
    lang = (
        db.get_user_language(user_id)
        if db and hasattr(db, "get_user_language") and user_id
        else "ru"
    )

    msg = "Bekor qilindi." if lang == "uz" else "Отменено."
    await callback.answer(msg)

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
        lang = (
            db.get_user_language(user_id)
            if db and hasattr(db, "get_user_language")
            else _lang_code(message.from_user)
        )
        data = await state.get_data()
        order_id = data.get("order_id")

        if not order_id:
            await message.answer(_t(lang, "Заказ не найден.", "Buyurtma topilmadi."))
            await state.clear()
            return

        # Get order
        if not db or not hasattr(db, "get_order"):
            await message.answer(_service_unavailable(lang))
            await state.clear()
            return

        order = db.get_order(order_id)
        if not order:
            await message.answer(_t(lang, "Заказ не найден.", "Buyurtma topilmadi."))
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
            await message.answer(_t(lang, "Это не ваш заказ.", "Bu buyurtma sizniki emas."))
            await state.clear()
            return

        # Get user info
        user = db.get_user(user_id) if hasattr(db, "get_user") else None
        customer_name = ""
        customer_phone = ""
        if user:
            if isinstance(user, dict):
                customer_name = user.get("full_name") or user.get("username") or f"User {user_id}"
                customer_phone = user.get("phone") or ""
            else:
                customer_name = (
                    getattr(user, "full_name", None)
                    or getattr(user, "username", None)
                    or f"User {user_id}"
                )
                customer_phone = getattr(user, "phone", "") or ""

        # Get store name
        store_name = "Магазин"
        if hasattr(db, "get_store"):
            store = db.get_store(store_id)
            if store:
                store_name = (
                    store.get("name")
                    if isinstance(store, dict)
                    else getattr(store, "name", "Магазин")
                )

        # Keep order_status as fulfillment-only; fix legacy statuses if present
        current_order_status = (
            order.get("order_status")
            if isinstance(order, dict)
            else getattr(order, "order_status", None)
        )
        if (
            current_order_status in ("awaiting_payment", "awaiting_admin_confirmation")
        ):
            order_service = get_unified_order_service()
            if not order_service:
                bot_ref = bot_instance or message.bot
                if bot_ref:
                    order_service = init_unified_order_service(db, bot_ref)
            if order_service:
                await order_service.update_status(
                    entity_id=order_id,
                    entity_type="order",
                    new_status=OrderStatus.PENDING,
                    notify_customer=False,
                )
            else:
                logger.warning("UnifiedOrderService not available to normalize order status")

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
            admin_id_env = int(os.getenv("ADMIN_ID", "0"))
            if admin_id_env:
                admin_ids.append(admin_id_env)
                logger.info("Using ADMIN_ID fallback: %s", admin_id_env)

        if not admin_ids:
            logger.warning("No admin users found in database")
            await message.answer(_t(lang, "Администраторы не найдены.", "Adminlar topilmadi."))
            await state.clear()
            return

        # Build admin message
        admin_msg = build_admin_payment_proof_caption(
            order_id=order_id,
            customer_name=customer_name,
            customer_phone=customer_phone,
            store_name=store_name,
            delivery_address=delivery_address,
            cart_items=None,
            total_price=total_price,
            delivery_fee=None,
            lang="ru",
        )
        admin_keyboard = build_admin_payment_proof_keyboard(order_id)

        # Send photo to all admins
        photo = message.photo[-1]

        repo = OrdersRepository(db) if db else None
        result = await submit_payment_proof(
            order_id,
            actor_user_id=user_id,
            proof_file_id=photo.file_id,
            repo=repo,
        )
        if not result.ok:
            error_map = {
                "db_error": _service_unavailable(lang),
                "processing_error": _service_unavailable(lang),
                "not_found": _t(lang, "Заказ не найден.", "Buyurtma topilmadi."),
                "forbidden": _t(lang, "Это не ваш заказ.", "Bu buyurtma sizniki emas."),
                "already_submitted": _t(
                    lang,
                    "Чек уже отправлен. Ожидайте подтверждения.",
                    "Chek allaqachon yuborilgan. Tasdiqlanishini kuting.",
                ),
                "already_confirmed": _t(
                    lang,
                    "Оплата уже подтверждена.",
                    "To'lov allaqachon tasdiqlangan.",
                ),
                "not_required": _t(
                    lang,
                    "Для этого заказа не требуется оплата.",
                    "Bu buyurtma uchun to'lov kerak emas.",
                ),
                "not_allowed": _t(
                    lang,
                    "Для этого заказа не требуется отправлять чек.",
                    "Bu buyurtma uchun chek yuborish kerak emas.",
                ),
            }
            await message.answer(error_map.get(result.error_key, _service_unavailable(lang)))
            await state.clear()
            return

        sent_count = 0
        for admin_id in admin_ids:
            try:
                await message.bot.send_photo(
                    chat_id=admin_id,
                    photo=photo.file_id,
                    caption=admin_msg,
                    reply_markup=admin_keyboard,
                    parse_mode="HTML",
                )
                sent_count += 1
            except Exception as e:
                logger.warning(f"Failed to send payment proof to admin {admin_id}: {e}")

        # Notify user
        if lang == "uz":
            success_msg = (
                f"<b>Chek yuborildi</b>\n\n"
                f"Buyurtma #{order_id} uchun to'lov cheki adminlarga yuborildi.\n"
                f"Tez orada tasdiqlash haqida xabar beramiz."
            )
        else:
            success_msg = (
                f"<b>Чек отправлен</b>\n\n"
                f"Чек об оплате для заказа #{order_id} отправлен администраторам.\n"
                f"Скоро мы сообщим о подтверждении."
            )

        existing_msg_id = None
        if isinstance(order, dict):
            existing_msg_id = order.get("customer_message_id")
        else:
            existing_msg_id = getattr(order, "customer_message_id", None)

        edit_success = False
        if existing_msg_id:
            try:
                await message.bot.edit_message_caption(
                    chat_id=user_id,
                    message_id=existing_msg_id,
                    caption=success_msg,
                    parse_mode="HTML",
                )
                edit_success = True
            except Exception:
                try:
                    await message.bot.edit_message_text(
                        chat_id=user_id,
                        message_id=existing_msg_id,
                        text=success_msg,
                        parse_mode="HTML",
                    )
                    edit_success = True
                except Exception:
                    pass

        if not edit_success:
            sent_msg = await message.answer(success_msg, parse_mode="HTML")
            if sent_msg and db and hasattr(db, "set_order_customer_message_id"):
                try:
                    db.set_order_customer_message_id(order_id, sent_msg.message_id)
                    logger.info(
                        "Saved customer_message_id=%s for order#%s",
                        sent_msg.message_id,
                        order_id,
                    )
                except Exception as save_err:  # pragma: no cover - defensive
                    logger.warning(
                        "Failed to save customer_message_id for order %s: %s",
                        order_id,
                        save_err,
                    )
        await state.clear()

        logger.info(f"Payment proof for order #{order_id} sent to {sent_count} admins")

    except Exception as e:
        logger.error(f"Error processing payment proof: {e}")
        await message.answer(_service_unavailable(_lang_code(message.from_user)))
        await state.clear()


@router.message(PaymentProofStates.waiting_for_photo)
async def wrong_content_type(message: types.Message, state: FSMContext) -> None:
    """User sent something other than photo."""
    if not message.from_user:
        return

    user_id = message.from_user.id
    lang = db.get_user_language(user_id) if db and hasattr(db, "get_user_language") else "ru"

    if lang == "uz":
        msg = (
            "Iltimos, faqat rasm yuboring.\n\nTo'lov cheki rasmini yuboring yoki /cancel bosing."
        )
    else:
        msg = "Пожалуйста, отправьте только фото.\n\nОтправьте фото чека об оплате или нажмите /cancel."

    await message.answer(msg)
