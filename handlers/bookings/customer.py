"""Customer booking handlers - create, view, cancel, rate bookings.

Premium UX v3 - Beautiful booking cards with photos and inline controls.
"""
from __future__ import annotations

import html
from typing import Any

from aiogram import F, Router, types
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.core.constants import OFFERS_PER_PAGE
from app.keyboards import cancel_keyboard, main_menu_customer, phone_request_keyboard
from app.services.unified_order_service import (
    OrderItem,
    OrderStatus,
    get_unified_order_service,
)
from handlers.bookings.utils import format_price
from handlers.common.states import BookOffer, OrderDelivery, Registration
from handlers.common.utils import is_main_menu_button
from localization import get_text
from logging_config import logger

from .utils import (
    calculate_total,
    can_proceed,
    format_booking_code,
    get_booking_field,
    get_offer_field,
    get_store_field,
    get_user_safe,
    safe_answer_or_send,
    safe_edit_reply_markup,
)

router = Router()

# Module dependencies (set via setup_dependencies)
db: Any = None
bot: Any = None
cache: Any = None
METRICS: dict = {}


def setup_dependencies(
    database: Any, bot_instance: Any, cache_manager: Any = None, metrics: dict = None
):
    """Setup module dependencies."""
    global db, bot, cache, METRICS
    db = database
    bot = bot_instance
    cache = cache_manager
    METRICS = metrics or {}


def _esc(val: Any) -> str:
    """HTML-escape helper."""
    if val is None:
        return ""
    return html.escape(str(val))


# ===================== PREMIUM UX v3: Beautiful booking cards =====================
# - New message with photo when booking
# - [−] [qty] [+] quantity controls
# - Radio-style delivery selection
# - Real-time total updates


def build_order_card_text(
    lang: str,
    title: str,
    price: int,
    quantity: int,
    store_name: str,
    delivery_enabled: bool,
    delivery_price: int,
    delivery_method: str | None,
    max_qty: int,
    original_price: int = 0,
    description: str = "",
    expiry_date: str = "",
    store_address: str = "",
    unit: str = "",
) -> str:
    """Build order card in same style as product card."""
    currency = "so'm" if lang == "uz" else "сум"
    unit = unit or ("dona" if lang == "uz" else "шт")

    # Calculate totals
    subtotal = price * quantity
    delivery_cost = delivery_price if delivery_method == "delivery" else 0
    total = subtotal + delivery_cost

    # Header - same as product card
    lines = [f"📦 <b>{_esc(title)}</b>"]

    if description:
        desc = description[:80] + "..." if len(description) > 80 else description
        lines.append(f"<i>{_esc(desc)}</i>")

    lines.append("")
    lines.append("─" * 25)

    # Price with discount - same style as product card
    # Use prices directly from database
    price_sums = int(price)
    original_price_sums = int(original_price) if original_price else 0

    if original_price and original_price > price:
        discount_pct = round((1 - price / original_price) * 100)
        lines.append(
            f"<s>{original_price_sums:,}</s> → <b>{price_sums:,}</b> {currency} (-{discount_pct}%)"
        )
    else:
        lines.append(f"💰 <b>{price_sums:,}</b> {currency}")

    lines.append("─" * 25)
    lines.append("")

    # Quantity selection
    qty_label = "Miqdor" if lang == "uz" else "Количество"
    lines.append(f"📦 {qty_label}: <b>{quantity}</b> {unit}")

    # Expiry date if available
    if expiry_date:
        expiry_label = "Yaroqlilik" if lang == "uz" else "Срок до"
        expiry_str = str(expiry_date)[:10]
        try:
            from datetime import datetime

            dt = datetime.strptime(expiry_str, "%Y-%m-%d")
            expiry_str = dt.strftime("%d.%m.%Y")
        except ValueError:
            logger.debug("Could not parse expiry date: %s", expiry_str)
        lines.append(f"📅 {expiry_label}: {expiry_str}")

    # Store info - same style
    lines.append("")
    lines.append(f"🏪 {_esc(store_name)}")
    if store_address:
        lines.append(f"📍 {_esc(store_address)}")

    # Delivery section - cleaner style with better hint
    if delivery_enabled:
        lines.append("")
        # Show delivery price
        delivery_label = "Yetkazish" if lang == "uz" else "Доставка"
        delivery_price_sums = int(delivery_price) // 100
        lines.append(f"🚚 {delivery_label}: {delivery_price_sums:,} {currency}")

        # Pickup option
        pickup_label = "Olib ketish" if lang == "uz" else "Самовывоз"
        lines.append(
            f"🏪 {pickup_label}: bepul" if lang == "uz" else f"🏪 {pickup_label}: бесплатно"
        )

        # Show selection hint if not selected - clearer text
        if not delivery_method:
            hint = (
                "👇 Yetkazish yoki olib ketish tanlang"
                if lang == "uz"
                else "👇 Выберите доставку или самовывоз"
            )
            lines.append(f"\n<i>{hint}</i>")

    # Totals section
    lines.append("")
    lines.append("─" * 25)
    total_label = "JAMI" if lang == "uz" else "ИТОГО"
    lines.append(f"💵 <b>{total_label}: {total:,} {currency}</b>")
    if delivery_method == "delivery" and delivery_cost > 0:
        incl_delivery = "yetkazish bilan" if lang == "uz" else "с доставкой"
        lines.append(f"   <i>({incl_delivery})</i>")

    return "\n".join(lines)


def build_order_card_keyboard(
    lang: str,
    offer_id: int,
    store_id: int,
    quantity: int,
    max_qty: int,
    delivery_enabled: bool,
    delivery_method: str | None,
) -> InlineKeyboardBuilder:
    """Build order card keyboard with quick quantity buttons and delivery options."""
    kb = InlineKeyboardBuilder()

    # Row 1: Quick quantity buttons [1] [2] [3] [5] or [−][qty][+] for large max
    if max_qty <= 10:
        # Show quick buttons for small quantities
        quick_qtys = [q for q in [1, 2, 3, 5, 10] if q <= max_qty]
        for q in quick_qtys[:4]:  # Max 4 quick buttons
            is_selected = quantity == q
            text = f"✓ {q}" if is_selected else str(q)
            kb.button(text=text, callback_data=f"pbook_qty_{offer_id}_{q}")
    else:
        # Show [−][qty][+] for large quantities
        minus_enabled = quantity > 1
        plus_enabled = quantity < max_qty

        # Use simple ASCII/basic Unicode that works everywhere
        minus_text = "−" if minus_enabled else "▫"
        plus_text = "+" if plus_enabled else "▫"

        kb.button(
            text=minus_text,
            callback_data=f"pbook_qty_{offer_id}_{quantity - 1}" if minus_enabled else "pbook_noop",
        )
        kb.button(text=f"{quantity} шт", callback_data="pbook_noop")
        kb.button(
            text=plus_text,
            callback_data=f"pbook_qty_{offer_id}_{quantity + 1}" if plus_enabled else "pbook_noop",
        )

    # Row 2-3: Delivery options (if enabled)
    if delivery_enabled:
        pickup_text = "🏪 Olib ketish" if lang == "uz" else "🏪 Самовывоз"
        delivery_text = "🚚 Yetkazish" if lang == "uz" else "🚚 Доставка"

        # Add checkmarks for selected option
        if delivery_method == "pickup":
            pickup_text = "✅ " + pickup_text
        elif delivery_method == "delivery":
            delivery_text = "✅ " + delivery_text

        kb.button(text=pickup_text, callback_data=f"pbook_method_{offer_id}_pickup")
        kb.button(text=delivery_text, callback_data=f"pbook_method_{offer_id}_delivery")

    # Row 4: Confirm and Back
    if delivery_method or not delivery_enabled:
        confirm_text = "✅ Tasdiqlash" if lang == "uz" else "✅ Подтвердить"
        kb.button(text=confirm_text, callback_data=f"pbook_confirm_{offer_id}")

    back_text = "◀️ Orqaga" if lang == "uz" else "◀️ Назад"
    kb.button(text=back_text, callback_data=f"pbook_cancel_{offer_id}_{store_id}")

    # Layout - calculate based on what we have
    qty_button_count = (
        min(4, len([q for q in [1, 2, 3, 5, 10] if q <= max_qty])) if max_qty <= 10 else 3
    )
    if delivery_enabled:
        if delivery_method:
            kb.adjust(qty_button_count, 2, 2)  # qty buttons, [pickup][delivery], [confirm][back]
        else:
            kb.adjust(qty_button_count, 2, 1)  # qty buttons, [pickup][delivery], [back]
    else:
        kb.adjust(qty_button_count, 2)  # qty buttons, [confirm][back]

    return kb


