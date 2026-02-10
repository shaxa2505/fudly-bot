"""Hot offers and catalog browsing handlers split from browse.py."""
from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any

from aiogram import Dispatcher, F, types
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.core.constants import OFFERS_PER_PAGE, STORES_PER_PAGE
from app.core.utils import normalize_city
from app.keyboards import offers as offer_keyboards
from app.keyboards import offers_category_filter
from app.services.offer_service import OfferDetails, OfferListItem, OfferService
from app.templates import offers as offer_templates
from handlers.common import BrowseOffers
from handlers.common.utils import is_hot_offers_button, safe_delete_message, safe_edit_message
from localization import get_product_categories, get_text, normalize_category

from .browse_helpers import (
    callback_message as _callback_message,
)
from .browse_helpers import (
    invalid_number_text as _invalid_number_text,
)
from .browse_helpers import (
    range_text as _range_text,
)

FetchOffersFn = Callable[[str | None, int, str | None, str | None], list[OfferListItem]]

DEFAULT_CITY = "Ташкент"
_CATEGORY_IDS = [
    "bakery",
    "dairy",
    "meat",
    "fruits",
    "vegetables",
    "drinks",
    "snacks",
    "frozen",
    "sweets",
    "other",
]


def _format_time(value: str | Any | None) -> str:
    if not value:
        return ""
    try:
        if hasattr(value, "strftime"):
            return value.strftime("%H:%M")
        text = str(value)
        if "T" in text:
            text = text.split("T")[-1]
        return text[:5] if len(text) >= 5 else text
    except Exception:
        return ""


def _format_date(value: str | Any | None) -> str:
    if not value:
        return ""
    try:
        from datetime import datetime

        if isinstance(value, str):
            expiry_str = value[:10]
            dt = datetime.strptime(expiry_str, "%Y-%m-%d")
        else:
            dt = value
        now = datetime.now()
        if dt.year == now.year:
            return dt.strftime("%d.%m")
        return dt.strftime("%d.%m.%Y")
    except Exception:
        return str(value)[:10]


def _catalog_filters_from_state(data: dict[str, Any]) -> dict[str, Any]:
    return {
        "store_id": data.get("catalog_store_id"),
        "store_name": data.get("catalog_store_name"),
        "category_id": data.get("catalog_category_id"),
        "category_label": data.get("catalog_category_label"),
        "min_discount": data.get("catalog_min_discount"),
        "only_today": bool(data.get("catalog_only_today")),
    }


def _filters_active(filters: dict[str, Any]) -> bool:
    return any(
        [
            filters.get("store_id"),
            filters.get("category_id"),
            filters.get("min_discount"),
            filters.get("only_today"),
        ]
    )


def _render_empty_catalog(lang: str) -> str:
    return f"{get_text(lang, 'catalog_empty_title')}\n\n{get_text(lang, 'catalog_empty_subtitle')}"


def _catalog_empty_keyboard(lang: str) -> InlineKeyboardBuilder:
    kb = InlineKeyboardBuilder()
    kb.button(text=get_text(lang, "catalog_empty_notify"), callback_data="toggle_notifications")
    kb.button(
        text=get_text(lang, "catalog_empty_change_city"),
        callback_data="profile_change_city",
    )
    kb.adjust(1, 1)
    return kb


def _format_money(value: float | int) -> str:
    return f"{int(value):,}".replace(",", " ")


def _short_title(title: str, limit: int = 26) -> str:
    cleaned = title or ""
    if cleaned.startswith("Пример:"):
        cleaned = cleaned[7:].strip()
    return cleaned if len(cleaned) <= limit else f"{cleaned[: limit - 2]}.."


def _short_store(name: str, limit: int = 16) -> str:
    cleaned = name or ""
    return cleaned if len(cleaned) <= limit else f"{cleaned[: limit - 2]}.."


def _offer_price_line(offer: OfferDetails | OfferListItem, lang: str) -> str:
    currency = "so'm" if lang == "uz" else "сум"
    current = getattr(offer, "discount_price", 0) or getattr(offer, "price", 0) or 0
    original = getattr(offer, "original_price", 0) or 0
    if original and original > current:
        discount_pct = round((1 - current / original) * 100)
        discount_pct = min(99, max(1, discount_pct))
        return f"{_format_money(current)} {currency} (-{discount_pct}%)"
    return f"{_format_money(current)} {currency}"


def _discount_percent(offer: OfferDetails | OfferListItem) -> int:
    current = getattr(offer, "discount_price", 0) or getattr(offer, "price", 0) or 0
    original = getattr(offer, "original_price", 0) or 0
    pct = getattr(offer, "discount_percent", 0) or 0
    if not pct and original and original > current:
        pct = round((1 - current / original) * 100)
    return int(pct or 0)


def _render_catalog_details(
    lang: str,
    offer: OfferDetails,
    store: Any | None,
) -> str:
    currency = "so'm" if lang == "uz" else "сум"
    title = _short_title(offer.title or "", limit=40)

    current = getattr(offer, "discount_price", 0) or getattr(offer, "price", 0) or 0
    original = getattr(offer, "original_price", 0) or current
    discount_pct = _discount_percent(offer)

    qty = offer.quantity or 0
    unit = offer.unit or ("dona" if lang == "uz" else "шт")

    pickup_until = _format_time(getattr(offer, "available_until", None))
    if not pickup_until:
        pickup_until = get_text(lang, "catalog_time_unknown")

    store_name = getattr(store, "name", None) if store else None
    if not store_name:
        store_name = getattr(offer, "store_name", "") or ""
    if not store_name:
        store_name = get_text(lang, "catalog_expiry_unknown")
    store_address = getattr(store, "address", None) if store else None
    if not store_address:
        store_address = getattr(offer, "store_address", "") or ""

    lines = [
        f"<b>{title}</b>",
        f"{get_text(lang, 'catalog_discount')}: -{discount_pct}%",
        f"{get_text(lang, 'catalog_price')}: {_format_money(original)} → {_format_money(current)} {currency}",
        "",
        f"{get_text(lang, 'catalog_in_stock')}: {qty} {unit}",
        f"{get_text(lang, 'catalog_pickup_until')}: {pickup_until}",
        "",
        f"{get_text(lang, 'catalog_store')}: {store_name}",
        f"{get_text(lang, 'catalog_address')}: {store_address or get_text(lang, 'catalog_expiry_unknown')}",
    ]

    return "\n".join(lines).rstrip()


def _category_label(lang: str, category: str) -> str:
    categories = get_product_categories(lang)
    mapping = dict(zip(_CATEGORY_IDS, categories))
    return mapping.get(category, category.replace("_", " ").title())


def _render_offers_list_text(
    lang: str,
    title: str,
    city: str,
    offers: list[OfferListItem],
    page: int,
    total_pages: int | None,
    total_count: int | None = None,
) -> str:
    city_label = "Город" if lang == "ru" else "Shahar"
    page_label = "Стр." if lang == "ru" else "Sah."
    page_info = f"{page_label} {page + 1}"
    if total_pages:
        page_info += f"/{total_pages}"
    total_label = "Всего" if lang == "ru" else "Jami"
    meta = f"{city_label}: {city} | {page_info}"
    if total_count is not None:
        meta = f"{meta} | {total_label} {total_count}"
    lines = [title, meta]

    for idx, offer in enumerate(offers, start=1):
        title_line = _short_title(offer.title, limit=28)
        price_line = _offer_price_line(offer, lang)
        store_name = _short_store(getattr(offer, "store_name", "") or "", limit=16)
        meta = price_line
        if store_name:
            meta = f"{meta} | {store_name}"
        lines.append(f"{idx}. <b>{title_line}</b> - {meta}")

    return "\n".join(lines).rstrip()


