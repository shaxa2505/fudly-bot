"""Search handlers."""
from __future__ import annotations

import re
from aiogram import F, Router, types
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.fsm.context import FSMContext

from app.keyboards import main_menu_customer, search_cancel_keyboard, offer_quick_keyboard
from app.services.offer_service import OfferService
from app.templates.offers import render_offer_card
from database_protocol import DatabaseProtocol
from handlers.common_states.states import Search
from localization import get_text

router = Router()

# Словарь синонимов и переводов для поиска
SEARCH_KEYWORDS = {
    "ru": {
        "чай": ["чай", "choy", "чой", "ахмад", "акбар", "бернар", "tea", "ahmad", "akbar"],
        "кофе": ["кофе", "qahva", "кахва", "нескафе", "nescafe", "coffee"],
        "молоко": ["молоко", "sut", "сут", "кефир", "йогурт", "yogurt", "yoghurt", "milk"],
        "хлеб": ["хлеб", "non", "нон", "булка", "лепешка", "bread"],
        "мясо": ["мясо", "go'sht", "гушт", "курица", "говядина", "свинина", "meat", "chicken", "beef"],
        "фрукты": ["фрукты", "meva", "мева", "яблоко", "банан", "апельсин", "fruits", "apple", "banana"],
        "овощи": ["овощи", "sabzavot", "сабзавот", "помидор", "огурец", "картошка", "vegetables"],
        "вода": ["вода", "suv", "сув", "минералка", "газировка", "water"],
        "сок": ["сок", "sharbat", "шарбат", "напиток", "juice"],
        "сыр": ["сыр", "pishloq", "пишлок", "брынза", "cheese"],
        "колбаса": ["колбаса", "kolbasa", "колбаса", "сосиски", "sausage"],
        "шоколад": ["шоколад", "shokolad", "шоколат", "chocolate", "schoko"],
    },
    "uz": {
        "choy": ["choy", "чай", "чой", "ahmad", "akbar", "bernard", "tea"],
        "qahva": ["qahva", "кофе", "кахва", "nescafe", "нескафе", "coffee"],
        "sut": ["sut", "молоко", "сут", "kefir", "yogurt", "йогурт", "milk"],
        "non": ["non", "хлеб", "нон", "bulka", "lepeshka", "bread"],
        "go'sht": ["go'sht", "мясо", "гушт", "tovuq", "mol", "cho'chqa", "meat", "chicken"],
        "meva": ["meva", "фрукты", "мева", "olma", "banan", "apelsin", "fruits"],
        "sabzavot": ["sabzavot", "овощи", "сабзавот", "pomidor", "bodring", "kartoshka", "vegetables"],
        "suv": ["suv", "вода", "сув", "mineral", "gazlangan", "water"],
        "sharbat": ["sharbat", "сок", "шарбат", "ichimlik", "juice"],
        "pishloq": ["pishloq", "сыр", "пишлок", "brynza", "cheese"],
        "kolbasa": ["kolbasa", "колбаса", "колбаса", "sosiska", "sausage"],
        "shokolad": ["shokolad", "шоколад", "шоколат", "chocolate", "schoko"],
    }
}

