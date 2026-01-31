from __future__ import annotations

from aiogram import F, Router, types

from app.application.orders.confirm_payment import confirm_payment
from app.application.orders.reject_payment import reject_payment
from app.infra.db.orders_repo import OrdersRepository
from app.interfaces.bot.presenters.order_messages import (
    build_admin_payment_confirmed_caption,
    build_admin_payment_rejected_caption,
    build_customer_payment_confirmed,
    build_customer_payment_rejected,
)
from app.services.unified_order_service import get_unified_order_service, init_unified_order_service
from localization import get_text

try:
    from logging_config import logger
except ImportError:
    import logging

    logger = logging.getLogger(__name__)


router = Router(name="admin_delivery_orders")

# Module dependencies
db = None
MAX_CAPTION_LENGTH = 1000


def setup(database) -> None:
    """Setup module dependencies."""
    global db
    db = database
    logger.info("Admin delivery orders handler initialized")


def _get_lang(user_id: int | None) -> str:
    if db and hasattr(db, "get_user_language") and user_id:
        return db.get_user_language(user_id)
    return "ru"


def _safe_caption(text: str) -> str:
    if len(text) <= MAX_CAPTION_LENGTH:
        return text
    return text[: MAX_CAPTION_LENGTH - 3] + "..."


async def _append_admin_note(message: types.Message | None, note: str) -> None:
    if not message:
        return

    if message.caption is not None:
        caption = _safe_caption((message.caption + "\n\n" + note).strip())
        try:
            await message.edit_caption(caption=caption, parse_mode="HTML")
            return
        except Exception:
            try:
                await message.bot.send_message(chat_id=message.chat.id, text=note, parse_mode="HTML")
            except Exception:
                pass
        return

    if message.text is not None:
        try:
            await message.edit_text(text=(message.text + "\n\n" + note).strip(), parse_mode="HTML")
        except Exception:
            pass


@router.callback_query(F.data.startswith("admin_confirm_payment_"))
async def admin_confirm_payment(callback: types.CallbackQuery) -> None:
    """Admin confirms payment proof for delivery order."""
    if not callback.message or not callback.from_user:
        return

    lang = _get_lang(callback.from_user.id)

    try:
        order_id = int(callback.data.split("_")[-1])
    except (ValueError, IndexError):
        await callback.answer(get_text(lang, "error"), show_alert=True)
        return

    try:
        if not db or not hasattr(db, "get_order"):
            await callback.answer(get_text(lang, "admin_db_error"), show_alert=True)
            return

        repo = OrdersRepository(db)
        order_service = get_unified_order_service()
        if not order_service and callback.bot:
            order_service = init_unified_order_service(db, callback.bot)

        result = await confirm_payment(order_id, repo=repo, order_service=order_service)
        if not result.ok:
            if result.error_key == "already_processed":
                status = result.payment_status or repo.get_field(
                    result.order, "order_status", ""
                )
                await callback.answer(
                    get_text(
                        lang,
                        "admin_order_already_processed",
                        status=status or "",
                    ),
                    show_alert=True,
                )
                return
            error_map = {
                "db_error": "admin_db_error",
                "not_found": "admin_order_not_found",
                "service_unavailable": "admin_service_unavailable",
                "processing_error": "admin_payment_processing_error",
            }
            key = error_map.get(result.error_key or "", "error")
            await callback.answer(get_text(lang, key), show_alert=True)
            return

        order = result.order
        user_id = repo.get_field(order, "user_id")
        store_id = repo.get_field(order, "store_id")
        store = repo.get_store(store_id)
        store_name = str(repo.get_field(store, "name", ""))

        customer_lang = _get_lang(user_id)
        customer_msg = build_customer_payment_confirmed(customer_lang, order_id, store_name)

        if callback.bot and user_id:
            await callback.bot.send_message(chat_id=user_id, text=customer_msg, parse_mode="HTML")

        admin_note = build_admin_payment_confirmed_caption(
            lang, callback.from_user.first_name or ""
        )
        await _append_admin_note(callback.message, admin_note)

        await callback.answer(get_text(lang, "admin_payment_confirmed"))
        logger.info("Order #%s payment confirmed by admin", order_id)

    except Exception as e:
        logger.error("Error confirming payment: %s", e)
        await callback.answer(get_text(lang, "error"), show_alert=True)


@router.callback_query(F.data.startswith("admin_reject_payment_"))
async def admin_reject_payment(callback: types.CallbackQuery) -> None:
    """Admin rejects payment proof for delivery order."""
    if not callback.message or not callback.from_user:
        return

    lang = _get_lang(callback.from_user.id)

    try:
        order_id = int(callback.data.split("_")[-1])
    except (ValueError, IndexError):
        await callback.answer(get_text(lang, "error"), show_alert=True)
        return

    try:
        if not db or not hasattr(db, "get_order"):
            await callback.answer(get_text(lang, "admin_db_error"), show_alert=True)
            return

        repo = OrdersRepository(db)
        order_service = get_unified_order_service()
        if not order_service and callback.bot:
            order_service = init_unified_order_service(db, callback.bot)

        result = await reject_payment(order_id, repo=repo, order_service=order_service)
        if not result.ok:
            if result.error_key == "already_processed":
                status = result.payment_status or repo.get_field(
                    result.order, "order_status", ""
                )
                await callback.answer(
                    get_text(
                        lang,
                        "admin_order_already_processed",
                        status=status or "",
                    ),
                    show_alert=True,
                )
                return
            error_map = {
                "db_error": "admin_db_error",
                "not_found": "admin_order_not_found",
                "service_unavailable": "admin_service_unavailable",
                "processing_error": "admin_payment_processing_error",
            }
            key = error_map.get(result.error_key or "", "error")
            await callback.answer(get_text(lang, key), show_alert=True)
            return

        order = result.order
        user_id = repo.get_field(order, "user_id")

        customer_lang = _get_lang(user_id)
        customer_msg = build_customer_payment_rejected(customer_lang, order_id)

        if callback.bot and user_id:
            await callback.bot.send_message(chat_id=user_id, text=customer_msg, parse_mode="HTML")

        admin_note = build_admin_payment_rejected_caption(
            lang, callback.from_user.first_name or ""
        )
        await _append_admin_note(callback.message, admin_note)

        await callback.answer(get_text(lang, "admin_payment_rejected"))
        logger.info("Order #%s payment rejected by admin", order_id)

    except Exception as e:
        logger.error("Error rejecting payment: %s", e)
        await callback.answer(get_text(lang, "error"), show_alert=True)
