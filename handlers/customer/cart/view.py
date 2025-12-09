"""Cart view and editing handlers.

Contains unified `show_cart` helper used by other modules
and all handlers that display or refresh the cart contents.
"""
from __future__ import annotations

from typing import Any

from aiogram import F, Router, types
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder

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
        empty_text = (
            "🛒 Корзина пуста\n\nДобавьте товары из каталога!"
            if lang == "ru"
            else "🛒 Savat bo'sh\n\nKatalogdan mahsulot qo'shing!"
        )
        kb = InlineKeyboardBuilder()
        kb.button(
            text="🔥 Горячие предложения" if lang == "ru" else "🔥 Issiq takliflar",
            callback_data="hot_offers",
        )
        return empty_text, kb

    currency = "so'm" if lang == "uz" else "сум"
    lines: list[str] = [f"🛒 <b>{'Savat' if lang == 'uz' else 'Корзина'}</b>\n"]

    total = 0
    for i, item in enumerate(items, 1):
        subtotal = int(item.price * item.quantity)
        total += subtotal
        lines.append(f"\n<b>{i}. {esc(item.title)}</b>")
        lines.append(
            f"   {item.quantity} × {int(item.price):,} = <b>{subtotal:,}</b> {currency}"
        )
        lines.append(f"   🏪 {esc(item.store_name)}")

    lines.append("\n" + "─" * 25)
    lines.append(f"💵 <b>{'JAMI' if lang == 'uz' else 'ИТОГО'}: {total:,} {currency}</b>")

    # Delivery summary
    delivery_enabled = any(item.delivery_enabled for item in items)
    delivery_price = max(
        (item.delivery_price for item in items if item.delivery_enabled), default=0
    )

    if delivery_enabled:
        lines.append(
            f"\n🚚 {'Yetkazish' if lang == 'uz' else 'Доставка'}: +{delivery_price:,} {currency}"
        )

    text = "\n".join(lines)

    kb = InlineKeyboardBuilder()

    # Item delete buttons (one row per item)
    for i, item in enumerate(items, 1):
        title_short = item.title[:25] + "..." if len(item.title) > 25 else item.title
        kb.button(text=f"{i}. {title_short} ({item.quantity})", callback_data="cart_noop")
        kb.button(text="🗑", callback_data=f"cart_remove_{item.offer_id}")

    # Checkout options - directly on cart screen
    kb.button(
        text="🏪 Самовывоз" if lang == "ru" else "🏪 O'zim olaman",
        callback_data="cart_confirm_pickup",
    )
    if delivery_enabled:
        kb.button(
            text=(
                f"🚚 Доставка (+{delivery_price:,})"
                if lang == "ru"
                else f"🚚 Yetkazish (+{delivery_price:,})"
            ),
            callback_data="cart_confirm_delivery",
        )

    # Clear cart button
    kb.button(
        text="🗑 Очистить" if lang == "ru" else "🗑 Tozalash",
        callback_data="cart_clear",
    )

    # Adjust: 2 buttons per item row + checkout buttons
    num_items = len(items)
    adjust_pattern = [2] * num_items  # 2 buttons per item row
    if delivery_enabled:
        adjust_pattern.extend([2, 1])  # pickup+delivery, then clear
    else:
        adjust_pattern.extend([1, 1])  # just pickup, then clear

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
        # Empty cart case was handled inside _build_cart_view
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

    @router.message(F.text.in_(["🛒 Корзина", "🛒 Savat"]))
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
            await callback.answer(
                "❌ Ошибка" if lang == "ru" else "❌ Xatolik", show_alert=True
            )
            return

        items = cart_storage.get_cart(user_id)
        item = next((i for i in items if i.offer_id == offer_id), None)

        if not item:
            await callback.answer(
                "❌ Товар не найден" if lang == "ru" else "❌ Mahsulot topilmadi",
                show_alert=True,
            )
            return

        if item.quantity >= item.max_quantity:
            await callback.answer(
                (
                    f"⚠️ Максимум: {item.max_quantity}"
                    if lang == "ru"
                    else f"⚠️ Maksimal: {item.max_quantity}"
                ),
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
            await callback.answer(
                "❌ Ошибка" if lang == "ru" else "❌ Xatolik", show_alert=True
            )
            return

        items = cart_storage.get_cart(user_id)
        item = next((i for i in items if i.offer_id == offer_id), None)

        if not item:
            await callback.answer(
                "❌ Товар не найден" if lang == "ru" else "❌ Mahsulot topilmadi",
                show_alert=True,
            )
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
            await callback.answer(
                "❌ Ошибка" if lang == "ru" else "❌ Xatolik", show_alert=True
            )
            return

        cart_storage.remove_item(user_id, offer_id)
        await show_cart(callback, state, is_callback=True)

    @router.callback_query(F.data == "view_cart")
    async def view_cart_callback(callback: types.CallbackQuery, state: FSMContext) -> None:
        if not callback.message or not callback.from_user:
            await callback.answer()
            return
        await show_cart(callback, state, is_callback=True)