@router.callback_query(F.data.regexp(r"^book_\d+$"))
async def book_offer_start(callback: types.CallbackQuery, state: FSMContext) -> None:
    """Premium UX: Update current card with order controls (no new message)."""
    if not db or not bot or not callback.message:
        await callback.answer(get_text("ru", "system_error"), show_alert=True)
        return

    user_id = callback.from_user.id
    lang = db.get_user_language(user_id)

    # Rate limit check
    if not can_proceed(user_id, "book_start"):
        await callback.answer(get_text(lang, "too_many_requests"), show_alert=True)
        return

    # Parse offer_id
    try:
        offer_id = int(callback.data.split("_")[1])
    except (ValueError, IndexError):
        await callback.answer(get_text(lang, "error"), show_alert=True)
        return

    offer = db.get_offer(offer_id)
    if not offer:
        await callback.answer(get_text(lang, "offer_not_found"), show_alert=True)
        return

    # Check availability
    max_quantity = get_offer_field(offer, "quantity", 0)
    if max_quantity <= 0:
        await callback.answer(get_text(lang, "no_offers"), show_alert=True)
        return

    # Get offer details
    offer_price = get_offer_field(offer, "discount_price", 0)
    original_price = get_offer_field(offer, "original_price", 0)
    offer_title = get_offer_field(offer, "title", "Товар")
    offer_description = get_offer_field(offer, "description", "")
    offer_unit = get_offer_field(offer, "unit", "")
    expiry_date = get_offer_field(offer, "expiry_date", "")
    store_id = get_offer_field(offer, "store_id")

    # Get store details
    store = db.get_store(store_id) if store_id else None
    store_name = get_store_field(store, "name", "Магазин")
    store_address = get_store_field(store, "address", "")
    delivery_enabled = get_store_field(store, "delivery_enabled", 0) == 1
    delivery_price = get_store_field(store, "delivery_price", 0) if delivery_enabled else 0

    # Initial state: quantity=1, no delivery method selected
    initial_qty = 1
    initial_method = None if delivery_enabled else "pickup"

    # Get offer photo
    offer_photo = get_offer_field(offer, "photo", None)

    # Save to state (including new fields)
    await state.update_data(
        offer_id=offer_id,
        max_quantity=max_quantity,
        offer_price=offer_price,
        original_price=original_price,
        offer_title=offer_title,
        offer_description=offer_description,
        offer_unit=offer_unit,
        expiry_date=str(expiry_date) if expiry_date else "",
        store_id=store_id,
        store_name=store_name,
        store_address=store_address,
        delivery_enabled=delivery_enabled,
        delivery_price=delivery_price,
        selected_qty=initial_qty,
        selected_delivery=initial_method,
        offer_photo=offer_photo,
    )
    await state.set_state(BookOffer.quantity)

    # Build card text and keyboard
    text = build_order_card_text(
        lang,
        offer_title,
        offer_price,
        initial_qty,
        store_name,
        delivery_enabled,
        delivery_price,
        initial_method,
        max_quantity,
        original_price=original_price,
        description=offer_description,
        expiry_date=str(expiry_date) if expiry_date else "",
        store_address=store_address,
        unit=offer_unit,
    )
    kb = build_order_card_keyboard(
        lang, offer_id, store_id, initial_qty, max_quantity, delivery_enabled, initial_method
    )

    # Update EXISTING message - edit in place, no new messages
    try:
        if callback.message.photo:
            await callback.message.edit_caption(
                caption=text, parse_mode="HTML", reply_markup=kb.as_markup()
            )
        else:
            await callback.message.edit_text(text, parse_mode="HTML", reply_markup=kb.as_markup())
        await callback.answer()
    except Exception as e:
        logger.warning(f"Failed to edit message in book_offer_start: {e}")
        # Fallback: delete old and send new
        try:
            await callback.message.delete()
        except Exception as del_e:
            logger.debug("Could not delete message: %s", del_e)
        offer_photo = get_offer_field(offer, "photo", None)
        if offer_photo:
            await callback.message.answer_photo(
                photo=offer_photo, caption=text, parse_mode="HTML", reply_markup=kb.as_markup()
            )
        else:
            await callback.message.answer(text, parse_mode="HTML", reply_markup=kb.as_markup())
        await callback.answer()


@router.callback_query(F.data == "pbook_noop")
async def pbook_noop(callback: types.CallbackQuery) -> None:
    """No-op for disabled buttons."""
    await callback.answer()


@router.callback_query(F.data.startswith("pbook_qty_"))
async def pbook_change_qty(callback: types.CallbackQuery, state: FSMContext) -> None:
    """Premium UX: Change quantity and update card."""
    if not db or not bot or not callback.message:
        await callback.answer()
        return

    user_id = callback.from_user.id
    lang = db.get_user_language(user_id)

    try:
        parts = callback.data.split("_")
        offer_id = int(parts[2])
        new_qty = int(parts[3])
    except (ValueError, IndexError):
        await callback.answer("❌", show_alert=True)
        return

    data = await state.get_data()
    max_quantity = data.get("max_quantity", 1)

    if new_qty < 1 or new_qty > max_quantity:
        await callback.answer("❌", show_alert=True)
        return

    # Update state
    await state.update_data(selected_qty=new_qty)
    data = await state.get_data()

    # Rebuild card
    text = build_order_card_text(
        lang,
        data.get("offer_title", ""),
        data.get("offer_price", 0),
        new_qty,
        data.get("store_name", ""),
        data.get("delivery_enabled", False),
        data.get("delivery_price", 0),
        data.get("selected_delivery"),
        max_quantity,
        original_price=data.get("original_price", 0),
        description=data.get("offer_description", ""),
        expiry_date=data.get("expiry_date", ""),
        store_address=data.get("store_address", ""),
        unit=data.get("offer_unit", ""),
    )
    kb = build_order_card_keyboard(
        lang,
        offer_id,
        data.get("store_id", 0),
        new_qty,
        max_quantity,
        data.get("delivery_enabled", False),
        data.get("selected_delivery"),
    )

    # Update message
    try:
        if callback.message.photo:
            await callback.message.edit_caption(
                caption=text, parse_mode="HTML", reply_markup=kb.as_markup()
            )
        else:
            await callback.message.edit_text(text, parse_mode="HTML", reply_markup=kb.as_markup())
    except Exception as e:
        logger.debug("Could not edit quantity message: %s", e)
    await callback.answer()


