"""Seller offer creation handlers - simplified 2-step process for supermarkets."""
from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Any, Optional

from aiogram import F, Router, types
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder

from database_protocol import DatabaseProtocol
from handlers.common_states.states import CreateOffer
from app.keyboards import cancel_keyboard, main_menu_seller
from localization import get_text
from logging_config import logger

# Module-level dependencies
db: DatabaseProtocol | None = None
bot: Any | None = None

router = Router()


def setup_dependencies(database: DatabaseProtocol, bot_instance: Any) -> None:
    """Setup module dependencies."""
    global db, bot
    db = database
    bot = bot_instance


def get_store_field(store: Any, field: str, default: Any = None) -> Any:
    """Extract field from store tuple/dict."""
    if isinstance(store, dict):
        return store.get(field, default)
    # For tuple, need index mapping
    if isinstance(store, (tuple, list)):
        field_map = {"store_id": 0, "owner_id": 1, "name": 2, "city": 4, "status": 6}
        idx = field_map.get(field)
        if idx is not None and idx < len(store):
            return store[idx]
    return default


def detect_category(title: str) -> str:
    """Auto-detect category based on title keywords with improved matching."""
    title_lower = title.lower()
    
    # Expanded keywords with more variations and common product names
    keywords = {
        "bakery": {
            "keywords": [
                "хлеб", "батон", "лепешка", "торт", "пирожное", "булка", "багет", "круассан",
                "non", "nan", "bread", "cake", "pizza", "сомса", "самса", "somsa", 
                "пирог", "печенье", "кекс", "вафли", "булочка", "сдоба", "baguette",
                "эклер", "слойка", "пирожок", "чебурек", "беляш", "lavash", "лаваш"
            ],
            "priority": 1
        },
        "dairy": {
            "keywords": [
                "молоко", "кефир", "творог", "сыр", "йогурт", "йогурт", "сметана", "сливки", "масло",
                "sut", "qatiq", "tvorog", "pishloq", "qaymoq", "yogurt", "yoghurt", "ayran", "айран",
                "ряженка", "простокваша", "брынза", "моцарелла", "голландский", "российский",
                "milk", "cheese", "butter", "cream", "мороженое", "muzqaymoq"
            ],
            "priority": 1
        },
        "meat": {
            "keywords": [
                "мясо", "говядина", "курица", "колбаса", "сосиски", "фарш", "шашлык",
                "go'sht", "tovuq", "kolbasa", "sosiska", "qiym", "qovurilgan", 
                "рыба", "baliq", "fish", "свинина", "баранина", "chicken", "beef",
                "котлета", "пельмени", "манты", "manti", "стейк", "вырезка", "филе"
            ],
            "priority": 1
        },
        "fruits": {
            "keywords": [
                "яблоко", "банан", "груша", "виноград", "лимон", "апельсин", "мандарин",
                "olma", "banan", "uzum", "limon", "apelsin", "mandarin", 
                "фрукт", "meva", "fruit", "ягода", "клубника", "черешня", "вишня",
                "персик", "абрикос", "слива", "киви", "гранат", "ананас", "арбуз", "дыня"
            ],
            "priority": 2
        },
        "vegetables": {
            "keywords": [
                "картофель", "лук", "морковь", "помидор", "огурец", "капуста", "перец",
                "kartoshka", "piyoz", "sabzi", "pomidor", "bodring", "karam", 
                "овощ", "sabzavot", "vegetable", "баклажан", "кабачок", "тыква",
                "редис", "редька", "свекла", "чеснок", "sarimsoq", "salat", "салат"
            ],
            "priority": 2
        },
        "drinks": {
            "keywords": [
                "кола", "вода", "сок", "чай", "кофе", "пепси", "фанта", "спрайт",
                "suv", "choy", "kofe", "qahva", "pepsi", "fanta", "sprite", "cola",
                "напиток", "ichimlik", "drink", "лимонад", "квас", "компот", 
                "минералка", "газировка", "энергетик", "red bull"
            ],
            "priority": 1
        },
        "snacks": {
            "keywords": [
                "чипсы", "сухарики", "орешки", "семечки", "шоколад", "конфеты",
                "lays", "pringles", "chocolate", "shokolad", "konfet", 
                "снеки", "закуска", "орехи", "миндаль", "фисташки", "изюм"
            ],
            "priority": 2
        },
        "frozen": {
            "keywords": [
                "замороженный", "мороженое", "muzlatilgan", "muzqaymoq", 
                "frozen", "ice cream", "пельмени", "вареники", "заморозка"
            ],
            "priority": 1
        },
    }
    
    # Score each category
    category_scores = {}
    for category, data in keywords.items():
        score = 0
        words = data["keywords"]
        priority = data["priority"]
        
        for word in words:
            if word in title_lower:
                # Exact match gets higher score
                if title_lower == word:
                    score += 10 * priority
                # Word at start of title gets bonus
                elif title_lower.startswith(word):
                    score += 5 * priority
                # Word anywhere in title
                else:
                    score += 2 * priority
        
        if score > 0:
            category_scores[category] = score
    
    # Return category with highest score
    if category_scores:
        return max(category_scores, key=category_scores.get)
    
    return "other"


