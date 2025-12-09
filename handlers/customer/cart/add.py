"""Add-to-cart flow: quantity selection and confirmation."""
from __future__ import annotations

from aiogram import F, Router, types
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder

from .common import esc
from . import common
from .storage import cart_storage


def build_cart_add_card_text(
    lang: str,
    title: str,
    price: float,
    quantity: int,
    store_name: str,
    max_qty: int,
    original_price: float = 0,
    description: str = "",
    expiry_date: str = "",
    store_address: str = "",
    unit: str = "шт",
) -> str:
    text_parts: list[str] = []

    text_parts.append(f"🍱 <b>{title}</b>")
    if description:
        text_parts.append(f"<i>{description}</i>")

    text_parts.append("")

    if original_price and original_price > price:
        discount_pct = int(((original_price - price) / original_price) * 100)
        text_parts.append(
            f"<s>{original_price:,.0f}</s> → <b>{price:,.0f} сум</b> <code>(-{discount_pct}%)</code>"
        )
    else:
        text_parts.append(f"💰 <b>{price:,.0f} сум</b>")

    text_parts.append(
        (
            f"📦 Количество: <b>{quantity} {unit}</b>"
            if lang == "ru"
            else f"📦 Miqdor: <b>{quantity} {unit}</b>"
        )
    )

    stock_label = "В наличии" if lang == "ru" else "Omborda"
    text_parts.append(f"📊 {stock_label}: {max_qty} {unit}")

    if expiry_date:
        expiry_label = "Годен до" if lang == "ru" else "Srok"
        text_parts.append(f"📅 {expiry_label}: {expiry_date}")

    text_parts.append("")

    text_parts.append(f"🏪 <b>{store_name}</b>")
    if store_address:
        text_parts.append(f"📍 {store_address}")

    text_parts.append("")

    total = price * quantity
    text_parts.append(
        (
            f"💳 <b>ИТОГО: {total:,.0f} сум</b>"
            if lang == "ru"
            else f"💳 <b>JAMI: {total:,.0f} so'm</b>"
        )
    )

    return "\n".join(text_parts)


def build_cart_add_card_keyboard(
    lang: str, offer_id: int, quantity: int, max_qty: int
) -> InlineKeyboardBuilder:
    kb = InlineKeyboardBuilder()

    minus_btn = "➖" if quantity > 1 else "▫️"
    plus_btn = "➕" if quantity < max_qty else "▫️"

    kb.button(
        text=minus_btn,
        callback_data=f"cart_qty_{offer_id}_{quantity - 1}" if quantity > 1 else "cart_noop",
    )
    kb.button(text=f"📦 {quantity}", callback_data="cart_noop")
    kb.button(
        text=plus_btn,
        callback_data=f"cart_qty_{offer_id}_{quantity + 1}" if quantity < max_qty else "cart_noop",
    )
    kb.adjust(3)

    kb.button(
        text="✅ Добавить в корзину" if lang == "ru" else "✅ Savatga qo'shish",
        callback_data=f"cart_add_confirm_{offer_id}",
    )
    kb.button(
        text="❌ Отмена" if lang == "ru" else "❌ Bekor qilish",
        callback_data=f"cart_add_cancel_{offer_id}",
    )

    kb.adjust(3, 1, 1)

    return kb