def _extract_location(
    user: Any,
) -> tuple[str, str | None, str | None, float | None, float | None]:
    city = getattr(user, "city", None) or DEFAULT_CITY
    region = getattr(user, "region", None)
    district = getattr(user, "district", None)
    latitude = getattr(user, "latitude", None)
    longitude = getattr(user, "longitude", None)
    return city, region, district, latitude, longitude


def register_hot(
    dp: Dispatcher,
    db: Any,
    offer_service: OfferService,
    logger: Any,
) -> None:
    """Register hot-offers and catalog-related handlers on dispatcher."""

    def _entry_text(lang: str, city: str) -> str:
        return (
            f"<b>{get_text(lang, 'hot_offers')}</b>\n\n"
            f"{'Город' if lang == 'ru' else 'Shahar'}: {city}\n"
            f"{get_text(lang, 'hot_offers_subtitle')}"
        )

    @dp.message(F.text.func(is_hot_offers_button))
    async def hot_offers_handler(message: types.Message, state: FSMContext) -> None:
        logger.info(f"[HOT_OFFERS] Handler triggered, text='{message.text}'")
        if not message.from_user:
            return
        # Clear any active FSM state when returning to main menu
        await state.clear()

        user_id = message.from_user.id
        logger.info(f"[HOT_OFFERS] User {user_id} requesting hot offers")
        lang = db.get_user_language(user_id)
        user = db.get_user_model(user_id)
        if not user:
            await message.answer(
                "Сессия истекла. Нажмите /start."
                if lang == "ru"
                else "Sessiya tugadi. /start bosing.",
            )
            return
        city, region, district, latitude, longitude = _extract_location(user)
        search_city = normalize_city(city)
        search_region = normalize_city(region) if region else None
        search_district = normalize_city(district) if district else None

        await _send_hot_offers_list(
            message,
            state,
            lang,
            city,
            search_city,
            search_region,
            search_district,
            latitude,
            longitude,
            offer_service,
            logger,
            page=0,
            edit_message=False,
        )

    @dp.callback_query(F.data == "hot_entry_offers")
    async def hot_entry_offers(callback: types.CallbackQuery, state: FSMContext) -> None:
        if not callback.from_user:
            await callback.answer()
            return
        msg = _callback_message(callback)
        if not msg:
            await callback.answer()
            return

        user_id = callback.from_user.id
        lang = db.get_user_language(user_id)
        user = db.get_user_model(user_id)
        if not user:
            await callback.answer(
                "Сессия истекла. Нажмите /start."
                if lang == "ru"
                else "Sessiya tugadi. /start bosing.",
                show_alert=True,
            )
            return

        await state.clear()

        city, region, district, latitude, longitude = _extract_location(user)
        search_city = normalize_city(city)
        search_region = normalize_city(region) if region else None
        search_district = normalize_city(district) if district else None

        sent = await _send_hot_offers_list(
            msg,
            state,
            lang,
            city,
            search_city,
            search_region,
            search_district,
            latitude,
            longitude,
            offer_service,
            logger,
            page=0,
            edit_message=True,
        )
        if not sent:
            await callback.answer(get_text(lang, "no_offers"), show_alert=True)
            return
        await callback.answer()

    @dp.callback_query(F.data == "hot_entry_stores")
    async def hot_entry_stores(callback: types.CallbackQuery, state: FSMContext) -> None:
        if not callback.from_user:
            await callback.answer()
            return
        msg = _callback_message(callback)
        if not msg:
            await callback.answer()
            return
        lang = db.get_user_language(callback.from_user.id)
        user = db.get_user_model(callback.from_user.id)
        if not user:
            await callback.answer(get_text(lang, "error"), show_alert=True)
            return

        await state.clear()
        city, region, district, latitude, longitude = _extract_location(user)
        search_city = normalize_city(city)
        search_region = normalize_city(region) if region else None
        search_district = normalize_city(district) if district else None

        await _send_store_list(
            msg,
            state,
            lang,
            city,
            search_city,
            search_region,
            search_district,
            latitude,
            longitude,
            offer_service,
            logger,
            page=0,
            edit_message=True,
            back_to_filters=False,
        )
        await callback.answer()

    @dp.callback_query(F.data == "hot_entry_back")
    async def hot_entry_back(callback: types.CallbackQuery, state: FSMContext) -> None:
        if not callback.from_user:
            await callback.answer()
            return
        msg = _callback_message(callback)
        if not msg:
            await callback.answer()
            return

        user_id = callback.from_user.id
        lang = db.get_user_language(user_id)
        user = db.get_user_model(user_id)
        if not user:
            await callback.answer(get_text(lang, "error"), show_alert=True)
            return

        await state.clear()

        city, region, district, latitude, longitude = _extract_location(user)
        search_city = normalize_city(city)
        search_region = normalize_city(region) if region else None
        search_district = normalize_city(district) if district else None

        await _send_hot_offers_list(
            msg,
            state,
            lang,
            city,
            search_city,
            search_region,
            search_district,
            latitude,
            longitude,
            offer_service,
            logger,
            page=0,
            edit_message=True,
        )
        await callback.answer()

    @dp.callback_query(F.data == "hot_offers")
    async def hot_offers_callback(callback: types.CallbackQuery, state: FSMContext) -> None:
        """Handle hot offers inline button (e.g., from cart empty state)."""
        if not callback.from_user:
            await callback.answer()
            return
        msg = _callback_message(callback)
        if not msg:
            await callback.answer()
            return

        user_id = callback.from_user.id
        lang = db.get_user_language(user_id)
        user = db.get_user_model(user_id)
        if not user:
            await callback.answer(
                "Сессия истекла. Нажмите /start."
                if lang == "ru"
                else "Sessiya tugadi. /start bosing.",
                show_alert=True,
            )
            return

        city, region, district, latitude, longitude = _extract_location(user)
        search_city = normalize_city(city)
        search_region = normalize_city(region) if region else None
        search_district = normalize_city(district) if district else None

        await callback.answer()
        data = await state.get_data()
        page = int(data.get("catalog_page", 0) or 0)

        sent = await _send_hot_offers_list(
            msg,
            state,
            lang,
            city,
            search_city,
            search_region,
            search_district,
            latitude,
            longitude,
            offer_service,
            logger,
            page=page,
            edit_message=True,
        )
        if not sent:
            await callback.answer(get_text(lang, "no_offers"), show_alert=True)
            return
        await callback.answer()

    @dp.callback_query(F.data.startswith("hot_page_"))
    async def hot_offers_page_handler(callback: types.CallbackQuery, state: FSMContext) -> None:
        """Handle hot offers pagination."""
        if not callback.from_user or not callback.data:
            await callback.answer()
            return
        msg = _callback_message(callback)
        if not msg:
            await callback.answer()
            return

        user_id = callback.from_user.id
        lang = db.get_user_language(user_id)
        user = db.get_user_model(user_id)
        if not user:
            await callback.answer(
                "Сессия истекла. Нажмите /start."
                if lang == "ru"
                else "Sessiya tugadi. /start bosing.",
                show_alert=True,
            )
            return

        try:
            page = int(callback.data.split("_")[-1])
        except (ValueError, IndexError):
            await callback.answer(get_text(lang, "error"), show_alert=True)
            return

        city, region, district, latitude, longitude = _extract_location(user)
        search_city = normalize_city(city)
        search_region = normalize_city(region) if region else None
        search_district = normalize_city(district) if district else None
        data = await state.get_data()
        sent = await _send_hot_offers_list(
            msg,
            state,
            lang,
            city,
            search_city,
            search_region,
            search_district,
            latitude,
            longitude,
            offer_service,
            logger,
            page=page,
            edit_message=True,
        )
        if not sent:
            await callback.answer(get_text(lang, "no_offers"), show_alert=True)
            return
        await callback.answer()

    @dp.callback_query(F.data.startswith("hot_offer_"))
    async def hot_offer_selected_handler(callback: types.CallbackQuery, state: FSMContext) -> None:
        """Handle hot offer selection - show offer card with cart/order buttons."""
        if not callback.from_user or not callback.data:
            await callback.answer()
            return
        msg = _callback_message(callback)
        if not msg:
            await callback.answer()
            return

        user_id = callback.from_user.id
        lang = db.get_user_language(user_id)

        try:
            offer_id = int(callback.data.split("_")[-1])
        except (ValueError, IndexError):
            await callback.answer(get_text(lang, "error"), show_alert=True)
            return

        offer = offer_service.get_offer_details(offer_id)
        if not offer:
            not_found = "Mahsulot topilmadi" if lang == "uz" else "Товар не найден"
            await callback.answer(not_found, show_alert=True)
            return

        # Check availability
        max_quantity = offer.quantity or 0
        if max_quantity <= 0:
            sold_out = "Mahsulot tugadi" if lang == "uz" else "Товар закончился"
            await callback.answer(sold_out, show_alert=True)
            return

        store = offer_service.get_store(offer.store_id) if offer.store_id else None
        text = _render_catalog_details(lang, offer, store)
        kb = offer_keyboards.catalog_details_keyboard(lang, offer_id)

        if await safe_edit_message(msg, text, reply_markup=kb):
            await callback.answer()
            return

        await safe_delete_message(msg)
        await msg.answer(text, parse_mode="HTML", reply_markup=kb)
        await callback.answer()

    @dp.callback_query(F.data.startswith("catalog_details_"))
    async def catalog_details_handler(callback: types.CallbackQuery, state: FSMContext) -> None:
        """Handle catalog details button."""
        if not callback.from_user or not callback.data:
            await callback.answer()
            return
        msg = _callback_message(callback)
        if not msg:
            await callback.answer()
            return

        user_id = callback.from_user.id
        lang = db.get_user_language(user_id)

        try:
            offer_id = int(callback.data.split("_")[-1])
        except (ValueError, IndexError):
            await callback.answer(get_text(lang, "error"), show_alert=True)
            return

        offer = offer_service.get_offer_details(offer_id)
        if not offer:
            not_found = "Mahsulot topilmadi" if lang == "uz" else "Товар не найден"
            await callback.answer(not_found, show_alert=True)
            return

        max_quantity = offer.quantity or 0
        if max_quantity <= 0:
            sold_out = "Mahsulot tugadi" if lang == "uz" else "Товар закончился"
            await callback.answer(sold_out, show_alert=True)
            return

        store = offer_service.get_store(offer.store_id) if offer.store_id else None
        text = _render_catalog_details(lang, offer, store)
        kb = offer_keyboards.catalog_details_keyboard(lang, offer_id)

        if await safe_edit_message(msg, text, reply_markup=kb):
            await callback.answer()
            return

        await safe_delete_message(msg)
        await msg.answer(text, parse_mode="HTML", reply_markup=kb)
        await callback.answer()

    @dp.callback_query(F.data == "hot_noop")
    async def hot_noop_handler(callback: types.CallbackQuery) -> None:
        """Handle noop button (page indicator)."""
        await callback.answer()

    @dp.callback_query(F.data == "catalog_noop")
    async def catalog_noop_handler(callback: types.CallbackQuery) -> None:
        await callback.answer()

    @dp.callback_query(F.data.startswith("catalog_page_"))
    async def catalog_page_handler(callback: types.CallbackQuery, state: FSMContext) -> None:
        if not callback.from_user or not callback.data:
            await callback.answer()
            return
        msg = _callback_message(callback)
        if not msg:
            await callback.answer()
            return
        user_id = callback.from_user.id
        lang = db.get_user_language(user_id)
        user = db.get_user_model(user_id)
        if not user:
            await callback.answer(get_text(lang, "error"), show_alert=True)
            return
        try:
            page = int(callback.data.split("_")[-1])
        except (ValueError, IndexError):
            await callback.answer()
            return

        city, region, district, latitude, longitude = _extract_location(user)
        search_city = normalize_city(city)
        search_region = normalize_city(region) if region else None
        search_district = normalize_city(district) if district else None

        await _send_hot_offers_list(
            msg,
            state,
            lang,
            city,
            search_city,
            search_region,
            search_district,
            latitude,
            longitude,
            offer_service,
            logger,
            page=page,
            edit_message=True,
        )
        await callback.answer()

    @dp.callback_query(F.data == "catalog_back")
    async def catalog_back_handler(callback: types.CallbackQuery, state: FSMContext) -> None:
        if not callback.from_user:
            await callback.answer()
            return
        msg = _callback_message(callback)
        if not msg:
            await callback.answer()
            return
        user_id = callback.from_user.id
        lang = db.get_user_language(user_id)
        user = db.get_user_model(user_id)
        if not user:
            await callback.answer(get_text(lang, "error"), show_alert=True)
            return
        city, region, district, latitude, longitude = _extract_location(user)
        search_city = normalize_city(city)
        search_region = normalize_city(region) if region else None
        search_district = normalize_city(district) if district else None
        data = await state.get_data()
        page = int(data.get("catalog_page", 0) or 0)

        await _send_hot_offers_list(
            msg,
            state,
            lang,
            city,
            search_city,
            search_region,
            search_district,
            latitude,
            longitude,
            offer_service,
            logger,
            page=page,
            edit_message=True,
        )
        await callback.answer()

    @dp.callback_query(F.data == "catalog_continue")
    async def catalog_continue_handler(callback: types.CallbackQuery, state: FSMContext) -> None:
        await catalog_back_handler(callback, state)

    @dp.callback_query(F.data == "catalog_filter")
    async def catalog_filter_handler(callback: types.CallbackQuery, state: FSMContext) -> None:
        if not callback.from_user:
            await callback.answer()
            return
        msg = _callback_message(callback)
        if not msg:
            await callback.answer()
            return
        lang = db.get_user_language(callback.from_user.id)
        await _send_filter_menu(msg, state, lang)
        await callback.answer()

    @dp.callback_query(F.data == "catalog_filter_reset")
    async def catalog_filter_reset_handler(callback: types.CallbackQuery, state: FSMContext) -> None:
        if not callback.from_user:
            await callback.answer()
            return
        msg = _callback_message(callback)
        if not msg:
            await callback.answer()
            return
        await state.update_data(
            catalog_store_id=None,
            catalog_store_name=None,
            catalog_category_id=None,
            catalog_category_label=None,
            catalog_min_discount=None,
            catalog_only_today=False,
        )
        user_id = callback.from_user.id
        lang = db.get_user_language(user_id)
        user = db.get_user_model(user_id)
        if not user:
            await callback.answer(get_text(lang, "error"), show_alert=True)
            return
        city, region, district, latitude, longitude = _extract_location(user)
        search_city = normalize_city(city)
        search_region = normalize_city(region) if region else None
        search_district = normalize_city(district) if district else None

        await _send_hot_offers_list(
            msg,
            state,
            lang,
            city,
            search_city,
            search_region,
            search_district,
            latitude,
            longitude,
            offer_service,
            logger,
            page=0,
            edit_message=True,
        )
        await callback.answer()

    @dp.callback_query(F.data == "catalog_filter_today")
    async def catalog_filter_today_handler(callback: types.CallbackQuery, state: FSMContext) -> None:
        if not callback.from_user:
            await callback.answer()
            return
        msg = _callback_message(callback)
        if not msg:
            await callback.answer()
            return
        data = await state.get_data()
        current = bool(data.get("catalog_only_today"))
        await state.update_data(catalog_only_today=not current)

        user_id = callback.from_user.id
        lang = db.get_user_language(user_id)
        user = db.get_user_model(user_id)
        if not user:
            await callback.answer(get_text(lang, "error"), show_alert=True)
            return
        city, region, district, latitude, longitude = _extract_location(user)
        search_city = normalize_city(city)
        search_region = normalize_city(region) if region else None
        search_district = normalize_city(district) if district else None

        await _send_hot_offers_list(
            msg,
            state,
            lang,
            city,
            search_city,
            search_region,
            search_district,
            latitude,
            longitude,
            offer_service,
            logger,
            page=0,
            edit_message=True,
        )
        await callback.answer()

    @dp.callback_query(F.data.startswith("catalog_filter_discount_"))
    async def catalog_filter_discount_handler(
        callback: types.CallbackQuery, state: FSMContext
    ) -> None:
        if not callback.from_user or not callback.data:
            await callback.answer()
            return
        msg = _callback_message(callback)
        if not msg:
            await callback.answer()
            return
        try:
            discount_value = callback.data.split("_")[-1]
            if discount_value == "any":
                min_discount = None
            else:
                min_discount = int(discount_value)
        except (ValueError, IndexError):
            await callback.answer()
            return

        await state.update_data(catalog_min_discount=min_discount)

        user_id = callback.from_user.id
        lang = db.get_user_language(user_id)
        user = db.get_user_model(user_id)
        if not user:
            await callback.answer(get_text(lang, "error"), show_alert=True)
            return
        city, region, district, latitude, longitude = _extract_location(user)
        search_city = normalize_city(city)
        search_region = normalize_city(region) if region else None
        search_district = normalize_city(district) if district else None

        await _send_hot_offers_list(
            msg,
            state,
            lang,
            city,
            search_city,
            search_region,
            search_district,
            latitude,
            longitude,
            offer_service,
            logger,
            page=0,
            edit_message=True,
        )
        await callback.answer()

    @dp.callback_query(F.data == "catalog_filter_category")
    async def catalog_filter_category(callback: types.CallbackQuery) -> None:
        if not callback.from_user:
            await callback.answer()
            return
        msg = _callback_message(callback)
        if not msg:
            await callback.answer()
            return
        lang = db.get_user_language(callback.from_user.id)
        text = get_text(lang, "catalog_filter_select_category")
        keyboard = _build_category_keyboard(lang)
        if not await safe_edit_message(msg, text, reply_markup=keyboard.as_markup()):
            await safe_delete_message(msg)
            await msg.answer(text, parse_mode="HTML", reply_markup=keyboard.as_markup())
        await callback.answer()

    @dp.callback_query(F.data == "catalog_clear_category")
    async def catalog_clear_category(callback: types.CallbackQuery, state: FSMContext) -> None:
        if not callback.from_user:
            await callback.answer()
            return
        msg = _callback_message(callback)
        if not msg:
            await callback.answer()
            return
        await state.update_data(catalog_category_id=None, catalog_category_label=None)

        user_id = callback.from_user.id
        lang = db.get_user_language(user_id)
        user = db.get_user_model(user_id)
        if not user:
            await callback.answer(get_text(lang, "error"), show_alert=True)
            return
        city, region, district, latitude, longitude = _extract_location(user)
        search_city = normalize_city(city)
        search_region = normalize_city(region) if region else None
        search_district = normalize_city(district) if district else None

        await _send_hot_offers_list(
            msg,
            state,
            lang,
            city,
            search_city,
            search_region,
            search_district,
            latitude,
            longitude,
            offer_service,
            logger,
            page=0,
            edit_message=True,
        )
        await callback.answer()

    @dp.callback_query(F.data.startswith("catalog_set_category_"))
    async def catalog_set_category(callback: types.CallbackQuery, state: FSMContext) -> None:
        if not callback.from_user or not callback.data:
            await callback.answer()
            return
        msg = _callback_message(callback)
        if not msg:
            await callback.answer()
            return
        lang = db.get_user_language(callback.from_user.id)
        category_id = callback.data.split("_", 3)[-1]
        category_label = _category_label(lang=lang, category=category_id)
        await state.update_data(
            catalog_category_id=category_id,
            catalog_category_label=category_label,
        )

        user_id = callback.from_user.id
        user = db.get_user_model(user_id)
        if not user:
            await callback.answer(get_text(lang, "error"), show_alert=True)
            return
        city, region, district, latitude, longitude = _extract_location(user)
        search_city = normalize_city(city)
        search_region = normalize_city(region) if region else None
        search_district = normalize_city(district) if district else None

        await _send_hot_offers_list(
            msg,
            state,
            lang,
            city,
            search_city,
            search_region,
            search_district,
            latitude,
            longitude,
            offer_service,
            logger,
            page=0,
            edit_message=True,
        )
        await callback.answer()

    @dp.callback_query(F.data == "catalog_filter_store")
    async def catalog_filter_store(callback: types.CallbackQuery, state: FSMContext) -> None:
        if not callback.from_user:
            await callback.answer()
            return
        msg = _callback_message(callback)
        if not msg:
            await callback.answer()
            return
        user_id = callback.from_user.id
        lang = db.get_user_language(user_id)
        user = db.get_user_model(user_id)
        if not user:
            await callback.answer(get_text(lang, "error"), show_alert=True)
            return

        city, region, district, latitude, longitude = _extract_location(user)
        search_city = normalize_city(city)
        search_region = normalize_city(region) if region else None
        search_district = normalize_city(district) if district else None

        await _send_store_list(
            msg,
            state,
            lang,
            city,
            search_city,
            search_region,
            search_district,
            latitude,
            longitude,
            offer_service,
            logger,
            page=0,
            edit_message=True,
            back_to_filters=True,
        )
        await callback.answer()

    @dp.callback_query(F.data.startswith("catalog_filter_store_page_"))
    async def catalog_filter_store_page(
        callback: types.CallbackQuery, state: FSMContext
    ) -> None:
        if not callback.from_user or not callback.data:
            await callback.answer()
            return
        msg = _callback_message(callback)
        if not msg:
            await callback.answer()
            return
        try:
            page = int(callback.data.split("_")[-1])
        except (ValueError, IndexError):
            await callback.answer()
            return
        user_id = callback.from_user.id
        lang = db.get_user_language(user_id)
        user = db.get_user_model(user_id)
        if not user:
            await callback.answer(get_text(lang, "error"), show_alert=True)
            return
        city, region, district, latitude, longitude = _extract_location(user)
        search_city = normalize_city(city)
        search_region = normalize_city(region) if region else None
        search_district = normalize_city(district) if district else None

        await _send_store_list(
            msg,
            state,
            lang,
            city,
            search_city,
            search_region,
            search_district,
            latitude,
            longitude,
            offer_service,
            logger,
            page=page,
            edit_message=True,
            back_to_filters=True,
        )
        await callback.answer()

    @dp.callback_query(F.data.startswith("catalog_filter_store_select_"))
    async def catalog_filter_store_select(
        callback: types.CallbackQuery, state: FSMContext
    ) -> None:
        if not callback.from_user or not callback.data:
            await callback.answer()
            return
        msg = _callback_message(callback)
        if not msg:
            await callback.answer()
            return
        lang = db.get_user_language(callback.from_user.id)
        try:
            store_id = int(callback.data.split("_")[-1])
        except (ValueError, IndexError):
            await callback.answer(get_text(lang, "error"), show_alert=True)
            return
        store = offer_service.get_store(store_id)
        await state.update_data(
            catalog_store_id=store_id,
            catalog_store_name=store.name if store else None,
        )

        user_id = callback.from_user.id
        user = db.get_user_model(user_id)
        if not user:
            await callback.answer(get_text(lang, "error"), show_alert=True)
            return
        city, region, district, latitude, longitude = _extract_location(user)
        search_city = normalize_city(city)
        search_region = normalize_city(region) if region else None
        search_district = normalize_city(district) if district else None

        await _send_hot_offers_list(
            msg,
            state,
            lang,
            city,
            search_city,
            search_region,
            search_district,
            latitude,
            longitude,
            offer_service,
            logger,
            page=0,
            edit_message=True,
        )
        await callback.answer()

    @dp.callback_query(F.data == "catalog_store_clear")
    async def catalog_store_clear(callback: types.CallbackQuery, state: FSMContext) -> None:
        if not callback.from_user:
            await callback.answer()
            return
        msg = _callback_message(callback)
        if not msg:
            await callback.answer()
            return
        await state.update_data(catalog_store_id=None, catalog_store_name=None)

        user_id = callback.from_user.id
        lang = db.get_user_language(user_id)
        user = db.get_user_model(user_id)
        if not user:
            await callback.answer(get_text(lang, "error"), show_alert=True)
            return
        city, region, district, latitude, longitude = _extract_location(user)
        search_city = normalize_city(city)
        search_region = normalize_city(region) if region else None
        search_district = normalize_city(district) if district else None

        await _send_hot_offers_list(
            msg,
            state,
            lang,
            city,
            search_city,
            search_region,
            search_district,
            latitude,
            longitude,
            offer_service,
            logger,
            page=0,
            edit_message=True,
        )
        await callback.answer()

    @dp.callback_query(F.data == "catalog_stores")
    async def catalog_stores(callback: types.CallbackQuery, state: FSMContext) -> None:
        if not callback.from_user:
            await callback.answer()
            return
        msg = _callback_message(callback)
        if not msg:
            await callback.answer()
            return
        user_id = callback.from_user.id
        lang = db.get_user_language(user_id)
        user = db.get_user_model(user_id)
        if not user:
            await callback.answer(get_text(lang, "error"), show_alert=True)
            return
        city, region, district, latitude, longitude = _extract_location(user)
        search_city = normalize_city(city)
        search_region = normalize_city(region) if region else None
        search_district = normalize_city(district) if district else None

        await _send_store_list(
            msg,
            state,
            lang,
            city,
            search_city,
            search_region,
            search_district,
            latitude,
            longitude,
            offer_service,
            logger,
            page=0,
            edit_message=True,
            back_to_filters=False,
        )
        await callback.answer()

    @dp.callback_query(F.data.startswith("catalog_store_page_"))
    async def catalog_store_page(callback: types.CallbackQuery, state: FSMContext) -> None:
        if not callback.from_user or not callback.data:
            await callback.answer()
            return
        msg = _callback_message(callback)
        if not msg:
            await callback.answer()
            return
        try:
            page = int(callback.data.split("_")[-1])
        except (ValueError, IndexError):
            await callback.answer()
            return
        user_id = callback.from_user.id
        lang = db.get_user_language(user_id)
        user = db.get_user_model(user_id)
        if not user:
            await callback.answer(get_text(lang, "error"), show_alert=True)
            return
        city, region, district, latitude, longitude = _extract_location(user)
        search_city = normalize_city(city)
        search_region = normalize_city(region) if region else None
        search_district = normalize_city(district) if district else None

        await _send_store_list(
            msg,
            state,
            lang,
            city,
            search_city,
            search_region,
            search_district,
            latitude,
            longitude,
            offer_service,
            logger,
            page=page,
            edit_message=True,
            back_to_filters=False,
        )
        await callback.answer()

    @dp.callback_query(F.data.startswith("catalog_store_select_"))
    async def catalog_store_select(callback: types.CallbackQuery, state: FSMContext) -> None:
        if not callback.from_user or not callback.data:
            await callback.answer()
            return
        msg = _callback_message(callback)
        if not msg:
            await callback.answer()
            return
        lang = db.get_user_language(callback.from_user.id)
        try:
            store_id = int(callback.data.split("_")[-1])
        except (ValueError, IndexError):
            await callback.answer(get_text(lang, "error"), show_alert=True)
            return
        store = offer_service.get_store(store_id)
        await state.update_data(
            catalog_store_id=store_id,
            catalog_store_name=store.name if store else None,
        )

        user_id = callback.from_user.id
        user = db.get_user_model(user_id)
        if not user:
            await callback.answer(get_text(lang, "error"), show_alert=True)
            return
        city, region, district, latitude, longitude = _extract_location(user)
        search_city = normalize_city(city)
        search_region = normalize_city(region) if region else None
        search_district = normalize_city(district) if district else None

        await _send_hot_offers_list(
            msg,
            state,
            lang,
            city,
            search_city,
            search_region,
            search_district,
            latitude,
            longitude,
            offer_service,
            logger,
            page=0,
            edit_message=True,
        )
        await callback.answer()

    @dp.message(BrowseOffers.offer_list, F.text.regexp(r"^\d+$"))
    async def select_offer_by_number(message: types.Message, state: FSMContext) -> None:
        if not message.from_user:
            return
        logger.info(
            f"📥 select_offer_by_number triggered: user={message.from_user.id}, text={message.text}"
        )
        user_id = message.from_user.id
        lang = db.get_user_language(user_id)
        data = await state.get_data()
        offer_list: list[int] = data.get("offer_list", [])
        logger.info(f"📥 FSM data: offer_list={offer_list}, state={await state.get_state()}")
        if not offer_list:
            # Friendly hint if session state lost or expired
            await message.answer(
                "Список устарел. Откройте раздел еще раз."
                if lang == "ru"
                else "Ro'yxat eskirgan. Bo'limni qayta oching.",
            )
            await state.clear()
            return
        try:
            if not message.text:
                await message.answer(_invalid_number_text(lang, "товара"))
                return
            number = int(message.text)
        except ValueError:
            await message.answer(_invalid_number_text(lang, "товара"))
            return
        if number < 1 or number > len(offer_list):
            await message.answer(_range_text(lang, len(offer_list), "товара"))
            return
        offer_id = offer_list[number - 1]
        details = offer_service.get_offer_details(offer_id)
        if not details:
            await message.answer(get_text(lang, "error"))
            await state.clear()
            return

        # Determine context: hot offers or store offers
        store_id = data.get("current_store_id")
        if store_id:
            current_page = data.get("store_offers_page", 0)
            category = data.get("store_category", "all")
            await state.update_data(
                last_store_id=store_id,
                last_store_page=current_page,
                last_store_category=category,
                source="store",
            )
            await _send_offer_details(
                message,
                details,
                lang,
                with_back=True,
                back_callback=f"back_to_store_offers_{store_id}",
            )
            return

        # Hot offers context (default)
        current_page = data.get('hot_offers_page', 0)
        await state.update_data(last_hot_page=current_page, source="hot")
        await _send_offer_details(message, details, lang, with_back=True)

    @dp.callback_query(F.data == "offers_all")
    async def show_all_offers(callback: types.CallbackQuery, state: FSMContext) -> None:
        if not callback.from_user:
            await callback.answer()
            return
        msg = _callback_message(callback)
        if not msg:
            await callback.answer()
            return
        lang = db.get_user_language(callback.from_user.id)
        user = db.get_user_model(callback.from_user.id)
        if not user:
            await callback.answer(get_text(lang, "error"), show_alert=True)
            return
        city, region, district, latitude, longitude = _extract_location(user)
        search_city = normalize_city(city)
        search_region = normalize_city(region) if region else None
        search_district = normalize_city(district) if district else None
        await state.update_data(catalog_category_id=None, catalog_category_label=None)

        sent = await _send_hot_offers_list(
            msg,
            state,
            lang,
            city,
            search_city,
            search_region,
            search_district,
            latitude,
            longitude,
            offer_service,
            logger,
            page=0,
            edit_message=True,
        )
        if not sent:
            await callback.answer(get_text(lang, "no_offers"), show_alert=True)
            return
        await callback.answer()

    @dp.callback_query(F.data.startswith("offers_cat_"))
    async def filter_offers_by_category(callback: types.CallbackQuery, state: FSMContext) -> None:
        if not callback.from_user or not callback.data:
            await callback.answer()
            return
        msg = _callback_message(callback)
        if not msg:
            await callback.answer()
            return
        lang = db.get_user_language(callback.from_user.id)
        user = db.get_user_model(callback.from_user.id)
        if not user:
            await callback.answer(get_text(lang, "error"), show_alert=True)
            return

        city, region, district, latitude, longitude = _extract_location(user)
        search_city = normalize_city(city)
        search_region = normalize_city(region) if region else None
        search_district = normalize_city(district) if district else None

        categories = get_product_categories(lang)
        try:
            cat_index = int(callback.data.split("_")[-1])
        except (ValueError, IndexError) as e:
            logger.error(f"Invalid cat_index in callback data: {callback.data}, error: {e}")
            await callback.answer(get_text(lang, "error"), show_alert=True)
            return

        if cat_index >= len(categories):
            await callback.answer(get_text(lang, "error"), show_alert=True)
            return

        category_label = categories[cat_index]
        normalized = normalize_category(category_label)

        await state.update_data(
            catalog_category_id=normalized,
            catalog_category_label=category_label,
        )

        sent = await _send_hot_offers_list(
            msg,
            state,
            lang,
            city,
            search_city,
            search_region,
            search_district,
            latitude,
            longitude,
            offer_service,
            logger,
            page=0,
            edit_message=True,
        )
        if not sent:
            await callback.answer(get_text(lang, "no_offers"), show_alert=True)
            return
        await callback.answer()

    @dp.callback_query(F.data == "filter_all")
    async def show_all_offers_filter(callback: types.CallbackQuery, state: FSMContext) -> None:
        if not callback.from_user:
            await callback.answer()
            return
        msg = _callback_message(callback)
        if not msg:
            await callback.answer()
            return
        lang = db.get_user_language(callback.from_user.id)
        user = db.get_user_model(callback.from_user.id)
        if not user:
            await callback.answer(get_text(lang, "error"), show_alert=True)
            return
        city, region, district, latitude, longitude = _extract_location(user)
        search_city = normalize_city(city)
        search_region = normalize_city(region) if region else None
        search_district = normalize_city(district) if district else None

        await callback.answer()
        await _send_hot_offers_list(
            msg,
            state,
            lang,
            city,
            search_city,
            search_region,
            search_district,
            latitude,
            longitude,
            offer_service,
            logger,
            page=0,
            edit_message=True,
        )

    @dp.callback_query(F.data == "back_to_hot")
    async def back_to_hot(callback: types.CallbackQuery, state: FSMContext) -> None:
        if not callback.from_user:
            await callback.answer()
            return
        msg = _callback_message(callback)
        if not msg:
            await callback.answer()
            return
        user_id = callback.from_user.id
        lang = db.get_user_language(user_id)
        user = db.get_user_model(user_id)
        if not user:
            await callback.answer(get_text(lang, "error"), show_alert=True)
            return
        city, region, district, latitude, longitude = _extract_location(user)
        search_city = normalize_city(city)
        search_region = normalize_city(region) if region else None
        search_district = normalize_city(district) if district else None

        data = await state.get_data()
        last_page = data.get("catalog_page", 0)

        if getattr(msg, "photo", None):
            await safe_delete_message(msg)
            await _send_hot_offers_list(
                msg,
                state,
                lang,
                city,
                search_city,
                search_region,
                search_district,
                latitude,
                longitude,
                offer_service,
                logger,
                page=last_page,
                edit_message=False,
            )
        else:
            await _send_hot_offers_list(
                msg,
                state,
                lang,
                city,
                search_city,
                search_region,
                search_district,
                latitude,
                longitude,
                offer_service,
                logger,
                page=last_page,
                edit_message=True,
            )
        await callback.answer()

    # ------------------------------------------------------------------
    # Helper functions (kept as inner functions to use closures)
    # ------------------------------------------------------------------

    def _build_category_keyboard(lang: str) -> InlineKeyboardBuilder:
        categories = get_product_categories(lang)
        builder = InlineKeyboardBuilder()
        builder.button(text=get_text(lang, "catalog_category_all"), callback_data="catalog_clear_category")
        for idx, category in enumerate(categories):
            cat_id = _CATEGORY_IDS[idx] if idx < len(_CATEGORY_IDS) else "other"
            builder.button(text=category, callback_data=f"catalog_set_category_{cat_id}")
        builder.button(text=get_text(lang, "catalog_filter_back"), callback_data="catalog_filter")

        rows = [1]
        rows.extend([2] * ((len(categories) + 1) // 2))
        rows.append(1)
        builder.adjust(*rows)
        return builder

    async def _send_filter_menu(
        target: types.Message,
        state: FSMContext,
        lang: str,
    ) -> None:
        data = await state.get_data()
        filters = _catalog_filters_from_state(data)

        store_label = filters.get("store_name") or get_text(lang, "catalog_store_all")
        category_label = filters.get("category_label") or get_text(lang, "catalog_category_all")
        discount_label = (
            f"{filters.get('min_discount')}%+"
            if filters.get("min_discount")
            else get_text(lang, "catalog_discount_any")
        )
        today_label = get_text(
            lang,
            "catalog_filter_on" if filters.get("only_today") else "catalog_filter_off",
        )

        text = (
            f"{get_text(lang, 'catalog_filter_title')}\n\n"
            f"{get_text(lang, 'catalog_filter_store')}: {store_label}\n"
            f"{get_text(lang, 'catalog_filter_category')}: {category_label}\n"
            f"{get_text(lang, 'catalog_filter_discount')}: {discount_label}\n"
            f"{get_text(lang, 'catalog_filter_today')}: {today_label}"
        )

        kb = InlineKeyboardBuilder()
        kb.button(
            text=f"🏪 {get_text(lang, 'catalog_filter_store')}",
            callback_data="catalog_filter_store",
        )
        kb.button(
            text=f"🏷 {get_text(lang, 'catalog_filter_category')}",
            callback_data="catalog_filter_category",
        )
        kb.button(text=get_text(lang, "catalog_discount_30"), callback_data="catalog_filter_discount_30")
        kb.button(text=get_text(lang, "catalog_discount_50"), callback_data="catalog_filter_discount_50")
        kb.button(text=get_text(lang, "catalog_discount_70"), callback_data="catalog_filter_discount_70")
        kb.button(text=get_text(lang, "catalog_discount_any"), callback_data="catalog_filter_discount_any")
        kb.button(text=get_text(lang, "catalog_filter_today"), callback_data="catalog_filter_today")
        kb.button(text=get_text(lang, "catalog_filter_reset"), callback_data="catalog_filter_reset")
        kb.button(text=get_text(lang, "catalog_filter_back"), callback_data="catalog_back")
        kb.adjust(1, 1, 3, 1, 1, 2)

        if not await safe_edit_message(target, text, reply_markup=kb.as_markup()):
            await safe_delete_message(target)
            await target.answer(text, parse_mode="HTML", reply_markup=kb.as_markup())

    async def _send_store_list(
        target: types.Message,
        state: FSMContext,
        lang: str,
        city: str,
        search_city: str,
        search_region: str | None,
        search_district: str | None,
        latitude: float | None,
        longitude: float | None,
        service: OfferService,
        log: Any,
        page: int = 0,
        edit_message: bool = False,
        back_to_filters: bool = False,
    ) -> None:
        try:
            stores = service.list_active_stores(
                search_city,
                region=search_region,
                district=search_district,
                latitude=latitude,
                longitude=longitude,
            )
            if not stores:
                text = get_text(lang, "no_stores_in_city", city=city)
                if edit_message:
                    if not await safe_edit_message(target, text):
                        await safe_delete_message(target)
                        await target.answer(text)
                else:
                    await target.answer(text)
                return

            total_count = len(stores)
            total_pages = max(1, (total_count + STORES_PER_PAGE - 1) // STORES_PER_PAGE)
            page = max(0, min(int(page), total_pages - 1))
            start_idx = page * STORES_PER_PAGE
            page_stores = stores[start_idx : start_idx + STORES_PER_PAGE]

            title = (
                get_text(lang, "catalog_filter_select_store")
                if back_to_filters
                else get_text(lang, "catalog_stores_button")
            )
            text = (
                f"{title}\n"
                f"{city} • {get_text(lang, 'catalog_today')}\n"
                f"{get_text(lang, 'catalog_stores_found', count=total_count)}"
            )

            kb = InlineKeyboardBuilder()
            kb.button(text=get_text(lang, "catalog_store_all"), callback_data="catalog_store_clear")
            select_prefix = (
                "catalog_filter_store_select" if back_to_filters else "catalog_store_select"
            )
            for store in page_stores:
                label = f"{store.name} ({store.offers_count})"
                kb.button(text=label, callback_data=f"{select_prefix}_{store.id}")

            kb.adjust(*([1] * (len(page_stores) + 1)))

            nav_builder = InlineKeyboardBuilder()
            page_prefix = (
                "catalog_filter_store_page" if back_to_filters else "catalog_store_page"
            )
            prev_cb = f"{page_prefix}_{page - 1}" if page > 0 else "catalog_noop"
            next_cb = f"{page_prefix}_{page + 1}" if page < total_pages - 1 else "catalog_noop"
            nav_builder.button(text="◀️", callback_data=prev_cb)
            nav_builder.button(text=f"{page + 1} / {total_pages}", callback_data="catalog_noop")
            nav_builder.button(text="▶️", callback_data=next_cb)
            nav_builder.adjust(3)
            kb.attach(nav_builder)

            back_cb = "catalog_filter" if back_to_filters else "catalog_back"
            back_builder = InlineKeyboardBuilder()
            back_builder.button(text=get_text(lang, "catalog_filter_back"), callback_data=back_cb)
            back_builder.adjust(1)
            kb.attach(back_builder)

            if edit_message:
                if not await safe_edit_message(target, text, reply_markup=kb.as_markup()):
                    await safe_delete_message(target)
                    await target.answer(text, parse_mode="HTML", reply_markup=kb.as_markup())
            else:
                await target.answer(text, parse_mode="HTML", reply_markup=kb.as_markup())
        except Exception as exc:  # pragma: no cover
            log.error("Failed to send store list: %s", exc)
            await target.answer(get_text(lang, "error"))
    async def _send_hot_offers_list(
        target: types.Message,
        state: FSMContext,
        lang: str,
        city: str,
        search_city: str,
        search_region: str | None,
        search_district: str | None,
        latitude: float | None,
        longitude: float | None,
        service: OfferService,
        log: Any,
        page: int = 0,
        edit_message: bool = False,
    ) -> bool:
        """Send catalog list with compact view. Returns False for empty filtered lists."""
        ITEMS_PER_PAGE = OFFERS_PER_PAGE
        try:
            state_data = await state.get_data()
            filters = _catalog_filters_from_state(state_data)
            offset = max(0, page) * ITEMS_PER_PAGE

            result = service.list_hot_offers(
                search_city,
                limit=ITEMS_PER_PAGE,
                offset=offset,
                region=search_region,
                district=search_district,
                latitude=latitude,
                longitude=longitude,
                min_discount=filters.get("min_discount"),
                category=filters.get("category_id"),
                store_id=filters.get("store_id"),
                only_today=filters.get("only_today", False),
            )

            total_count = result.total
            if total_count <= 0:
                text = _render_empty_catalog(lang)
                kb = _catalog_empty_keyboard(lang)
                if edit_message:
                    if not await safe_edit_message(target, text, reply_markup=kb.as_markup()):
                        await safe_delete_message(target)
                        await target.answer(text, parse_mode="HTML", reply_markup=kb.as_markup())
                else:
                    await target.answer(text, parse_mode="HTML", reply_markup=kb.as_markup())
                return True

            total_pages = max(1, (total_count + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE)
            if page >= total_pages:
                page = max(0, total_pages - 1)
                offset = page * ITEMS_PER_PAGE
                result = service.list_hot_offers(
                    search_city,
                    limit=ITEMS_PER_PAGE,
                    offset=offset,
                    region=search_region,
                    district=search_district,
                    latitude=latitude,
                    longitude=longitude,
                    min_discount=filters.get("min_discount"),
                    category=filters.get("category_id"),
                    store_id=filters.get("store_id"),
                    only_today=filters.get("only_today", False),
                )

            items = list(result.items)
            await state.set_state(BrowseOffers.offer_list)
            await state.update_data(
                offer_list=[offer.id for offer in items],
                catalog_page=page,
                catalog_store_id=filters.get("store_id"),
                catalog_store_name=filters.get("store_name"),
                catalog_category_id=filters.get("category_id"),
                catalog_category_label=filters.get("category_label"),
                catalog_min_discount=filters.get("min_discount"),
                catalog_only_today=filters.get("only_today", False),
            )

            text = offer_templates.render_hot_offers_list(
                lang,
                city,
                items,
                total_count,
                "",
                offset=page * ITEMS_PER_PAGE,
            )

            keyboard = offer_keyboards.hot_offers_compact_keyboard(
                lang,
                items,
                page,
                total_pages,
                show_filters=True,
                show_stores=True,
                show_reset=_filters_active(filters),
            )

            if edit_message:
                if not await safe_edit_message(target, text, reply_markup=keyboard):
                    await safe_delete_message(target)
                    await target.answer(text, parse_mode="HTML", reply_markup=keyboard)
            else:
                await target.answer(text, parse_mode="HTML", reply_markup=keyboard)
            return True

        except Exception as exc:  # pragma: no cover
            log.error("Failed to send hot offers: %s", exc)
            await target.answer(get_text(lang, "error"))
            return False

    async def _send_offer_details(
        message: types.Message,
        offer: OfferDetails,
        lang: str,
        with_back: bool = False,
        back_callback: str | None = None,
        back_text: str | None = None,
    ) -> None:
        store = offer_service.get_store(offer.store_id)
        text = offer_templates.render_offer_details(lang, offer, store)
        back_cb = back_callback or "back_to_hot"
        if with_back:
            keyboard = offer_keyboards.offer_details_with_back_keyboard(
                lang,
                offer.id,
                offer.store_id,
                store.delivery_enabled if store else False,
                back_callback=back_cb,
                back_text=back_text,
            )
        else:
            keyboard = offer_keyboards.offer_details_keyboard(
                lang, offer.id, offer.store_id, store.delivery_enabled if store else False
            )
        if offer.photo:
            # Try editing caption if original is photo, otherwise send new photo
            if getattr(message, "photo", None):
                try:
                    await message.edit_caption(
                        caption=text, parse_mode="HTML", reply_markup=keyboard
                    )
                    return
                except Exception:
                    pass
            try:
                await message.answer_photo(
                    photo=offer.photo,
                    caption=text,
                    parse_mode="HTML",
                    reply_markup=keyboard,
                )
                return
            except Exception:  # pragma: no cover - fallback to text only
                pass
        try:
            await message.edit_text(text, parse_mode="HTML", reply_markup=keyboard)
        except Exception:
            await message.answer(text, parse_mode="HTML", reply_markup=keyboard)

    async def _send_offer_details_edit(
        message: types.Message,
        offer: OfferDetails,
        lang: str,
        offer_id: int,
    ) -> None:
        """Edit current message to show offer details (no new message)."""
        store = offer_service.get_store(offer.store_id)
        text = offer_templates.render_offer_details(lang, offer, store)

        # Keyboard with back button
        keyboard = offer_keyboards.offer_details_with_back_keyboard(
            lang, offer.id, offer.store_id, store.delivery_enabled if store else False
        )

        # If offer has photo, prefer editing caption or sending new photo without deleting
        if offer.photo:
            if getattr(message, "photo", None):
                try:
                    await message.edit_caption(
                        caption=text,
                        parse_mode="HTML",
                        reply_markup=keyboard,
                    )
                    return
                except Exception:
                    pass
            try:
                await message.answer_photo(
                    photo=offer.photo,
                    caption=text,
                    parse_mode="HTML",
                    reply_markup=keyboard,
                )
                return
            except Exception:
                pass

        # Try to edit text message
        try:
            await message.edit_text(text, parse_mode="HTML", reply_markup=keyboard)
        except Exception:
            await message.answer(text, parse_mode="HTML", reply_markup=keyboard)

    async def _send_offer_card(
        message: types.Message,
        offer: OfferListItem,
        lang: str,
    ) -> None:
        text = offer_templates.render_offer_card(lang, offer)
        keyboard = offer_keyboards.offer_quick_keyboard(
            lang, offer.id, offer.store_id, offer.delivery_enabled
        )

        # If offer has a photo, send it as a photo message with caption to be consistent
        # with search and seller flows. Fallback to text if sending photo fails.
        if getattr(offer, "photo", None):
            try:
                await message.answer_photo(
                    photo=offer.photo,
                    caption=text,
                    parse_mode="HTML",
                    reply_markup=keyboard,
                )
                return
            except Exception:
                # Fall back to text-only message on any failure
                pass

        await message.answer(text, parse_mode="HTML", reply_markup=keyboard)

    async def _show_offers_catalog(
        callback: types.CallbackQuery,
        fetcher: FetchOffersFn,
        log: Any,
    ) -> None:
        if not callback.from_user:
            await callback.answer()
            return
        msg = _callback_message(callback)
        if not msg:
            await callback.answer()
            return
        lang = db.get_user_language(callback.from_user.id)
        user = db.get_user_model(callback.from_user.id)
        if not user:
            await callback.answer(get_text(lang, "error"), show_alert=True)
            return
        city, region, district, _, _ = _extract_location(user)
        search_city = normalize_city(city)
        search_region = normalize_city(region) if region else None
        search_district = normalize_city(district) if district else None
        offers: list[OfferListItem] = fetcher(search_city, 20, search_region, search_district)
        if not offers:
            await callback.answer("Нет доступных предложений", show_alert=True)
            return
        await callback.answer()
        header = (
            f"<b>{'ВСЕ ПРЕДЛОЖЕНИЯ' if lang == 'ru' else 'BARCHA TAKLIFLAR'}</b>\n"
            f"{city}\n\n"
            f"{'Найдено' if lang == 'ru' else 'Topildi'}: {len(offers)}"
        )
        await msg.edit_text(
            header,
            parse_mode="HTML",
            reply_markup=offers_category_filter(lang),
        )
        for offer in offers[:10]:
            await _send_offer_card(msg, offer, lang)
            await asyncio.sleep(0.1)