@router.message(F.text.contains("Добавить") | F.text.contains("Qo'shish"))
async def add_offer_start(message: types.Message, state: FSMContext) -> None:
    """Start offer creation - select store."""
    if not db:
        await message.answer("System error")
        return
    
    lang = db.get_user_language(message.from_user.id)
    
    # Get only APPROVED stores
    stores = [
        s
        for s in db.get_user_stores(message.from_user.id)
        if get_store_field(s, "status") == "active"
    ]
    
    if not stores:
        await message.answer(get_text(lang, "no_approved_stores"))
        return
    
    # Partner has only one store - auto-select it
    store_id = get_store_field(stores[0], "store_id")
    store_name = get_store_field(stores[0], "name", "Магазин")
    await state.update_data(store_id=store_id, store_name=store_name)
    await _ask_for_category(message, lang, store_name, state)


async def _ask_for_category(message: types.Message, lang: str, store_name: str, state: FSMContext):
    """Ask seller to choose product category."""
    from app.keyboards import product_categories_keyboard
    
    step_text = "ШАГ 1 из 3: КАТЕГОРИЯ" if lang == "ru" else "1-QADAM 3 tadan: KATEGORIYA"
    choose_text = "Выберите категорию товара:" if lang == "ru" else "Mahsulot kategoriyasini tanlang:"
    
    text = (
        f"🏪 <b>{store_name}</b>\n\n"
        f"<b>{step_text}</b>\n\n"
        f"📂 {choose_text}"
    )
    
    await message.answer(
        text, 
        parse_mode="HTML", 
        reply_markup=product_categories_keyboard(lang)
    )
    await state.set_state(CreateOffer.category)


async def _ask_for_data(message: types.Message, lang: str, store_name: str, category: str, state: FSMContext):
    """Ask for all data in one message."""
    builder = InlineKeyboardBuilder()
    builder.button(
        text="❌ Отменить" if lang == "ru" else "❌ Bekor qilish",
        callback_data="create_cancel",
    )
    
    example = (
        "Ахмад Чай Английский\n"
        "50000 50% 20\n"
        "25.12"
    )
    
    # Category name display
    category_names = {
        "bakery": "🥖 Выпечка" if lang == "ru" else "🥖 Pishiriq",
        "dairy": "🥛 Молочные" if lang == "ru" else "🥛 Sut mahsulotlari",
        "meat": "🥩 Мясные" if lang == "ru" else "🥩 Go'sht mahsulotlari",
        "fruits": "🍎 Фрукты" if lang == "ru" else "🍎 Mevalar",
        "vegetables": "🥕 Овощи" if lang == "ru" else "🥕 Sabzavotlar",
        "drinks": "🥤 Напитки" if lang == "ru" else "🥤 Ichimliklar",
        "snacks": "🍿 Снеки" if lang == "ru" else "🍿 Gaz. ovqatlar",
        "frozen": "🧊 Замороженное" if lang == "ru" else "🧊 Muzlatilgan",
    }
    category_display = category_names.get(category, category)
    
    step_2_text = "ШАГ 2 из 3: ДАННЫЕ ТОВАРА" if lang == "ru" else "2-QADAM 3 tadan: MAHSULOT MA'LUMOTLARI"
    send_format_text = "Отправьте данные в формате:" if lang == "ru" else "Ma'lumotlarni formatda yuboring:"
    
    text = (
        f"🏪 <b>{store_name}</b>\n"
        f"📂 {category_display}\n\n"
        f"<b>{step_2_text}</b>\n\n"
        f"{send_format_text}\n\n"
        f"1️⃣ {'Название товара' if lang == 'ru' else 'Mahsulot nomi'}\n"
        f"2️⃣ {'Цена Скидка% Количество' if lang == 'ru' else 'Narx Chegirma% Miqdor'}\n"
        f"3️⃣ {'Срок годности (дд.мм)' if lang == 'ru' else 'Yaroqlilik muddati (kk.oo)'}\n\n"
        f"📝 <b>{'Пример:' if lang == 'ru' else 'Misol:'}</b>\n"
        f"<code>{example}</code>"
    )
    
    await message.answer(text, parse_mode="HTML", reply_markup=builder.as_markup())
    await state.set_state(CreateOffer.title)  # Using 'title' state for the main input


