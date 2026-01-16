"""Search handlers."""
from __future__ import annotations

import html
import logging
import re

from aiogram import F, Router, types
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.keyboards import (
    main_menu_customer,
    offer_quick_keyboard,
    search_cancel_keyboard,
    search_results_compact_keyboard,
)
from app.services.offer_service import OfferService
from app.templates.offers import render_offer_card, render_offer_details
from database_protocol import DatabaseProtocol
from handlers.common.states import BrowseOffers, Search
from handlers.common.utils import is_main_menu_button, is_search_button
from localization import get_text

logger = logging.getLogger(__name__)
router = Router()

# Словарь синонимов и переводов для поиска
SEARCH_KEYWORDS = {
    "ru": {
        "чай": [
            "чай",
            "choy",
            "чой",
            "ахмад",
            "акбар",
            "бернар",
            "tea",
            "ahmad",
            "akbar",
            "зеленый чай",
            "черный чай",
        ],
        "кофе": [
            "кофе",
            "qahva",
            "кахва",
            "нескафе",
            "nescafe",
            "coffee",
            "эспрессо",
            "капучино",
            "латте",
        ],
        "молоко": [
            "молоко",
            "sut",
            "сут",
            "кефир",
            "йогурт",
            "yogurt",
            "yoghurt",
            "milk",
            "сливки",
            "творог",
            "сметана",
        ],
        "хлеб": ["хлеб", "non", "нон", "булка", "лепешка", "bread", "батон", "багет", "лаваш"],
        "мясо": [
            "мясо",
            "go'sht",
            "гушт",
            "курица",
            "говядина",
            "свинина",
            "meat",
            "chicken",
            "beef",
            "баранина",
            "фарш",
            "стейк",
            "филе",
            "крылья",
            "ножки",
        ],
        "фрукты": [
            "фрукты",
            "meva",
            "мева",
            "яблоко",
            "банан",
            "апельсин",
            "fruits",
            "apple",
            "banana",
            "груша",
            "виноград",
            "мандарин",
            "лимон",
            "персик",
            "абрикос",
            "слива",
            "арбуз",
            "дыня",
        ],
        "овощи": [
            "овощи",
            "sabzavot",
            "сабзавот",
            "помидор",
            "огурец",
            "картошка",
            "vegetables",
            "морковь",
            "лук",
            "чеснок",
            "перец",
            "капуста",
            "баклажан",
            "кабачок",
            "свекла",
        ],
        "вода": ["вода", "suv", "сув", "минералка", "газировка", "water", "бонаква", "nestle"],
        "сок": ["сок", "sharbat", "шарбат", "напиток", "juice", "компот", "морс", "нектар"],
        "сыр": ["сыр", "pishloq", "пишлок", "брынза", "cheese", "моцарелла", "пармезан", "фета"],
        "колбаса": ["колбаса", "kolbasa", "сосиски", "sausage", "ветчина", "бекон", "салями"],
        "шоколад": ["шоколад", "shokolad", "шоколат", "chocolate", "schoko", "конфеты", "сладости"],
        "рыба": [
            "рыба",
            "baliq",
            "балык",
            "fish",
            "лосось",
            "семга",
            "форель",
            "тунец",
            "креветки",
        ],
        "масло": ["масло", "yog", "ёг", "oil", "подсолнечное", "оливковое", "сливочное"],
        "рис": ["рис", "guruch", "гуруч", "rice", "плов", "девзира"],
        "макароны": ["макароны", "makaron", "pasta", "спагетти", "лапша", "вермишель"],
        "яйца": ["яйца", "tuxum", "тухум", "eggs", "яйцо"],
        "сахар": ["сахар", "shakar", "шакар", "sugar"],
        "соль": ["соль", "tuz", "туз", "salt"],
        "мука": ["мука", "un", "ун", "flour"],
    },
    "uz": {
        "choy": [
            "choy",
            "чай",
            "чой",
            "ahmad",
            "akbar",
            "bernard",
            "tea",
            "yashil choy",
            "qora choy",
        ],
        "qahva": [
            "qahva",
            "кофе",
            "кахва",
            "nescafe",
            "нескафе",
            "coffee",
            "espresso",
            "cappuccino",
        ],
        "sut": ["sut", "молоко", "сут", "kefir", "yogurt", "йогурт", "milk", "qaymoq", "tvorog"],
        "non": ["non", "хлеб", "нон", "bulka", "lepeshka", "bread", "baton", "lavash"],
        "go'sht": [
            "go'sht",
            "мясо",
            "гушт",
            "tovuq",
            "mol",
            "cho'chqa",
            "meat",
            "chicken",
            "qo'y go'shti",
        ],
        "meva": [
            "meva",
            "фрукты",
            "мева",
            "olma",
            "banan",
            "apelsin",
            "fruits",
            "nok",
            "uzum",
            "mandarin",
        ],
        "sabzavot": [
            "sabzavot",
            "овощи",
            "сабзавот",
            "pomidor",
            "bodring",
            "kartoshka",
            "vegetables",
            "sabzi",
            "piyoz",
            "sarimsoq",
            "qalampir",
        ],
        "suv": ["suv", "вода", "сув", "mineral", "gazlangan", "water", "bonaqua"],
        "sharbat": ["sharbat", "сок", "шарбат", "ichimlik", "juice", "kompot"],
        "pishloq": ["pishloq", "сыр", "пишлок", "brynza", "cheese"],
        "kolbasa": ["kolbasa", "колбаса", "sosiska", "sausage", "vetçhina"],
        "shokolad": ["shokolad", "шоколад", "шоколат", "chocolate", "schoko", "konfet"],
        "baliq": ["baliq", "рыба", "fish", "losos", "forel"],
        "yog": ["yog", "масло", "oil", "sariyog", "zaytun yog'i"],
        "guruch": ["guruch", "рис", "rice", "palov", "devzira"],
        "makaron": ["makaron", "макароны", "pasta", "spagetti", "lapsha"],
        "tuxum": ["tuxum", "яйца", "eggs"],
        "shakar": ["shakar", "сахар", "sugar"],
        "tuz": ["tuz", "соль", "salt"],
        "un": ["un", "мука", "flour"],
    },
}


