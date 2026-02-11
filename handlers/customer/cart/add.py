from __future__ import annotations

from aiogram import F, Router, types
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder

from localization import get_text
from app.core.units import (
    calc_total_price,
    format_quantity,
    normalize_unit,
    parse_quantity_input,
    unit_label,
)
from handlers.common.states import CartAdd

from . import common
from .common import esc
from .storage import cart_storage



def build_cart_add_card_text(
    lang: str,
    title: str,
    price: float,
    quantity: float,
    store_name: str,
    max_qty: float,
    original_price: float = 0,
    description: str = "",
    expiry_date: str = "",
    store_address: str = "",
    unit: str = "piece",
) -> str:
    currency = "so'm" if lang == "uz" else "сум"
    safe_title = esc(title)
    safe_description = esc(description)
    safe_store = esc(store_name)
    safe_address = esc(store_address)
    unit_type = normalize_unit(unit)
    unit_text = unit_label(unit_type, lang)

    text_parts: list[str] = [f"<b>{safe_title}</b>"]

    if description:
        text_parts.append(f"<i>{safe_description}</i>")

    text_parts.append("")

    if original_price and original_price > price:
        discount_pct = int(((original_price - price) / original_price) * 100)
        text_parts.append(
            f"{get_text(lang, 'cart_add_price_label')}: <s>{original_price:,.0f}</s> -> "
            f"<b>{price:,.0f} {currency}</b> / {unit_text} <code>(-{discount_pct}%)</code>"
        )
    else:
        text_parts.append(
            f"{get_text(lang, 'cart_add_price_label')}: <b>{price:,.0f} {currency}</b> / {unit_text}"
        )

    text_parts.append(
        f"{get_text(lang, 'cart_add_quantity_label')}: <b>{format_quantity(quantity, unit_type, lang)} {unit_text}</b>"
    )

    stock_label = get_text(lang, 'cart_add_stock_label')
    qty_text = format_quantity(max_qty, unit_type, lang)
    if unit_type == "piece":
        text_parts.append(f"{stock_label}: {qty_text} {unit_text}")
    else:
        upto = get_text(lang, "catalog_pickup_until_short")
        text_parts.append(f"{stock_label}: {upto} {qty_text} {unit_text}")

    if expiry_date:
        expiry_label = get_text(lang, 'cart_add_expiry_label')
        text_parts.append(f"{expiry_label}: {esc(expiry_date)}")

    text_parts.append("")

    store_label = "Магазин" if lang == "ru" else "Do'kon"
    text_parts.append(f"{store_label}: <b>{safe_store}</b>")
    if store_address:
        address_label = get_text(lang, 'cart_delivery_address_label')
        text_parts.append(f"{address_label}: {safe_address}")

    text_parts.append("")

    total = calc_total_price(price, quantity)
    text_parts.append(
        f"<b>{get_text(lang, 'cart_add_total_label')}: {total:,.0f} {currency}</b>"
    )

    return "\n".join(text_parts)

def build_cart_add_card_keyboard(
    lang: str, offer_id: int, quantity: float, max_qty: float, unit: str
) -> InlineKeyboardBuilder:
    unit_type = normalize_unit(unit)
    if unit_type == "piece":
        return _build_cart_add_piece_keyboard(lang, offer_id, int(quantity), int(max_qty))
    return _build_cart_add_weight_keyboard(lang, offer_id, float(quantity), float(max_qty), unit_type)


def _build_cart_add_piece_keyboard(
    lang: str, offer_id: int, quantity: int, max_qty: int
) -> InlineKeyboardBuilder:
    kb = InlineKeyboardBuilder()

    minus_btn = "−"
    plus_btn = "+"

    kb.button(
        text=minus_btn,
        callback_data=f"cart_qty_{offer_id}_{quantity - 1}" if quantity > 1 else "cart_noop",
    )
    kb.button(text=str(quantity), callback_data="cart_noop")
    kb.button(
        text=plus_btn,
        callback_data=f"cart_qty_{offer_id}_{quantity + 1}" if quantity < max_qty else "cart_noop",
    )
    kb.adjust(3)

    kb.button(
        text=get_text(lang, 'cart_add_confirm_button'),
        callback_data=f"cart_add_confirm_{offer_id}",
    )
    kb.button(
        text=get_text(lang, 'cart_add_cancel_button'),
        callback_data=f"cart_add_cancel_{offer_id}",
    )

    kb.adjust(3, 2)

    return kb


