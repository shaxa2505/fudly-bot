from __future__ import annotations

from aiogram import F, Router, types
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.keyboards import main_menu_customer
from app.services.unified_order_service import (
    NotificationTemplates,
    OrderItem,
    OrderResult,
    get_unified_order_service,
)
from localization import get_text

from . import common
from .common import esc
from .storage import cart_storage


def register(router: Router) -> None:
    """Register checkout-related cart handlers on the given router."""

    @router.callback_query(F.data == "cart_clear")
    async def cart_clear(callback: types.CallbackQuery) -> None:
        if not common.db or not callback.message:
            await callback.answer()
            return

        user_id = callback.from_user.id
        lang = common.db.get_user_language(user_id)

        cart_storage.clear_cart(user_id)

        text = get_text(lang, "cart_cleared")
        kb = InlineKeyboardBuilder()
        kb.button(text=get_text(lang, "cart_empty_cta"), callback_data="hot_offers")

        try:
            await callback.message.edit_text(text, parse_mode="HTML", reply_markup=kb.as_markup())
        except Exception:
            await callback.message.answer(text, parse_mode="HTML", reply_markup=kb.as_markup())

        await callback.answer()

    @router.callback_query(F.data == "cart_checkout")
    async def cart_checkout(callback: types.CallbackQuery, state: FSMContext) -> None:
        if not common.db or not callback.message:
            await callback.answer()
            return

        user_id = callback.from_user.id
        lang = common.db.get_user_language(user_id)

        items = cart_storage.get_cart(user_id)
        if not items:
            await callback.answer(get_text(lang, "cart_empty_alert"), show_alert=True)
            return

        low_stock_warnings = []
        for item in items:
            if item.max_quantity < 5 and item.quantity > (item.max_quantity * 0.5):
                low_stock_warnings.append(
                    get_text(
                        lang,
                        "cart_low_stock_item",
                        title=item.title,
                        max=item.max_quantity,
                        unit=item.unit,
                    )
                )

        if low_stock_warnings:
            warning_text = "\n".join(low_stock_warnings)
            warning_text += "\n\n" + get_text(lang, "cart_low_stock_hint")
            try:
                await callback.message.answer(warning_text, parse_mode="HTML")
            except Exception:
                pass

        user = common.db.get_user_model(user_id)
        if not user or not getattr(user, "phone", None):
            from app.keyboards import phone_request_keyboard
            from handlers.common.states import Registration

            await callback.message.answer(
                get_text(lang, "cart_phone_required"),
                reply_markup=phone_request_keyboard(lang),
            )
            await state.update_data(pending_cart_checkout=True)
            await state.set_state(Registration.phone)
            await callback.answer()
            return

        stores = {item.store_id for item in items}
        if len(stores) > 1:
            await callback.answer(
                get_text(lang, "cart_single_store_only"),
                show_alert=True,
            )
            return

        delivery_enabled = any(item.delivery_enabled for item in items)
        delivery_price = max(
            (item.delivery_price for item in items if item.delivery_enabled), default=0
        )

        currency = "so'm" if lang == "uz" else "сум"
        total = int(sum(item.price * item.quantity for item in items))

        lines: list[str] = [f"🧾 <b>{get_text(lang, 'cart_order_title')}</b>\n"]
        lines.append(f"🏪 {esc(items[0].store_name)}\n")

        for item in items:
            subtotal = int(item.price * item.quantity)
            lines.append(f"• {esc(item.title)} x {item.quantity} = {subtotal:,} {currency}")

        lines.append("\n" + "-" * 25)
        lines.append(f"<b>{get_text(lang, 'cart_total_label')}: {total:,} {currency}</b>")
        if delivery_enabled:
            lines.append(
                f"{get_text(lang, 'cart_delivery_label')}: {delivery_price:,} {currency}"
            )
            grand_total = total + delivery_price
            lines.append(
                f"<b>{get_text(lang, 'cart_grand_total_label')}: {grand_total:,} {currency}</b>"
            )

        text = "\n".join(lines)

        kb = InlineKeyboardBuilder()

        if delivery_enabled:
            kb.button(
                text=get_text(lang, "cart_pickup_button"),
                callback_data="cart_confirm_pickup",
            )
            kb.button(
                text=get_text(lang, "cart_delivery_button"),
                callback_data="cart_confirm_delivery",
            )
            kb.adjust(2)
        else:
            kb.button(
                text=get_text(lang, "cart_confirm_button"),
                callback_data="cart_confirm_pickup",
            )

        kb.button(
            text=get_text(lang, "cart_back_button"),
            callback_data="back_to_cart",
        )

        try:
            await callback.message.edit_text(text, parse_mode="HTML", reply_markup=kb.as_markup())
        except Exception:
            await callback.message.answer(text, parse_mode="HTML", reply_markup=kb.as_markup())

        await callback.answer()

    @router.callback_query(F.data == "cart_confirm_pickup")
    async def cart_confirm_pickup(callback: types.CallbackQuery) -> None:
        """Create a pickup order from the cart and show a clear confirmation."""

        if not common.db or not callback.message:
            await callback.answer()
            return

        user_id = callback.from_user.id
        lang = common.db.get_user_language(user_id)

        items = cart_storage.get_cart(user_id)
        if not items:
            await callback.answer(get_text(lang, "cart_empty_alert"), show_alert=True)
            return

        order_service = get_unified_order_service()
        if not order_service:
            await callback.answer(get_text(lang, "system_error"), show_alert=True)
            return

        order_items: list[OrderItem] = []
        for item in items:
            order_items.append(
                OrderItem(
                    offer_id=item.offer_id,
                    store_id=item.store_id,
                    title=item.title,
                    price=int(item.price),
                    original_price=int(item.price),
                    quantity=int(item.quantity),
                    store_name=item.store_name,
                    store_address=item.store_address,
                    delivery_price=0,
                )
            )

        try:
            result: OrderResult = await order_service.create_order(
                user_id=user_id,
                items=order_items,
                order_type="pickup",
                delivery_address=None,
                payment_method="cash",
                notify_customer=True,
                notify_sellers=True,
                telegram_notify=True,
            )
        except Exception as e:  # pragma: no cover - defensive logging
            from logging_config import logger

            logger.error(f"Failed to create unified pickup order from cart: {e}")
            await callback.answer(get_text(lang, "system_error"), show_alert=True)
            return

        if not result.success:
            msg = result.error_message or get_text(lang, "system_error")
            await callback.answer(msg, show_alert=True)
            return

        cart_storage.clear_cart(user_id)

        user = common.db.get_user_model(user_id)
        if isinstance(user, dict):
            notifications_enabled = bool(user.get("notifications_enabled", True))
        else:
            notifications_enabled = bool(getattr(user, "notifications_enabled", True))

        if not notifications_enabled:
            order_ids = [str(oid) for oid in result.order_ids if oid]
            pickup_codes = [code for code in result.pickup_codes if code]
            items_for_template = [
                {"title": i.title, "price": i.price, "quantity": i.quantity} for i in order_items
            ]
            store_name = order_items[0].store_name if order_items else ""
            store_address = order_items[0].store_address if order_items else ""
            currency = "so'm" if lang == "uz" else "сум"

            text = NotificationTemplates.customer_order_created(
                lang=lang,
                order_ids=order_ids,
                pickup_codes=pickup_codes,
                items=items_for_template,
                order_type="pickup",
                delivery_address=None,
                payment_method="cash",
                store_name=store_name,
                store_address=store_address,
                total=int(result.total_price) if hasattr(result, "total_price") else total,
                delivery_price=0,
                currency=currency,
            )
            text += "\n\n" + get_text(lang, "cart_order_created_menu_hint")

            try:
                await callback.message.answer(text, parse_mode="HTML")
            except Exception:
                pass

        await callback.answer()

    @router.callback_query(F.data == "back_to_menu")
    async def back_to_menu(callback: types.CallbackQuery, state: FSMContext) -> None:
        if not common.db or not callback.message:
            await callback.answer()
            return

        await state.clear()

        user_id = callback.from_user.id
        lang = common.db.get_user_language(user_id)

        cart_count = cart_storage.get_cart_count(user_id)

        text = get_text(lang, "main_menu")

        await callback.message.answer(text, reply_markup=main_menu_customer(lang, cart_count))
        await callback.answer()