@router.callback_query(F.data.startswith("pbook_method_"))
async def pbook_select_method(callback: types.CallbackQuery, state: FSMContext) -> None:
    """Premium UX: Select delivery method and update card."""
    if not db or not bot or not callback.message:
        await callback.answer()
        return

    user_id = callback.from_user.id
    lang = db.get_user_language(user_id)

    try:
        parts = callback.data.split("_")
        offer_id = int(parts[2])
        method = parts[3]  # "pickup" or "delivery"
    except (ValueError, IndexError):
        await callback.answer("❌", show_alert=True)
        return

    # Update state
    await state.update_data(selected_delivery=method)
    data = await state.get_data()

    quantity = data.get("selected_qty", 1)
    max_quantity = data.get("max_quantity", 1)

    # Rebuild card
    text = build_order_card_text(
        lang,
        data.get("offer_title", ""),
        data.get("offer_price", 0),
        quantity,
        data.get("store_name", ""),
        data.get("delivery_enabled", False),
        data.get("delivery_price", 0),
        method,
        max_quantity,
        original_price=data.get("original_price", 0),
        description=data.get("offer_description", ""),
        expiry_date=data.get("expiry_date", ""),
        store_address=data.get("store_address", ""),
        unit=data.get("offer_unit", ""),
    )
    kb = build_order_card_keyboard(
        lang,
        offer_id,
        data.get("store_id", 0),
        quantity,
        max_quantity,
        data.get("delivery_enabled", False),
        method,
    )

    # Update message
    try:
        if callback.message.photo:
            await callback.message.edit_caption(
                caption=text, parse_mode="HTML", reply_markup=kb.as_markup()
            )
        else:
            await callback.message.edit_text(text, parse_mode="HTML", reply_markup=kb.as_markup())
    except Exception as e:
        logger.debug("Could not edit delivery method message: %s", e)
    await callback.answer()