def _build_cart_add_weight_keyboard(
    lang: str, offer_id: int, quantity: float, max_qty: float, unit_type: str
) -> InlineKeyboardBuilder:
    kb = InlineKeyboardBuilder()

    unit_text = unit_label(unit_type, lang)
    if unit_type in {"kg", "l"}:
        options = [0.5, 1, 1.5, 2]
    elif unit_type == "g":
        options = [200, 500, 1000]
    else:
        options = [250, 500, 1000]

    for opt in options:
        if opt > max_qty:
            continue
        label = f"{format_quantity(opt, unit_type, lang)} {unit_text}"
        kb.button(text=label, callback_data=f"cart_qty_{offer_id}_{opt}")

    kb.button(
        text="✍️ Другое" if lang == "ru" else "✍️ Boshqa",
        callback_data=f"cart_qty_custom_{offer_id}",
    )
    kb.adjust(2, 2, 1)

    kb.button(
        text=get_text(lang, 'cart_add_confirm_button'),
        callback_data=f"cart_add_confirm_{offer_id}",
    )
    kb.button(
        text=get_text(lang, 'cart_add_cancel_button'),
        callback_data=f"cart_add_cancel_{offer_id}",
    )
    kb.adjust(2)
    return kb


def build_catalog_added_keyboard(lang: str) -> InlineKeyboardBuilder:
    kb = InlineKeyboardBuilder()
    kb.button(text=get_text(lang, "catalog_checkout_cta"), callback_data="view_cart")
    kb.button(text=get_text(lang, "catalog_continue_cta"), callback_data="catalog_continue")
    kb.adjust(1, 1)
    return kb