def normalize_text(text: str) -> str:
    """Нормализация текста для поиска"""
    if not text:
        return ""
    # Приводим к нижнему регистру и удаляем лишние пробелы
    text = text.lower().strip()
    # Удаляем специальные символы, оставляем буквы, цифры и пробелы
    text = re.sub(r'[^\w\s]', ' ', text)
    # Заменяем множественные пробелы на один
    text = re.sub(r'\s+', ' ', text)
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
    
    @dp.message(F.text.in_(["🔍 Поиск", "🔍 Qidirish"]))
    async def start_search(message: types.Message, state: FSMContext):
        """Start search flow."""
        lang = db.get_user_language(message.from_user.id)
        
        await state.set_state(Search.query)
        await message.answer(
            get_text(lang, "enter_search_query"),
            reply_markup=search_cancel_keyboard(lang)
        )

    @dp.message(Search.query)
    async def process_search_query(message: types.Message, state: FSMContext):
        """Process search query with improved search."""
        lang = db.get_user_language(message.from_user.id)
        
        # Handle cancellation
        if message.text in ["Отмена", "Bekor qilish", "❌ Отмена", "❌ Bekor qilish"]:
            await state.clear()
            await message.answer(
                get_text(lang, "action_cancelled"),
                reply_markup=main_menu_customer(lang)
            )
            return
            
        query = message.text.strip()
        if len(query) < 2:
            await message.answer(
                "Введите минимум 2 символа" if lang == "ru" else "Kamida 2 ta belgi kiriting"
            )
            return
        
        # Расширяем запрос синонимами
        search_terms = expand_search_query(query, lang)
        
        # Log search for debugging
        from logging import getLogger
        logger = getLogger(__name__)
        logger.info(f"🔍 Search: query='{query}', terms={search_terms}, lang={lang}")
        
        # Perform search
        # Use get_user instead of get_user_model if protocol doesn't support it
        user_data = db.get_user(message.from_user.id)
        raw_city = user_data.get("city") if user_data else None
        
        # Normalize city (e.g. "Samarqand" -> "Самарканд") to match DB records
        from app.core.utils import normalize_city
        city = normalize_city(raw_city) if raw_city else None
        
        logger.info(f"🔍 Search: user_city='{raw_city}', normalized_city='{city}'")
        
        # Search both offers and stores
        all_results = []
        seen_offer_ids = set()
        store_results = []
        
        # 1. Search stores first
        if hasattr(db, 'search_stores'):
            try:
                stores = db.search_stores(query, city or "Ташкент")
                logger.info(f"🔍 Store search found {len(stores)} stores")
                store_results = stores
            except Exception as e:
                logger.error(f"Error searching stores: {e}")
        
        # 2. Search offers (including by category)
        # Ищем по расширенным терминам
        for term in search_terms:
            if len(term) < 2:  # Пропускаем короткие термины
                continue
                
            results = offer_service.search_offers(term, city)
            logger.info(f"🔍 Search term '{term}' found {len(results)} offers")
            
            for offer in results:
                if offer.id not in seen_offer_ids:
                    seen_offer_ids.add(offer.id)
                    all_results.append(offer)
        
        # Сортируем результаты по релевантности (сначала те, где запрос в начале названия)
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
            # Показываем подсказки для улучшения поиска
            tips_ru = [
                "💡 <b>Советы для поиска:</b>",
                "• Используйте простые слова: <i>чай, молоко, хлеб</i>",
                "• Попробуйте название магазина: <i>Космос, Korzinka</i>",
                "• Ищите на русском или узбекском",
                "• Попробуйте похожие товары в разделе «Горячее»"
            ]
            
            tips_uz = [
                "💡 <b>Qidiruv bo'yicha maslahatlar:</b>", 
                "• Oddiy so'zlardan foydalaning: <i>choy, sut, non</i>",
                "• Do'kon nomini kiriting: <i>Kosmos, Korzinka</i>",
                "• Rus yoki o'zbek tilida qidiring",
                "• «Issiq» bo'limida o'xshash mahsulotlarni ko'rib chiqing"
            ]
            
            tips = tips_ru if lang == "ru" else tips_uz
            
            await message.answer(
                "😔 <b>Ничего не найдено</b>\n\n" + "\n".join(tips) if lang == "ru"
                else "😔 <b>Hech narsa topilmadi</b>\n\n" + "\n".join(tips_uz),
                parse_mode="HTML"
            )
            return
        
        # Show results summary
        result_msg = f"🔍 <b>Результаты поиска:</b> {total_results}\n" if lang == "ru" else f"🔍 <b>Qidiruv natijalari:</b> {total_results}\n"
        if store_results:
            result_msg += f"🏪 Магазины: {len(store_results)}\n" if lang == "ru" else f"🏪 Do'konlar: {len(store_results)}\n"
        if all_results:
            result_msg += f"📦 Товары: {len(all_results)}" if lang == "ru" else f"📦 Mahsulotlar: {len(all_results)}"
            
        await message.answer(
            result_msg,
            parse_mode="HTML",
            reply_markup=main_menu_customer(lang)
        )
        await state.clear()
        
        # Show store results first - present each store as a card with a button to view its products
        if store_results:
            # If the user's query likely targets a specific store name, prefer showing store cards
            norm_q = normalize_text(query)
            is_store_query = any(norm_q in normalize_text((s.get('name') or s.get('store_name') or '')).lower() for s in store_results)

            # Send up to 5 stores as separate cards each with an inline "Смотреть товары" button
            for store in store_results[:5]:
                store_name = store.get('name', 'Магазин')
                address = store.get('address', 'Адрес не указан')
                category = store.get('category', 'Продукты')

                stores_card = (
                    f"🏪 <b>{store_name}</b>\n"
                    f"📍 {address}\n"
                    f"📂 {category}\n"
                )

                if store.get('delivery_enabled') == 1:
                    delivery_price = store.get('delivery_price', 0)
                    min_order = store.get('min_order_amount', 0)
                    stores_card += (
                        f"🚚 Доставка: {delivery_price:,} сум (мин. {min_order:,} сум)\n"
                        if lang == "ru"
                        else f"🚚 Yetkazib berish: {delivery_price:,} so'm (min. {min_order:,} so'm)\n"
                    )

                kb = InlineKeyboardBuilder()
                sid = store.get('store_id') or store.get('id') or store.get('storeId')
                kb.button(text=("Смотреть товары" if lang == 'ru' else "Mahsulotlarni ko'rish"), callback_data=f"show_store_products_{sid}")
                kb.adjust(1)

                await message.answer(stores_card, parse_mode="HTML", reply_markup=kb.as_markup())

            # If user likely searched store name, do not flood with all offers — stop here
            if is_store_query:
                return
        
        # Show offer results (grouped in media group if possible)
        if all_results:
            offers_count = min(10, len(all_results))
            offers_text = f"\n📦 <b>Найденные товары ({offers_count}):</b>\n" if lang == "ru" else f"\n📦 <b>Topilgan mahsulotlar ({offers_count}):</b>\n"
            await message.answer(offers_text, parse_mode="HTML")
            
            for offer in all_results[:10]:  # Show top 10 offers
                caption = render_offer_card(lang, offer)
                
                keyboard = offer_quick_keyboard(
                    lang, 
                    offer.id, 
                    offer.store_id, 
                    offer.delivery_enabled
                )
                
                if offer.photo:
                    try:
                        await message.answer_photo(
                            photo=offer.photo,
                            caption=caption,
                            parse_mode="HTML",
                            reply_markup=keyboard
                        )
                    except Exception:
                        await message.answer(caption, parse_mode="HTML", reply_markup=keyboard)
                else:
                    await message.answer(caption, parse_mode="HTML", reply_markup=keyboard)

    @dp.callback_query(F.data.startswith("show_store_products_"))
    async def show_store_products(callback: types.CallbackQuery) -> None:
        """Show products for a specific store when user taps 'Смотреть товары'."""
        if not db:
            await callback.answer("System error", show_alert=True)
            return

        lang = db.get_user_language(callback.from_user.id)
        try:
            store_id = int(callback.data.rsplit("_", 1)[-1])
        except (ValueError, IndexError) as e:
            await callback.answer(get_text(lang, "error"), show_alert=True)
            return

        # Prefer service method to list active offers for the store
        try:
            offers = offer_service.list_active_offers_by_store(store_id)
        except Exception:
            offers = []

        # If no active offers found, try a fallback to list all store offers
        # (including inactive / out-of-stock) so users can at least see what's offered.
        if not offers:
            try:
                store_offers = offer_service.list_store_offers(store_id)
            except Exception:
                store_offers = []

            if not store_offers:
                await callback.answer(get_text(lang, "no_offers"), show_alert=True)
                return

            # Inform the user these items may be unavailable but allow browsing
            info_text = (
                "⚠️ Эти товары есть в магазине, но сейчас недоступны.\n"
                "Вы можете просмотреть их, но некоторые позиции могут быть распроданы."
            )
            if lang != 'ru':
                info_text = (
                    "⚠️ Bu do'konda mahsulotlar mavjud, lekin hozirda mavjud emas.\n"
                    "Ularni ko'rishingiz mumkin, lekin ba'zi mahsulotlar sotib yuborilgan bo'lishi mumkin."
                )

            await callback.message.answer(info_text, parse_mode="HTML")
            offers = store_offers

        # Header
        header = (
            f"📦 <b>Товары магазина</b>\n" if lang == 'ru' else f"📦 <b>Do'kon mahsulotlari</b>\n"
        )
        await callback.message.answer(header, parse_mode="HTML")

        # Send up to 20 offers from the store
        for offer in offers[:20]:
            caption = render_offer_card(lang, offer)
            keyboard = offer_quick_keyboard(lang, offer.id, offer.store_id, offer.delivery_enabled)

            if getattr(offer, 'photo', None):
                try:
                    await callback.message.answer_photo(
                        photo=offer.photo,
                        caption=caption,
                        parse_mode="HTML",
                        reply_markup=keyboard
                    )
                except Exception:
                    await callback.message.answer(caption, parse_mode="HTML", reply_markup=keyboard)
            else:
                await callback.message.answer(caption, parse_mode="HTML", reply_markup=keyboard)

        await callback.answer()

    @dp.message(F.text.in_(["🎯 Горячее", "🎯 Issiq"]))
    async def show_hot_offers(message: types.Message):
        """Show popular/hot offers."""
        lang = db.get_user_language(message.from_user.id)
        
        # Use get_user instead of get_user_model
        user_data = db.get_user(message.from_user.id)
        city = user_data.get("city") if user_data else "Ташкент"
        
        # Получаем популярные товары (можно добавить логику для определения "горячих")
        # Используем list_hot_offers как аналог get_popular_offers
        result = offer_service.list_hot_offers(city or "Ташкент", limit=10)
        popular_offers = result.items
        
        if not popular_offers:
            text = (
                "😔 <b>Популярные товары пока отсутствуют</b>\n\n"
                "Загляните сюда позже или воспользуйтесь поиском."
                if lang == "ru"
                else "😔 <b>Hozircha mashhur mahsulotlar yo'q</b>\n\n"
                "Keyinroq qaytib keling yoki qidiruvdan foydalaning."
            )
            await message.answer(text, parse_mode="HTML")
            return
            
        await message.answer(
            "🎯 <b>Горячие предложения</b>" if lang == "ru" else "🎯 <b>Issiq takliflar</b>",
            parse_mode="HTML"
        )
        
        for offer in popular_offers:
            caption = render_offer_card(lang, offer)
            
            keyboard = offer_quick_keyboard(
                lang, 
                offer.id, 
                offer.store_id, 
                offer.delivery_enabled
            )
            
            if offer.photo:
                try:
                    await message.answer_photo(
                        photo=offer.photo,
                        caption=caption,
                        parse_mode="HTML",
                        reply_markup=keyboard
                    )
                except Exception:
                    await message.answer(caption, parse_mode="HTML", reply_markup=keyboard)
            else:
                await message.answer(caption, parse_mode="HTML", reply_markup=keyboard)