@router.callback_query(F.data.startswith("pbook_cancel_"))
async def pbook_cancel(callback: types.CallbackQuery, state: FSMContext) -> None:
    """Cancel booking - return to source list (store, search, or hot offers)."""
    if not db or not callback.message:
        await callback.answer()
        return

    user_id = callback.from_user.id
    lang = db.get_user_language(user_id)
    data = await state.get_data()

    # Check source context
    source = data.get("source", "hot")  # Default to hot offers

    # Delete current message
    try:
        await callback.message.delete()
    except Exception as e:
        logger.debug("Could not delete cancel message: %s", e)

    from app.core.utils import normalize_city
    from app.services.offer_service import OfferService

    offer_service = OfferService(db)

    user = db.get_user_model(user_id)
    city = user.city if user else "Ташкент"
    region = getattr(user, "region", None) if user else None
    district = getattr(user, "district", None) if user else None
    latitude = getattr(user, "latitude", None) if user else None
    longitude = getattr(user, "longitude", None) if user else None
    search_city = normalize_city(city)
    search_region = normalize_city(region) if region else None
    search_district = normalize_city(district) if district else None

    # Return to store list
    if source == "store":
        store_id = data.get("last_store_id") or data.get("store_id")
        store_page = data.get("last_store_page", 0)
        category = data.get("last_store_category", "all")

        await state.clear()

        if store_id:
            store = offer_service.get_store(store_id)
            if store:
                all_offers = offer_service.list_store_offers(store_id)

                # Filter by category if not "all"
                if category != "all":
                    category_map = {
                        "bakery": "bakery",
                        "dairy": "dairy",
                        "meat": "meat",
                        "fruits": "fruits",
                        "vegetables": "vegetables",
                        "drinks": "drinks",
                        "snacks": "snacks",
                        "frozen": "frozen",
                    }
                    db_category = category_map.get(category, category)
                    offers = [offer for offer in all_offers if offer.category == db_category]
                else:
                    offers = all_offers

                if offers:
                    from app.keyboards.offers import store_offers_compact_keyboard
                    from handlers.common import BrowseOffers

                    total_pages = (len(offers) + OFFERS_PER_PAGE - 1) // OFFERS_PER_PAGE
                    page = min(store_page, total_pages - 1)  # Ensure valid page
                    offset = page * OFFERS_PER_PAGE
                    page_offers = offers[offset : offset + OFFERS_PER_PAGE]

                    await state.set_state(BrowseOffers.offer_list)
                    await state.update_data(
                        offer_list=[offer.id for offer in offers],
                        store_offers_page=page,
                        current_store_id=store_id,
                        store_category=category,
                    )

                    currency = "so'm" if lang == "uz" else "сум"
                    category_title = (
                        category.replace("_", " ").title()
                        if category != "all"
                        else ("Все категории" if lang == "ru" else "Barcha toifalar")
                    )

                    text = f"🏪 <b>{store.name}</b> | 📂 {category_title}\n"
                    text += f"{'Стр.' if lang == 'ru' else 'Sah.'} {page + 1}/{total_pages} ({len(offers)} {'махсулот' if lang == 'uz' else 'товаров'})\n"
                    text += "─" * 28 + "\n\n"

                    for idx, offer in enumerate(page_offers, start=1):
                        title = offer.title[:25] + ".." if len(offer.title) > 25 else offer.title
                        discount_pct = 0
                        if (
                            offer.original_price
                            and offer.discount_price
                            and offer.original_price > 0
                        ):
                            discount_pct = int(
                                (1 - offer.discount_price / offer.original_price) * 100
                            )
                        text += f"<b>{idx}.</b> {title}\n"
                        if offer.original_price and discount_pct > 0:
                            text += f"    <s>{int(offer.original_price):,}</s> → <b>{int(offer.discount_price):,}</b> {currency} <i>(-{discount_pct}%)</i>\n"
                        else:
                            price_kopeks = offer.discount_price or offer.price or 0
                            text += f"    <b>{int(price_kopeks):,}</b> {currency}\n"

                    hint = "👆 Tanlang" if lang == "uz" else "👆 Выберите товар"
                    text += f"\n{hint}"

                    kb = store_offers_compact_keyboard(
                        lang, page_offers, store_id, page, total_pages
                    )
                    await callback.message.answer(text, parse_mode="HTML", reply_markup=kb)
                    await callback.answer()
                    return

        # Fallback to main menu if store not found
        cancelled = "❌ Bekor qilindi" if lang == "uz" else "❌ Отменено"
        await callback.message.answer(cancelled, reply_markup=main_menu_customer(lang))
        await callback.answer()
        return

    # Return to search results
    if source == "search":
        search_results = data.get("search_results", [])
        search_query = data.get("search_query", "")
        search_page = data.get("search_page", 0)

        await state.clear()

        if search_results and search_query:
            from app.keyboards.offers import search_results_compact_keyboard

            # Fetch offer objects
            all_results = []
            for offer_id in search_results:
                try:
                    offer = offer_service.get_offer_details(offer_id)
                    if offer:
                        all_results.append(offer)
                except Exception as e:
                    logger.debug("Could not fetch offer %s: %s", offer_id, e)

            if all_results:
                total_count = len(all_results)
                total_pages = max(1, (total_count + OFFERS_PER_PAGE - 1) // OFFERS_PER_PAGE)
                page = min(search_page, total_pages - 1)

                start_idx = page * OFFERS_PER_PAGE
                end_idx = min(start_idx + OFFERS_PER_PAGE, total_count)
                page_offers = all_results[start_idx:end_idx]

                # Build compact list text
                lines = []
                for idx, offer in enumerate(page_offers, start=1):
                    title = offer.title if hasattr(offer, "title") else "Товар"
                    price = getattr(offer, "discount_price", 0) or getattr(offer, "price", 0)
                    quantity = getattr(offer, "quantity", 0)
                    price_str = f"{int(price):,}".replace(",", " ")
                    qty_text = (
                        f"({quantity} шт)"
                        if quantity > 0
                        else "(нет)"
                        if lang == "ru"
                        else "(yo'q)"
                    )
                    lines.append(f"<b>{idx}.</b> {title}\n   💰 {price_str} сум {qty_text}")

                header = (
                    f"📦 <b>Товары по запросу «{search_query}»</b>\n"
                    f"Показано {start_idx + 1}-{end_idx} из {total_count}\n\n"
                    if lang == "ru"
                    else f"📦 <b>«{search_query}» bo'yicha mahsulotlar</b>\n"
                    f"{start_idx + 1}-{end_idx} / {total_count} ko'rsatilmoqda\n\n"
                )

                text = header + "\n".join(lines)
                kb = search_results_compact_keyboard(
                    lang, page_offers, page, total_pages, search_query
                )

                await callback.message.answer(text, parse_mode="HTML", reply_markup=kb)
                await callback.answer()
                return

        # Fallback to main menu
        cancelled = "❌ Bekor qilindi" if lang == "uz" else "❌ Отменено"
        await callback.message.answer(cancelled, reply_markup=main_menu_customer(lang))
        await callback.answer()
        return

    # Default: return to hot offers
    last_page = data.get("last_hot_page", 0)
    await state.clear()

    result = offer_service.list_hot_offers(
        search_city,
        limit=OFFERS_PER_PAGE,
        offset=last_page * OFFERS_PER_PAGE,
        region=search_region,
        district=search_district,
        latitude=latitude,
        longitude=longitude,
    )
    if not result.items:
        # No offers - show main menu
        cancelled = "❌ Bekor qilindi" if lang == "uz" else "❌ Отменено"
        await callback.message.answer(cancelled, reply_markup=main_menu_customer(lang))
        await callback.answer()
        return

    # Build hot offers list
    from app.keyboards.offers import hot_offers_compact_keyboard
    from app.templates.offers import render_hot_offers_list

    total_pages = (result.total + OFFERS_PER_PAGE - 1) // OFFERS_PER_PAGE
    select_hint = "👆 Выберите товар" if lang == "ru" else "👆 Mahsulotni tanlang"
    text = render_hot_offers_list(
        lang, city, result.items, result.total, select_hint, offset=last_page * OFFERS_PER_PAGE
    )
    kb = hot_offers_compact_keyboard(lang, result.items, last_page, total_pages)

    await callback.message.answer(text, parse_mode="HTML", reply_markup=kb)
    await callback.answer()


@router.callback_query(F.data.startswith("pbook_confirm_"))
async def pbook_confirm(callback: types.CallbackQuery, state: FSMContext) -> None:
    """Confirm order - create booking or start delivery flow."""
    logger.info(f"📥 pbook_confirm called: user={callback.from_user.id}, data={callback.data}")

    if not db or not bot or not callback.message:
        logger.error("pbook_confirm: db or bot or message is None")
        await callback.answer("System error", show_alert=True)
        return

    user_id = callback.from_user.id
    lang = db.get_user_language(user_id)

    # Check if user has phone - required for order
    # Use get_user() which is more robust than get_user_model()
    user_dict = db.get_user(user_id)
    user_phone = user_dict.get("phone") if user_dict else None
    if not user_phone:
        # Ask for phone before proceeding
        from app.keyboards import phone_request_keyboard
        from handlers.common.states import Registration

        msg = (
            "📱 Buyurtma berish uchun telefon raqamingizni kiriting"
            if lang == "uz"
            else "📱 Для оформления заказа укажите номер телефона"
        )

        await callback.message.answer(
            msg,
            reply_markup=phone_request_keyboard(lang),
        )

        # Save current state to resume after phone
        data = await state.get_data()
        await state.update_data(pending_order=True, **data)
        await state.set_state(Registration.phone)
        await callback.answer()
        return

    data = await state.get_data()
    logger.info(f"📥 pbook_confirm state data: {data}")

    selected_delivery = data.get("selected_delivery")

    if not selected_delivery:
        msg = "Avval olish usulini tanlang" if lang == "uz" else "Сначала выберите способ получения"
        await callback.answer(msg, show_alert=True)
        return

    offer_id = data.get("offer_id")
    quantity = data.get("selected_qty", 1)
    store_id = data.get("store_id")
    offer_price = data.get("offer_price", 0)
    offer_title = data.get("offer_title", "Товар")

    logger.info(
        f"📥 pbook_confirm: offer_id={offer_id}, qty={quantity}, delivery={selected_delivery}"
    )

    # Check minimum order for delivery
    if selected_delivery == "delivery":
        store = db.get_store(store_id) if store_id else None
        min_order = get_store_field(store, "min_order_amount", 0)
        order_total = offer_price * quantity

        if min_order > 0 and order_total < min_order:
            currency = "so'm" if lang == "uz" else "сум"
            msg = (
                f"❌ Min. buyurtma: {min_order:,} {currency}"
                if lang == "uz"
                else f"❌ Мин. заказ: {min_order:,} {currency}"
            )
            await callback.answer(msg, show_alert=True)
            return

    # Show processing status in the card (no keyboard)
    currency = "so'm" if lang == "uz" else "сум"
    total = offer_price * quantity
    processing_text = (
        f"⏳ <b>Bron yuborilmoqda...</b>\n\n"
        f"🛒 {_esc(offer_title)} × {quantity}\n"
        f"💵 {total:,} {currency}"
        if lang == "uz"
        else f"⏳ <b>Оформляем бронь...</b>\n\n"
        f"🛒 {_esc(offer_title)} × {quantity}\n"
        f"💵 {total:,} {currency}"
    )

    try:
        if callback.message.photo:
            await callback.message.edit_caption(
                caption=processing_text, parse_mode="HTML", reply_markup=None
            )
        else:
            await callback.message.edit_text(processing_text, parse_mode="HTML", reply_markup=None)
        logger.info("📥 pbook_confirm: processing text shown")
    except Exception as e:
        logger.warning(f"📥 pbook_confirm: failed to show processing: {e}")

    if selected_delivery == "delivery":
        logger.info("📥 pbook_confirm: starting delivery flow")
        # Switch to delivery flow - preserve ALL data for delivery card
        delivery_price = data.get("delivery_price", 0)

        # Load saved address
        saved_address = None
        try:
            saved_address = db.get_last_delivery_address(user_id)
        except Exception as e:
            logger.debug("Could not load saved address for user %d: %s", user_id, e)

        await state.clear()
        await state.update_data(
            offer_id=offer_id,
            store_id=store_id,
            quantity=quantity,
            max_qty=data.get("max_quantity", 1),
            price=offer_price,
            title=offer_title,
            store_name=data.get("store_name", ""),
            delivery_price=delivery_price,
            saved_address=saved_address,
            offer_photo=data.get("offer_photo"),
            order_type="delivery",  # FIXED: Explicitly mark as delivery order
        )
        await state.set_state(OrderDelivery.address)

        # Build delivery card text inline (no extra message)
        from handlers.customer.orders.delivery import (
            build_delivery_address_keyboard,
            build_delivery_card_text,
        )

        card_text = build_delivery_card_text(
            lang,
            offer_title,
            offer_price,
            quantity,
            data.get("max_quantity", 1),
            data.get("store_name", ""),
            delivery_price,
            None,
            "address",
        )
        kb = build_delivery_address_keyboard(lang, offer_id, saved_address)

        # Update existing message with delivery card
        try:
            if callback.message.photo:
                await callback.message.edit_caption(
                    caption=card_text, parse_mode="HTML", reply_markup=kb.as_markup()
                )
            else:
                await callback.message.edit_text(
                    card_text, parse_mode="HTML", reply_markup=kb.as_markup()
                )
        except Exception as e:
            logger.warning(f"Failed to edit message for delivery: {e}")
            # Fallback - send new message
            await bot.send_message(
                user_id, card_text, parse_mode="HTML", reply_markup=kb.as_markup()
            )
    else:
        # Pickup - create booking directly
        await state.update_data(quantity=quantity, delivery_option=0, delivery_cost=0)

        # Create booking (will send notification in same chat)
        await create_booking(callback.message, state, real_user_id=user_id)

    await callback.answer()


# ===================== LEGACY HANDLERS (kept for compatibility) =====================


@router.message(BookOffer.quantity)
async def book_offer_quantity(message: types.Message, state: FSMContext) -> None:
    """Process quantity input."""
    if not db:
        await message.answer("System error")
        return

    user_id = message.from_user.id
    lang = db.get_user_language(user_id)
    text = (message.text or "").strip()

    # Check if user pressed main menu button - clear state and let other handlers process
    if is_main_menu_button(text):
        await state.clear()
        return

    # Check cancel - accept all variants
    if (
        text in ["❌ Отмена", "❌ Bekor qilish", "/cancel", "Отмена", "Bekor qilish"]
        or "отмена" in text.lower()
        or "bekor" in text.lower()
    ):
        await state.clear()
        await message.answer(
            get_text(lang, "action_cancelled"), reply_markup=main_menu_customer(lang)
        )
        return

    # Validate quantity
    data = await state.get_data()
    max_qty = data.get("max_quantity", 1)

    try:
        quantity = int(text)
        if quantity < 1 or quantity > max_qty:
            raise ValueError("Invalid quantity")
    except ValueError:
        if lang == "uz":
            await message.answer(f"❌ Iltimos, 1 dan {max_qty} gacha raqam kiriting")
        else:
            await message.answer(f"❌ Введите число от 1 до {max_qty}")
        return

    await state.update_data(quantity=quantity)

    # Check if store has delivery
    store_id = data.get("store_id")
    store = db.get_store(store_id) if store_id else None
    delivery_enabled = get_store_field(store, "delivery_enabled", 0) == 1

    if delivery_enabled:
        # Ask for delivery choice
        await state.set_state(BookOffer.delivery_choice)

        delivery_price = get_store_field(store, "delivery_price", 0)

        kb = InlineKeyboardBuilder()
        if lang == "uz":
            kb.button(text="🏪 O'zim olib ketaman", callback_data="pickup_choice")
            kb.button(
                text=f"🚚 Yetkazib berish ({delivery_price:,} so'm)",
                callback_data="delivery_choice",
            )
        else:
            kb.button(text="🏪 Самовывоз", callback_data="pickup_choice")
            kb.button(text=f"🚚 Доставка ({delivery_price:,} сум)", callback_data="delivery_choice")
        kb.button(
            text="❌ " + ("Bekor qilish" if lang == "uz" else "Отмена"),
            callback_data="cancel_booking_flow",
        )
        kb.adjust(2, 1)

        if lang == "uz":
            text = "📦 Yetkazib berish usulini tanlang:"
        else:
            text = "📦 Выберите способ получения:"

        await message.answer(text, reply_markup=kb.as_markup())
    else:
        # No delivery - go straight to booking
        await state.update_data(delivery_option=0, delivery_cost=0)
        await create_booking(message, state)


@router.callback_query(F.data == "pickup_choice")
async def pickup_choice(callback: types.CallbackQuery, state: FSMContext) -> None:
    """User chose pickup."""
    user_id = callback.from_user.id  # Real user ID from callback
    await state.update_data(delivery_option=0, delivery_cost=0)
    await safe_edit_reply_markup(callback.message)
    await create_booking(callback.message, state, real_user_id=user_id)
    await callback.answer()


@router.callback_query(F.data == "delivery_choice")
async def delivery_choice(callback: types.CallbackQuery, state: FSMContext) -> None:
    """User chose delivery - redirect to OrderDelivery flow."""
    if not db:
        await callback.answer("System error", show_alert=True)
        return

    user_id = callback.from_user.id
    lang = db.get_user_language(user_id)

    # Get data from BookOffer state
    data = await state.get_data()
    offer_id = data.get("offer_id")
    quantity = data.get("quantity", 1)
    store_id = data.get("store_id")
    offer_price = data.get("offer_price", 0)

    # CHECK MIN_ORDER_AMOUNT before allowing delivery
    store = db.get_store(store_id) if store_id else None
    min_order_amount = get_store_field(store, "min_order_amount", 0)
    order_total = offer_price * quantity

    if min_order_amount > 0 and order_total < min_order_amount:
        currency = "сум" if lang == "ru" else "so'm"
        if lang == "uz":
            msg = (
                f"❌ Yetkazib berish uchun minimal buyurtma: {min_order_amount:,} {currency}\n"
                f"Sizning buyurtmangiz: {order_total:,} {currency}\n\n"
                f"Iltimos, miqdorni oshiring yoki olib ketishni tanlang."
            )
        else:
            msg = (
                f"❌ Минимальная сумма для доставки: {min_order_amount:,} {currency}\n"
                f"Ваш заказ: {order_total:,} {currency}\n\n"
                f"Пожалуйста, увеличьте количество или выберите самовывоз."
            )
        await callback.answer(msg, show_alert=True)
        return

    # Transfer to OrderDelivery state (orders.py handles delivery with payment)
    await state.clear()
    await state.update_data(
        offer_id=offer_id,
        store_id=store_id,
        quantity=quantity,
    )
    await state.set_state(OrderDelivery.address)

    await safe_edit_reply_markup(callback.message)

    if lang == "uz":
        text = "📍 Yetkazib berish manzilini kiriting:\n\nMasalan: Chilanzar tumani, 5-mavze, 10-uy"
    else:
        text = "📍 Введите адрес доставки:\n\nНапример: Чиланзарский район, 5-массив, дом 10"

    await callback.message.answer(text, reply_markup=cancel_keyboard(lang))
    await callback.answer()


# NOTE: BookOffer.delivery_address handler removed - delivery now uses OrderDelivery flow
# from handlers/orders.py which handles address -> payment -> order creation


@router.callback_query(F.data == "cancel_booking_flow")
async def cancel_booking_flow(callback: types.CallbackQuery, state: FSMContext) -> None:
    """Cancel booking flow."""
    if not db:
        await callback.answer("System error", show_alert=True)
        return

    user_id = callback.from_user.id
    lang = db.get_user_language(user_id)

    await state.clear()
    await safe_edit_reply_markup(callback.message)
    await callback.message.answer(
        get_text(lang, "action_cancelled"), reply_markup=main_menu_customer(lang)
    )
    await callback.answer()


async def create_booking(
    message: types.Message, state: FSMContext, real_user_id: int | None = None
) -> None:
    """Create the final booking."""
    logger.info(f"📦 create_booking called: real_user_id={real_user_id}")

    if not db or not bot:
        logger.error("create_booking: db or bot is None")
        await message.answer("System error")
        return

    # Use provided user_id or fallback to message.from_user.id
    # Important: when called from callback, message.from_user is the BOT, not the user!
    user_id = real_user_id if real_user_id else message.from_user.id
    lang = db.get_user_language(user_id)
    data = await state.get_data()
    logger.info(f"📦 create_booking state data: {data}")

    # SAFETY NET: ensure user has phone before creating any booking
    # (pbook_confirm/cart_checkout already check this, but we double-check here
    #  so что бы ни один заказ не прошёл без номера телефона в профиле).
    user_dict = None
    user_phone: str | None = None
    try:
        if hasattr(db, "get_user"):
            user_dict = db.get_user(user_id)
        elif hasattr(db, "get_user_model"):
            user_dict = db.get_user_model(user_id)
        if user_dict is not None:
            if isinstance(user_dict, dict):
                user_phone = user_dict.get("phone")  # type: ignore[arg-type]
            else:
                user_phone = getattr(user_dict, "phone", None)
    except Exception as e:
        logger.warning(f"create_booking: failed to load user phone: {e}")

    if not user_phone:
        msg = (
            "📱 Для оформления заказа укажите номер телефона"
            if lang == "ru"
            else "📱 Buyurtma berish uchun telefon raqamingizni kiriting"
        )

        await message.answer(msg, reply_markup=phone_request_keyboard(lang))

        # Сохраняем состояние, чтобы вернуться к бронированию после ввода телефона
        await state.update_data(pending_order=True, **data)
        await state.set_state(Registration.phone)
        return

    offer_id = data.get("offer_id")
    # Support both "quantity" and "selected_qty" keys
    quantity = data.get("quantity") or data.get("selected_qty", 1)
    offer_price = data.get("offer_price", 0)
    offer_title = data.get("offer_title", "Товар")
    store_id = data.get("store_id")

    logger.info(f"📦 create_booking: offer_id={offer_id}, qty={quantity}, store={store_id}")

    if not offer_id:
        logger.error("create_booking: offer_id is None")
        await message.answer(get_text(lang, "error"))
        await state.clear()
        return

    # Pre-check: verify offer still available before atomic booking
    offer = db.get_offer(offer_id)
    if not offer:
        await message.answer(get_text(lang, "offer_not_found") or "❌ Предложение не найдено")
        await state.clear()
        return

    offer_status = get_offer_field(offer, "status", "inactive")
    offer_qty = get_offer_field(offer, "quantity", 0)

    if offer_status != "active":
        if lang == "uz":
            await message.answer("❌ Bu taklif hozirda mavjud emas. Boshqa taklif tanlang.")
        else:
            await message.answer("❌ Это предложение сейчас недоступно. Выберите другое.")
        await state.clear()
        return

    if offer_qty < quantity:
        if lang == "uz":
            await message.answer(f"❌ Faqat {offer_qty} dona qolgan. Miqdorni kamaytiring.")
        else:
            await message.answer(f"❌ Осталось только {offer_qty} шт. Уменьшите количество.")
        await state.clear()
        return

    # Create pickup order in unified orders table (v24+)
    try:
        unit_price = int(get_offer_field(offer, "discount_price", offer_price) or offer_price or 0)
    except Exception:
        unit_price = int(offer_price or 0)


    created_orders = []
    used_unified_service = False
    store_id_int = int(store_id or get_offer_field(offer, "store_id") or 0)
    store = db.get_store(store_id_int) if store_id_int else None
    store_name = get_store_field(store, "name", "Store")
    store_address = get_store_field(store, "address", "")

    order_service = get_unified_order_service()
    if order_service:
        try:
            order_item = OrderItem(
                offer_id=int(offer_id),
                store_id=store_id_int,
                title=offer_title,
                price=unit_price,
                original_price=unit_price,
                quantity=int(quantity),
                store_name=store_name,
                store_address=store_address,
                delivery_price=0,
            )
            result = await order_service.create_order(
                user_id=user_id,
                items=[order_item],
                order_type="pickup",
                delivery_address=None,
                payment_method="cash",
                notify_customer=True,
                notify_sellers=True,
                telegram_notify=True,
            )
            if result.success and result.order_ids:
                created_orders = [
                    {
                        "order_id": result.order_ids[0],
                        "pickup_code": result.pickup_codes[0] if result.pickup_codes else None,
                    }
                ]
                used_unified_service = True
            else:
                logger.error(
                    f"Unified order service failed for pickup order: {result.error_message}"
                )
        except Exception as e:
            logger.error(f"Unified pickup order creation failed: {e}")

    if not created_orders:
        try:
            result = db.create_cart_order(
                user_id=user_id,
                items=[
                    {
                        "offer_id": int(offer_id),
                        "store_id": store_id_int,
                        "quantity": int(quantity),
                        "price": unit_price,
                        "title": offer_title,
                    }
                ],
                order_type="pickup",
                delivery_address=None,
                payment_method="cash",
                notify_customer=False,
            )
            created_orders = result.get("created_orders", [])
        except Exception as e:
            logger.error(f"Order creation failed: {e}")
            created_orders = []

    order_id = created_orders[0].get("order_id") if created_orders else None
    code = created_orders[0].get("pickup_code") if created_orders else None

    if not order_id:
        if lang == "uz":
            await message.answer("❌ Buyurtma yaratib bo'lmadi. Keyinroq urinib ko'ring.")
        else:
            await message.answer("❌ Не удалось создать заказ. Попробуйте позже.")
        await state.clear()
        return

    # Update metrics
    if METRICS:
        METRICS["bookings_created"] = METRICS.get("bookings_created", 0) + 1

    logger.info(f"✅ Pickup order created: id={order_id}, code={code}, user={user_id}")

    # Structured logging
    total = calculate_total(offer_price, quantity, 0)
    logger.info(
        f"ORDER_CREATED: id={order_id}, user={user_id}, type=pickup, "
        f"total={total}, items=1, source=pickup_bot, pickup_code={code}"
    )

    await state.clear()

    # Get store info
    owner_id = get_store_field(store, "owner_id")

    # Get offer photo
    offer_photo_val = get_offer_field(offer, "photo")
    offer_photo = str(offer_photo_val) if offer_photo_val else None

    # Notify partner
    if owner_id and not used_unified_service:
        await notify_partner_new_pickup_order(
            owner_id=owner_id,
            order_id=int(order_id),
            pickup_code=code,
            offer_title=offer_title,
            quantity=quantity,
            total=total,
            customer_id=user_id,
            customer_name=message.from_user.first_name,
            offer_photo=offer_photo,
        )


async def notify_partner_new_pickup_order(
    owner_id: int,
    order_id: int,
    pickup_code: str | None,
    offer_title: str,
    quantity: int,
    total: int,
    customer_id: int,
    customer_name: str,
    offer_photo: str | None = None,
) -> None:
    """Send pickup order notification to partner (unified orders table)."""
    if not db or not bot:
        return

    partner_lang = db.get_user_language(owner_id)
    customer = get_user_safe(db, customer_id)

    # Use get_user_field for dict/model compatible access
    from .utils import get_user_field

    customer_phone = get_user_field(customer, "phone") or "Не указан"
    customer_username = get_user_field(customer, "username")

    # Contact info
    contact_info = f"@{customer_username}" if customer_username else customer_phone
    currency = "so'm" if partner_lang == "uz" else "сум"

    code_line = f"<code>{_esc(pickup_code)}</code>" if pickup_code else "—"

    if partner_lang == "uz":
        text = (
            f"🔔 <b>YANGI BUYURTMA!</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n\n"
            f"📦 <b>#{order_id}</b>\n"
            f"🔑 Kod: {code_line}\n\n"
            f"🛒 <b>{_esc(offer_title)}</b>\n"
            f"📦 Miqdor: <b>{quantity}</b> dona\n"
            f"💰 Jami: <b>{total:,}</b> {currency}\n\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"👤 <b>Xaridor:</b>\n"
            f"   Ism: {_esc(customer_name)}\n"
            f"   📱 <code>{_esc(customer_phone)}</code>\n"
            f"   💬 {_esc(contact_info)}\n\n"
            f"🏪 <b>O'zi olib ketadi</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"⏳ <b>Buyurtmani tasdiqlang!</b>"
        )
        confirm_text = "✅ Tasdiqlash"
        reject_text = "❌ Rad etish"
    else:
        text = (
            f"🔔 <b>НОВЫЙ ЗАКАЗ!</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n\n"
            f"📦 <b>#{order_id}</b>\n"
            f"🔑 Код: {code_line}\n\n"
            f"🛒 <b>{_esc(offer_title)}</b>\n"
            f"📦 Количество: <b>{quantity}</b> шт\n"
            f"💰 Итого: <b>{total:,}</b> {currency}\n\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"👤 <b>Покупатель:</b>\n"
            f"   Имя: {_esc(customer_name)}\n"
            f"   📱 <code>{_esc(customer_phone)}</code>\n"
            f"   💬 {_esc(contact_info)}\n\n"
            f"🏪 <b>Самовывоз</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"⏳ <b>Подтвердите заказ!</b>"
        )
        confirm_text = "✅ Принять"
        reject_text = "❌ Отклонить"

    kb = InlineKeyboardBuilder()
    kb.button(text=confirm_text, callback_data=f"order_confirm_{order_id}")
    kb.button(text=reject_text, callback_data=f"order_reject_{order_id}")
    kb.adjust(2)

    try:
        sent_msg = None
        if offer_photo:
            try:
                sent_msg = await bot.send_photo(
                    owner_id,
                    photo=offer_photo,
                    caption=text,
                    parse_mode="HTML",
                    reply_markup=kb.as_markup(),
                )
            except Exception as photo_err:
                logger.warning(f"Failed to send photo to partner: {photo_err}")

        if not sent_msg:
            sent_msg = await bot.send_message(
                owner_id, text, parse_mode="HTML", reply_markup=kb.as_markup()
            )

        if sent_msg and hasattr(db, "set_order_seller_message_id"):
            try:
                db.set_order_seller_message_id(order_id, sent_msg.message_id)
                logger.info(f"Saved seller_message_id={sent_msg.message_id} for order#{order_id}")
            except Exception as save_err:
                logger.error(f"Failed to save seller_message_id: {save_err}")
    except Exception as e:
        logger.error(f"Failed to notify partner {owner_id}: {e}")


async def notify_partner_new_booking(
    owner_id: int,
    booking_id: int,
    offer_title: str,
    quantity: int,
    total: int,
    customer_id: int,
    customer_name: str,
    offer_photo: str | None = None,
) -> None:
    """Send beautiful booking notification to partner with photo (pickup only)."""
    if not db or not bot:
        return

    partner_lang = db.get_user_language(owner_id)
    customer = get_user_safe(db, customer_id)

    # Use get_user_field for dict/model compatible access
    from .utils import get_user_field

    customer_phone = get_user_field(customer, "phone") or "Не указан"
    customer_username = get_user_field(customer, "username")

    # Contact info
    contact_info = f"@{customer_username}" if customer_username else customer_phone
    currency = "so'm" if partner_lang == "uz" else "сум"

    # Build beautiful notification card
    if partner_lang == "uz":
        text = (
            f"🔔 <b>YANGI BRON!</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n\n"
            f"🛒 <b>{_esc(offer_title)}</b>\n"
            f"📦 Miqdor: <b>{quantity}</b> dona\n"
            f"💰 Jami: <b>{total:,}</b> {currency}\n\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"👤 <b>Xaridor:</b>\n"
            f"   Ism: {_esc(customer_name)}\n"
            f"   📱 <code>{_esc(customer_phone)}</code>\n"
            f"   💬 {_esc(contact_info)}\n\n"
            f"🏪 <b>O'zi olib ketadi</b>\n"
            f"━━━━━━━━━━━━━━━━━━"
        )
        confirm_text = "✅ Tasdiqlash"
        reject_text = "❌ Rad etish"
    else:
        text = (
            f"🔔 <b>НОВАЯ БРОНЬ!</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n\n"
            f"🛒 <b>{_esc(offer_title)}</b>\n"
            f"📦 Количество: <b>{quantity}</b> шт\n"
            f"💰 Итого: <b>{total:,}</b> {currency}\n\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"👤 <b>Покупатель:</b>\n"
            f"   Имя: {_esc(customer_name)}\n"
            f"   📱 <code>{_esc(customer_phone)}</code>\n"
            f"   💬 {_esc(contact_info)}\n\n"
            f"🏪 <b>Самовывоз</b>\n"
            f"━━━━━━━━━━━━━━━━━━"
        )
        confirm_text = "✅ Подтвердить"
        reject_text = "❌ Отклонить"

    kb = InlineKeyboardBuilder()
    # Use order_ prefix since pickup orders live in orders.
    kb.button(text=confirm_text, callback_data=f"order_confirm_{booking_id}")
    kb.button(text=reject_text, callback_data=f"order_reject_{booking_id}")
    kb.adjust(2)

    try:
        sent_msg = None
        # Try to send with photo first for beautiful card
        if offer_photo:
            try:
                sent_msg = await bot.send_photo(
                    owner_id,
                    photo=offer_photo,
                    caption=text,
                    parse_mode="HTML",
                    reply_markup=kb.as_markup(),
                )
            except Exception as photo_err:
                logger.warning(f"Failed to send photo to partner: {photo_err}")

        # Fallback to text only
        if not sent_msg:
            sent_msg = await bot.send_message(
                owner_id, text, parse_mode="HTML", reply_markup=kb.as_markup()
            )

        # Save seller_message_id for live editing
        if sent_msg and hasattr(db, "set_order_seller_message_id"):
            try:
                db.set_order_seller_message_id(booking_id, sent_msg.message_id)
                logger.info(f"Saved seller_message_id={sent_msg.message_id} for order#{booking_id}")
            except Exception as save_err:
                logger.error(f"Failed to save seller_message_id: {save_err}")
    except Exception as e:
        logger.error(f"Failed to notify partner {owner_id}: {e}")


# ===================== VIEW BOOKINGS =====================


@router.callback_query(F.data.in_(["bookings_active", "bookings_completed", "bookings_cancelled"]))
async def filter_bookings(callback: types.CallbackQuery) -> None:
    """Show filtered bookings list."""
    if not db:
        await callback.answer("System error", show_alert=True)
        return

    user_id = callback.from_user.id
    lang = db.get_user_language(user_id)

    status_map = {
        "bookings_active": "active",
        "bookings_completed": "completed",
        "bookings_cancelled": "cancelled",
    }
    status = status_map.get(callback.data, "active")

    bookings = db.get_user_bookings_by_status(user_id, status)

    if not bookings:
        await callback.answer(
            get_text(lang, f"no_{status}_bookings") or "Нет бронирований", show_alert=True
        )
        return

    # Build list
    if lang == "uz":
        text = f"📋 <b>Bronlar ({status})</b>\n\n"
    else:
        text = f"📋 <b>Бронирования ({status})</b>\n\n"

    for booking in bookings[:10]:
        b_id = get_booking_field(booking, "booking_id")
        code = get_booking_field(booking, "code")
        qty = get_booking_field(booking, "quantity", 1)
        created = get_booking_field(booking, "created_at", "")

        # Get joined offer info (usually at positions 8+)
        offer_title = (
            booking[8] if isinstance(booking, (list, tuple)) and len(booking) > 8 else "Товар"
        )
        offer_price = booking[9] if isinstance(booking, (list, tuple)) and len(booking) > 9 else 0

        total = int(offer_price * qty)
        code_display = format_booking_code(code, b_id)

        text += (
            f"🍽 <b>{_esc(offer_title)}</b>\n"
            f"📦 {qty} × {int(offer_price):,} = {total:,}\n"
            f"🎫 <code>{code_display}</code>\n"
            f"📅 {created}\n\n"
        )

    await safe_answer_or_send(callback.message, user_id, text, bot=bot, parse_mode="HTML")
    await callback.answer()


# ===================== CANCEL BOOKING =====================


@router.callback_query(F.data.regexp(r"^cancel_booking_\d+$"))
async def cancel_booking_confirm(callback: types.CallbackQuery) -> None:
    """Ask for cancellation confirmation."""
    if not db:
        await callback.answer("System error", show_alert=True)
        return

    user_id = callback.from_user.id
    lang = db.get_user_language(user_id)

    try:
        booking_id = int(callback.data.split("_")[-1])
    except ValueError:
        await callback.answer(get_text(lang, "error"), show_alert=True)
        return

    booking = db.get_booking(booking_id)
    if not booking:
        await callback.answer(get_text(lang, "booking_not_found"), show_alert=True)
        return

    # Check ownership
    if get_booking_field(booking, "user_id") != user_id:
        await callback.answer(get_text(lang, "error"), show_alert=True)
        return

    kb = InlineKeyboardBuilder()
    if lang == "uz":
        kb.button(text="✅ Ha, bekor qilish", callback_data=f"confirm_cancel_{booking_id}")
        kb.button(text="❌ Yo'q", callback_data="noop")
        text = "❓ Bronni bekor qilmoqchimisiz?"
    else:
        kb.button(text="✅ Да, отменить", callback_data=f"confirm_cancel_{booking_id}")
        kb.button(text="❌ Нет", callback_data="noop")
        text = "❓ Вы уверены, что хотите отменить бронирование?"
    kb.adjust(2)

    await safe_answer_or_send(callback.message, user_id, text, bot=bot, reply_markup=kb.as_markup())
    await callback.answer()


@router.callback_query(F.data.regexp(r"^confirm_cancel_\d+$"))
async def confirm_cancel_booking(callback: types.CallbackQuery) -> None:
    """Execute booking cancellation."""
    if not db:
        await callback.answer("System error", show_alert=True)
        return

    user_id = callback.from_user.id
    lang = db.get_user_language(user_id)

    try:
        booking_id = int(callback.data.split("_")[-1])
    except ValueError:
        await callback.answer(get_text(lang, "error"), show_alert=True)
        return

    booking = db.get_booking(booking_id)
    if not booking:
        await callback.answer(get_text(lang, "booking_not_found"), show_alert=True)
        return

    # Check ownership
    if get_booking_field(booking, "user_id") != user_id:
        await callback.answer(get_text(lang, "error"), show_alert=True)
        return

    # Cancel and restore quantity (prefer unified service for consistent status)
    order_service = get_unified_order_service()
    if order_service:
        success = await order_service.update_status(
            entity_id=booking_id,
            entity_type="booking",
            new_status=OrderStatus.CANCELLED,
            notify_customer=False,
        )
    else:
        success = db.cancel_booking(booking_id)

    if success:
        await callback.answer(
            get_text(lang, "booking_cancelled") or "Бронирование отменено", show_alert=True
        )
        await safe_edit_reply_markup(callback.message)

        # Show main menu so user can continue
        cancel_text = (
            "✅ Бронирование отменено. Количество товара возвращено."
            if lang == "ru"
            else "✅ Bron bekor qilindi. Mahsulot miqdori qaytarildi."
        )
        await bot.send_message(user_id, cancel_text, reply_markup=main_menu_customer(lang))
    else:
        await callback.answer(get_text(lang, "error"), show_alert=True)


@router.callback_query(F.data == "noop")
async def noop_handler(callback: types.CallbackQuery) -> None:
    """No-operation handler for closing dialogs."""
    await callback.answer()
