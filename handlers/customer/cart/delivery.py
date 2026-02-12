from __future__ import annotations

import os

from aiogram import F, Router, types
from aiogram.filters import BaseFilter
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.core.geocoding import reverse_geocode_store
from handlers.common.states import OrderDelivery
from localization import get_text

from .common import esc
from . import common
from app.core.order_math import calc_items_total

try:
    from logging_config import logger
except ImportError:
    import logging

    logger = logging.getLogger(__name__)


class IsCartOrder(BaseFilter):
    """Filter messages for which current FSM data indicates cart delivery flow."""

    async def __call__(self, message: types.Message, state: FSMContext) -> bool:  # type: ignore[override]
        data = await state.get_data()
        return bool(data.get("is_cart_order"))


def location_request_keyboard(lang: str) -> types.ReplyKeyboardMarkup:
    """Keyboard for requesting delivery geolocation."""
    location_text = get_text(lang, "cart_delivery_location_button")
    return types.ReplyKeyboardMarkup(
        keyboard=[
            [types.KeyboardButton(text=location_text, request_location=True)],
        ],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


def _delivery_cash_enabled() -> bool:
    return os.getenv("FUDLY_DELIVERY_CASH_ENABLED", "0").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


async def _remove_location_keyboard(message: types.Message, lang: str) -> None:
    """Replace location request keyboard with the main menu."""
    try:
        from app.keyboards import main_menu_customer
        from .storage import cart_storage

        user_id = message.from_user.id if message.from_user else 0
        cart_count = cart_storage.get_cart_count(user_id) if user_id else 0
        await message.answer(
            get_text(lang, "cart_delivery_keyboard_removed"),
            reply_markup=main_menu_customer(lang, cart_count),
        )
    except Exception:
        pass


async def _send_cart_payment_selection(
    message: types.Message,
    state: FSMContext,
    lang: str,
    delivery_address: str,
) -> None:
    data = await state.get_data()
    cart_items_stored = data.get("cart_items", [])
    store_id = data.get("store_id")
    delivery_price = data.get("delivery_price", 0)

    if not cart_items_stored or not store_id:
        await message.answer(get_text(lang, "cart_delivery_data_lost"))
        await state.clear()
        return

    await _remove_location_keyboard(message, lang)
    await state.update_data(address=delivery_address)
    await state.set_state(OrderDelivery.payment_method_select)

    currency = "so'm" if lang == "uz" else "сум"
    total = calc_items_total(cart_items_stored)

    lines: list[str] = [f"<b>{get_text(lang, 'cart_delivery_products_title')}:</b>"]
    for item in cart_items_stored:
        subtotal = item["price"] * item["quantity"]
        lines.append(f"- {esc(item['title'])} x {item['quantity']} = {subtotal:,} {currency}")

    lines.append("")
    lines.append(f"<b>{get_text(lang, 'cart_grand_total_label')}: {total:,} {currency}</b>")
    if delivery_price:
        delivery_note = get_text(lang, "delivery_fee_paid_to_courier")
        if delivery_note and delivery_note != "delivery_fee_paid_to_courier":
            lines.append(f"<i>{delivery_note}</i>")
    lines.append("")
    lines.append(f"{get_text(lang, 'cart_delivery_address_label')}: {esc(delivery_address)}")
    lines.append("")
    lines.append(get_text(lang, "cart_delivery_payment_prompt"))

    text = "\n".join(lines)

    kb = InlineKeyboardBuilder()
    cash_enabled = _delivery_cash_enabled()
    if cash_enabled:
        kb.button(
            text=get_text(lang, "cart_delivery_payment_cash"),
            callback_data="cart_pay_cash",
        )
    kb.button(
        text=get_text(lang, "cart_delivery_payment_click"),
        callback_data="cart_pay_click",
    )
    kb.button(
        text=get_text(lang, "cart_delivery_back_button"),
        callback_data="cart_back_to_address",
    )
    if cash_enabled:
        kb.adjust(1, 1, 1)
    else:
        kb.adjust(1, 1)

    await message.answer(text, parse_mode="HTML", reply_markup=kb.as_markup())


def register(router: Router) -> None:
    """Register delivery-related handlers for cart orders."""

    @router.callback_query(F.data == "cart_confirm_delivery")
    async def cart_confirm_delivery(callback: types.CallbackQuery, state: FSMContext) -> None:
        if not common.db or not callback.message:
            await callback.answer()
            return

        user_id = callback.from_user.id
        lang = common.db.get_user_language(user_id)
        updates, changed = common.refresh_cart_items(user_id, lang)
        if updates:
            warning_text = get_text(lang, "cart_updated_notice") + "\n" + "\n".join(updates)
            await callback.message.answer(warning_text, parse_mode="HTML")
        if changed:
            from .view import show_cart

            await show_cart(callback, state, is_callback=True)
            await callback.answer()
            return

        from .storage import cart_storage

        items = cart_storage.get_cart(user_id)
        if not items:
            await callback.answer(get_text(lang, "cart_empty_alert"), show_alert=True)
            return

        store_id = items[0].store_id
        delivery_enabled = any(item.delivery_enabled for item in items)
        if not delivery_enabled:
            await callback.answer(get_text(lang, "cart_delivery_unavailable"), show_alert=True)
            return
        delivery_price = max(
            (item.delivery_price for item in items if item.delivery_enabled), default=0
        )

        total = calc_items_total(
            [{"price": item.price, "quantity": item.quantity} for item in items]
        )

        store = common.db.get_store(store_id)
        if store:
            from handlers.bookings.utils import get_store_field

            min_order_amount = get_store_field(store, "min_order_amount", 0)

            if min_order_amount > 0 and total < min_order_amount:
                currency = "so'm" if lang == "uz" else "сум"
                msg = get_text(
                    lang,
                    "cart_delivery_min_order",
                    min=f"{min_order_amount:,}",
                    total=f"{total:,}",
                    currency=currency,
                )
                await callback.answer(msg, show_alert=True)
                return

        cart_items_dict = [
            {
                "offer_id": item.offer_id,
                "store_id": item.store_id,
                "title": item.title,
                "price": item.price,
                "original_price": item.original_price,
                "quantity": item.quantity,
                "unit": item.unit,
                "store_name": item.store_name,
            }
            for item in items
        ]
        await state.update_data(
            cart_items=cart_items_dict,
            store_id=store_id,
            delivery_price=delivery_price,
            is_cart_order=True,
            delivery_lat=None,
            delivery_lon=None,
        )

        await state.set_state(OrderDelivery.address)

        text = get_text(lang, "cart_delivery_address_prompt")
        kb = InlineKeyboardBuilder()
        kb.button(text=get_text(lang, "cart_delivery_back_button"), callback_data="back_to_cart")

        try:
            await callback.message.edit_text(text, parse_mode="HTML", reply_markup=kb.as_markup())
        except Exception:
            await callback.message.answer(text, parse_mode="HTML", reply_markup=kb.as_markup())

        location_prompt = get_text(lang, "cart_delivery_location_prompt")
        await callback.message.answer(
            location_prompt,
            reply_markup=location_request_keyboard(lang),
        )

        await callback.answer()

    @router.message(OrderDelivery.address, IsCartOrder(), F.location)
    async def cart_process_delivery_location(message: types.Message, state: FSMContext) -> None:
        if not common.db or not message.from_user or not message.location:
            return

        lang = common.db.get_user_language(message.from_user.id)
        latitude = message.location.latitude
        longitude = message.location.longitude

        await state.update_data(delivery_lat=latitude, delivery_lon=longitude)

        delivery_address = None
        try:
            geo = await reverse_geocode_store(latitude, longitude)
            if geo:
                delivery_address = geo.get("display_name")
        except Exception as e:
            logger.warning("Cart delivery reverse geocode failed: %s", e)

        if delivery_address:
            await _send_cart_payment_selection(message, state, lang, str(delivery_address))
            return

        await message.answer(
            get_text(lang, "cart_delivery_location_received"),
            reply_markup=location_request_keyboard(lang),
        )

    @router.message(OrderDelivery.address, IsCartOrder(), F.text)
    async def cart_process_delivery_address(message: types.Message, state: FSMContext) -> None:
        if not common.db or not message.from_user or not message.text:
            return

        user_id = message.from_user.id
        lang = common.db.get_user_language(user_id)
        delivery_address = message.text.strip()

        data = await state.get_data()

        cart_items_stored = data.get("cart_items", [])
        store_id = data.get("store_id")
        delivery_lat = data.get("delivery_lat")
        delivery_lon = data.get("delivery_lon")

        if not cart_items_stored or not store_id:
            await message.answer(get_text(lang, "cart_delivery_data_lost"))
            await state.clear()
            return

        if len(delivery_address) < 10 and not (delivery_lat and delivery_lon):
            await message.answer(get_text(lang, "cart_delivery_address_too_short"))
            return

        await _send_cart_payment_selection(message, state, lang, delivery_address)

    @router.callback_query(F.data == "cart_back_to_address")
    async def cart_back_to_address(callback: types.CallbackQuery, state: FSMContext) -> None:
        if not common.db or not callback.message:
            await callback.answer()
            return

        user_id = callback.from_user.id
        lang = common.db.get_user_language(user_id)

        text = get_text(lang, "cart_delivery_address_prompt")
        kb = InlineKeyboardBuilder()
        kb.button(text=get_text(lang, "cart_delivery_back_button"), callback_data="back_to_cart")

        try:
            await callback.message.edit_text(text, parse_mode="HTML", reply_markup=kb.as_markup())
        except Exception:
            await callback.message.answer(text, parse_mode="HTML", reply_markup=kb.as_markup())

        location_prompt = get_text(lang, "cart_delivery_location_prompt")
        await callback.message.answer(
            location_prompt,
            reply_markup=location_request_keyboard(lang),
        )

        await state.set_state(OrderDelivery.address)
        await callback.answer()