def register(router: Router) -> None:
    """Register add-to-cart and related handlers on the given router."""

    async def _quick_add_one(callback: types.CallbackQuery, offer_id: int) -> None:
        if not common.db or not callback.message:
            await callback.answer()
            return

        user_id = callback.from_user.id
        lang = common.db.get_user_language(user_id)

        offer = common.db.get_offer(offer_id)
        if not offer:
            await callback.answer(get_text(lang, "offer_not_found"), show_alert=True)
            return

        def get_field(data: object, key: str, default: object = None) -> object:
            if isinstance(data, dict):
                return data.get(key, default)
            return default

        max_qty = float(get_field(offer, "quantity", 0) or 0)
        if max_qty <= 0:
            await callback.answer(get_text(lang, "cart_add_out_of_stock"), show_alert=True)
            return

        price = float(get_field(offer, "discount_price", 0) or 0)
        original_price = float(get_field(offer, "original_price", 0) or 0)
        title = str(get_field(offer, "title", get_text(lang, "offer_not_found")))
        unit = normalize_unit(get_field(offer, "unit", None))
        expiry_date = str(get_field(offer, "expiry_date", "") or "")
        store_id = get_field(offer, "store_id")
        offer_photo = get_field(offer, "photo", None)

        store = common.db.get_store(store_id) if store_id else None
        store_name = str(get_field(store, "name", ""))
        store_address = str(get_field(store, "address", ""))
        delivery_enabled = bool(get_field(store, "delivery_enabled", 0) == 1)
        delivery_price = float(get_field(store, "delivery_price", 0) or 0)

        added = cart_storage.add_item(
            user_id=user_id,
            offer_id=offer_id,
            store_id=store_id,
            title=title,
            price=price,
            quantity=1,
            original_price=original_price,
            max_quantity=max_qty,
            store_name=store_name,
            store_address=store_address,
            photo=offer_photo,
            unit=unit,
            expiry_date=expiry_date,
            delivery_enabled=delivery_enabled,
            delivery_price=delivery_price,
        )
        if not added:
            await callback.answer(get_text(lang, "cart_single_store_only"), show_alert=True)
            return

        short_title = title[:40] + ("..." if len(title) > 40 else "")
        toast = get_text(lang, "catalog_added_to_cart_short", title=short_title)
        await callback.answer(toast, show_alert=False)

    @router.callback_query(F.data.startswith("catalog_add_"))
    async def catalog_add_one(callback: types.CallbackQuery, state: FSMContext) -> None:
        if not common.db or not callback.message or not callback.data:
            await callback.answer()
            return

        user_id = callback.from_user.id
        lang = common.db.get_user_language(user_id)

        try:
            offer_id = int(callback.data.split("_")[-1])
        except (ValueError, IndexError):
            await callback.answer(get_text(lang, "error"), show_alert=True)
            return
        await _quick_add_one(callback, offer_id)

    @router.callback_query(F.data.startswith("add_to_cart:"))
    async def add_to_cart_quick(callback: types.CallbackQuery) -> None:
        if not callback.data:
            await callback.answer()
            return
        try:
            offer_id = int(callback.data.split(":")[-1])
        except (ValueError, IndexError):
            await callback.answer()
            return
        await _quick_add_one(callback, offer_id)

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
            await callback.answer(get_text(lang, "error"), show_alert=True)
            return

        offer = common.db.get_offer(offer_id)
        if not offer:
            await callback.answer(
                get_text(lang, "offer_not_found"),
                show_alert=True,
            )
            return

        def get_field(data: object, key: str, default: object = None) -> object:
            if isinstance(data, dict):
                return data.get(key, default)
            return default

        max_qty = float(get_field(offer, "quantity", 0) or 0)
        if max_qty <= 0:
            await callback.answer(
                get_text(lang, "cart_add_out_of_stock"),
                show_alert=True,
            )
            return

        price = float(get_field(offer, "discount_price", 0) or 0)
        original_price = float(get_field(offer, "original_price", 0) or 0)
        title = str(get_field(offer, "title", get_text(lang, "offer_not_found")))
        description = str(get_field(offer, "description", ""))
        unit = normalize_unit(get_field(offer, "unit", None))
        expiry_date = str(get_field(offer, "expiry_date", "") or "")
        store_id = get_field(offer, "store_id")
        offer_photo = get_field(offer, "photo", None)

        store = common.db.get_store(store_id) if store_id else None
        store_name = str(get_field(store, "name", ""))
        store_address = str(get_field(store, "address", ""))
        delivery_enabled = bool(get_field(store, "delivery_enabled", 0) == 1)
        delivery_price = float(get_field(store, "delivery_price", 0) or 0)

        if unit in {"kg", "l"}:
            initial_qty = min(max_qty, 0.5)
        elif unit == "g":
            initial_qty = min(max_qty, 200)
        elif unit == "ml":
            initial_qty = min(max_qty, 250)
        else:
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
            cart_message_id=callback.message.message_id if callback.message else None,
            cart_chat_id=callback.message.chat.id if callback.message and callback.message.chat else None,
            cart_message_has_photo=bool(getattr(callback.message, "photo", None)),
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

        kb = build_cart_add_card_keyboard(lang, offer_id, initial_qty, max_qty, unit)

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
            await callback.answer(get_text(lang, "error"), show_alert=True)

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
            new_qty_raw = parts[3]
        except (ValueError, IndexError):
            await callback.answer(get_text(lang, "error"), show_alert=True)
            return

        data = await state.get_data()
        max_qty = float(data.get("max_quantity", 1))
        unit = data.get("offer_unit", "piece")

        try:
            new_qty = float(parse_quantity_input(new_qty_raw, unit))
        except ValueError:
            await callback.answer(get_text(lang, "error"), show_alert=True)
            return

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

        kb = build_cart_add_card_keyboard(
            lang, offer_id, new_qty, max_qty, str(data.get("offer_unit", "piece"))
        )

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

    @router.callback_query(F.data.startswith("cart_qty_custom_"))
    async def cart_custom_quantity(callback: types.CallbackQuery, state: FSMContext) -> None:
        if not common.db or not callback.message:
            await callback.answer()
            return

        user_id = callback.from_user.id
        lang = common.db.get_user_language(user_id)
        data = await state.get_data()
        unit = data.get("offer_unit", "piece")

        if unit in {"kg", "g"}:
            prompt = get_text(lang, "cart_weight_custom_prompt")
        elif unit in {"l", "ml"}:
            prompt = get_text(lang, "cart_volume_custom_prompt")
        else:
            prompt = get_text(lang, "offer_step3_quantity_custom")

        await state.set_state(CartAdd.quantity)
        await callback.message.answer(prompt)
        await callback.answer()

    @router.message(CartAdd.quantity, F.text)
    async def cart_custom_quantity_entered(message: types.Message, state: FSMContext) -> None:
        if not common.db or not message.from_user:
            return

        user_id = message.from_user.id
        lang = common.db.get_user_language(user_id)
        data = await state.get_data()
        unit = data.get("offer_unit", "piece")
        max_qty = float(data.get("max_quantity", 1))

        try:
            qty_val = parse_quantity_input(message.text, unit)
            new_qty = float(qty_val)
        except ValueError:
            await message.answer(get_text(lang, "cart_weight_invalid"))
            return

        if new_qty <= 0 or new_qty > max_qty:
            await message.answer(
                get_text(lang, "offer_error_quantity_range").format(max=max_qty)
            )
            return

        await state.update_data(selected_qty=new_qty)
        await state.set_state(None)

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
        kb = build_cart_add_card_keyboard(
            lang, int(data.get("offer_id") or 0), new_qty, max_qty, str(unit)
        )

        chat_id = data.get("cart_chat_id")
        message_id = data.get("cart_message_id")
        has_photo = bool(data.get("cart_message_has_photo"))
        if chat_id and message_id:
            try:
                if has_photo:
                    await message.bot.edit_message_caption(
                        chat_id=chat_id,
                        message_id=message_id,
                        caption=text,
                        parse_mode="HTML",
                        reply_markup=kb.as_markup(),
                    )
                else:
                    await message.bot.edit_message_text(
                        text,
                        chat_id=chat_id,
                        message_id=message_id,
                        parse_mode="HTML",
                        reply_markup=kb.as_markup(),
                    )
            except Exception:
                await message.answer(text, parse_mode="HTML", reply_markup=kb.as_markup())
        else:
            await message.answer(text, parse_mode="HTML", reply_markup=kb.as_markup())

        try:
            await message.delete()
        except Exception:
            pass

    @router.callback_query(F.data.startswith("cart_add_confirm_"))
    async def cart_add_confirm(callback: types.CallbackQuery, state: FSMContext) -> None:
        if not common.db or not callback.message:
            await callback.answer()
            return

        user_id = callback.from_user.id
        lang = common.db.get_user_language(user_id)

        data = await state.get_data()

        offer_id = int(data.get("offer_id")) if data.get("offer_id") is not None else None
        quantity = float(data.get("selected_qty", 1))
        store_id = data.get("store_id")
        offer_title = str(data.get("offer_title", ""))
        offer_price = float(data.get("offer_price", 0) or 0)
        original_price = float(data.get("original_price", 0) or 0)
        max_qty = float(data.get("max_quantity", 1))
        store_name = str(data.get("store_name", ""))
        store_address = str(data.get("store_address", ""))
        description = str(data.get("offer_description", ""))
        delivery_enabled = bool(data.get("delivery_enabled", False))
        delivery_price = float(data.get("delivery_price", 0) or 0)
        offer_photo = data.get("offer_photo")
        offer_unit = str(data.get("offer_unit", "piece"))
        expiry_date = str(data.get("expiry_date", ""))

        # Enforce single-store cart at add time
        existing_stores = cart_storage.get_cart_stores(user_id)
        if existing_stores and store_id is not None and store_id not in existing_stores:
            await callback.answer(get_text(lang, "cart_single_store_only"), show_alert=True)
            return

        added = cart_storage.add_item(
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
        if not added:
            await callback.answer(get_text(lang, "cart_single_store_only"), show_alert=True)
            return

        cart_count = cart_storage.get_cart_count(user_id)

        popup_text = get_text(lang, "cart_add_popup", count=cart_count)
        await callback.answer(popup_text, show_alert=False)

        source = str(data.get("source", ""))

        if source in {"hot", "search"}:
            from app.keyboards.offers import offer_in_cart_keyboard

            text = build_cart_add_card_text(
                lang,
                offer_title,
                offer_price,
                quantity,
                store_name,
                max_qty,
                original_price=original_price,
                description=description,
                expiry_date=expiry_date,
                store_address=store_address,
                unit=offer_unit,
            )

            hint_key = "cart_add_hint_hot" if source == "hot" else "cart_add_hint_search"
            text += "\n\n" + get_text(lang, hint_key)

            kb = offer_in_cart_keyboard(lang, source)

            try:
                if callback.message.photo:
                    await callback.message.edit_caption(
                        caption=text,
                        parse_mode="HTML",
                        reply_markup=kb,
                    )
                else:
                    await callback.message.edit_text(
                        text,
                        parse_mode="HTML",
                        reply_markup=kb,
                    )
            except Exception:
                pass
            return

        if store_id is not None:
            try:
                await _show_store_offers(callback, state, int(store_id), lang)
            except Exception:
                pass

        await state.clear()

    @router.callback_query(F.data.startswith("cart_add_cancel_"))
    async def cart_add_cancel(callback: types.CallbackQuery, state: FSMContext) -> None:
        if not callback.message:
            await callback.answer()
            return

        user_id = callback.from_user.id
        lang = common.db.get_user_language(user_id) if common.db else "ru"

        data = await state.get_data()
        store_id = data.get("store_id")

        await state.clear()

        if store_id is not None:
            try:
                await _show_store_offers(callback, state, int(store_id), lang)
            except Exception:
                try:
                    await callback.message.delete()
                except Exception:
                    pass
        else:
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
                get_text(lang, "store_not_found"),
                show_alert=True,
            )
            return

        from handlers.bookings.utils import get_store_field

        store_name = get_store_field(store, "name", get_text(lang, "store_not_found"))

        offers = common.db.get_active_offers(store_id)
        if not offers:
            await callback.answer(
                get_text(lang, "no_offers_in_store"),
                show_alert=True,
            )
            return

        currency = "so'm" if lang == "uz" else "сум"
        stock_label = get_text(lang, "store_offers_stock_label")

        text_lines: list[str] = [f"<b>{esc(store_name)}</b>", "", get_text(lang, "store_offers_list_title")]

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
            title = get_offer_field(offer, "title", get_text(lang, "offer_not_found"))
            price = get_offer_field(offer, "discount_price", 0)
            qty = get_offer_field(offer, "quantity", 0)

            text_lines.append(
                f"{i}. {esc(title)} - {price:,} {currency} ({stock_label}: {qty})"
            )

        text = "\n".join(text_lines)

        kb = InlineKeyboardBuilder()

        for offer in page_offers:
            offer_id = get_offer_field(offer, "id", 0) or get_offer_field(offer, "offer_id", 0)
            title = get_offer_field(offer, "title", get_text(lang, "offer_not_found"))

            kb.button(
                text=f"{title[:30]}{'...' if len(title) > 30 else ''}",
                callback_data=f"view_offer_{offer_id}",
            )

        kb.adjust(1)

        total_offers = len(offers) if isinstance(offers, list) else offers
        total_pages = (total_offers + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE

        if total_pages > 1:
            nav_buttons = []
            if page > 0:
                nav_buttons.append((get_text(lang, "back"), f"store_page_{store_id}_{page - 1}"))
            nav_buttons.append((f"{page + 1}/{total_pages}", "noop"))
            if page < total_pages - 1:
                nav_buttons.append((get_text(lang, "next_page"), f"store_page_{store_id}_{page + 1}"))

            for btn_text, btn_data in nav_buttons:
                kb.button(text=btn_text, callback_data=btn_data)
            kb.adjust(1, *([len(nav_buttons)] if len(nav_buttons) > 1 else [1]))

        cart_count = cart_storage.get_cart_count(user_id)
        if cart_count > 0:
            kb.button(
                text=f"{get_text(lang, 'my_cart')} ({cart_count})",
                callback_data="view_cart",
            )
            kb.adjust(1)

        kb.button(
            text=get_text(lang, "back"),
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
