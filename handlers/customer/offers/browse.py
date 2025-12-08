"""Handlers for browsing hot offers, stores, and offer filters."""
from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any

from aiogram import Dispatcher, F, types
from aiogram.fsm.context import FSMContext

from app.core.utils import normalize_city
from app.keyboards import business_type_keyboard, offers_category_filter
from app.keyboards import offers as offer_keyboards
from app.services.offer_service import OfferDetails, OfferListItem, OfferService
from app.templates import offers as offer_templates
from handlers.common import BrowseOffers
from localization import get_product_categories, get_text, normalize_category

from .browse_helpers import (
    CATEGORY_MAP,
    normalize_db_category,
)
from .browse_helpers import (
    callback_message as _callback_message,
)
from .browse_helpers import (
    invalid_number_text as _invalid_number_text,
)
from .browse_helpers import (
    no_stores_text as _no_stores_text,
)
from .browse_helpers import (
    range_text as _range_text,
)

FetchOffersFn = Callable[[str, int], list[OfferListItem]]


def setup(
    dp: Dispatcher,
    db: Any,
    offer_service: OfferService,
    logger: Any,
) -> None:
    """Register offer-related handlers on dispatcher."""

    # Support both old and new button names for backwards compatibility
    @dp.message(
        F.text.in_(
            [
                "🔥 Горячее",
                "🔥 Issiq takliflar",  # Old names
                "🔥 Акции до -70%",
                "🔥 -70% gacha aksiyalar",  # New names
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
            await message.answer(get_text(lang, "error"))
            return
        city = user.city or "Ташкент"
        search_city = normalize_city(city)
        await _send_hot_offers_list(
            message,
            state,
            lang,
            city,
            search_city,
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
            await callback.answer(get_text(lang, "error"), show_alert=True)
            return

        city = user.city or "Ташкент"
        search_city = normalize_city(city)

        await callback.answer()
        await _send_hot_offers_list(
            callback.message,
            state,
            lang,
            city,
            search_city,
            offer_service,
            logger,
        )

    @dp.message(F.text.in_(["🏪 Заведения", "🏪 Do'konlar"]))
    async def show_establishments_handler(message: types.Message) -> None:
        """Show establishment types."""
        if not message.from_user:
            return
        lang = db.get_user_language(message.from_user.id)

        await message.answer(
            get_text(
                lang, "choose_category"
            ),  # Reusing key or need new one? "choose_category" might be for product category
            reply_markup=business_type_keyboard(lang),
        )

    @dp.message(F.text.contains("Категории") | F.text.contains("Kategoriyalar"))
    async def show_categories_handler(message: types.Message) -> None:
        """Показать категории товаров для фильтрации"""
        if not message.from_user:
            return
        lang = db.get_user_language(message.from_user.id)
        user = db.get_user_model(message.from_user.id)
        if not user:
            await message.answer(get_text(lang, "error"))
            return
        city = user.city or "Ташкент"

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
        """Обновление списка горячих предложений"""
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
        city = user.city or "Ташкент"
        search_city = normalize_city(city)
        await _send_hot_offers_list(
            msg,
            state,
            lang,
            city,
            search_city,
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
            await callback.answer(get_text(lang, "error"), show_alert=True)
            return

        try:
            page = int(callback.data.split("_")[-1])
        except (ValueError, IndexError):
            await callback.answer(get_text(lang, "error"), show_alert=True)
            return

        city = user.city or "Ташкент"
        search_city = normalize_city(city)

        await _send_hot_offers_list(
            msg,
            state,
            lang,
            city,
            search_city,
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
            lines.append(f"🚚 {delivery_label}: {int(delivery_price):,} {currency}")
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

    # Note: Old handler `hot_offers_next_` removed - using `hot_page_` system now

    @dp.message(F.text.in_(["🏪 Заведения", "🏪 Muassasalar", "🏪 Места", "🏪 Joylar"]))
    async def browse_places_handler(message: types.Message) -> None:
        if not message.from_user:
            return
        lang = db.get_user_language(message.from_user.id)
        await message.answer(
            get_text(lang, "browse_by_business_type"),
            parse_mode="HTML",
            reply_markup=business_type_keyboard(lang),
        )

    @dp.callback_query(F.data.startswith("biztype_"))
    async def business_type_selected(callback: types.CallbackQuery, state: FSMContext):
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
            await callback.answer(get_text(lang, "error"))
            return
        data = callback.data or ""
        business_type = data.replace("biztype_", "")
        city = user.city or "Ташкент"
        search_city = normalize_city(city)

        logger.info(
            f"🏪 Browse stores: business_type={business_type}, user_city={city}, search_city={search_city}"
        )

        stores = offer_service.list_stores_by_type(search_city, business_type)

        logger.info(f"🏪 Found {len(stores)} stores for {business_type} in {search_city}")

        if not stores:
            await msg.edit_text(_no_stores_text(lang, business_type))
            await callback.answer()
            return
        await state.set_state(BrowseOffers.store_list)
        # Save store list and business type for pagination
        await state.update_data(
            store_list=[store.id for store in stores], current_business_type=business_type
        )
        text = offer_templates.render_business_type_store_list(lang, business_type, city, stores)
        # Compact keyboard with pagination
        keyboard = offer_keyboards.store_list_keyboard(lang, stores, page=0)
        await msg.edit_text(text, parse_mode="HTML", reply_markup=keyboard)
        await callback.answer()

    @dp.callback_query(F.data.startswith("select_store_"))
    async def select_store_callback(callback: types.CallbackQuery, state: FSMContext):
        """Select store by inline button - show store info."""
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

        await state.clear()

        # Get store info and show full card
        store = offer_service.get_store(store_id)
        if not store:
            await callback.answer(
                "Магазин не найден" if lang == "ru" else "Do'kon topilmadi",
                show_alert=True,
            )
            return

        # Render full store card
        text = offer_templates.render_store_card(lang, store)
        keyboard = offer_keyboards.store_card_keyboard(
            lang, store_id, store.offers_count, store.ratings_count
        )

        # Try to get photo from raw store data
        photo = None
        try:
            raw_store = db.get_store(store_id) if db else None
            if isinstance(raw_store, dict):
                photo = raw_store.get("photo") or raw_store.get("photo_id")
        except Exception:
            photo = None

        if photo:
            try:
                await msg.answer_photo(
                    photo=photo, caption=text, parse_mode="HTML", reply_markup=keyboard
                )
                await callback.answer()
                return
            except Exception:
                pass

        await msg.edit_text(text, parse_mode="HTML", reply_markup=keyboard)
        await callback.answer()

    @dp.message(BrowseOffers.store_list, F.text.regexp(r"^\d+$"))
    async def select_store_by_number(message: types.Message, state: FSMContext):
        """Select store by number - show categories directly."""
        if not message.from_user:
            return
        lang = db.get_user_language(message.from_user.id)
        data = await state.get_data()
        store_list: list[int] = data.get("store_list", [])
        if not store_list:
            await message.answer(get_text(lang, "error"))
            await state.clear()
            return
        try:
            if not message.text:
                await message.answer(_invalid_number_text(lang, "магазина"))
                return
            number = int(message.text)
        except ValueError:
            await message.answer(_invalid_number_text(lang, "магазина"))
            return
        if number < 1 or number > len(store_list):
            await message.answer(_range_text(lang, len(store_list), "магазина"))
            return
        store_id = store_list[number - 1]
        await state.clear()

        # Get store info
        store = offer_service.get_store(store_id)
        if not store:
            await message.answer("Магазин не найден" if lang == "ru" else "Do'kon topilmadi")
            return

        # Show category selection directly
        text = (
            f"🏪 <b>{store.name}</b>\n\n" f"📂 Выберите категорию товаров:"
            if lang == "ru"
            else f"🏪 <b>{store.name}</b>\n\n" f"📂 Mahsulot toifasini tanlang:"
        )

        from app.keyboards import offers_category_filter

        keyboard = offers_category_filter(lang, store_id=store_id)

        await message.answer(text, parse_mode="HTML", reply_markup=keyboard)

    @dp.message(BrowseOffers.offer_list, F.text.regexp(r"^\d+$"))
    async def select_offer_by_number(message: types.Message, state: FSMContext):
        if not message.from_user:
            return
        logger.info(
            f"📥 select_offer_by_number triggered: user={message.from_user.id}, text={message.text}"
        )
        lang = db.get_user_language(message.from_user.id)
        data = await state.get_data()
        offer_list: list[int] = data.get("offer_list", [])
        logger.info(f"📥 FSM data: offer_list={offer_list}, state={await state.get_state()}")
        if not offer_list:
            await message.answer(get_text(lang, "error"))
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
        await state.clear()
        await _send_offer_details(message, details, lang)

    @dp.callback_query(F.data == "offers_all")
    async def show_all_offers(callback: types.CallbackQuery):
        await _show_offers_catalog(callback, offer_service.list_top_offers, logger)

    @dp.callback_query(F.data.startswith("offers_cat_"))
    async def filter_offers_by_category(callback: types.CallbackQuery, state: FSMContext):
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
        city = user.city or "Ташкент"
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
            offers = offer_service.list_offers_by_category(city, normalized, limit=20)

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

    @dp.callback_query(F.data.startswith("filter_store_"))
    async def filter_offers_by_store(callback: types.CallbackQuery, state: FSMContext):
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
        except (ValueError, IndexError) as e:
            logger.error(f"Invalid store_id in callback data: {callback.data}, error: {e}")
            await callback.answer(get_text(lang, "error"), show_alert=True)
            return

        store = offer_service.get_store(store_id)
        if not store:
            await callback.answer("× Магазин не найден", show_alert=True)
            return

        # Save store_id to state so we can filter by category later
        await state.update_data(viewing_store_id=store_id)

        # Show categories for this store instead of all offers
        # We need a keyboard with categories available in this store
        # For now, let's show the generic category filter but maybe we should filter it?
        # Or just show the store card with "All products" and "Categories"

        # The user requested: "choice of establishment, then categories"
        # So when clicking a store, we should ask "Select category"

        header = (
            f"<b>{store.name}</b>\n"
            f"{store.address or ''}\n\n"
            f"{get_text(lang, 'select_category_in_store')}"
        )

        # We reuse offers_category_filter but ideally it should be filtered by what the store has.
        # For MVP, showing all categories is acceptable, or we can check what categories the store has.
        # Let's stick to the requested flow: Store -> Category -> Offers

        await msg.edit_text(
            header,
            parse_mode="HTML",
            reply_markup=offers_category_filter(lang),
        )
        # Do NOT show offers list immediately

    @dp.callback_query(F.data == "filter_all")
    async def show_all_offers_filter(callback: types.CallbackQuery):
        await _show_offers_catalog(callback, offer_service.list_top_offers, logger)

    @dp.callback_query(F.data.startswith("store_info_"))
    async def show_store_info(callback: types.CallbackQuery):
        """Show full store information card with photo."""
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
        except (ValueError, IndexError) as e:
            logger.error(f"Invalid store_id in callback data: {callback.data}, error: {e}")
            await callback.answer(get_text(lang, "error"), show_alert=True)
            return

        # Use offer_service for structured store details
        store = offer_service.get_store(store_id)
        if not store:
            await callback.answer(
                "Магазин не найден" if lang == "ru" else "Do'kon topilmadi",
                show_alert=True,
            )
            return

        # Render full store card with all details
        text = offer_templates.render_store_card(lang, store)
        keyboard = offer_keyboards.store_card_keyboard(
            lang, store_id, store.offers_count, store.ratings_count
        )

        # Try to get photo from raw store data
        photo = None
        try:
            raw_store = db.get_store(store_id) if db else None
            if isinstance(raw_store, dict):
                photo = raw_store.get("photo") or raw_store.get("photo_id")
        except Exception:
            photo = None

        # Send with photo if available
        if photo:
            try:
                await msg.answer_photo(
                    photo=photo, caption=text, parse_mode="HTML", reply_markup=keyboard
                )
                await callback.answer()
                return
            except Exception:
                # Fall back to text if photo fails
                pass

        # Try to edit existing message or send new one
        try:
            await msg.edit_text(text, parse_mode="HTML", reply_markup=keyboard)
        except Exception:
            await msg.answer(text, parse_mode="HTML", reply_markup=keyboard)
        await callback.answer()

    @dp.callback_query(F.data == "back_to_hot")
    async def back_to_hot(callback: types.CallbackQuery, state: FSMContext):
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
        city = user.city or "Ташкент"
        search_city = normalize_city(city)

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
            offer_service,
            logger,
            page=last_page,
            edit_message=False,  # Already deleted, send new
        )
        await callback.answer()

    @dp.callback_query(F.data.startswith("store_offers_"))
    async def show_store_offers(callback: types.CallbackQuery, state: FSMContext):
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
        except (ValueError, IndexError) as e:
            logger.error(f"Invalid store_id in callback data: {callback.data}, error: {e}")
            await callback.answer(get_text(lang, "error"), show_alert=True)
            return

        store = offer_service.get_store(store_id)
        if not store:
            await callback.answer(
                "Магазин не найден" if lang == "ru" else "Do'kon topilmadi",
                show_alert=True,
            )
            return

        # Show category selection for store
        text = (
            f"🏪 <b>{store.name}</b>\n\n" f"📂 Выберите категорию товаров:"
            if lang == "ru"
            else f"🏪 <b>{store.name}</b>\n\n" f"📂 Mahsulot toifasini tanlang:"
        )

        # Import category keyboard
        from app.keyboards import offers_category_filter

        keyboard = offers_category_filter(lang, store_id=store_id)

        # Try edit_text first, fallback to edit_caption for photo messages
        try:
            await msg.edit_text(text, parse_mode="HTML", reply_markup=keyboard)
        except Exception:
            try:
                await msg.edit_caption(caption=text, parse_mode="HTML", reply_markup=keyboard)
            except Exception:
                # If both fail, delete old message and send new one
                try:
                    await msg.delete()
                except Exception:
                    pass
                await callback.message.answer(text, parse_mode="HTML", reply_markup=keyboard)
        await callback.answer()

    @dp.callback_query(F.data.startswith("store_cat_"))
    async def show_store_offers_by_category(callback: types.CallbackQuery, state: FSMContext):
        """Show store offers filtered by category."""
        if not callback.from_user or not callback.data:
            await callback.answer()
            return
        msg = _callback_message(callback)
        if not msg:
            await callback.answer()
            return
        lang = db.get_user_language(callback.from_user.id)

        try:
            # Parse: store_cat_{store_id}_{category}
            parts = callback.data.split("_", 3)  # Split into max 4 parts
            store_id = int(parts[2])
            category = parts[3] if len(parts) > 3 else "all"
        except (ValueError, IndexError) as e:
            logger.error(f"Invalid callback data: {callback.data}, error: {e}")
            await callback.answer(get_text(lang, "error"), show_alert=True)
            return

        store = offer_service.get_store(store_id)
        if not store:
            await callback.answer(
                "Магазин не найден" if lang == "ru" else "Do'kon topilmadi",
                show_alert=True,
            )
            return

        # Get all offers for the store
        all_offers = offer_service.list_store_offers(store_id)

        # Filter by category if not "all"
        if category != "all":
            # Map display category to database category value
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

            # Filter offers by their category field
            offers = []
            for offer in all_offers:
                if offer.category == db_category:
                    offers.append(offer)
        else:
            offers = all_offers

        if not offers:
            await callback.answer(
                "В этой категории пока нет товаров"
                if lang == "ru"
                else "Bu toifada hali mahsulotlar yo'q",
                show_alert=True,
            )
            return

        # Delete current message and send new compact list
        try:
            await msg.delete()
        except Exception:
            pass

        await _send_store_offers_list(
            msg, state, lang, store, offers, page=0, edit_message=False, category=category
        )
        await callback.answer()

    @dp.callback_query(F.data.startswith("store_offers_page_"))
    async def store_offers_page_handler(callback: types.CallbackQuery, state: FSMContext):
        """Handle store offers pagination with compact view."""
        if not callback.from_user or not callback.data:
            await callback.answer()
            return
        msg = _callback_message(callback)
        if not msg:
            await callback.answer()
            return
        lang = db.get_user_language(callback.from_user.id)

        try:
            # Parse: store_offers_page_{store_id}_{page}
            parts = callback.data.split("_")
            store_id = int(parts[3])
            page = int(parts[4])
        except (ValueError, IndexError) as e:
            logger.error(f"Invalid pagination data: {callback.data}, error: {e}")
            await callback.answer(get_text(lang, "error"), show_alert=True)
            return

        store = offer_service.get_store(store_id)
        if not store:
            await callback.answer("Магазин не найден", show_alert=True)
            return

        # Get stored category from state
        data = await state.get_data()
        category = data.get("store_category", "all")

        # Get all offers for the store
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

        await _send_store_offers_list(
            msg, state, lang, store, offers, page=page, edit_message=True, category=category
        )
        await callback.answer()

    @dp.callback_query(F.data.startswith("store_offer_"))
    async def store_offer_select_handler(callback: types.CallbackQuery, state: FSMContext):
        """Handle store offer selection - show offer card with cart controls."""
        if not callback.from_user or not callback.message:
            await callback.answer()
            return

        lang = db.get_user_language(callback.from_user.id)
        user_id = callback.from_user.id

        try:
            # Parse: store_offer_{store_id}_{offer_id}
            parts = callback.data.split("_")
            store_id = int(parts[2])
            offer_id = int(parts[3])
        except (ValueError, IndexError) as e:
            logger.error(f"Invalid offer data: {callback.data}, error: {e}")
            await callback.answer(get_text(lang, "error"), show_alert=True)
            return

        # Get offer details
        offer = offer_service.get_offer_details(offer_id)
        if not offer:
            not_found = "Mahsulot topilmadi" if lang == "uz" else "Товар не найден"
            await callback.answer(not_found, show_alert=True)
            return

        # Save store context for returning
        data = await state.get_data()
        await state.update_data(
            last_store_id=store_id,
            last_store_page=data.get("store_offers_page", 0),
            last_store_category=data.get("store_category", "all"),
            source="store",
            store_id=store_id,
        )

        # Get store info
        store = offer_service.get_store(offer.store_id) if offer.store_id else None
        store_name = store.name if store else ("Do'kon" if lang == "uz" else "Магазин")

        max_quantity = offer.quantity or 0
        if max_quantity <= 0:
            sold_out = "Mahsulot tugadi" if lang == "uz" else "Товар закончился"
            await callback.answer(sold_out, show_alert=True)
            return

        # Localized labels
        currency = "so'm" if lang == "uz" else "сум"
        in_stock_label = "Mavjud" if lang == "uz" else "В наличии"
        expiry_label = "Yaroqlilik" if lang == "uz" else "Годен до"
        delivery_label = "Yetkazish" if lang == "uz" else "Доставка"

        # Build offer card text
        discount_pct = 0
        if offer.original_price and offer.original_price > offer.discount_price:
            discount_pct = min(
                99, max(0, round((1 - offer.discount_price / offer.original_price) * 100))
            )

        # Clean title
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

        # Get store details for delivery info
        store_address = store.address if store else ""
        delivery_enabled = store.delivery_enabled if store else False
        delivery_price = store.delivery_price if store and delivery_enabled else 0

        if store_address:
            lines.append(f"📍 {store_address}")
        if delivery_enabled:
            lines.append(f"🚚 {delivery_label}: {int(delivery_price):,} {currency}")

        text = "\n".join(lines)

        # Use cart keyboard
        kb = offer_keyboards.offer_details_with_back_keyboard(
            lang, offer_id, offer.store_id, delivery_enabled
        )

        # Get message to respond to
        msg = _callback_message(callback)
        if not msg:
            await callback.answer()
            return

        # Send offer card - handle photo vs text properly to avoid duplicates
        msg_deleted = False
        if getattr(offer, "photo", None):
            # Photo messages require delete + send (can't edit to photo)
            try:
                await msg.delete()
                msg_deleted = True
            except Exception:
                pass
            try:
                await msg.answer_photo(
                    photo=offer.photo,
                    caption=text,
                    parse_mode="HTML",
                    reply_markup=kb,
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

    @dp.callback_query(F.data.startswith("store_offers_next_"))
    async def store_offers_pagination(callback: types.CallbackQuery, state: FSMContext):
        if not callback.from_user or not callback.data:
            await callback.answer()
            return
        msg = _callback_message(callback)
        if not msg:
            await callback.answer()
            return
        lang = db.get_user_language(callback.from_user.id)

        try:
            parts = callback.data.split("_")
            store_id = int(parts[3])
            offset = int(parts[4])
        except (ValueError, IndexError) as e:
            logger.error(f"Invalid pagination data in callback: {callback.data}, error: {e}")
            await callback.answer(get_text(lang, "error"), show_alert=True)
            return

        store = offer_service.get_store(store_id)
        if not store:
            await callback.answer("Магазин не найден", show_alert=True)
            return
        offers = offer_service.list_store_offers(store_id)
        if offset >= len(offers):
            await callback.answer(
                "Больше товаров нет" if lang == "ru" else "Boshqa mahsulotlar yo'q",
                show_alert=True,
            )
            return
        page = offers[offset : offset + 20]
        await _set_offer_state(state, offers)
        text = offer_templates.render_store_offers_list(
            lang,
            store.name,
            page,
            offset=offset,
            total=len(offers),
        )
        has_more = offset + len(page) < len(offers)
        keyboard = offer_keyboards.store_offers_keyboard(
            lang,
            store_id,
            has_more,
            offset + 20 if has_more else None,
        )
        await msg.answer(text, parse_mode="HTML", reply_markup=keyboard)
        await callback.answer()

    @dp.callback_query(F.data.startswith("store_reviews_"))
    async def show_store_reviews(callback: types.CallbackQuery):
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
        except (ValueError, IndexError) as e:
            logger.error(f"Invalid store_id in callback data: {callback.data}, error: {e}")
            await callback.answer(get_text(lang, "error"), show_alert=True)
            return

        store = offer_service.get_store(store_id)
        if not store:
            await callback.answer("Магазин не найден", show_alert=True)
            return
        avg_rating, reviews = offer_service.get_store_reviews(store_id)
        text = offer_templates.render_store_reviews(lang, store.name, avg_rating, reviews)
        keyboard = offer_keyboards.store_reviews_keyboard(lang, store_id)
        await msg.answer(text, parse_mode="HTML", reply_markup=keyboard)
        await callback.answer()

    @dp.callback_query(F.data.startswith("back_to_store_"))
    async def back_to_store_card(callback: types.CallbackQuery):
        """Return to store - show categories instead of card."""
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
        except (ValueError, IndexError) as e:
            logger.error(f"Invalid store_id in callback data: {callback.data}, error: {e}")
            await callback.answer(get_text(lang, "error"), show_alert=True)
            return

        # Get store and show categories
        store = offer_service.get_store(store_id)
        if not store:
            logger.warning(f"Store {store_id} not found in back_to_store_card")
            await callback.answer(
                "Магазин не найден" if lang == "ru" else "Do'kon topilmadi", show_alert=True
            )
            return

        # Show category selection
        text = (
            f"🏪 <b>{store.name}</b>\n\n" f"📂 Выберите категорию товаров:"
            if lang == "ru"
            else f"🏪 <b>{store.name}</b>\n\n" f"📂 Mahsulot toifasini tanlang:"
        )

        from app.keyboards import offers_category_filter

        keyboard = offers_category_filter(lang, store_id=store_id)

        # Try edit_text first, then edit_caption, then send new message
        try:
            await msg.edit_text(text, parse_mode="HTML", reply_markup=keyboard)
        except Exception:
            try:
                await msg.edit_caption(caption=text, parse_mode="HTML", reply_markup=keyboard)
            except Exception:
                # Delete old message and send new one
                try:
                    await msg.delete()
                except Exception:
                    pass
                await callback.message.answer(text, parse_mode="HTML", reply_markup=keyboard)
        await callback.answer()

    @dp.callback_query(F.data == "back_to_places")
    async def back_to_places_menu(callback: types.CallbackQuery):
        if not callback.from_user:
            await callback.answer()
            return
        lang = db.get_user_language(callback.from_user.id)
        msg = _callback_message(callback)
        if not msg:
            await callback.answer()
            return
        await msg.answer(
            get_text(lang, "browse_by_business_type"),
            parse_mode="HTML",
            reply_markup=business_type_keyboard(lang),
        )
        await callback.answer()

    @dp.callback_query(F.data.startswith("stores_page_"))
    async def stores_page_handler(callback: types.CallbackQuery, state: FSMContext):
        """Handle store list pagination."""
        if not callback.from_user or not callback.data:
            await callback.answer()
            return
        msg = _callback_message(callback)
        if not msg:
            await callback.answer()
            return

        lang = db.get_user_language(callback.from_user.id)

        try:
            page = int(callback.data.split("_")[-1])
        except (ValueError, IndexError):
            await callback.answer()
            return

        # Get stored data
        data = await state.get_data()
        store_ids = data.get("store_list", [])
        business_type = data.get("current_business_type", "")

        if not store_ids:
            await callback.answer()
            return

        user = db.get_user_model(callback.from_user.id)
        city = user.city if user else "Ташкент"

        # Get stores
        stores = []
        for sid in store_ids:
            store = offer_service.get_store(sid)
            if store:
                stores.append(store)

        if not stores:
            await callback.answer()
            return

        # Render with new page
        text = offer_templates.render_business_type_store_list(lang, business_type, city, stores)
        keyboard = offer_keyboards.store_list_keyboard(lang, stores, page=page)

        try:
            await msg.edit_text(text, parse_mode="HTML", reply_markup=keyboard)
        except Exception:
            pass

        await callback.answer()

    @dp.callback_query(F.data == "stores_noop")
    async def stores_noop_handler(callback: types.CallbackQuery):
        """Handle noop button (page indicator)."""
        await callback.answer()

    # Touch handler names so static analysis does not flag them as unused.
    _ = (
        hot_offers_handler,
        show_categories_handler,
        refresh_hot_offers_handler,
        browse_places_handler,
        business_type_selected,
        select_store_by_number,
        select_offer_by_number,
        show_all_offers,
        filter_offers_by_category,
        filter_offers_by_store,
        show_all_offers_filter,
        show_store_info,
        back_to_hot,
        show_store_offers,
        store_offers_pagination,
        show_store_reviews,
        back_to_store_card,
        back_to_places_menu,
        stores_page_handler,
        stores_noop_handler,
    )

    # ------------------------------------------------------------------
    # Helper closures
    # ------------------------------------------------------------------

    async def _send_hot_offers_list(
        target: types.Message,
        state: FSMContext,
        lang: str,
        city: str,
        search_city: str,
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
            result = service.list_hot_offers(search_city, limit=ITEMS_PER_PAGE, offset=offset)
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
                        99, max(0, round((1 - offer.discount_price / offer.original_price) * 100))
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
                "👆 Tanlang yoki raqam yozing"
                if lang == "uz"
                else "👆 Нажмите на товар или введите номер"
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

    async def _send_store_offers_list(
        target: types.Message,
        state: FSMContext,
        lang: str,
        store: Any,
        offers: list,
        page: int = 0,
        edit_message: bool = False,
        category: str = "all",
    ) -> None:
        """Send store offers with compact list and inline buttons (like hot offers)."""
        ITEMS_PER_PAGE = 5
        try:
            store_id = store.id
            total_offers = len(offers)

            if total_offers == 0:
                await target.answer(
                    "В этом магазине пока нет товаров"
                    if lang == "ru"
                    else "Bu do'konda hali mahsulotlar yo'q",
                    parse_mode="HTML",
                )
                return

            offset = page * ITEMS_PER_PAGE
            page_offers = offers[offset : offset + ITEMS_PER_PAGE]

            await state.set_state(BrowseOffers.offer_list)
            await state.update_data(
                offer_list=[offer.id for offer in offers],
                store_offers_page=page,
                current_store_id=store_id,
                store_category=category,
            )

            total_pages = (total_offers + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE
            currency = "so'm" if lang == "uz" else "сум"

            # Category title
            category_title = (
                category.replace("_", " ").title()
                if category != "all"
                else ("Все категории" if lang == "ru" else "Barcha toifalar")
            )

            # Clean professional header
            text = f"🏪 <b>{store.name}</b> | 📂 {category_title}\n"
            text += f"{'Стр.' if lang == 'ru' else 'Sah.'} {page + 1}/{total_pages} ({total_offers} {'махсулот' if lang == 'uz' else 'товаров'})\n"
            text += "─" * 28 + "\n\n"

            for idx, offer in enumerate(page_offers, start=1):
                title = offer.title[:25] + ".." if len(offer.title) > 25 else offer.title
                discount_pct = 0
                if offer.original_price and offer.discount_price and offer.original_price > 0:
                    discount_pct = round((1 - offer.discount_price / offer.original_price) * 100)

                # Clean format: number + title on first line
                text += f"<b>{idx}.</b> {title}\n"
                # Price on second line - compact
                if offer.original_price and discount_pct > 0:
                    text += f"    <s>{int(offer.original_price):,}</s> → <b>{int(offer.discount_price):,}</b> {currency} <i>(-{discount_pct}%)</i>\n"
                else:
                    text += (
                        f"    <b>{int(offer.discount_price or offer.price or 0):,}</b> {currency}\n"
                    )

            # Hint at bottom
            hint = "👆 Tanlang" if lang == "uz" else "👆 Выберите товар"
            text += f"\n{hint}"

            # Build keyboard with offer buttons
            keyboard = offer_keyboards.store_offers_compact_keyboard(
                lang, page_offers, store_id, page, total_pages
            )

            if edit_message:
                try:
                    await target.edit_text(text, parse_mode="HTML", reply_markup=keyboard)
                except Exception:
                    await target.answer(text, parse_mode="HTML", reply_markup=keyboard)
            else:
                await target.answer(text, parse_mode="HTML", reply_markup=keyboard)

        except Exception as exc:  # pragma: no cover
            logger.error("Failed to send store offers: %s", exc)
            await target.answer(f"😔 {get_text(lang, 'error')}")

    async def _send_store_card(message: types.Message, store_id: int, lang: str) -> None:
        store = offer_service.get_store(store_id)
        if not store:
            await message.answer("Магазин не найден" if lang == "ru" else "Do'kon topilmadi")
            return
        text = offer_templates.render_store_card(lang, store)
        keyboard = offer_keyboards.store_card_keyboard(
            lang, store_id, store.offers_count, store.ratings_count
        )

        # Try to fetch raw store data from DB to get photo/photo_id (repo may keep photo field)
        photo = None
        try:
            raw_store = db.get_store(store_id) if db else None
            if isinstance(raw_store, dict):
                photo = raw_store.get("photo") or raw_store.get("photo_id")
        except Exception:
            photo = None

        # Отправить с фото если есть
        if photo:
            try:
                await message.answer_photo(
                    photo=photo, caption=text, parse_mode="HTML", reply_markup=keyboard
                )
                return
            except Exception:
                # If sending photo fails, fall back to text
                pass

        await message.answer(text, parse_mode="HTML", reply_markup=keyboard)

    async def _send_offer_details(message: types.Message, offer: OfferDetails, lang: str) -> None:
        store = offer_service.get_store(offer.store_id)
        text = offer_templates.render_offer_details(lang, offer, store)
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
        message: types.Message, offer: OfferDetails, lang: str, offer_id: int
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

    async def _send_offer_card(message: types.Message, offer: OfferListItem, lang: str) -> None:
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
        city = user.city or "Ташкент"
        offers: list[OfferListItem] = fetcher(city, 20)
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

    async def _set_offer_state(state: FSMContext, offers: list[OfferListItem]) -> None:
        offer_ids = [offer.id for offer in offers]
        logger.info(
            f"📝 Setting FSM state BrowseOffers.offer_list with {len(offer_ids)} offers: {offer_ids[:5]}..."
        )
        await state.set_state(BrowseOffers.offer_list)
        await state.update_data(offer_list=offer_ids)
        # Verify state was set
        current_state = await state.get_state()
        current_data = await state.get_data()
        logger.info(
            f"📝 FSM state after set: state={current_state}, data_keys={list(current_data.keys())}"
        )

    async def _append_offer_ids(state: FSMContext, offers: list[OfferListItem]) -> None:
        data = await state.get_data()
        existing: list[int] = data.get("offer_list", [])
        for offer in offers:
            if offer.id not in existing:
                existing.append(offer.id)
        await state.update_data(offer_list=existing)
