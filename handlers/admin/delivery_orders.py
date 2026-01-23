from __future__ import annotations

from html import escape as esc

from aiogram import F, Router, types

from app.services.unified_order_service import (
    OrderStatus,
    get_unified_order_service,
    init_unified_order_service,
)
from localization import get_text

try:
    from logging_config import logger
except ImportError:
    import logging

    logger = logging.getLogger(__name__)


router = Router(name="admin_delivery_orders")

# Module dependencies
db = None


def setup(database) -> None:
    """Setup module dependencies."""
    global db
    db = database
    logger.info("Admin delivery orders handler initialized")


def _get_lang(user_id: int | None) -> str:
    if db and hasattr(db, "get_user_language") and user_id:
        return db.get_user_language(user_id)
    return "ru"


def _get_order_field(order, key: str, default=None):
    if isinstance(order, dict):
        return order.get(key, default)
    return getattr(order, key, default)


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

        order = db.get_order(order_id)
        if not order:
            await callback.answer(get_text(lang, "admin_order_not_found"), show_alert=True)
            return

        user_id = _get_order_field(order, "user_id")
        store_id = _get_order_field(order, "store_id")
        order_status = _get_order_field(order, "order_status")
        payment_status = _get_order_field(order, "payment_status")

        if payment_status not in ["proof_submitted", "awaiting_proof", "awaiting_admin_confirmation"]:
            await callback.answer(
                get_text(
                    lang,
                    "admin_order_already_processed",
                    status=payment_status or order_status,
                ),
                show_alert=True,
            )
            return

        order_service = get_unified_order_service()
        if not order_service and callback.bot:
            order_service = init_unified_order_service(db, callback.bot)
        if not order_service:
            await callback.answer(get_text(lang, "admin_service_unavailable"), show_alert=True)
            return

        ok = await order_service.confirm_payment(order_id)
        if not ok:
            await callback.answer(get_text(lang, "admin_payment_processing_error"), show_alert=True)
            return

        store = db.get_store(store_id) if hasattr(db, "get_store") and store_id else None
        store_name = esc(str(_get_order_field(store, "name", "")))

        customer_lang = _get_lang(user_id)
        customer_msg = get_text(
            customer_lang,
            "admin_payment_confirmed_customer",
            order_id=str(order_id),
            store_name=store_name,
        )

        if callback.bot and user_id:
            await callback.bot.send_message(
                chat_id=user_id,
                text=customer_msg,
                parse_mode="HTML",
            )

        caption = callback.message.caption or ""
        admin_note = get_text(
            lang,
            "admin_payment_confirmed_caption",
            admin_name=esc(callback.from_user.first_name or ""),
        )
        try:
            await callback.message.edit_caption(
                caption=(caption + "\n\n" + admin_note).strip(),
                parse_mode="HTML",
            )
        except Exception:
            pass

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

        order = db.get_order(order_id)
        if not order:
            await callback.answer(get_text(lang, "admin_order_not_found"), show_alert=True)
            return

        user_id = _get_order_field(order, "user_id")
        order_status = _get_order_field(order, "order_status")
        payment_status = _get_order_field(order, "payment_status")

        if payment_status not in ["proof_submitted", "awaiting_proof", "awaiting_admin_confirmation"]:
            await callback.answer(
                get_text(
                    lang,
                    "admin_order_already_processed",
                    status=payment_status or order_status,
                ),
                show_alert=True,
            )
            return

        order_service = get_unified_order_service()
        if not order_service and callback.bot:
            order_service = init_unified_order_service(db, callback.bot)
        if not order_service:
            await callback.answer(get_text(lang, "admin_service_unavailable"), show_alert=True)
            return

        await order_service.update_status(
            entity_id=order_id,
            entity_type="order",
            new_status=OrderStatus.REJECTED,
            notify_customer=False,
            reject_reason="payment_rejected_by_admin",
        )
        if hasattr(db, "update_payment_status"):
            db.update_payment_status(order_id, "rejected")

        customer_lang = _get_lang(user_id)
        customer_msg = get_text(
            customer_lang,
            "admin_payment_rejected_customer",
            order_id=str(order_id),
        )

        if callback.bot and user_id:
            await callback.bot.send_message(
                chat_id=user_id,
                text=customer_msg,
                parse_mode="HTML",
            )

        caption = callback.message.caption or ""
        admin_note = get_text(
            lang,
            "admin_payment_rejected_caption",
            admin_name=esc(callback.from_user.first_name or ""),
        )
        try:
            await callback.message.edit_caption(
                caption=(caption + "\n\n" + admin_note).strip(),
                parse_mode="HTML",
            )
        except Exception:
            pass

        await callback.answer(get_text(lang, "admin_payment_rejected"))
        logger.info("Order #%s payment rejected by admin", order_id)

    except Exception as e:
        logger.error("Error rejecting payment: %s", e)
        await callback.answer(get_text(lang, "error"), show_alert=True)
