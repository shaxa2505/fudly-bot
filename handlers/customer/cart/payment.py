from __future__ import annotations

from aiogram import F, Router, types
from aiogram.filters import BaseFilter
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.services.unified_order_service import (
    NotificationTemplates,
    OrderItem,
    OrderResult,
    get_unified_order_service,
)
from handlers.common.states import OrderDelivery
from localization import get_text

from .common import esc
from . import common


class IsCartOrderFilter(BaseFilter):
    """Filter that checks if current FSM state data has is_cart_order=True."""

    async def __call__(self, message: types.Message, state: FSMContext) -> bool:  # type: ignore[override]
        data = await state.get_data()
        return bool(data.get("is_cart_order"))


async def _cart_show_card_payment_details(
    message: types.Message, state: FSMContext, lang: str
) -> None:
    data = await state.get_data()
    store_id = data.get("store_id")
    cart_items_stored = data.get("cart_items", [])
    delivery_price = data.get("delivery_price", 0)

    payment_card = None
    try:
        payment_card = common.db.get_payment_card(store_id)
    except Exception:
        pass

    if not payment_card:
        try:
            payment_card = common.db.get_platform_payment_card()
        except Exception:
            pass

    if not payment_card:
        payment_card = {"card_number": "8600 1234 5678 9012", "card_holder": "FUDLY"}

    if isinstance(payment_card, dict):
        card_number = payment_card.get("card_number", "")
        card_holder = payment_card.get("card_holder", "FUDLY")
    elif isinstance(payment_card, (tuple, list)) and len(payment_card) > 1:
        card_number = payment_card[1]
        card_holder = payment_card[2] if len(payment_card) > 2 else "FUDLY"
    else:
        card_number = str(payment_card)
        card_holder = "FUDLY"

    total = sum(item["price"] * item["quantity"] for item in cart_items_stored)
    total_with_delivery = total + delivery_price

    currency = "so'm" if lang == "uz" else "сум"

    safe_holder = esc(card_holder)
    lines = [
        f"<b>{get_text(lang, 'cart_payment_card_title')}</b>",
        "",
        f"{get_text(lang, 'cart_payment_amount_label')}: <b>{total_with_delivery:,} {currency}</b>",
        f"{get_text(lang, 'cart_payment_card_label')}: <code>{card_number}</code>",
        f"{get_text(lang, 'cart_payment_holder_label')}: {safe_holder}",
        "",
        f"<i>{get_text(lang, 'cart_payment_receipt_hint')}</i>",
    ]

    text = "\n".join(lines)

    kb = InlineKeyboardBuilder()
    kb.button(text=get_text(lang, "cart_delivery_back_button"), callback_data="cart_back_to_payment")
    kb.button(text=get_text(lang, "cart_payment_cancel_button"), callback_data="cart_cancel_payment")

    await message.answer(text, parse_mode="HTML", reply_markup=kb.as_markup())


