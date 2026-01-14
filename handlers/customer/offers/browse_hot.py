"""Hot offers and catalog browsing handlers split from browse.py."""
from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any

from aiogram import Dispatcher, F, types
from aiogram.fsm.context import FSMContext

from app.core.utils import normalize_city
from app.keyboards import business_type_keyboard
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
_CATEGORY_IDS = ["bakery", "dairy", "meat", "fruits", "vegetables", "drinks", "snacks", "frozen"]


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
        return f"💰 {_format_money(current)} {currency} (-{discount_pct}%)"
    return f"💰 {_format_money(current)} {currency}"


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
) -> str:
    page_label = "Стр." if lang == "ru" else "Sah."
    page_info = f"{page_label} {page + 1}"
    if total_pages:
        page_info += f"/{total_pages}"
    lines = [title, f"📍 {city} | {page_info}", "-" * 24]

    for idx, offer in enumerate(offers, start=1):
        title_line = _short_title(offer.title, limit=28)
        price_line = _offer_price_line(offer, lang)
        store_name = _short_store(getattr(offer, "store_name", "") or "", limit=16)
        meta = f"{price_line}"
        if store_name:
            meta += f" | 🏪 {store_name}"
        lines.append(f"{idx}. <b>{title_line}</b>")
        lines.append(f"   {meta}")
        lines.append("")

    lines.append(get_text(lang, "select_by_number"))
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
                "⚠️ Сессия устарела. Нажмите /start и откройте ‘🏪 Магазины и акции’ заново."
                if lang == "ru"
                else "⚠️ Sessiya eskirgan. /start ni bosing va ‘🏪 Do'konlar va aksiyalar’ ni qayta oching.",
            )
            return
        city, region, district, latitude, longitude = _extract_location(user)
        search_city = normalize_city(city)
        search_region = normalize_city(region) if region else None
        search_district = normalize_city(district) if district else None

        entry_text = (
            f"🏪 <b>{get_text(lang, 'hot_offers')}</b>\n\n"
            f"📍 {city}\n"
            f"{get_text(lang, 'hot_offers_subtitle')}"
        )
        await message.answer(
            entry_text,
            parse_mode="HTML",
            reply_markup=offer_keyboards.hot_entry_keyboard(lang),
        )

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
                "⚠️ Сессия устарела. Нажмите /start и откройте ‘🏪 Магазины и акции’ заново."
                if lang == "ru"
                else "⚠️ Sessiya eskirgan. /start ni bosing va ‘🏪 Do'konlar va aksiyalar’ ni qayta oching.",
                show_alert=True,
            )
            return

        city, region, district, latitude, longitude = _extract_location(user)
        search_city = normalize_city(city)
        search_region = normalize_city(region) if region else None
        search_district = normalize_city(district) if district else None

        await callback.answer()
        data = await state.get_data()
        page = int(data.get("hot_offers_page", 0) or 0)
        filter_mode = data.get("hot_filter_mode", "hot")
        category_id = data.get("hot_filter_value")
        category_label = data.get("hot_filter_label")
        show_entry_back = data.get("hot_entry_back")

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
            show_entry_back=show_entry_back,
            filter_mode=filter_mode,
            category_id=category_id,
            category_label=category_label,
        )
        if not sent:
            await callback.answer(get_text(lang, "no_offers"), show_alert=True)
            return
        await callback.answer("🔄", show_alert=False)

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
                "⚠️ Сессия устарела. Нажмите /start и откройте ‘🏪 Магазины и акции’ заново."
                if lang == "ru"
                else "⚠️ Sessiya eskirgan. /start ni bosing va ‘🏪 Do'konlar va aksiyalar’ ni qayta oching.",
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
        filter_mode = data.get("hot_filter_mode", "hot")
        category_id = data.get("hot_filter_value")
        category_label = data.get("hot_filter_label")
        show_entry_back = data.get("hot_entry_back")

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
            show_entry_back=show_entry_back,
            filter_mode=filter_mode,
            category_id=category_id,
            category_label=category_label,
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

        # Save current page for back navigation
        data = await state.get_data()
        current_page = data.get("hot_offers_page", 0)
        await state.update_data(last_hot_page=current_page, source="hot")

        # Check availability
        max_quantity = offer.quantity or 0
        if max_quantity <= 0:
            sold_out = "Mahsulot tugadi" if lang == "uz" else "Товар закончился"
            await callback.answer(sold_out, show_alert=True)
            return

        # Get store details
        store = offer_service.get_store(offer.store_id) if offer.store_id else None
        delivery_enabled = store.delivery_enabled if store else False

        text = offer_templates.render_offer_details(lang, offer, store)

        # Use keyboard with cart buttons
        kb = offer_keyboards.offer_details_with_back_keyboard(
            lang, offer_id, offer.store_id, delivery_enabled
        )

        # Send offer card - keep one active message
        if offer.photo:
            try:
                await msg.answer_photo(
                    photo=offer.photo, caption=text, parse_mode="HTML", reply_markup=kb
                )
                await safe_delete_message(msg)
                await callback.answer()
                return
            except Exception:
                pass

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
                "⚠️ Список товаров устарел. Нажмите ‘🏪 Магазины и акции’ ещё раз."
                if lang == "ru"
                else "⚠️ Mahsulotlar ro'yxati eskirgan. ‘🏪 Do'konlar va aksiyalar’ tugmasini qayta bosing.",
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
        current_page = data.get("hot_offers_page", 0)
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
        data = await state.get_data()
        show_entry_back = data.get("hot_entry_back")

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
            show_entry_back=show_entry_back,
            filter_mode="all",
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

        data = await state.get_data()
        show_entry_back = data.get("hot_entry_back")

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
            show_entry_back=show_entry_back,
            filter_mode="category",
            category_id=normalized,
            category_label=category_label,
        )
        if not sent:
            no_offers_msg = (
                f"В категории {category_label} нет предложений"
                if lang == "ru"
                else f"{category_label} toifasida takliflar yo'q"
            )
            await callback.answer(no_offers_msg, show_alert=True)
            return
        await callback.answer()

    @dp.callback_query(F.data == "filter_all")
    async def show_all_offers_filter(callback: types.CallbackQuery) -> None:
        await _show_offers_catalog(callback, offer_service.list_top_offers, logger)

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

        # Get last page from state or default to 0
        data = await state.get_data()
        last_page = data.get("last_hot_page", 0)

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
        show_entry_back: bool | None = None,
        filter_mode: str = "hot",
        category_id: str | None = None,
        category_label: str | None = None,
    ) -> bool:
        """Send offers list with compact view. Returns False for empty filtered lists."""
        ITEMS_PER_PAGE = 5
        try:
            offset = page * ITEMS_PER_PAGE
            if show_entry_back is None:
                state_data = await state.get_data()
                show_entry_back = bool(state_data.get("hot_entry_back"))
            show_entry_back = bool(show_entry_back)

            items: list[OfferListItem] = []
            total_pages: int | None = None
            keyboard_pages = 1
            title = get_text(lang, "hot_offers_title")

            if filter_mode == "category":
                if not category_id:
                    return False
                raw = service.list_offers_by_category(
                    search_city,
                    category_id,
                    limit=ITEMS_PER_PAGE + 1,
                    offset=offset,
                    region=search_region,
                    district=search_district,
                )
                has_more = len(raw) > ITEMS_PER_PAGE
                items = raw[:ITEMS_PER_PAGE]
                if not items:
                    return False
                keyboard_pages = page + 1 + (1 if has_more else 0)
                title = f"🗂 <b>{category_label or _category_label(lang, category_id)}</b>"
                total_pages = None
            elif filter_mode == "all":
                result = service.list_hot_offers(
                    search_city,
                    limit=ITEMS_PER_PAGE,
                    offset=offset,
                    region=search_region,
                    district=search_district,
                    latitude=latitude,
                    longitude=longitude,
                    sort_by="new",
                )
                items = result.items
                total_pages = max(1, (result.total + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE)
                keyboard_pages = total_pages
                title = (
                    "📦 <b>Все предложения</b>" if lang == "ru" else "📦 <b>Barcha takliflar</b>"
                )
                if not items and page == 0:
                    await target.answer(
                        offer_templates.render_hot_offers_empty(lang), parse_mode="HTML"
                    )
                    return True
                if not items:
                    return False
            else:
                result = service.list_hot_offers(
                    search_city,
                    limit=ITEMS_PER_PAGE,
                    offset=offset,
                    region=search_region,
                    district=search_district,
                    latitude=latitude,
                    longitude=longitude,
                )
                items = result.items
                total_pages = max(1, (result.total + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE)
                keyboard_pages = total_pages
                if not items and page == 0:
                    await target.answer(
                        offer_templates.render_hot_offers_empty(lang), parse_mode="HTML"
                    )
                    return True
                if not items:
                    return False

            await state.set_state(BrowseOffers.offer_list)
            await state.update_data(
                offer_list=[offer.id for offer in items],
                hot_offers_page=page,
                hot_entry_back=show_entry_back,
                hot_filter_mode=filter_mode,
                hot_filter_value=category_id,
                hot_filter_label=category_label,
            )

            text = _render_offers_list_text(lang, title, city, items, page, total_pages)

            keyboard = offer_keyboards.hot_offers_compact_keyboard(
                lang,
                items,
                page,
                keyboard_pages,
                show_entry_back=show_entry_back,
                show_categories=True,
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
            await target.answer(f"❌ {get_text(lang, 'error')}")
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
            await callback.answer("😔 Нет доступных предложений", show_alert=True)
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






