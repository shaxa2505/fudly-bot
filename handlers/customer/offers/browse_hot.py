"""Hot offers and catalog browsing handlers split from browse.py."""
from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any

from aiogram import Dispatcher, F, types
from aiogram.fsm.context import FSMContext

from app.core.utils import normalize_city
from app.keyboards import offers as offer_keyboards
from app.keyboards import offers_category_filter
from app.services.offer_service import OfferDetails, OfferListItem, OfferService
from app.templates import offers as offer_templates
from handlers.common import BrowseOffers
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

DEFAULT_CITY = "ђчђш‘?ђуђзђ?‘'"


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

    @dp.message(
        F.text.in_(
            [
                "🔥 Горячее",
                "🔥 Issiq takliflar",  # Old names
                "🔥 Акции до -70%",  # Legacy label
                "🔥 -70% gacha aksiyalar",  # Legacy label
                "🏪 Магазины и акции",  # Current RU label
                "🏪 Do'konlar va aksiyalar",  # Current UZ label
            ]
        )
    )
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
        )

    @dp.callback_query(F.data == "hot_offers")
    async def hot_offers_callback(callback: types.CallbackQuery, state: FSMContext) -> None:
        """Handle hot offers inline button (e.g., from cart empty state)."""
        if not callback.from_user or not callback.message:
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
        await _send_hot_offers_list(
            callback.message,
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
        )

    @dp.message(F.text.contains("Категории") | F.text.contains("Kategoriyalar"))
    async def show_categories_handler(message: types.Message) -> None:
        """Show product categories for filtering."""
        if not message.from_user:
            return
        lang = db.get_user_language(message.from_user.id)
        user = db.get_user_model(message.from_user.id)
        if not user:
            await message.answer(
                "⚠️ Сессия устарела. Нажмите /start и откройте ‘🏪 Магазины и акции’ заново."
                if lang == "ru"
                else "⚠️ Sessiya eskirgan. /start ni bosing va ‘🏪 Do'konlar va aksiyalar’ ni qayta oching.",
            )
            return
        city, _, _, _, _ = _extract_location(user)

        select_text = (
            "Выберите категорию для просмотра актуальных предложений"
            if lang == "ru"
            else "Tegishli takliflarni korish uchun toifani tanlang"
        )
        text = (
            f"🗂 <b>{'Категории товаров' if lang == 'ru' else 'Mahsulot turlari'}</b>\n\n"
            f"📍 {city}\n\n"
            f"{select_text}:"
        )

        await message.answer(text, parse_mode="HTML", reply_markup=offers_category_filter(lang))

    @dp.callback_query(F.data == "hot_offers_refresh")
    async def refresh_hot_offers_handler(callback: types.CallbackQuery, state: FSMContext) -> None:
        """Refresh hot offers list."""
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
        await callback.answer("✓", show_alert=False)

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
        store_name = store.name if store else ("Do'kon" if lang == "uz" else "Магазин")
        store_address = store.address if store else ""
        delivery_enabled = store.delivery_enabled if store else False
        delivery_price = store.delivery_price if store and delivery_enabled else 0

        # Localized labels
        currency = "so'm" if lang == "uz" else "сум"
        in_stock_label = "Mavjud" if lang == "uz" else "В наличии"
        expiry_label = "Yaroqlilik" if lang == "uz" else "Годен до"
        delivery_label = "Yetkazish" if lang == "uz" else "Доставка"
        pickup_label = "Olib ketish" if lang == "uz" else "Самовывоз"
        free_label = "bepul" if lang == "uz" else "бесплатно"
        pickup_only = "Faqat olib ketish" if lang == "uz" else "Только самовывоз"

        # Build offer card text
        discount_pct = 0
        if offer.original_price and offer.original_price > offer.discount_price:
            discount_pct = min(
                99, max(0, round((1 - offer.discount_price / offer.original_price) * 100))
            )

        # Clean title - remove "Пример:" prefix if present
        title = offer.title
        if title.startswith("Пример:"):
            title = title[7:].strip()

        lines = [f"🏷 <b>{title}</b>"]

        # Only show description if different from title
        if offer.description and offer.description.strip() != offer.title.strip():
            desc = offer.description
            if desc.startswith("Пример:"):
                desc = desc[7:].strip()
            if desc and desc != title:
                lines.append(f"<i>{desc[:100]}</i>")

        lines.append("")

        if discount_pct > 0:
            lines.append(
                f"<s>{int(offer.original_price):,}</s> → <b>{int(offer.discount_price):,} {currency}</b> (-{discount_pct}%)"
            )
        else:
            lines.append(f"💰 <b>{int(offer.discount_price):,} {currency}</b>")

        # Use actual unit from offer, fallback to dona/шт
        unit_label = offer.unit if offer.unit else ("dona" if lang == "uz" else "шт")
        lines.append(f"📦 {in_stock_label}: {max_quantity} {unit_label}")
        if offer.expiry_date:
            expiry_str = str(offer.expiry_date)[:10]
            try:
                from datetime import datetime

                dt = datetime.strptime(expiry_str, "%Y-%m-%d")
                expiry_str = dt.strftime("%d.%m.%Y")
            except Exception:
                pass
            lines.append(f"📅 {expiry_label}: {expiry_str}")
        lines.append("")
        lines.append(f"🏪 {store_name}")
        if store_address:
            lines.append(f"📍 {store_address}")

        # Delivery/pickup options
        lines.append("")
        if delivery_enabled:
            lines.append(f"🚚 {delivery_label}: {int(delivery_price) // 100:,} {currency}")
            lines.append(f"🏪 {pickup_label}: {free_label}")
        else:
            lines.append(f"🏪 {pickup_only}")

        text = "\n".join(lines)

        # Use keyboard with cart buttons
        kb = offer_keyboards.offer_details_with_back_keyboard(
            lang, offer_id, offer.store_id, delivery_enabled
        )

        # Send offer card - handle photo vs text properly to avoid duplicates
        msg_deleted = False
        if offer.photo:
            # Photo messages require delete + send (can't edit to photo)
            try:
                await msg.delete()
                msg_deleted = True
            except Exception:
                pass
            try:
                await msg.answer_photo(
                    photo=offer.photo, caption=text, parse_mode="HTML", reply_markup=kb
                )
                await callback.answer()
                return  # Success - exit early
            except Exception:
                # Photo failed - will fallback to text below
                pass
        else:
            # Text only - try to edit in place
            try:
                await msg.edit_text(text, parse_mode="HTML", reply_markup=kb)
                await callback.answer()
                return  # Success - exit early
            except Exception:
                # Edit failed - will fallback to delete + send
                pass

        # Fallback: send as text message (only if we haven't succeeded above)
        if not msg_deleted:
            try:
                await msg.delete()
            except Exception:
                pass
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
        # Save current page for back navigation (same as hot_offer_selected_handler)
        current_page = data.get("hot_offers_page", 0)
        await state.update_data(last_hot_page=current_page, source="hot")

        # Show offer details with back-to-list button for consistent UX
        await _send_offer_details(message, details, lang, with_back=True)

    @dp.callback_query(F.data == "offers_all")
    async def show_all_offers(callback: types.CallbackQuery) -> None:
        await _show_offers_catalog(callback, offer_service.list_top_offers, logger)

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
        city, region, district, _, _ = _extract_location(user)
        categories = get_product_categories(lang)  # Используем категории товаров

        try:
            cat_index = int(callback.data.split("_")[-1])
        except (ValueError, IndexError) as e:
            logger.error(f"Invalid cat_index in callback data: {callback.data}, error: {e}")
            await callback.answer(get_text(lang, "error"), show_alert=True)
            return

        if cat_index >= len(categories):
            await callback.answer("Ошибка", show_alert=True)
            return
        category = categories[cat_index]
        normalized = normalize_category(category)

        # Check if we are viewing a specific store
        state_data = await state.get_data()
        viewing_store_id = state_data.get("viewing_store_id")

        if viewing_store_id:
            # Filter by store AND category
            offers = offer_service.list_active_offers_by_store(viewing_store_id)
            # Filter in memory for now as list_active_offers_by_store returns all
            # Ideally should have list_store_offers_by_category
            offers = [
                o for o in offers if o.store_category == normalized or o.store_category == category
            ]
        else:
            # Global category filter
            offers = offer_service.list_offers_by_category(
                normalize_city(city),
                normalized,
                limit=20,
                region=normalize_city(region) if region else None,
                district=normalize_city(district) if district else None,
            )

        if not offers:
            no_offers_msg = f"😔 {'В категории' if lang == 'ru' else 'Toifada'} {category} {'нет предложений' if lang == 'ru' else 'takliflar yoq'}"
            await callback.answer(no_offers_msg, show_alert=True)
            return
        await callback.answer()

        # Улучшенный заголовок с информацией
        select_msg = "Выберите товар для бронирования" if lang == "ru" else "Mahsulotni tanlang"
        header = (
            f"📂 <b>{category.upper()}</b>\n"
            f"📍 {city}\n"
            f"{'─' * 25}\n"
            f"✨ {'Найдено' if lang == 'ru' else 'Topildi'}: <b>{len(offers)}</b> {'предложений' if lang == 'ru' else 'taklif'}\n\n"
            f"👇 {select_msg}"
        )
        await msg.edit_text(
            header,
            parse_mode="HTML",
            reply_markup=offers_category_filter(lang),
        )

        # Отправляем карточки товаров через исходное сообщение (msg)
        for offer in offers[:10]:
            await _send_offer_card(msg, offer, lang)
            await asyncio.sleep(0.1)

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

        # Delete current message (may have photo) and send list
        try:
            await msg.delete()
        except Exception:
            pass

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
            edit_message=False,  # Already deleted, send new
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
    ) -> None:
        """Send hot offers with compact list and inline buttons."""
        ITEMS_PER_PAGE = 5
        try:
            offset = page * ITEMS_PER_PAGE
            log.info(f"[HOT_OFFERS] Fetching offers for city='{search_city}', offset={offset}")
            result = service.list_hot_offers(
                search_city,
                limit=ITEMS_PER_PAGE,
                offset=offset,
                region=search_region,
                district=search_district,
                latitude=latitude,
                longitude=longitude,
            )
            log.info(f"[HOT_OFFERS] Got {len(result.items)} items, total={result.total}")
            if not result.items and page == 0:
                log.info("[HOT_OFFERS] No items - showing empty message")
                await target.answer(
                    offer_templates.render_hot_offers_empty(lang), parse_mode="HTML"
                )
                return

            await state.set_state(BrowseOffers.offer_list)
            await state.update_data(
                offer_list=[offer.id for offer in result.items],
                hot_offers_page=page,
            )

            total_pages = (result.total + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE
            currency = "so'm" if lang == "uz" else "сум"

            # Clean professional header - proper language separation
            header_title = "АКЦИИ ДО -70%" if lang == "ru" else "CHEGIRMALAR -70% GACHA"
            page_label = "Стр." if lang == "ru" else "Sah."
            text = f"🔥 <b>{header_title}</b>\n"
            text += f"📍 {city} | {page_label} {page + 1}/{total_pages}\n"
            text += "━" * 24 + "\n\n"

            for idx, offer in enumerate(result.items, start=1):
                # Clean title - remove test data prefix
                title = offer.title
                if title.startswith("Пример:"):
                    title = title[7:].strip()
                title = title[:22] + ".." if len(title) > 22 else title

                # Safe discount calculation - handle invalid data, use round() for proper rounding
                discount_pct = 0
                if (
                    offer.original_price
                    and offer.discount_price
                    and offer.original_price > offer.discount_price
                ):
                    discount_pct = min(
                        99,
                        max(0, round((1 - offer.discount_price / offer.original_price) * 100)),
                    )

                # Get store name if available
                store_name = ""
                if hasattr(offer, "store_name") and offer.store_name:
                    store_name = offer.store_name[:15]
                elif hasattr(offer, "store_id") and offer.store_id:
                    store = service.get_store(offer.store_id)
                    if store:
                        store_name = store.name[:15] if hasattr(store, "name") else ""

                # Improved format: number + title + discount badge
                if discount_pct > 0:
                    text += f"<b>{idx}.</b> {title} <b>-{discount_pct}%</b>\n"
                else:
                    text += f"<b>{idx}.</b> {title}\n"
                # Price + store on second line
                text += f"    💰 <b>{int(offer.discount_price):,}</b> {currency}"
                if store_name:
                    text += f" • 🏪 {store_name}"
                text += "\n\n"

            # Hint at bottom - clearer call to action
            hint = (
                "👆 Tanlang tugmani yoki raqam yozing"
                if lang == "uz"
                else "👆 Нажмите кнопку под списком или введите номер"
            )
            text += f"\n{hint}"

            # Build keyboard with offer buttons
            keyboard = offer_keyboards.hot_offers_compact_keyboard(
                lang, result.items, page, total_pages
            )

            if edit_message:
                try:
                    await target.edit_text(text, parse_mode="HTML", reply_markup=keyboard)
                except Exception:
                    await target.answer(text, parse_mode="HTML", reply_markup=keyboard)
            else:
                await target.answer(text, parse_mode="HTML", reply_markup=keyboard)

        except Exception as exc:  # pragma: no cover
            log.error("Failed to send hot offers: %s", exc)
            await target.answer(f"😔 {get_text(lang, 'error')}")

    async def _send_offer_details(
        message: types.Message,
        offer: OfferDetails,
        lang: str,
        with_back: bool = False,
    ) -> None:
        store = offer_service.get_store(offer.store_id)
        text = offer_templates.render_offer_details(lang, offer, store)
        if with_back:
            keyboard = offer_keyboards.offer_details_with_back_keyboard(
                lang, offer.id, offer.store_id, store.delivery_enabled if store else False
            )
        else:
            keyboard = offer_keyboards.offer_details_keyboard(
                lang, offer.id, offer.store_id, store.delivery_enabled if store else False
            )
        if offer.photo:
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
        await message.answer(text, parse_mode="HTML", reply_markup=keyboard)

    async def _send_offer_details_edit(
        message: types.Message,
        offer: OfferDetails,
        lang: str,
        offer_id: int,
    ) -> None:
        """Edit current message to show offer details (no new message)."""
        store = offer_service.get_store(offer.store_id)
        currency = "so'm" if lang == "uz" else "сум"

        # Clean professional card format
        lines = [f"📦 <b>{offer.title}</b>"]

        if offer.description:
            desc = (
                offer.description[:100] + "..."
                if len(offer.description) > 100
                else offer.description
            )
            lines.append(f"<i>{desc}</i>")

        lines.append("")
        lines.append("─" * 25)

        # Price with discount
        if offer.original_price and offer.discount_price:
            discount_pct = round((1 - offer.discount_price / offer.original_price) * 100)
            lines.append(
                f"<s>{int(offer.original_price):,}</s> → <b>{int(offer.discount_price):,}</b> {currency} <b>(-{discount_pct}%)</b>"
            )
        else:
            lines.append(f"💰 <b>{int(offer.discount_price):,}</b> {currency}")

        lines.append("─" * 25)
        lines.append("")

        # Stock info
        stock_label = "Mavjud" if lang == "uz" else "В наличии"
        unit = offer.unit or "шт"
        lines.append(f"📦 {stock_label}: <b>{offer.quantity}</b> {unit}")

        # Expiry date
        if offer.expiry_date:
            expiry_label = "Yaroqlilik" if lang == "uz" else "Срок до"
            expiry_str = str(offer.expiry_date)[:10]
            try:
                from datetime import datetime

                dt = datetime.strptime(expiry_str, "%Y-%m-%d")
                expiry_str = dt.strftime("%d.%m.%Y")
            except Exception:
                pass
            lines.append(f"📅 {expiry_label}: {expiry_str}")

        # Store info
        lines.append("")
        store_name = store.name if store else offer.store_name
        store_addr = store.address if store else offer.store_address
        lines.append(f"🏪 {store_name}")
        if store_addr:
            lines.append(f"📍 {store_addr}")

        # Delivery info
        if store and store.delivery_enabled:
            lines.append("")
            delivery_label = "Yetkazish" if lang == "uz" else "Доставка"
            lines.append(f"🚚 {delivery_label}: {int(store.delivery_price):,} {currency}")
            if store.min_order_amount:
                min_label = "Min." if lang == "uz" else "Мин."
                lines.append(f"   {min_label}: {int(store.min_order_amount):,} {currency}")

        text = "\n".join(lines)

        # Keyboard with back button
        keyboard = offer_keyboards.offer_details_with_back_keyboard(
            lang, offer.id, offer.store_id, store.delivery_enabled if store else False
        )

        # If offer has photo, need to delete old message and send photo
        if offer.photo:
            try:
                await message.delete()
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