@router.callback_query(CreateOffer.category)
async def create_offer_category_selected(callback: types.CallbackQuery, state: FSMContext) -> None:
    """Category selected - proceed to data input."""
    if not db or not callback.data:
        await callback.answer("System error", show_alert=True)
        return
    
    lang = db.get_user_language(callback.from_user.id)
    
    # Extract category from callback data (format: "product_cat_bakery")
    if callback.data.startswith("product_cat_"):
        category = callback.data.replace("product_cat_", "")
        data = await state.get_data()
        store_name = data.get("store_name", "Магазин")
        
        await state.update_data(category=category)
        
        if callback.message:
            await _ask_for_data(callback.message, lang, store_name, category, state)
        await callback.answer()
    else:
        await callback.answer("Invalid category", show_alert=True)


@router.message(CreateOffer.title)
async def process_offer_data(message: types.Message, state: FSMContext) -> None:
    """Process the multi-line input data."""
    if not db:
        await message.answer("System error")
        return
    
    lang = db.get_user_language(message.from_user.id)
    text = message.text.strip()
    lines = [line.strip() for line in text.split('\n') if line.strip()]
    
    if len(lines) < 3:
        await message.answer(
            "❌ " + ("Неверный формат. Нужно 3 строки:\n1. Название\n2. Цена Скидка% Количество\n3. Срок годности" 
                     if lang == "ru" else 
                     "Noto'g'ri format. 3 qator kerak:\n1. Nomi\n2. Narx Chegirma% Miqdor\n3. Yaroqlilik muddati")
        )
        return

    # 1. Parse Title
    title = lines[0]
    
    # 2. Parse Price, Discount, Quantity
    try:
        # Remove currency symbols and extra spaces
        price_line = lines[1].replace('сум', '').replace("so'm", "").replace(',', '.')
        parts = price_line.split()
        
        if len(parts) != 3:
            raise ValueError("Expected 3 values in line 2")
            
        original_price = float(parts[0])
        
        # Handle discount (50 or 50% - both work)
        discount_str = parts[1].strip().replace('%', '').strip()
        discount_percent = float(discount_str)
        
        quantity = int(parts[2])
        
        # Log for debugging
        logger.info(f"Parsed: price={original_price}, discount={discount_percent}%, quantity={quantity}")
        
        if original_price <= 0 or quantity <= 0:
            raise ValueError("Price and quantity must be positive")
            
        if discount_percent < 0 or discount_percent >= 100:
            raise ValueError("Invalid discount percent")
            
        discount_price = original_price * (1 - discount_percent / 100)
        logger.info(f"Calculated discount_price={discount_price}")
        
    except ValueError:
        await message.answer(
            "❌ " + ("Ошибка во 2-й строке. Формат: Цена Скидка% Количество\nПример: 50000 50% 20" 
                     if lang == "ru" else 
                     "2-qatorda xatolik. Format: Narx Chegirma% Miqdor\nMisol: 50000 50% 20")
        )
        return

    # 3. Parse Expiry Date
    try:
        date_str = lines[2].replace('/', '.').replace('-', '.')
        today = datetime.now()
        
        # Try DD.MM.YYYY
        if len(date_str.split('.')) == 3:
            date_obj = datetime.strptime(date_str, "%d.%m.%Y")
        # Try DD.MM (current year)
        elif len(date_str.split('.')) == 2:
            date_obj = datetime.strptime(f"{date_str}.{today.year}", "%d.%m.%Y")
            # If date is in the past (e.g. entered 01.01 in Dec), assume next year
            if date_obj.date() < today.date():
                date_obj = date_obj.replace(year=today.year + 1)
        else:
            raise ValueError("Invalid date format")
            
        expiry_date = date_obj.strftime("%Y-%m-%d")
        
    except ValueError:
        await message.answer(
            "❌ " + ("Ошибка в дате. Формат: ДД.ММ (например 25.12)" 
                     if lang == "ru" else 
                     "Sanada xatolik. Format: KK.OO (masalan 25.12)")
        )
        return

    # Get category from state (already selected by user)
    data = await state.get_data()
    category = data.get("category", "other")
    
    # Save all data
    await state.update_data(
        title=title,
        original_price=original_price,
        discount_price=discount_price,
        quantity=quantity,
        expiry_date=expiry_date,
        category=category,
        unit="шт",
        description=title  # Use title as description by default
    )
    
    # Step 3: Ask for Photo
    builder = InlineKeyboardBuilder()
    builder.button(
        text="➡️ Без фото (Пропустить)" if lang == "ru" else "➡️ Fotosiz (O'tkazib yuborish)",
        callback_data="create_skip_photo",
    )
    
    step_3_text = "ШАГ 3 из 3: ФОТО" if lang == "ru" else "3-QADAM 3 tadan: RASM"
    photo_prompt = "Отправьте фото товара или нажмите кнопку пропустить." if lang == "ru" else "Mahsulot rasmini yuboring yoki o'tkazib yuborish tugmasini bosing."
    category_text = "Категория:" if lang == "ru" else "Kategoriya:"
    
    # Category name display
    category_names = {
        "bakery": "🥖 Выпечка" if lang == "ru" else "🥖 Pishiriq",
        "dairy": "🥛 Молочные" if lang == "ru" else "🥛 Sut mahsulotlari",
        "meat": "🥩 Мясные" if lang == "ru" else "🥩 Go'sht mahsulotlari",
        "fruits": "🍎 Фрукты" if lang == "ru" else "🍎 Mevalar",
        "vegetables": "🥕 Овощи" if lang == "ru" else "🥕 Sabzavotlar",
        "drinks": "🥤 Напитки" if lang == "ru" else "🥤 Ichimliklar",
        "snacks": "🍿 Снеки" if lang == "ru" else "🍿 Gaz. ovqatlar",
        "frozen": "🧊 Замороженное" if lang == "ru" else "🧊 Muzlatilgan",
    }
    category_display = category_names.get(category, category)

    await message.answer(
        f"<b>{step_3_text}</b>\n\n"
        f"📸 {photo_prompt}\n\n"
        f"✅ {category_text} <b>{category_display}</b>",
        parse_mode="HTML",
        reply_markup=builder.as_markup()
    )
    await state.set_state(CreateOffer.photo)