def register(router: Router) -> None:
    """Register payment-related handlers for cart orders."""

    @router.callback_query(F.data.startswith("cart_pay_click_"))
    async def cart_pay_click(callback: types.CallbackQuery, state: FSMContext) -> None:
        if not common.db or not callback.message:
            await callback.answer()
            return

        user_id = callback.from_user.id
        lang = common.db.get_user_language(user_id)

        data = await state.get_data()
        cart_items_stored = data.get("cart_items", [])
        store_id = data.get("store_id")
        address = data.get("address", "")

        if not cart_items_stored or not store_id or not address:
            await state.clear()
            await callback.answer(get_text(lang, "cart_payment_data_missing"), show_alert=True)
            return

        await callback.answer(get_text(lang, "cart_payment_click_unavailable"), show_alert=True)
        return

    @router.callback_query(F.data == "cart_back_to_payment")
    async def cart_back_to_payment(callback: types.CallbackQuery, state: FSMContext) -> None:
        """Go back from card details to payment method selection for cart orders."""
        if not common.db or not callback.message:
            await callback.answer()
            return

        user_id = callback.from_user.id
        lang = common.db.get_user_language(user_id)

        data = await state.get_data()
        cart_items_stored = data.get("cart_items", [])
        store_id = data.get("store_id")
        delivery_price = data.get("delivery_price", 0)
        address = data.get("address", "")

        if not cart_items_stored or not store_id or not address:
            await state.clear()
            await callback.answer(get_text(lang, "cart_payment_data_missing"), show_alert=True)
            return

        currency = "so'm" if lang == "uz" else "сум"
        total = sum(int(item["price"]) * int(item["quantity"]) for item in cart_items_stored)
        total_with_delivery = total + int(delivery_price)

        safe_address = esc(address)
        text = (
            f"💳 <b>{get_text(lang, 'cart_payment_select_title')}</b>\n\n"
            f"{get_text(lang, 'cart_payment_amount_label')}: <b>{total_with_delivery:,} {currency}</b>\n"
            f"{get_text(lang, 'cart_delivery_address_label')}: {safe_address}"
        )

        kb = InlineKeyboardBuilder()
        kb.button(
            text=get_text(lang, "cart_delivery_payment_card"),
            callback_data=f"cart_pay_card_{store_id}",
        )
        kb.button(
            text=get_text(lang, "cart_delivery_back_button"),
            callback_data="cart_back_to_address",
        )
        kb.button(
            text=get_text(lang, "cart_payment_cancel_button"),
            callback_data="cart_cancel_payment",
        )
        kb.adjust(1, 2)

        try:
            await callback.message.edit_text(text, parse_mode="HTML", reply_markup=kb.as_markup())
        except Exception:
            await callback.message.answer(text, parse_mode="HTML", reply_markup=kb.as_markup())

        await callback.answer()

    @router.callback_query(F.data.startswith("cart_pay_card_"))
    async def cart_pay_card(callback: types.CallbackQuery, state: FSMContext) -> None:
        if not common.db or not callback.message:
            await callback.answer()
            return

        user_id = callback.from_user.id
        lang = common.db.get_user_language(user_id)

        data = await state.get_data()
        cart_items_stored = data.get("cart_items", [])
        store_id = data.get("store_id")
        address = data.get("address", "")

        if not cart_items_stored or not store_id or not address:
            await state.clear()
            await callback.answer(get_text(lang, "cart_payment_data_missing"), show_alert=True)
            return

        await state.update_data(payment_method="card")
        await state.set_state(OrderDelivery.payment_proof)

        try:
            await callback.message.delete()
        except Exception:
            pass
        await _cart_show_card_payment_details(callback.message, state, lang)
        await callback.answer()

    @router.message(OrderDelivery.payment_proof, F.photo, IsCartOrderFilter())
    async def cart_payment_proof(message: types.Message, state: FSMContext) -> None:
        if not common.db or not common.bot or not message.from_user:
            return

        user_id = message.from_user.id
        lang = common.db.get_user_language(user_id)
        data = await state.get_data()
        photo_id = message.photo[-1].file_id

        cart_items_stored = data.get("cart_items", [])
        store_id = data.get("store_id")
        delivery_price = data.get("delivery_price", 0)
        address = data.get("address", "")

        if not cart_items_stored or not store_id or not address:
            await message.answer(get_text(lang, "cart_delivery_data_lost"))
            await state.clear()
            return

        if data.get("payment_proof_in_progress"):
            await message.answer(get_text(lang, "cart_payment_photo_already_received"))
            return

        await state.update_data(payment_proof_in_progress=True)

        order_service = get_unified_order_service()
        if not order_service:
            await message.answer(get_text(lang, "cart_payment_service_unavailable"))
            await state.clear()
            return

        order_items: list[OrderItem] = []
        for item in cart_items_stored:
            order_items.append(
                OrderItem(
                    offer_id=int(item["offer_id"]),
                    store_id=int(item["store_id"]),
                    title=str(item["title"]),
                    price=int(item["price"]),
                    original_price=int(item.get("original_price") or item["price"]),
                    quantity=int(item["quantity"]),
                    store_name=str(item.get("store_name", "")),
                    store_address="",
                    delivery_price=int(delivery_price),
                )
            )

        try:
            result: OrderResult = await order_service.create_order(
                user_id=user_id,
                items=order_items,
                order_type="delivery",
                delivery_address=address,
                payment_method="card",
                payment_proof=photo_id,
                notify_customer=False,
                notify_sellers=False,
            )
        except Exception as e:
            from logging_config import logger

            logger.error(f"Failed to create unified delivery order from cart (after screenshot): {e}")
            await message.answer(get_text(lang, "cart_payment_order_failed"))
            await state.clear()
            return

        if not result.success or not result.order_ids:
            msg = result.error_message or get_text(lang, "cart_payment_order_failed")
            await message.answer(msg)
            await state.clear()
            return

        order_id = result.order_ids[0]

        from .storage import cart_storage

        cart_storage.clear_cart(user_id)

        common.db.update_payment_status(order_id, "proof_submitted", photo_id)

        try:
            common.db.save_delivery_address(user_id, address)
        except Exception as e:  # pragma: no cover - defensive logging
            from logging_config import logger

            logger.warning(f"Could not save address: {e}")

        await state.clear()

        store = common.db.get_store(store_id)
        from handlers.bookings.utils import get_store_field

        store_name = get_store_field(store, "name", get_text(lang, "store_not_found"))
        owner_id = get_store_field(store, "owner_id")

        customer = common.db.get_user_model(user_id) if common.db else None
        customer_phone = customer.phone if customer else ""

        total = sum(item["price"] * item["quantity"] for item in cart_items_stored)
        total_with_delivery = total + delivery_price
        currency = "so'm" if lang == "uz" else "сум"

        from bot import ADMIN_ID

        if ADMIN_ID > 0 and common.bot:
            kb = InlineKeyboardBuilder()
            kb.button(
                text=get_text(lang, "admin_confirm_payment_button"),
                callback_data=f"admin_confirm_payment_{order_id}",
            )
            kb.button(
                text=get_text(lang, "admin_reject_payment_button"),
                callback_data=f"admin_reject_payment_{order_id}",
            )
            kb.adjust(2)

            items_text = "\n".join(
                [f"• {esc(item['title'])} x {item['quantity']}" for item in cart_items_stored]
            )
            safe_address = esc(address)
            admin_caption = NotificationTemplates.admin_payment_review(
                lang=lang,
                order_id=order_id,
                store_name=store_name,
                items_text=items_text,
                total_with_delivery=total_with_delivery,
                currency=currency,
                address=safe_address,
                customer_name=message.from_user.first_name,
                customer_phone=customer_phone,
            )

            try:
                await common.bot.send_photo(
                    chat_id=ADMIN_ID,
                    photo=photo_id,
                    caption=admin_caption,
                    parse_mode="HTML",
                    reply_markup=kb.as_markup(),
                )
            except Exception as e:  # pragma: no cover - defensive logging
                from logging_config import logger

                logger.error(f"Failed to notify admin: {e}")

        items_for_template = [
            {
                "title": item["title"],
                "price": int(item["price"]),
                "quantity": int(item["quantity"]),
            }
            for item in cart_items_stored
        ]

        order_ids_for_template = [str(x) for x in result.order_ids]
        delivery_price_int = int(delivery_price)

        customer_msg = NotificationTemplates.customer_order_created(
            lang=lang,
            order_ids=order_ids_for_template,
            pickup_codes=[],
            items=items_for_template,
            order_type="delivery",
            delivery_address=address,
            payment_method="card",
            store_name=store_name,
            store_address=get_store_field(store, "address", ""),
            total=int(total),
            delivery_price=delivery_price_int,
            currency=currency,
            awaiting_payment=True,
        )

        confirm_text = customer_msg + "\n\n" + get_text(lang, "cart_payment_pending_confirmation")

        sent_msg = await message.answer(confirm_text, parse_mode="HTML")

        if sent_msg and order_id and hasattr(common.db, "set_order_customer_message_id"):
            from logging_config import logger

            try:
                common.db.set_order_customer_message_id(order_id, sent_msg.message_id)
                logger.info(
                    "Saved customer_message_id=%s for cart order #%s",
                    sent_msg.message_id,
                    order_id,
                )
            except Exception as e:  # pragma: no cover - defensive logging
                logger.warning(f"Failed to save customer_message_id: {e}")

    @router.callback_query(F.data == "cart_cancel_payment")
    async def cart_cancel_payment(callback: types.CallbackQuery, state: FSMContext) -> None:
        if not callback.message or not callback.from_user:
            await callback.answer()
            return

        user_id = callback.from_user.id
        lang = common.db.get_user_language(user_id) if common.db else "ru"

        await callback.message.answer(get_text(lang, "cart_payment_canceled"))
        await state.clear()
        await callback.answer()

    @router.message(OrderDelivery.payment_proof, IsCartOrderFilter())
    async def cart_payment_proof_invalid(message: types.Message, state: FSMContext) -> None:
        if not common.db or not message.from_user:
            return

        lang = common.db.get_user_language(message.from_user.id)
        await message.answer(get_text(lang, "cart_payment_photo_required"))