def register(router: Router) -> None:
    """Register add-to-cart and related handlers on the given router."""

    @router.callback_query(F.data.startswith("add_to_cart_"))
    async def add_to_cart_start(callback: types.CallbackQuery, state: FSMContext) -> None:
        if not common.db or not callback.message or not callback.data:
            await callback.answer()
            return

        user_id = callback.from_user.id
        lang = common.db.get_user_language(user_id)

        try:
            offer_id = int(callback.data.split("_")[-1])
        except (ValueError, IndexError):
            await callback.answer("❌", show_alert=True)
            return

        offer = common.db.get_offer(offer_id)
        if not offer:
            await callback.answer(
                "Товар не найден" if lang == "ru" else "Mahsulot topilmadi",
                show_alert=True,
            )
            return

        def get_field(data: object, key: str, default: object = None) -> object:
            if isinstance(data, dict):
                return data.get(key, default)
            return default

        max_qty = int(get_field(offer, "quantity", 0) or 0)
        if max_qty <= 0:
            await callback.answer(
                "Товар закончился" if lang == "ru" else "Mahsulot tugadi",
                show_alert=True,
            )
            return

        price = float(get_field(offer, "discount_price", 0) or 0)
        original_price = float(get_field(offer, "original_price", 0) or 0)
        title = str(get_field(offer, "title", "Товар"))
        description = str(get_field(offer, "description", ""))
        unit = str(get_field(offer, "unit", "шт"))
        expiry_date = str(get_field(offer, "expiry_date", "") or "")
        store_id = get_field(offer, "store_id")
        offer_photo = get_field(offer, "photo", None)

        store = common.db.get_store(store_id) if store_id else None
        store_name = str(get_field(store, "name", ""))
        store_address = str(get_field(store, "address", ""))
        delivery_enabled = bool(get_field(store, "delivery_enabled", 0) == 1)
        delivery_price = float(get_field(store, "delivery_price", 0) or 0)

        initial_qty = 1

        await state.update_data(
            offer_id=offer_id,
            max_quantity=max_qty,
            offer_price=price,
            original_price=original_price,
            offer_title=title,
            offer_description=description,
            offer_unit=unit,
            expiry_date=str(expiry_date) if expiry_date else "",
            store_id=store_id,
            store_name=store_name,
            store_address=store_address,
            delivery_enabled=delivery_enabled,
            delivery_price=delivery_price,
            selected_qty=initial_qty,
            offer_photo=offer_photo,
        )

        text = build_cart_add_card_text(
            lang,
            title,
            price,
            initial_qty,
            store_name,
            max_qty,
            original_price=original_price,
            description=description,
            expiry_date=str(expiry_date) if expiry_date else "",
            store_address=store_address,
            unit=unit,
        )

        kb = build_cart_add_card_keyboard(lang, offer_id, initial_qty, max_qty)

        try:
            if callback.message.photo:
                await callback.message.edit_caption(
                    caption=text, parse_mode="HTML", reply_markup=kb.as_markup()
                )
            else:
                await callback.message.edit_text(
                    text, parse_mode="HTML", reply_markup=kb.as_markup()
                )
            await callback.answer()
        except Exception:
            await callback.answer("❌", show_alert=True)

    @router.callback_query(F.data.startswith("cart_qty_"))
    async def cart_update_quantity(callback: types.CallbackQuery, state: FSMContext) -> None:
        if not common.db or not callback.message:
            await callback.answer()
            return

        user_id = callback.from_user.id
        lang = common.db.get_user_language(user_id)

        try:
            parts = callback.data.split("_")
            offer_id = int(parts[2])
            new_qty = int(parts[3])
        except (ValueError, IndexError):
            await callback.answer("❌", show_alert=True)
            return

        data = await state.get_data()
        max_qty = int(data.get("max_quantity", 1))

        if new_qty < 1 or new_qty > max_qty:
            await callback.answer()
            return

        await state.update_data(selected_qty=new_qty)

        text = build_cart_add_card_text(
            lang,
            str(data.get("offer_title", "")),
            float(data.get("offer_price", 0) or 0),
            new_qty,
            str(data.get("store_name", "")),
            max_qty,
            original_price=float(data.get("original_price", 0) or 0),
            description=str(data.get("offer_description", "")),
            expiry_date=str(data.get("expiry_date", "")),
            store_address=str(data.get("store_address", "")),
            unit=str(data.get("offer_unit", "")),
        )

        kb = build_cart_add_card_keyboard(lang, offer_id, new_qty, max_qty)

        try:
            if callback.message.photo:
                await callback.message.edit_caption(
                    caption=text, parse_mode="HTML", reply_markup=kb.as_markup()
                )
            else:
                await callback.message.edit_text(
                    text, parse_mode="HTML", reply_markup=kb.as_markup()
                )
        except Exception:
            pass

        await callback.answer()

    @router.callback_query(F.data.startswith("cart_add_confirm_"))
    async def cart_add_confirm(callback: types.CallbackQuery, state: FSMContext) -> None:
        if not common.db or not callback.message:
            await callback.answer()
            return

        user_id = callback.from_user.id
        lang = common.db.get_user_language(user_id)

        data = await state.get_data()

        offer_id = int(data.get("offer_id")) if data.get("offer_id") is not None else None
        quantity = int(data.get("selected_qty", 1))
        store_id = data.get("store_id")
        offer_title = str(data.get("offer_title", ""))
        offer_price = float(data.get("offer_price", 0) or 0)
        original_price = float(data.get("original_price", 0) or 0)
        max_qty = int(data.get("max_quantity", 1))
        store_name = str(data.get("store_name", ""))
        store_address = str(data.get("store_address", ""))
        delivery_enabled = bool(data.get("delivery_enabled", False))
        delivery_price = float(data.get("delivery_price", 0) or 0)
        offer_photo = data.get("offer_photo")
        offer_unit = str(data.get("offer_unit", "шт"))
        expiry_date = str(data.get("expiry_date", ""))

        cart_storage.add_item(
            user_id=user_id,
            offer_id=offer_id,
            store_id=store_id,
            title=offer_title,
            price=offer_price,
            quantity=quantity,
            original_price=original_price,
            max_quantity=max_qty,
            store_name=store_name,
            store_address=store_address,
            photo=offer_photo,
            unit=offer_unit,
            expiry_date=expiry_date,
            delivery_enabled=delivery_enabled,
            delivery_price=delivery_price,
        )

        cart_count = cart_storage.get_cart_count(user_id)

        added_text = "Добавлено!" if lang == "ru" else "Qo'shildi!"
        popup_text = (
            f"✅ {added_text} В корзине: {cart_count} шт"
            if lang == "ru"
            else f"✅ {added_text} Savatda: {cart_count} ta"
        )
        await callback.answer(popup_text, show_alert=False)

        # After adding, show the store's offer list again
        if store_id is not None:
            try:
                await _show_store_offers(callback, state, int(store_id), lang)
            except Exception:
                # Fallback: just clear state if showing offers fails
                pass

        await state.clear()

    @router.callback_query(F.data.startswith("cart_add_cancel_"))
    async def cart_add_cancel(callback: types.CallbackQuery, state: FSMContext) -> None:
        if not callback.message:
            await callback.answer()
            return

        await state.clear()

        try:
            await callback.message.delete()
        except Exception:
            pass

        await callback.answer()

    @router.callback_query(F.data == "cart_noop")
    async def cart_noop(callback: types.CallbackQuery) -> None:
        await callback.answer()

    async def _show_store_offers(
        callback: types.CallbackQuery, state: FSMContext, store_id: int, lang: str
    ) -> None:
        """Show offers list for a given store (used after add and from button)."""
        if not common.db or not callback.message:
            await callback.answer()
            return

        user_id = callback.from_user.id

        store = common.db.get_store(store_id)
        if not store:
            await callback.answer(
                "Магазин не найден" if lang == "ru" else "Do'kon topilmadi",
                show_alert=True,
            )
            return

        from handlers.bookings.utils import get_store_field

        store_name = get_store_field(store, "name", "Магазин")

        offers = common.db.get_active_offers(store_id)
        if not offers:
            await callback.answer(
                "Нет доступных товаров" if lang == "ru" else "Mahsulotlar yo'q",
                show_alert=True,
            )
            return

        text_lines: list[str] = []
        text_lines.append(f"🏪 <b>{esc(store_name)}</b>\n")
        text_lines.append(
            f"{'Mahsulotlar:' if lang == 'uz' else 'Товары:'}\n"
        )

        ITEMS_PER_PAGE = 5
        page = 0
        start_idx = page * ITEMS_PER_PAGE
        end_idx = start_idx + ITEMS_PER_PAGE
        page_offers = (
            offers[start_idx:end_idx]
            if isinstance(offers, list)
            else list(offers)[start_idx:end_idx]
        )

        from handlers.bookings.utils import get_offer_field

        for i, offer in enumerate(page_offers, start=start_idx + 1):
            title = get_offer_field(offer, "title", "Товар")
            price = get_offer_field(offer, "discount_price", 0)
            qty = get_offer_field(offer, "quantity", 0)

            text_lines.append(
                f"{i}. {esc(title)} - {price:,} сум (в наличии: {qty})"
            )

        text = "\n".join(text_lines)

        kb = InlineKeyboardBuilder()

        for offer in page_offers:
            offer_id = get_offer_field(offer, "id", 0) or get_offer_field(
                offer, "offer_id", 0
            )
            title = get_offer_field(offer, "title", "Товар")

            kb.button(
                text=f"📦 {title[:30]}{'...' if len(title) > 30 else ''}",
                callback_data=f"view_offer_{offer_id}",
            )

        kb.adjust(1)

        total_offers = len(offers) if isinstance(offers, list) else offers
        total_pages = (total_offers + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE

        if total_pages > 1:
            nav_buttons = []
            if page > 0:
                nav_buttons.append(
                    (
                        "⬅️ Назад" if lang == "ru" else "⬅️ Orqaga",
                        f"store_page_{store_id}_{page - 1}",
                    )
                )
            nav_buttons.append((f"📄 {page + 1}/{total_pages}", "noop"))
            if page < total_pages - 1:
                nav_buttons.append(
                    (
                        "Вперед ▶️" if lang == "ru" else "Oldinga ▶️",
                        f"store_page_{store_id}_{page + 1}",
                    )
                )

            for btn_text, btn_data in nav_buttons:
                kb.button(text=btn_text, callback_data=btn_data)
            kb.adjust(1, *([len(nav_buttons)] if len(nav_buttons) > 1 else [1]))

        cart_count = cart_storage.get_cart_count(user_id)
        if cart_count > 0:
            kb.button(
                text=(
                    f"🛒 Корзина ({cart_count})"
                    if lang == "ru"
                    else f"🛒 Savat ({cart_count})"
                ),
                callback_data="view_cart",
            )
            kb.adjust(1)

        kb.button(
            text="⬅️ Назад" if lang == "ru" else "⬅️ Orqaga",
            callback_data="back_to_menu",
        )

        try:
            await callback.message.edit_text(text, parse_mode="HTML", reply_markup=kb.as_markup())
        except Exception:
            await callback.message.answer(text, parse_mode="HTML", reply_markup=kb.as_markup())

        await callback.answer()

    @router.callback_query(F.data.startswith("continue_shopping_"))
    async def continue_shopping(callback: types.CallbackQuery, state: FSMContext) -> None:
        if not common.db or not callback.message or not callback.data:
            await callback.answer()
            return

        try:
            store_id = int(callback.data.split("_")[-1])
        except (ValueError, IndexError):
            await callback.answer()
            return

        user_id = callback.from_user.id
        lang = common.db.get_user_language(user_id)

        await _show_store_offers(callback, state, store_id, lang)