@router.message(CreateOffer.photo, F.photo)
async def process_offer_photo(message: types.Message, state: FSMContext) -> None:
    """Process the photo and finalize."""
    if not db:
        await message.answer("System error")
        return
    
    lang = db.get_user_language(message.from_user.id)
    photo_id = message.photo[-1].file_id
    
    await state.update_data(photo=photo_id)
    await _finalize_offer_creation(message, state, lang)


@router.callback_query(F.data == "create_skip_photo")
async def skip_photo(callback: types.CallbackQuery, state: FSMContext) -> None:
    """Skip photo and finalize."""
    if not db:
        await callback.answer("System error")
        return
    
    lang = db.get_user_language(callback.from_user.id)
    await state.update_data(photo=None)
    if callback.message:
        await _finalize_offer_creation(callback.message, state, lang)
    await callback.answer()


@router.callback_query(F.data == "create_cancel")
async def cancel_create_offer(callback: types.CallbackQuery, state: FSMContext) -> None:
    """Cancel offer creation."""
    if not db:
        await callback.answer("System error", show_alert=True)
        return
    
    lang = db.get_user_language(callback.from_user.id)
    await state.clear()
    
    if callback.message and isinstance(callback.message, types.Message):
        await callback.message.edit_text(
            f"❌ {'Создание товара отменено' if lang == 'ru' else 'Mahsulot yaratish bekor qilindi'}",
            parse_mode="HTML"
        )
    await callback.answer()


async def _finalize_offer_creation(message: types.Message | types.InaccessibleMessage, state: FSMContext, lang: str):
    """Finalize offer creation and save to DB."""
    data = await state.get_data()
    
    try:
        if not db:
            raise ValueError("Database not initialized")

        db.add_offer(
            store_id=data["store_id"],
            title=data["title"],
            description=data.get("description", data["title"]),
            original_price=data["original_price"],
            discount_price=data["discount_price"],
            quantity=data["quantity"],
            available_from="08:00",  # Default for supermarkets
            available_until="23:00", # Default for supermarkets
            photo=data.get("photo"),
            expiry_date=data["expiry_date"],
            unit=data.get("unit", "шт"),
            category=data.get("category", "other"),
        )
        
        discount_percent = int((1 - data["discount_price"] / data["original_price"]) * 100)
        
        if isinstance(message, types.Message):
            await message.answer(
                f"✅ <b>{'ТОВАР СОЗДАН!' if lang == 'ru' else 'MAHSULOT YARATILDI!'}</b>\n\n"
                f"📦 {data['title']}\n"
                f"💰 {int(data['original_price'])} ➜ {int(data['discount_price'])} сум (-{discount_percent}%)\n"
                f"📊 {data['quantity']} шт\n"
                f"📅 До: {data['expiry_date']}",
                parse_mode="HTML",
            )
            
            await message.answer(
                f"{'Что дальше?' if lang == 'ru' else 'Keyingi qadam?'}",
                reply_markup=main_menu_seller(lang),
            )
        else:
             # Fallback for InaccessibleMessage if needed
             pass

    except Exception as e:
        logger.error(f"Error creating offer: {e}")
        if isinstance(message, types.Message):
            await message.answer(
                "❌ " + ("Ошибка при сохранении. Попробуйте снова." if lang == "ru" else "Saqlashda xatolik. Qayta urinib ko'ring.")
            )
    finally:
        await state.clear()