def _escape(text: str) -> str:
    return html.escape(text or "")


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


def _offer_price_line(offer, lang: str) -> str:
    currency = "so'm" if lang == "uz" else "сум"
    current = getattr(offer, "discount_price", 0) or getattr(offer, "price", 0) or 0
    original = getattr(offer, "original_price", 0) or 0
    if original and original > current:
        discount_pct = round((1 - current / original) * 100)
        discount_pct = min(99, max(1, discount_pct))
        return f"{_format_money(current)} {currency} (-{discount_pct}%)"
    return f"{_format_money(current)} {currency}"


def normalize_text(text: str) -> str:
    """Нормализация текста для поиска"""
    if not text:
        return ""
    # Приводим к нижнему регистру и удаляем лишние пробелы
    text = text.lower().strip()
    # Удаляем специальные символы, оставляем буквы, цифры и пробелы
    text = re.sub(r"[^\w\s]", " ", text)
    # Заменяем множественные пробелы на один
    text = re.sub(r"\s+", " ", text)
    return text


def expand_search_query(query: str, lang: str) -> list[str]:
    """Расширяет поисковый запрос синонимами и ключевыми словами"""
    normalized_query = normalize_text(query)
    words = normalized_query.split()

    expanded_terms = set(words)  # Начинаем с оригинальных слов

    # Добавляем синонимы для каждого слова
    for word in words:
        if len(word) < 2:  # Пропускаем слишком короткие слова
            continue

        # Ищем слово в словаре ключевых слов
        # Search keywords in both language maps (ru and uz) to improve matching
        for lookup_lang in ("ru", "uz"):
            for category, keywords in SEARCH_KEYWORDS.get(lookup_lang, {}).items():
                if word in keywords:
                    expanded_terms.update(keywords)
                    break
            else:
                continue
            break

    return list(expanded_terms)


