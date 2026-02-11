from __future__ import annotations

from aiogram import F, Router, types
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder

from localization import get_text
from app.keyboards import main_menu_customer
from handlers.common.utils import is_cart_button

from .common import esc
from . import common
from .storage import cart_storage
from app.core.order_math import calc_items_total
from app.core.units import calc_total_price, format_quantity, normalize_unit, unit_label


async def _build_cart_view(user_id: int) -> tuple[str, InlineKeyboardBuilder] | None:
    """Build cart text and keyboard for given user_id.

    Returns None if dependencies are missing or cart is empty.
    """
    if not common.db:
        return None

    lang = common.db.get_user_language(user_id)
    items = cart_storage.get_cart(user_id)

    if not items:
        empty_text = get_text(lang, "cart_empty")
        kb = InlineKeyboardBuilder()
        kb.button(
            text=get_text(lang, "cart_empty_cta"),
            callback_data="hot_offers",
        )
        return empty_text, kb

    currency = "so'm" if lang == "uz" else "сум"
    store_label = get_text(lang, "cart_store_label")
    remove_label = get_text(lang, "cart_remove_button")
    lines: list[str] = [get_text(lang, "cart_title"), ""]

    cart_items = []
    for i, item in enumerate(items, 1):
        cart_items.append({"price": item.price, "quantity": item.quantity})
        price_sums = int(item.price)
        subtotal = calc_total_price(price_sums, item.quantity)
        lines.append(f"\n<b>{i}. {esc(item.title)}</b>")
        unit_type = normalize_unit(item.unit)
        unit_text = unit_label(unit_type, lang)
        qty_text = format_quantity(item.quantity, unit_type, lang)
        lines.append(
            f"   {qty_text} {unit_text} x {price_sums:,} = <b>{subtotal:,}</b> {currency}"
        )
        lines.append(f"   {store_label}: {esc(item.store_name)}")

    total = calc_items_total(cart_items)
    lines.append("\n" + "-" * 25)
    lines.append(f"<b>{get_text(lang, 'cart_total_label')}: {total:,} {currency}</b>")

    text = "\n".join(lines)

    kb = InlineKeyboardBuilder()

    for i, item in enumerate(items, 1):
        title_short = item.title[:18] + "..." if len(item.title) > 18 else item.title
        qty_label = format_quantity(item.quantity, normalize_unit(item.unit), lang)
        kb.button(text="-", callback_data=f"cart_qty_dec_{item.offer_id}")
        kb.button(text=f"{i}. {title_short} ({qty_label})", callback_data="cart_noop")
        kb.button(text="+", callback_data=f"cart_qty_inc_{item.offer_id}")
        kb.button(text=remove_label, callback_data=f"cart_remove_{item.offer_id}")

    kb.button(
        text=get_text(lang, "cart_checkout_button"),
        callback_data="cart_checkout",
    )
    kb.button(
        text=get_text(lang, "cart_empty_cta"),
        callback_data="hot_offers",
    )
    num_items = len(items)
    adjust_pattern = [4] * num_items
    adjust_pattern.extend([1, 1])

    kb.adjust(*adjust_pattern)

    return text, kb


async def show_cart(
    event: types.Message | types.CallbackQuery,
    state: FSMContext,
    is_callback: bool = False,
) -> None:
    """Public helper to display the current cart.

    Used both by local handlers and external modules
    (e.g. registration flow and customer features).
    """
    if not common.db or not event.from_user:
        if is_callback and isinstance(event, types.CallbackQuery):
            await event.answer()
        return

    await state.clear()

    result = await _build_cart_view(event.from_user.id)
    if not result:
        if is_callback and isinstance(event, types.CallbackQuery):
            await event.answer()
        return

    text, kb = result

    if is_callback and isinstance(event, types.CallbackQuery):
        try:
            await event.message.edit_text(text, parse_mode="HTML", reply_markup=kb.as_markup())
        except Exception:
            await event.message.answer(text, parse_mode="HTML", reply_markup=kb.as_markup())
        await event.answer()
    else:
        await event.answer(text, parse_mode="HTML", reply_markup=kb.as_markup())


