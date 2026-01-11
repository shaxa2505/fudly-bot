from __future__ import annotations

from aiogram import F, Router, types
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder

from localization import get_text
from handlers.common.utils import is_cart_button

from .common import esc
from . import common
from .storage import cart_storage


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
    lines: list[str] = [f"🛒 <b>{get_text(lang, 'cart_title')}</b>\n"]

    total = 0
    for i, item in enumerate(items, 1):
        price_sums = int(item.price)
        subtotal = price_sums * item.quantity
        total += subtotal
        lines.append(f"\n<b>{i}. {esc(item.title)}</b>")
        lines.append(
            f"   {item.quantity} x {price_sums:,} = <b>{subtotal:,}</b> {currency}"
        )
        lines.append(f"   🏪 {esc(item.store_name)}")

    lines.append("\n" + "-" * 25)
    lines.append(f"💰 <b>{get_text(lang, 'cart_total_label')}: {total:,} {currency}</b>")

    delivery_enabled = any(item.delivery_enabled for item in items)
    delivery_price = max(
        (item.delivery_price for item in items if item.delivery_enabled), default=0
    )

    if delivery_enabled:
        lines.append(
            f"\n🚚 {get_text(lang, 'cart_delivery_label')}: +{delivery_price:,} {currency}"
        )
        grand_total = total + delivery_price
        lines.append(
            f"🧾 <b>{get_text(lang, 'cart_grand_total_label')}: {grand_total:,} {currency}</b>"
        )

    text = "\n".join(lines)

    kb = InlineKeyboardBuilder()

    for i, item in enumerate(items, 1):
        title_short = item.title[:25] + "..." if len(item.title) > 25 else item.title
        kb.button(text=f"{i}. {title_short} ({item.quantity})", callback_data="cart_noop")
        kb.button(text="❌", callback_data=f"cart_remove_{item.offer_id}")

    kb.button(
        text=get_text(lang, "cart_pickup_button"),
        callback_data="cart_confirm_pickup",
    )
    if delivery_enabled:
        delivery_suffix = f" (+{delivery_price:,})" if delivery_price else ""
        kb.button(
            text=f"{get_text(lang, 'cart_delivery_button')}{delivery_suffix}",
            callback_data="cart_confirm_delivery",
        )

    kb.button(
        text=get_text(lang, "cart_clear_button"),
        callback_data="cart_clear",
    )

    num_items = len(items)
    adjust_pattern = [2] * num_items
    if delivery_enabled:
        adjust_pattern.extend([2, 1])
    else:
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

        if item.quantity >= item.max_quantity:
            await callback.answer(
                f"⚠ Максимум: {item.max_quantity}"
                if lang == "ru"
                else f"⚠ Maksimal: {item.max_quantity}",
                show_alert=True,
            )
            return

        cart_storage.update_quantity(user_id, offer_id, item.quantity + 1)
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

        if item.quantity <= 1:
            cart_storage.remove_item(user_id, offer_id)
        else:
            cart_storage.update_quantity(user_id, offer_id, item.quantity - 1)

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