def setup(
    dp: Router,
    db: DatabaseProtocol,
    offer_service: OfferService,
) -> None:
    """Register search handlers."""

    # Cancel handler - must be registered BEFORE Search.query handler
    @dp.message(
        Search.query, F.text.contains("Bekor") | F.text.contains("Отмена") | F.text.contains("❌")
    )
    async def cancel_search(message: types.Message, state: FSMContext):
        """Cancel search - handle cancel button immediately."""
        assert message.from_user is not None
        lang = db.get_user_language(message.from_user.id)
        await state.clear()
        await message.answer(
            get_text(lang, "operation_cancelled"), reply_markup=main_menu_customer(lang)
        )

    @dp.message(F.text.func(is_search_button))
    async def start_search(message: types.Message, state: FSMContext):
        """Start search flow."""
        assert message.from_user is not None
        # Clear any previous FSM state before starting search
        await state.clear()

        lang = db.get_user_language(message.from_user.id)

        await state.set_state(Search.query)
        # Simple search prompt
        prompt = "🔍 Nimani qidiryapsiz?" if lang == "uz" else "🔍 Что ищете?"
        await message.answer(prompt, reply_markup=search_cancel_keyboard(lang))

    @dp.message(Search.query)
    async def process_search_query(message: types.Message, state: FSMContext):
        """Process search query with improved search."""
        assert message.from_user is not None
        lang = db.get_user_language(message.from_user.id)

        # Import at function level to avoid UnboundLocalError
        from app.keyboards.user import main_menu_customer as menu_customer

        # Safely read incoming text and handle cancellation
        raw_text = (message.text or "").strip()

        # Check if user pressed main menu button - clear state and re-trigger the button handler
        if is_main_menu_button(raw_text):
            await state.clear()
            await message.answer(
                get_text(lang, "operation_cancelled"), reply_markup=menu_customer(lang)
            )
            return

        # Skip commands - let them be handled by command handlers
        if raw_text.startswith("/"):
            await state.clear()  # Exit search state
            return  # Let command handlers process this

        # Double-check cancel (fallback)
        if "bekor" in raw_text.lower() or "отмена" in raw_text.lower() or "❌" in raw_text:
            await state.clear()
            await message.answer(
                get_text(lang, "operation_cancelled"), reply_markup=menu_customer(lang)
            )
            return

        query = raw_text.strip()
        if len(query) < 2:
            await message.answer(
                "Введите минимум 2 символа" if lang == "ru" else "Kamida 2 ta belgi kiriting"
            )
            return

        # Расширяем запрос синонимами
        normalized_query = normalize_text(query)
        base_terms = [query]
        base_terms.extend([word for word in normalized_query.split() if len(word) >= 2])
        deduped_terms = []
        seen_terms = set()
        for term in base_terms:
            term = term.strip()
            if len(term) < 2 or term in seen_terms:
                continue
            seen_terms.add(term)
            deduped_terms.append(term)
        base_terms = deduped_terms

        # Log search for debugging
        from logging import getLogger

        logger = getLogger(__name__)
        logger.info(f"🔍 Search: query='{query}', base_terms={base_terms}, lang={lang}")

        # Perform search
        # Use get_user instead of get_user_model if protocol doesn't support it
        user_data = db.get_user(message.from_user.id)
        raw_city = user_data.get("city") if user_data else None
        raw_region = user_data.get("region") if user_data else None
        raw_district = user_data.get("district") if user_data else None

        # Normalize city (e.g. "Samarqand" -> "Самарканд") to match DB records
        from app.core.utils import normalize_city

        city = normalize_city(raw_city) if raw_city else None
        region = normalize_city(raw_region) if raw_region else None
        district = normalize_city(raw_district) if raw_district else None

        logger.info(f"🔍 Search: user_city='{raw_city}', normalized_city='{city}'")

        # Search both offers and stores
        all_results = []
        store_results = []

        # 1. Search stores first
        if hasattr(db, "search_stores"):
            try:
                store_city_scope = city or region
                stores = db.search_stores(query, store_city_scope)
                logger.info(f"🔍 Store search found {len(stores)} stores")
                store_results = stores
            except Exception as e:
                logger.error(f"Error searching stores: {e}")

        # 2. Search offers (including by category)
        min_results_for_synonyms = 10

        def run_offer_search(
            scope_city: str | None,
            scope_region: str | None,
            scope_district: str | None,
        ) -> tuple[list, list]:
            all_results = []
            seen_offer_ids = set()
            searched_terms = set()
            search_terms = []

            def search_by_term(term: str) -> None:
                term = term.strip()
                if len(term) < 2 or term in searched_terms:
                    return
                searched_terms.add(term)
                search_terms.append(term)
                results = offer_service.search_offers(
                    term,
                    scope_city,
                    region=scope_region,
                    district=scope_district,
                )
                logger.info(f"Search term '{term}' found {len(results)} offers")
                for offer in results:
                    if offer.id not in seen_offer_ids:
                        seen_offer_ids.add(offer.id)
                        all_results.append(offer)

            for term in base_terms:
                search_by_term(term)

            if len(all_results) < min_results_for_synonyms:
                expanded_terms = expand_search_query(query, lang)
                for term in expanded_terms:
                    if len(all_results) >= min_results_for_synonyms:
                        break
                    search_by_term(term)

            return all_results, search_terms

        all_results, search_terms = run_offer_search(city, region, district)

        if not all_results and (city or region or district):
            logger.info("Search: no results in scoped search, retrying without location")
            all_results, search_terms = run_offer_search(None, None, None)

        def relevance_score(offer_title: str) -> int:
            title_lower = normalize_text(offer_title)
            score = 0

            # Высший приоритет - точное совпадение
            if normalize_text(query) in title_lower:
                score += 100

            # Приоритет для совпадений в начале названия
            for term in search_terms:
                if title_lower.startswith(term):
                    score += 50
                elif term in title_lower:
                    score += 10

            return score

        all_results.sort(key=lambda x: relevance_score(x.title), reverse=True)

        # Check if we have any results (offers or stores)
        total_results = len(all_results) + len(store_results)

        if total_results == 0:
            # Короткое сообщение
            no_results_msg = (
                "😔 Ничего не найдено\n\nПопробуйте другой запрос"
                if lang == "ru"
                else "😔 Hech narsa topilmadi\n\nBoshqa so'z bilan qidirib ko'ring"
            )
            await message.answer(no_results_msg, reply_markup=menu_customer(lang))
            return

        # Save search results to FSM for pagination
        await state.update_data(
            search_results=[o.id for o in all_results],
            search_query=query,
            search_page=0,
        )

        # Show store results first - present each store as a card with a button to view its products
        if store_results:
            # If the user's query likely targets a specific store name, prefer showing store cards
            norm_q = normalize_text(query)
            is_store_query = any(
                norm_q in normalize_text(s.get("name") or s.get("store_name") or "").lower()
                for s in store_results
            )

            # Send up to 5 stores as separate cards each with an inline "Смотреть товары" button
            for store in store_results[:5]:
                store_name = store.get("name", "Магазин")
                address = store.get("address", "Адрес не указан")
                category = store.get("category", "Продукты")

                stores_card = f"🏪 <b>{store_name}</b>\n" f"📍 {address}\n" f"📂 {category}\n"

                if store.get("delivery_enabled") == 1:
                    delivery_price = store.get("delivery_price", 0)
                    min_order = store.get("min_order_amount", 0)
                    stores_card += (
                        f"🚚 Доставка: {delivery_price:,} сум (мин. {min_order:,} сум)\n"
                        if lang == "ru"
                        else f"🚚 Yetkazib berish: {delivery_price:,} so'm (min. {min_order:,} so'm)\n"
                    )

                kb = InlineKeyboardBuilder()
                sid = store.get("store_id") or store.get("id") or store.get("storeId")
                kb.button(
                    text=("🗂 Открыть каталог" if lang == "ru" else "🗂 Katalogni ochish"),
                    callback_data=f"show_store_products_{sid}",
                )
                kb.adjust(1)

                # If store record contains a photo (photo or photo_id), send as photo with caption
                photo = store.get("photo") or store.get("photo_id")
                if photo:
                    try:
                        await message.answer_photo(
                            photo=photo,
                            caption=stores_card,
                            parse_mode="HTML",
                            reply_markup=kb.as_markup(),
                        )
                        continue
                    except Exception:
                        # Fall back to text if sending photo fails
                        pass

                await message.answer(stores_card, parse_mode="HTML", reply_markup=kb.as_markup())

            # If user likely searched store name, do not flood with all offers — stop here
            if is_store_query:
                await state.clear()
                return

        # Show offer results as compact list with inline buttons
        if all_results:
            await _send_search_results_page(message, all_results, query, lang, page=0)
        else:
            await state.clear()

    async def _send_search_results_page(
        target: types.Message | types.CallbackQuery,
        all_results: list,
        query: str,
        lang: str,
        page: int = 0,
        edit: bool = False,
    ) -> None:
        """Send compact search results with pagination."""
        ITEMS_PER_PAGE = 10
        total_count = len(all_results)
        total_pages = max(1, (total_count + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE)
        page = max(0, min(page, total_pages - 1))

        start_idx = page * ITEMS_PER_PAGE
        page_offers = all_results[start_idx : start_idx + ITEMS_PER_PAGE]

        title_label = "Поиск" if lang == "ru" else "Qidiruv"
        page_label = "Стр." if lang == "ru" else "Sah."
        total_label = "Всего" if lang == "ru" else "Jami"

        lines = [
            f"{title_label}: <b>{_escape(query)}</b>",
            f"{page_label} {page + 1}/{total_pages} | {total_label} {total_count}",
        ]

        for idx, offer in enumerate(page_offers, start=1):
            title_line = _escape(_short_title(getattr(offer, "title", ""), limit=28))
            price_line = _offer_price_line(offer, lang)
            store_name = _short_store(getattr(offer, "store_name", "") or "", limit=16)
            meta = price_line
            if store_name:
                meta = f"{meta} | {_escape(store_name)}"
            lines.append(f"{idx}. <b>{title_line}</b> - {meta}")

        text = "\n".join(lines).rstrip()

        keyboard = search_results_compact_keyboard(lang, page_offers, page, total_pages, query)

        if edit and isinstance(target, types.CallbackQuery) and target.message:
            try:
                await target.message.edit_text(text, parse_mode="HTML", reply_markup=keyboard)
            except Exception:
                await target.message.answer(text, parse_mode="HTML", reply_markup=keyboard)
        elif isinstance(target, types.Message):
            await target.answer(text, parse_mode="HTML", reply_markup=keyboard)
        elif isinstance(target, types.CallbackQuery) and target.message:
            await target.message.answer(text, parse_mode="HTML", reply_markup=keyboard)

    @dp.callback_query(F.data.startswith("search_page_"))
    async def search_page_handler(callback: types.CallbackQuery, state: FSMContext) -> None:
        """Handle search results pagination."""
        if not callback.from_user:
            await callback.answer()
            return

        lang = db.get_user_language(callback.from_user.id)

        try:
            page = int((callback.data or "").split("_")[-1])
        except (ValueError, IndexError):
            await callback.answer(get_text(lang, "error"), show_alert=True)
            return

        # Get search results from FSM
        data = await state.get_data()
        offer_ids = data.get("search_results", [])
        query = data.get("search_query", "")

        if not offer_ids:
            await callback.answer(
                "Результаты поиска устарели. Повторите поиск."
                if lang == "ru"
                else "Qidiruv natijalari eskirgan. Qayta qidiring.",
                show_alert=True,
            )
            return

        # Fetch offer objects
        all_results = []
        for offer_id in offer_ids:
            try:
                offer = offer_service.get_offer_details(offer_id)
                if offer:
                    all_results.append(offer)
            except Exception:
                pass

        await state.update_data(search_page=page)
        await _send_search_results_page(callback, all_results, query, lang, page=page, edit=True)
        await callback.answer()

    @dp.callback_query(F.data.startswith("search_select_"))
    async def search_select_handler(callback: types.CallbackQuery, state: FSMContext) -> None:
        """Handle search result selection - show offer card with cart/order buttons."""
        if not callback.from_user or not callback.message:
            await callback.answer()
            return

        lang = db.get_user_language(callback.from_user.id)

        try:
            offer_id = int((callback.data or "").split("_")[-1])
        except (ValueError, IndexError):
            await callback.answer(get_text(lang, "error"), show_alert=True)
            return

        # Fetch offer details
        try:
            offer = offer_service.get_offer_details(offer_id)
            if not offer:
                await callback.answer(
                    "Товар не найден" if lang == "ru" else "Mahsulot topilmadi", show_alert=True
                )
                return

            # Get store details
            store = offer_service.get_store(offer.store_id) if offer.store_id else None
            delivery_enabled = store.delivery_enabled if store else False

            max_quantity = offer.quantity or 0
            if max_quantity <= 0:
                await callback.answer(
                    "Товар закончился" if lang == "ru" else "Mahsulot tugadi",
                    show_alert=True,
                )
                return

            # Get current search context to restore later
            data = await state.get_data()
            search_results = data.get("search_results", [])
            search_query = data.get("search_query", "")
            current_page = int(data.get("search_page", 0) or 0)

            # Save search context for back navigation
            await state.update_data(
                source="search",
                search_results=search_results,
                search_query=search_query,
                search_page=current_page,
            )

            text = render_offer_details(lang, offer, store)

            # Use keyboard with cart buttons and back to search
            from app.keyboards.offers import offer_details_search_keyboard

            kb = offer_details_search_keyboard(lang, offer_id, offer.store_id, delivery_enabled)

            # Delete search results and send offer card with photo
            try:
                await callback.message.delete()
            except Exception:
                pass

            if getattr(offer, "photo", None):
                try:
                    await callback.message.answer_photo(
                        photo=offer.photo,
                        caption=text,
                        parse_mode="HTML",
                        reply_markup=kb,
                    )
                    await callback.answer()
                    return
                except Exception:
                    pass

            await callback.message.answer(text, parse_mode="HTML", reply_markup=kb)

        except Exception as e:
            logger.error(f"Failed to show offer {offer_id}: {e}")
            await callback.answer(get_text(lang, "error"), show_alert=True)

        await callback.answer()

    @dp.callback_query(F.data == "search_new")
    async def search_new_handler(callback: types.CallbackQuery, state: FSMContext) -> None:
        """Start new search."""
        if not callback.from_user or not callback.message:
            await callback.answer()
            return

        lang = db.get_user_language(callback.from_user.id)
        await state.clear()
        await state.set_state(Search.query)
        await callback.message.answer(
            get_text(lang, "enter_search_query"), reply_markup=search_cancel_keyboard(lang)
        )
        await callback.answer()

    @dp.callback_query(F.data == "search_noop")
    async def search_noop_handler(callback: types.CallbackQuery) -> None:
        """Handle no-op callback for page indicator."""
        await callback.answer()

    @dp.callback_query(F.data == "back_to_search_results")
    async def back_to_search_results(callback: types.CallbackQuery, state: FSMContext) -> None:
        """Return from offer card back to the last search results list."""
        if not callback.from_user:
            await callback.answer()
            return

        lang = db.get_user_language(callback.from_user.id)

        # Restore search context from FSM
        data = await state.get_data()
        offer_ids = data.get("search_results", [])
        query = data.get("search_query", "")
        page = int(data.get("search_page", 0) or 0)

        if not offer_ids:
            await callback.answer(
                "Результаты поиска устарели. Повторите поиск."
                if lang == "ru"
                else "Qidiruv natijalari eskirgan. Qayta qidiring.",
                show_alert=True,
            )
            return

        # Fetch offer objects again
        all_results = []
        for offer_id in offer_ids:
            try:
                offer = offer_service.get_offer_details(offer_id)
                if offer:
                    all_results.append(offer)
            except Exception:
                pass

        # Delete current offer card and show the list
        msg = callback.message
        if msg:
            try:
                await msg.delete()
            except Exception:
                pass

        await _send_search_results_page(callback, all_results, query, lang, page=page, edit=False)
        await callback.answer()

    @dp.callback_query(F.data.startswith("show_store_products_"))
    async def show_store_products(callback: types.CallbackQuery, state: FSMContext) -> None:
        """Show products for a specific store when user taps 'Смотреть товары'."""
        if not db:
            lang_code = (callback.from_user.language_code or "ru") if callback.from_user else "ru"
            if lang_code.startswith("uz"):
                text = "❌ Xizmat vaqtincha mavjud emas. Keyinroq urinib ko'ring."
            else:
                text = "❌ Сервис временно недоступен. Попробуйте позже."
            await callback.answer(text, show_alert=True)
            return
        assert callback.from_user is not None
        # Ensure callback.message is accessible
        from aiogram import types as _ai_types

        msg = callback.message if isinstance(callback.message, _ai_types.Message) else None
        lang = db.get_user_language(callback.from_user.id)
        try:
            store_id = int(callback.data.rsplit("_", 1)[-1])
        except (ValueError, IndexError):
            await callback.answer(get_text(lang, "error"), show_alert=True)
            return

        # Prefer service method to list active offers for the store
        try:
            offers = offer_service.list_active_offers_by_store(store_id)
        except Exception:
            offers = []

        # If no active offers found, try a fallback to list all store offers
        # (including inactive / out-of-stock) so users can at least see what's offered.
        # Store offer ids in FSM so we can paginate and let user pick by inline numbers
        await state.set_state(BrowseOffers.offer_list)
        await state.update_data(
            offer_list=[o.id for o in offers],
            current_store_id=store_id,
            store_offers_page=0,
            store_category="all",
        )

        # Get store name
        store = offer_service.get_store(store_id)
        store_name = store.name if store else "Магазин"

        # Header like hot offers
        total = len(offers)
        per_page = 10
        total_pages = max(1, (total + per_page - 1) // per_page)

        page_offset = 0
        page_offers = offers[page_offset : page_offset + per_page]

        page_label = "Стр." if lang == "ru" else "Sah."
        total_label = "Всего" if lang == "ru" else "Jami"
        list_label = "Товары" if lang == "ru" else "Mahsulotlar"

        lines = [
            f"🏪 <b>{_escape(store_name)}</b>",
            f"{list_label} | {page_label} 1/{total_pages} | {total_label} {total}",
        ]

        for idx, off in enumerate(page_offers, start=1):
            title_line = _escape(_short_title(getattr(off, "title", ""), limit=28))
            price_line = _offer_price_line(off, lang)
            lines.append(f"{idx}. <b>{title_line}</b> - {price_line}")

        if not page_offers:
            empty = "Нет доступных товаров" if lang == "ru" else "Mavjud mahsulotlar yo'q"
            lines.append(empty)

        page_text = "\n".join(lines).rstrip()

        # Compact keyboard with offer buttons
        from aiogram.utils.keyboard import InlineKeyboardBuilder

        kb = InlineKeyboardBuilder()
        action = "🔎 Открыть" if lang == "ru" else "🔎 Ochish"
        for off in page_offers:
            offer_id = getattr(off, "id", 0)
            title = getattr(off, "title", "Товар")
            short = _short_title(title, limit=26)
            kb.button(text=f"{action} - {short}", callback_data=f"store_offer_{store_id}_{offer_id}")

        kb.adjust(1)

        # Pagination row
        if total_pages > 1:
            if page_offset > 0:
                kb.button(
                    text="Назад" if lang == "ru" else "Oldingi",
                    callback_data=f"store_page_{store_id}_{max(0, page_offset - per_page)}",
                )
            kb.button(text=f"1/{total_pages}", callback_data="store_offers_noop")
            if page_offset + per_page < total:
                kb.button(
                    text="Далее" if lang == "ru" else "Keyingi",
                    callback_data=f"store_page_{store_id}_{page_offset + per_page}",
                )

        # Back button
        back_text = "Назад" if lang == "ru" else "Orqaga"
        kb.button(text=back_text, callback_data=f"back_to_store_{store_id}")

        if msg:
            await msg.answer(page_text, parse_mode="HTML", reply_markup=kb.as_markup())
        else:
            await callback.answer(page_text, show_alert=True)

    @dp.callback_query(F.data.startswith("store_page_"))
    async def store_page(callback: types.CallbackQuery, state: FSMContext) -> None:
        """Show a different page of store offers - unified style."""
        if not callback.from_user:
            await callback.answer()
            return
        from aiogram import types as _ai_types

        msg = callback.message if isinstance(callback.message, _ai_types.Message) else None
        try:
            parts = (callback.data or "").split("_")
            store_id = int(parts[2])
            offset = int(parts[3])
        except Exception:
            await callback.answer(
                get_text(db.get_user_language(callback.from_user.id), "error"), show_alert=True
            )
            return

        lang = db.get_user_language(callback.from_user.id)

        try:
            offers = offer_service.list_active_offers_by_store(store_id)
        except Exception:
            offers = []

        # Get store name
        store = offer_service.get_store(store_id)
        store_name = store.name if store else "Магазин"

        total = len(offers)
        per_page = 10
        page_offers = offers[offset : offset + per_page]
        current_page = offset // per_page + 1
        total_pages = (total + per_page - 1) // per_page

        await state.update_data(store_offers_page=current_page - 1, store_category="all")

        # Header
        page_label = "Стр." if lang == "ru" else "Sah."
        total_label = "Всего" if lang == "ru" else "Jami"
        list_label = "Товары" if lang == "ru" else "Mahsulotlar"

        lines = [
            f"🏪 <b>{_escape(store_name)}</b>",
            f"{list_label} | {page_label} {current_page}/{total_pages} | {total_label} {total}",
        ]

        for idx, off in enumerate(page_offers, start=offset + 1):
            title_line = _escape(_short_title(getattr(off, "title", ""), limit=28))
            price_line = _offer_price_line(off, lang)
            lines.append(f"{idx}. <b>{title_line}</b> - {price_line}")

        if not page_offers:
            empty = "Нет доступных товаров" if lang == "ru" else "Mavjud mahsulotlar yo'q"
            lines.append(empty)

        page_text = "\n".join(lines).rstrip()

        # Compact keyboard
        from aiogram.utils.keyboard import InlineKeyboardBuilder

        kb = InlineKeyboardBuilder()
        action = "🔎 Открыть" if lang == "ru" else "🔎 Ochish"

        for off in page_offers:
            offer_id = getattr(off, "id", 0)
            title = getattr(off, "title", "Товар")
            short = _short_title(title, limit=26)
            kb.button(text=f"{action} - {short}", callback_data=f"store_offer_{store_id}_{offer_id}")

        kb.adjust(1)

        # Pagination row
        if total_pages > 1:
            if offset > 0:
                kb.button(
                    text="Назад" if lang == "ru" else "Oldingi",
                    callback_data=f"store_page_{store_id}_{max(0, offset - per_page)}",
                )
            kb.button(text=f"{current_page}/{total_pages}", callback_data="store_offers_noop")
            if offset + per_page < total:
                kb.button(
                    text="Далее" if lang == "ru" else "Keyingi",
                    callback_data=f"store_page_{store_id}_{offset + per_page}",
                )

        # Back button
        back_text = "Назад" if lang == "ru" else "Orqaga"
        kb.button(text=back_text, callback_data=f"back_to_store_{store_id}")

        if msg:
            try:
                await msg.edit_text(page_text, parse_mode="HTML", reply_markup=kb.as_markup())
            except Exception:
                await msg.answer(page_text, parse_mode="HTML", reply_markup=kb.as_markup())
        await callback.answer()

    @dp.callback_query(F.data == "store_offers_noop")
    async def store_offers_noop(callback: types.CallbackQuery) -> None:
        """Handle noop button (page indicator)."""
        await callback.answer()

    @dp.callback_query(F.data.startswith("store_choose_page_"))
    async def store_choose_page(callback: types.CallbackQuery, state: FSMContext) -> None:
        """Open inline numbered selector for offers on the given page."""
        if not callback.from_user:
            await callback.answer()
            return
        lang = db.get_user_language(callback.from_user.id)
        try:
            parts = (callback.data or "").split("_")
            store_id = int(parts[2])
            offset = int(parts[3])
        except Exception:
            await callback.answer(get_text(lang, "error"), show_alert=True)
            return

        data = await state.get_data()
        offer_list = data.get("offer_list", [])
        per_page = 10
        page_ids = offer_list[offset : offset + per_page]
        if not page_ids:
            await callback.answer(get_text(lang, "no_offers"), show_alert=True)
            return

        from aiogram.utils.keyboard import InlineKeyboardBuilder

        kb = InlineKeyboardBuilder()
        for idx in range(1, len(page_ids) + 1):
            kb.button(text=str(idx), callback_data=f"store_choose_item_{store_id}_{offset}_{idx}")
        kb.adjust(len(page_ids))

        # Send selection keyboard as a new message
        from aiogram import types as _ai_types

        msg = callback.message if isinstance(callback.message, _ai_types.Message) else None
        if msg:
            await msg.answer(
                (
                    "Выберите товар на этой странице:"
                    if lang == "ru"
                    else "Sahifadagi mahsulotni tanlang:"
                ),
                reply_markup=kb.as_markup(),
            )
        else:
            await callback.answer(
                (
                    "Выберите товар на этой странице:"
                    if lang == "ru"
                    else "Sahifadagi mahsulotni tanlang:"
                ),
                show_alert=True,
            )
        await callback.answer()

    @dp.callback_query(F.data.startswith("store_choose_item_"))
    async def store_choose_item(callback: types.CallbackQuery, state: FSMContext) -> None:
        """User chose a numbered item — show offer card with cart/order buttons."""
        if not callback.from_user:
            await callback.answer()
            return
        lang = db.get_user_language(callback.from_user.id)
        try:
            parts = (callback.data or "").split("_")
            store_id = int(parts[3])
            offset = int(parts[4])
            idx = int(parts[5])
        except Exception:
            await callback.answer(get_text(lang, "error"), show_alert=True)
            return

        data = await state.get_data()
        offer_list = data.get("offer_list", [])
        global_index = offset + (idx - 1)
        if global_index < 0 or global_index >= len(offer_list):
            await callback.answer(get_text(lang, "error"), show_alert=True)
            return

        offer_id = offer_list[global_index]
        # Fetch details and send with cart/order buttons
        try:
            details = offer_service.get_offer_details(offer_id)
            from aiogram import types as _ai_types

            msg = callback.message if isinstance(callback.message, _ai_types.Message) else None
            if msg and details:
                # Get store details
                store = offer_service.get_store(details.store_id) if details.store_id else None
                delivery_enabled = store.delivery_enabled if store else False

                max_quantity = details.quantity or 0
                if max_quantity <= 0:
                    await callback.answer(
                        "Товар закончился" if lang == "ru" else "Mahsulot tugadi",
                        show_alert=True,
                    )
                    return

                text = render_offer_details(lang, details, store)

                # Use keyboard with cart buttons and back to search
                from app.keyboards.offers import offer_details_search_keyboard

                kb = offer_details_search_keyboard(
                    lang, offer_id, details.store_id, delivery_enabled
                )

                # Delete message and send offer card with photo
                try:
                    await msg.delete()
                except Exception:
                    pass

                if getattr(details, "photo", None):
                    try:
                        await msg.answer_photo(
                            photo=details.photo,
                            caption=text,
                            parse_mode="HTML",
                            reply_markup=kb,
                        )
                        await callback.answer()
                        return
                    except Exception:
                        pass

                await msg.answer(text, parse_mode="HTML", reply_markup=kb)
            else:
                await callback.answer(
                    get_text(lang, "open_chat_to_view") or "Open chat to view the offer",
                    show_alert=True,
                )
        except Exception as e:
            logger.error(f"Failed to send offer details for {offer_id}: {e}")
            await callback.answer(get_text(lang, "error"), show_alert=True)
        await callback.answer()
