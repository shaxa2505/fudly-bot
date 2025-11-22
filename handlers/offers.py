"""Handlers for browsing hot offers, stores, and offer filters."""
from __future__ import annotations

import asyncio
from typing import Any, Callable, List

from aiogram import Dispatcher, F, types
from aiogram.fsm.context import FSMContext

from app.core.utils import normalize_city
from app.keyboards import offers as offer_keyboards
from app.services.offer_service import OfferDetails, OfferListItem, OfferService
from app.templates import offers as offer_templates
from handlers.common import BrowseOffers
from localization import get_categories, get_product_categories, get_text, normalize_category
from app.keyboards import business_type_keyboard, offers_category_filter

FetchOffersFn = Callable[[str, int], List[OfferListItem]]

def setup(
    dp: Dispatcher,
    db: Any,
    offer_service: OfferService,
    logger: Any,
) -> None:
    """Register offer-related handlers on dispatcher."""

    @dp.message(F.text.in_(["🔥 Горячее", "🔥 Issiq"]))
    async def hot_offers_handler(message: types.Message, state: FSMContext) -> None:
        if not message.from_user:
            return
        user_id = message.from_user.id
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

    @dp.message(F.text.in_(["🏪 Заведения", "🏪 Do'konlar"]))
    async def show_establishments_handler(message: types.Message) -> None:
        """Show establishment types."""
        if not message.from_user:
            return
        lang = db.get_user_language(message.from_user.id)
        
        await message.answer(
            get_text(lang, "choose_category"), # Reusing key or need new one? "choose_category" might be for product category
            reply_markup=business_type_keyboard(lang)
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
        
        select_text = 'Выберите категорию для просмотра актуальных предложений' if lang == 'ru' else 'Tegishli takliflarni korish uchun toifani tanlang'
        text = (
            f"🗂 <b>{'Категории товаров' if lang == 'ru' else 'Mahsulot turlari'}</b>\n\n"
            f"📍 {city}\n\n"
            f"{select_text}:"
        )
        
        await message.answer(
            text,
            parse_mode="HTML",
            reply_markup=offers_category_filter(lang)
        )

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
        )
        await callback.answer("✓" if lang == "ru" else "✓", show_alert=False)

    @dp.callback_query(F.data.startswith("hot_offers_next_"))
    async def hot_offers_pagination(callback: types.CallbackQuery, state: FSMContext) -> None:
        try:
            if not callback.from_user or not callback.data:
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
            
            try:
                offset = int(callback.data.split("_")[-1])
            except (ValueError, IndexError) as e:
                logger.error(f"Invalid offset in callback data: {callback.data}, error: {e}")
                await callback.answer(get_text(lang, "error"), show_alert=True)
                return
            
            msg = _callback_message(callback)
            if not msg:
                await callback.answer()
                return
            result = offer_service.list_hot_offers(search_city, limit=20, offset=offset)
            if not result.items:
                await callback.answer(
                    "Больше предложений нет" if lang == "ru" else "Boshqa takliflar yo'q",
                    show_alert=True,
                )
                return
            await _append_offer_ids(state, result.items)
            select_hint = get_text(lang, "select_by_number")
            text = offer_templates.render_hot_offers_list(
                lang,
                city,
                result.items,
                result.total,
                select_hint,
                offset=offset,
            )
            has_more = offset + len(result.items) < result.total
            keyboard = offer_keyboards.hot_offers_pagination_keyboard(
                lang, has_more, offset + 20
            )
            await msg.answer(text, parse_mode="HTML", reply_markup=keyboard)
            await callback.answer()
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.error("hot_offers_pagination error: %s", exc)
            lang = db.get_user_language(callback.from_user.id)
            await callback.answer(
                "Ошибка" if lang == "ru" else "Xato", show_alert=True
            )

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
        
        logger.info(f"🏪 Browse stores: business_type={business_type}, user_city={city}, search_city={search_city}")
        
        stores = offer_service.list_stores_by_type(search_city, business_type)
        
        logger.info(f"🏪 Found {len(stores)} stores for {business_type} in {search_city}")
        
        if not stores:
            await msg.edit_text(_no_stores_text(lang, business_type))
            await callback.answer()
            return
        await state.set_state(BrowseOffers.store_list)
        await state.update_data(store_list=[store.id for store in stores])
        text = offer_templates.render_business_type_store_list(lang, business_type, city, stores)
        await msg.edit_text(text, parse_mode="HTML")
        await callback.answer()

    @dp.message(BrowseOffers.store_list, F.text.regexp(r"^\d+$"))
    async def select_store_by_number(message: types.Message, state: FSMContext):
        """Select store by number - show categories directly."""
        if not message.from_user:
            return
        lang = db.get_user_language(message.from_user.id)
        data = await state.get_data()
        store_list: List[int] = data.get("store_list", [])
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
            await message.answer(
                "Магазин не найден" if lang == "ru" else "Do'kon topilmadi"
            )
            return
        
        # Show category selection directly
        text = (
            f"🏪 <b>{store.name}</b>\n\n"
            f"📂 Выберите категорию товаров:"
            if lang == "ru" else
            f"🏪 <b>{store.name}</b>\n\n"
            f"📂 Mahsulot toifasini tanlang:"
        )
        
        from app.keyboards import offers_category_filter
        keyboard = offers_category_filter(lang, store_id=store_id)
        
        await message.answer(text, parse_mode="HTML", reply_markup=keyboard)

    @dp.message(BrowseOffers.offer_list, F.text.regexp(r"^\d+$"))
    async def select_offer_by_number(message: types.Message, state: FSMContext):
        if not message.from_user:
            return
        lang = db.get_user_language(message.from_user.id)
        data = await state.get_data()
        offer_list: List[int] = data.get("offer_list", [])
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
            offers = [o for o in offers if o.store_category == normalized or o.store_category == category]
        else:
            # Global category filter
            offers = offer_service.list_offers_by_category(city, normalized, limit=20)
            
        if not offers:
            no_offers_msg = f"😔 {'В категории' if lang == 'ru' else 'Toifada'} {category} {'нет предложений' if lang == 'ru' else 'takliflar yoq'}"
            await callback.answer(no_offers_msg, show_alert=True)
            return
        await callback.answer()
        
        # Улучшенный заголовок с информацией
        select_msg = 'Выберите товар для бронирования' if lang == 'ru' else 'Mahsulotni tanlang'
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
        
        # Отправляем карточки товаров через callback.message
        for offer in offers[:10]:
            await _send_offer_card(callback.message, offer, lang)
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
        """Show store categories directly instead of store card."""
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
        
        # Show category selection directly
        text = (
            f"🏪 <b>{store.name}</b>\n\n"
            f"📂 Выберите категорию товаров:"
            if lang == "ru" else
            f"🏪 <b>{store.name}</b>\n\n"
            f"📂 Mahsulot toifasini tanlang:"
        )
        
        from app.keyboards import offers_category_filter
        keyboard = offers_category_filter(lang, store_id=store_id)
        
        await msg.edit_text(text, parse_mode="HTML", reply_markup=keyboard)
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
        await _send_hot_offers_list(
            msg,
            state,
            lang,
            city,
            search_city,
            offer_service,
            logger,
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
            f"🏪 <b>{store.name}</b>\n\n"
            f"📂 Выберите категорию товаров:"
            if lang == "ru" else
            f"🏪 <b>{store.name}</b>\n\n"
            f"📂 Mahsulot toifasini tanlang:"
        )
        
        # Import category keyboard
        from app.keyboards import offers_category_filter
        keyboard = offers_category_filter(lang, store_id=store_id)
        
        await msg.edit_text(text, parse_mode="HTML", reply_markup=keyboard)
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
        
        await _set_offer_state(state, offers)
        page = offers[:20]
        
        category_title = category.replace("_", " ").title() if category != "all" else (
            "Все категории" if lang == "ru" else "Barcha toifalar"
        )
        products_word = "Mahsulotlar" if lang == "uz" else "Товаров"
        text = (
            f"🏪 <b>{store.name}</b>\n"
            f"📂 {category_title}\n"
            f"📦 {products_word}: {len(offers)}\n\n"
        )
        text += offer_templates.render_store_offers_list(
            lang,
            store.name,
            page,
            offset=0,
            total=len(offers),
        )
        
        keyboard = offer_keyboards.store_offers_keyboard(
            lang,
            store_id,
            has_more=len(offers) > 20,
            next_offset=20 if len(offers) > 20 else None,
        )
        await msg.edit_text(text, parse_mode="HTML", reply_markup=keyboard)
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
            await callback.answer(
                "Магазин не найден" if lang == "ru" else "Do'kon topilmadi",
                show_alert=True
            )
            return
        
        # Show category selection
        text = (
            f"🏪 <b>{store.name}</b>\n\n"
            f"📂 Выберите категорию товаров:"
            if lang == "ru" else
            f"🏪 <b>{store.name}</b>\n\n"
            f"📂 Mahsulot toifasini tanlang:"
        )
        
        from app.keyboards import offers_category_filter
        keyboard = offers_category_filter(lang, store_id=store_id)
        
        await msg.edit_text(text, parse_mode="HTML", reply_markup=keyboard)
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

    # Touch handler names so static analysis does not flag them as unused.
    _ = (
        hot_offers_handler,
        show_categories_handler,
        refresh_hot_offers_handler,
        hot_offers_pagination,
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
    ) -> None:
        try:
            result = service.list_hot_offers(search_city, limit=20, offset=0)
            if not result.items:
                await target.answer(offer_templates.render_hot_offers_empty(lang), parse_mode="HTML")
                return
            await state.set_state(BrowseOffers.offer_list)
            await state.update_data(offer_list=[offer.id for offer in result.items])
            select_hint = get_text(lang, "select_by_number")
            text = offer_templates.render_hot_offers_list(
                lang,
                city,
                result.items,
                result.total,
                select_hint,
                offset=0,
            )
            has_more = len(result.items) < result.total
            keyboard = offer_keyboards.hot_offers_pagination_keyboard(
                lang,
                has_more,
                next_offset=20,
            )
            await target.answer(text, parse_mode="HTML", reply_markup=keyboard)
        except Exception as exc:  # pragma: no cover
            log.error("Failed to send hot offers: %s", exc)
            await target.answer(f"😔 {get_text(lang, 'error')}")

    async def _send_store_card(message: types.Message, store_id: int, lang: str) -> None:
        store = offer_service.get_store(store_id)
        if not store:
            await message.answer(
                "Магазин не найден" if lang == "ru" else "Do'kon topilmadi"
            )
            return
        text = offer_templates.render_store_card(lang, store)
        keyboard = offer_keyboards.store_card_keyboard(
            lang, store_id, store.offers_count, store.ratings_count
        )
        
        # Отправить с фото если есть
        if hasattr(store, 'photo') and store.photo:
            try:
                await message.answer_photo(
                    photo=store.photo,
                    caption=text,
                    parse_mode="HTML",
                    reply_markup=keyboard
                )
                return
            except Exception:
                pass  # Fallback to text if photo fails
        
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

    async def _send_offer_card(message: types.Message, offer: OfferListItem, lang: str) -> None:
        text = offer_templates.render_offer_card(lang, offer)
        keyboard = offer_keyboards.offer_quick_keyboard(lang, offer.id, offer.store_id, offer.delivery_enabled)
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
        offers: List[OfferListItem] = fetcher(city, 20)
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

    async def _set_offer_state(state: FSMContext, offers: List[OfferListItem]) -> None:
        await state.set_state(BrowseOffers.offer_list)
        await state.update_data(offer_list=[offer.id for offer in offers])

    async def _append_offer_ids(state: FSMContext, offers: List[OfferListItem]) -> None:
        data = await state.get_data()
        existing: List[int] = data.get("offer_list", [])
        for offer in offers:
            if offer.id not in existing:
                existing.append(offer.id)
        await state.update_data(offer_list=existing)

    def _callback_message(callback: types.CallbackQuery) -> types.Message | None:
        """Return callback's message when accessible."""
        message = callback.message
        return message if isinstance(message, types.Message) else None

    def _no_stores_text(lang: str, business_type: str) -> str:
        names = {
            "supermarket": get_text(lang, "supermarkets"),
            "restaurant": get_text(lang, "restaurants"),
            "bakery": get_text(lang, "bakeries"),
            "cafe": get_text(lang, "cafes"),
            "pharmacy": get_text(lang, "pharmacies"),
            "delivery": "🚚 Доставка" if lang == "ru" else "🚚 Yetkazish",
        }
        no_stores = (
            "В этой категории пока нет магазинов с активными предложениями"
            if lang == "ru"
            else "Bu kategoriyada hali do'konlar yo'q"
        )
        return f"😔 {names.get(business_type, business_type)}\n\n{no_stores}"

    def _invalid_number_text(lang: str, subject: str) -> str:
        base = "Пожалуйста, введите корректный номер" if lang == "ru" else "Iltimos, to'g'ri raqam kiriting"
        return f"× {base}"

    def _range_text(lang: str, max_value: int, subject: str) -> str:
        if lang == "ru":
            return f"❌ Номер должен быть от 1 до {max_value}"
        return f"❌ Raqam 1 dan {max_value} gacha bo'lishi kerak"