def register(router: Router) -> None:
    """Register cart view and editing handlers on the given router."""

    @router.message(F.text.func(is_cart_button))
    async def show_cart_message(message: types.Message, state: FSMContext) -> None:
        await show_cart(message, state, is_callback=False)

    @router.callback_query(F.data == "back_to_cart")
    async def back_to_cart(callback: types.CallbackQuery, state: FSMContext) -> None:
        if not callback.message or not callback.from_user:
            await callback.answer()
            return
        try:
            lang = common.db.get_user_language(callback.from_user.id)
            cart_count = cart_storage.get_cart_count(callback.from_user.id)
            await callback.message.answer(
                get_text(lang, "cart_delivery_keyboard_removed"),
                reply_markup=main_menu_customer(lang, cart_count),
            )
        except Exception:
            pass
        await show_cart(callback, state, is_callback=True)

    @router.callback_query(F.data.startswith("cart_qty_inc_"))
    async def cart_quantity_increase(callback: types.CallbackQuery, state: FSMContext) -> None:
        if not common.db or not callback.message:
            await callback.answer()
            return

        user_id = callback.from_user.id
        lang = common.db.get_user_language(user_id)

        try:
            offer_id = int(callback.data.split("_")[-1])
        except (ValueError, IndexError):
            await callback.answer(get_text(lang, "error"), show_alert=True)
            return

        items = cart_storage.get_cart(user_id)
        item = next((i for i in items if i.offer_id == offer_id), None)

        if not item:
            await callback.answer(get_text(lang, "offer_not_found"), show_alert=True)
            return

        unit_type = normalize_unit(item.unit)
        if unit_type != "piece":
            await callback.answer(get_text(lang, "cart_weight_edit_disabled"), show_alert=True)
            return

        if item.quantity >= item.max_quantity:
            await callback.answer(
                get_text(lang, "cart_max_quantity_alert", max=item.max_quantity),
                show_alert=True,
            )
            return

        cart_storage.update_quantity(user_id, offer_id, int(item.quantity) + 1)
        await show_cart(callback, state, is_callback=True)

    @router.callback_query(F.data.startswith("cart_qty_dec_"))
    async def cart_quantity_decrease(callback: types.CallbackQuery, state: FSMContext) -> None:
        if not common.db or not callback.message:
            await callback.answer()
            return

        user_id = callback.from_user.id
        lang = common.db.get_user_language(user_id)

        try:
            offer_id = int(callback.data.split("_")[-1])
        except (ValueError, IndexError):
            await callback.answer(get_text(lang, "error"), show_alert=True)
            return

        items = cart_storage.get_cart(user_id)
        item = next((i for i in items if i.offer_id == offer_id), None)

        if not item:
            await callback.answer(get_text(lang, "offer_not_found"), show_alert=True)
            return

        unit_type = normalize_unit(item.unit)
        if unit_type != "piece":
            await callback.answer(get_text(lang, "cart_weight_edit_disabled"), show_alert=True)
            return

        if item.quantity <= 1:
            cart_storage.remove_item(user_id, offer_id)
        else:
            cart_storage.update_quantity(user_id, offer_id, int(item.quantity) - 1)

        await show_cart(callback, state, is_callback=True)

    @router.callback_query(F.data.startswith("cart_remove_"))
    async def cart_remove_item(callback: types.CallbackQuery, state: FSMContext) -> None:
        if not common.db or not callback.message:
            await callback.answer()
            return

        user_id = callback.from_user.id
        lang = common.db.get_user_language(user_id)

        try:
            offer_id = int(callback.data.split("_")[-1])
        except (ValueError, IndexError):
            await callback.answer(get_text(lang, "error"), show_alert=True)
            return

        cart_storage.remove_item(user_id, offer_id)
        await show_cart(callback, state, is_callback=True)

    @router.callback_query(F.data == "view_cart")
    async def view_cart_callback(callback: types.CallbackQuery, state: FSMContext) -> None:
        if not callback.message or not callback.from_user:
            await callback.answer()
            return
        await show_cart(callback, state, is_callback=True)
