"""Seller offer creation handlers - simplified 3-step process."""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

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
    
    if len(stores) == 1:
        # One store - start creation immediately
        store_id = get_store_field(stores[0], "store_id")
        store_name = get_store_field(stores[0], "name", "Магазин")
        await state.update_data(store_id=store_id)
        
        # Keyboard with "Without photo" and "Cancel" buttons
        builder = InlineKeyboardBuilder()
        builder.button(
            text="📝 Без фото" if lang == "ru" else "📝 Fotosiz",
            callback_data="create_no_photo",
        )
        builder.button(
            text="❌ Отменить" if lang == "ru" else "❌ Bekor qilish",
            callback_data="create_cancel",
        )
        builder.adjust(1, 1)
        
        step1_text = (
            f"🏪 <b>{store_name}</b>\n\n"
            f"📝 {'Введите название товара' if lang == 'ru' else 'Mahsulot nomini kiriting'}\n\n"
            f"🖼 {'Можете сразу отправить фото с названием в подписи или нажать кнопку' if lang == 'ru' else 'Rasmni nom bilan yuboring yoki tugmani bosing'}"
        )
        
        await message.answer(
            step1_text, parse_mode="HTML", reply_markup=builder.as_markup()
        )
        await state.set_state(CreateOffer.title)
    else:
        # Multiple stores - need to choose
        await message.answer(
            get_text(lang, "choose_store"), reply_markup=cancel_keyboard(lang)
        )
        text = ""
        for i, store in enumerate(stores, 1):
            store_name = get_store_field(store, "name", "Магазин")
            store_city = get_store_field(store, "city", "")
            text += f"{i}. 🏪 {store_name} - 📍 {store_city}\n"
        await message.answer(text)
        await state.set_state(CreateOffer.store)


@router.message(CreateOffer.store)
async def create_offer_store_selected(message: types.Message, state: FSMContext) -> None:
    """Store selected - proceed to step 1."""
    if not db:
        await message.answer("System error")
        return
    
    lang = db.get_user_language(message.from_user.id)
    stores = [
        s
        for s in db.get_user_stores(message.from_user.id)
        if get_store_field(s, "status") == "active"
    ]
    
    try:
        store_num = int(message.text)
        if 1 <= store_num <= len(stores):
            selected_store = stores[store_num - 1]
            store_id = get_store_field(selected_store, "store_id")
            store_name = get_store_field(selected_store, "name", "Магазин")
            await state.update_data(store_id=store_id)
            
            builder = InlineKeyboardBuilder()
            builder.button(
                text="📝 Без фото" if lang == "ru" else "📝 Fotosiz",
                callback_data="create_no_photo",
            )
            builder.adjust(1)
            
            step1_text = (
                f"🏪 <b>{store_name}</b>\n\n"
                f"<b>{'ШАГ 1 из 3' if lang == 'ru' else '1-QADAM 3 tadan'}</b>\n\n"
                f"📝 {'Введите название товара' if lang == 'ru' else 'Mahsulot nomini kiriting'}\n"
                f"📸 {'Затем отправьте фото (или нажмите кнопку Без фото)' if lang == 'ru' else 'Keyin rasmni yuboring (yoki Fotosiz tugmasini bosing)'}"
            )
            
            await message.answer(
                step1_text, parse_mode="HTML", reply_markup=builder.as_markup()
            )
            await state.set_state(CreateOffer.title)
        else:
            await message.answer(get_text(lang, "error_invalid_number"))
    except Exception:
        await message.answer(get_text(lang, "error_invalid_number"))


@router.message(CreateOffer.title, F.photo)
async def create_offer_title_with_photo(
    message: types.Message, state: FSMContext
) -> None:
    """User sent photo with title in caption."""
    if not db:
        await message.answer("System error")
        return
    
    lang = db.get_user_language(message.from_user.id)
    title = message.caption if message.caption else "Товар"
    photo_id = message.photo[-1].file_id
    
    await state.update_data(title=title, photo=photo_id)
    
    # STEP 2: Prices and quantity
    builder = InlineKeyboardBuilder()
    builder.button(text="30%", callback_data="discount_30")
    builder.button(text="40%", callback_data="discount_40")
    builder.button(text="50%", callback_data="discount_50")
    builder.button(text="60%", callback_data="discount_60")
    builder.adjust(4)
    
    await message.answer(
        f"<b>{'ШАГ 2 из 3: ЦЕНЫ И КОЛИЧЕСТВО' if lang == 'ru' else '2-QADAM 3 tadan: NARXLAR VA MIQDOR'}</b>\n\n"
        f"💡 {'Быстрый формат' if lang == 'ru' else 'Tez format'}:\n"
        f"<code>{'обычная_цена скидка% количество' if lang == 'ru' else 'oddiy_narx chegirma% miqdor'}</code>\n\n"
        f"📝 {'Пример' if lang == 'ru' else 'Misol'}: <code>1000 40% 50</code>\n"
        f"   {'(обычная цена 1000, скидка 40%, количество 50)' if lang == 'ru' else '(oddiy narx 1000, chegirma 40%, miqdor 50)'}\n\n"
        f"{'Или введите только обычную цену и выберите % скидки кнопкой ⬇️' if lang == 'ru' else 'Yoki faqat oddiy narxni kiriting va tugma bilan % chegirmani tanlang ⬇️'}",
        parse_mode="HTML",
        reply_markup=builder.as_markup(),
    )
    await state.set_state(CreateOffer.original_price)


@router.message(CreateOffer.title)
async def create_offer_title(message: types.Message, state: FSMContext) -> None:
    """Title entered - check if photo already skipped, else ask for photo."""
    if not db:
        await message.answer("System error")
        return
    
    lang = db.get_user_language(message.from_user.id)
    data = await state.get_data()
    await state.update_data(title=message.text)
    
    # If photo was sent with title (caption), it's already saved
    # Go directly to step 2 (prices)
    builder = InlineKeyboardBuilder()
    builder.button(text="30%", callback_data="discount_30")
    builder.button(text="40%", callback_data="discount_40")
    builder.button(text="50%", callback_data="discount_50")
    builder.button(text="60%", callback_data="discount_60")
    builder.adjust(4)
    
    await message.answer(
        f"💰 <b>{'ЦЕНЫ И КОЛИЧЕСТВО' if lang == 'ru' else 'NARXLAR VA MIQDOR'}</b>\n\n"
        f"💡 {'Быстрый формат' if lang == 'ru' else 'Tez format'}:\n"
        f"<code>{'обычная_цена скидка% количество' if lang == 'ru' else 'oddiy_narx chegirma% miqdor'}</code>\n\n"
        f"📝 {'Пример' if lang == 'ru' else 'Misol'}: <code>1000 40% 50</code>\n"
        f"   {'(обычная цена 1000, скидка 40%, количество 50)' if lang == 'ru' else '(oddiy narx 1000, chegirma 40%, miqdor 50)'}\n\n"
        f"{'Или введите только обычную цену и выберите % скидки кнопкой ⬇️' if lang == 'ru' else 'Yoki faqat oddiy narxni kiriting va tugma bilan % chegirmani tanlang ⬇️'}",
        parse_mode="HTML",
        reply_markup=builder.as_markup(),
    )
    await state.set_state(CreateOffer.original_price)


@router.callback_query(F.data == "create_no_photo")
async def offer_without_photo(callback: types.CallbackQuery, state: FSMContext) -> None:
    """Create without photo from start."""
    if not db:
        await callback.answer("System error", show_alert=True)
        return
    
    lang = db.get_user_language(callback.from_user.id)
    await state.update_data(photo=None)  # Set photo to None
    await callback.message.edit_text(
        f"📝 {'Введите название товара' if lang == 'ru' else 'Mahsulot nomini kiriting'}:",
        parse_mode="HTML",
    )
    await state.set_state(CreateOffer.title)  # FIXED: Set state to wait for title
    await callback.answer()


@router.callback_query(F.data == "create_cancel")
async def cancel_create_offer(callback: types.CallbackQuery, state: FSMContext) -> None:
    """Cancel offer creation."""
    if not db:
        await callback.answer("System error", show_alert=True)
        return
    
    lang = db.get_user_language(callback.from_user.id)
    await state.clear()
    
    await callback.message.edit_text(
        f"❌ {'Создание товара отменено' if lang == 'ru' else 'Mahsulot yaratish bekor qilindi'}",
        parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(F.data == "create_skip_photo")
async def skip_photo_goto_step2(callback: types.CallbackQuery, state: FSMContext) -> None:
    """Skip photo and go to step 2."""
    if not db:
        await callback.answer("System error", show_alert=True)
        return
    
    lang = db.get_user_language(callback.from_user.id)
    await state.update_data(photo=None)
    
    builder = InlineKeyboardBuilder()
    builder.button(text="30%", callback_data="discount_30")
    builder.button(text="40%", callback_data="discount_40")
    builder.button(text="50%", callback_data="discount_50")
    builder.button(text="60%", callback_data="discount_60")
    builder.adjust(4)
    
    await callback.message.edit_text(
        f"💰 <b>{'ЦЕНЫ И КОЛИЧЕСТВО' if lang == 'ru' else 'NARXLAR VA MIQDOR'}</b>\n\n"
        f"{'Введите в формате' if lang == 'ru' else 'Formatda kiriting'}:\n"
        f"<code>{'обычная_цена скидка количество' if lang == 'ru' else 'oddiy_narx chegirma miqdor'}</code>\n\n"
        f"{'Пример' if lang == 'ru' else 'Misol'}: <code>1000 40% 50</code>\n"
        f"{'(цена 1000, скидка 40%, количество 50 шт)' if lang == 'ru' else '(narx 1000, chegirma 40%, miqdor 50 dona)'}\n\n"
        f"{'Или просто введите обычную цену и выберите % скидки:' if lang == 'ru' else 'Yoki oddiy narxni kiriting va chegirma % tanlang:'}",
        parse_mode="HTML",
        reply_markup=builder.as_markup(),
    )
    await state.set_state(CreateOffer.original_price)
    await callback.answer()


@router.message(CreateOffer.photo, F.photo | F.document)
async def create_offer_photo_received(
    message: types.Message, state: FSMContext
) -> None:
    """Photo received - proceed to step 2."""
    if not db:
        await message.answer("System error")
        return
    
    lang = db.get_user_language(message.from_user.id)
    
    # Handle photo or document
    if message.photo:
        photo_id = message.photo[-1].file_id
    elif message.document:
        # Check mime type
        if message.document.mime_type and message.document.mime_type.startswith('image/'):
            photo_id = message.document.file_id
        else:
            await message.answer(
                "❌ " + ("Пожалуйста, отправьте изображение (JPG/PNG)" if lang == "ru" else "Iltimos, rasm yuboring (JPG/PNG)")
            )
            return
    else:
        return

    await state.update_data(photo=photo_id)
    
    builder = InlineKeyboardBuilder()
    builder.button(text="30%", callback_data="discount_30")
    builder.button(text="40%", callback_data="discount_40")
    builder.button(text="50%", callback_data="discount_50")
    builder.button(text="60%", callback_data="discount_60")
    builder.adjust(4)
    
    await message.answer(
        f"<b>{'ШАГ 2 из 3: ЦЕНЫ И КОЛИЧЕСТВО' if lang == 'ru' else '2-QADAM 3 tadan: NARXLAR VA MIQDOR'}</b>\n\n"
        f"{'Введите в формате' if lang == 'ru' else 'Formatda kiriting'}:\n"
        f"<code>{'обычная_цена скидка количество' if lang == 'ru' else 'oddiy_narx chegirma miqdor'}</code>\n\n"
        f"{'Пример' if lang == 'ru' else 'Misol'}: <code>1000 40% 50</code>\n"
        f"{'(цена 1000, скидка 40%, количество 50 шт)' if lang == 'ru' else '(narx 1000, chegirma 40%, miqdor 50 dona)'}\n\n"
        f"{'Или просто введите обычную цену и выберите % скидки:' if lang == 'ru' else 'Yoki oddiy narxni kiriting va chegirma % tanlang:'}",
        parse_mode="HTML",
        reply_markup=builder.as_markup(),
    )
    await state.set_state(CreateOffer.original_price)


@router.callback_query(F.data.startswith("discount_"))
async def select_discount_percent(
    callback: types.CallbackQuery, state: FSMContext
) -> None:
    """User selected discount percent via button."""
    if not db:
        await callback.answer("System error", show_alert=True)
        return
    
    lang = db.get_user_language(callback.from_user.id)
    
    try:
        percent = int(callback.data.split("_")[1])
    except (ValueError, IndexError) as e:
        logger.error(f"Invalid discount percent in callback data: {callback.data}, error: {e}")
        await callback.answer(get_text(lang, "error"), show_alert=True)
        return
    
    await state.update_data(discount_percent=percent)
    await callback.message.edit_text(
        f"✅ {'Скидка' if lang == 'ru' else 'Chegirma'}: <b>{percent}%</b>\n\n"
        f"{'Теперь введите обычную цену и количество:' if lang == 'ru' else 'Endi oddiy narx va miqdorni kiriting:'}\n"
        f"{'Формат' if lang == 'ru' else 'Format'}: <code>{'цена количество' if lang == 'ru' else 'narx miqdor'}</code>\n"
        f"{'Пример' if lang == 'ru' else 'Misol'}: <code>1000 50</code>",
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(CreateOffer.original_price)
async def create_offer_prices_and_quantity(
    message: types.Message, state: FSMContext
) -> None:
    """Process price, discount, quantity in one step."""
    if not db:
        await message.answer("System error")
        return
    
    lang = db.get_user_language(message.from_user.id)
    
    try:
        parts = message.text.split()
        data = await state.get_data()
        
        # Check if user selected discount with button
        if "discount_percent" in data:
            # Format: "price quantity"
            if len(parts) == 2:
                original_price = float(parts[0])
                quantity = int(parts[1])
                discount_percent = data["discount_percent"]
                discount_price = original_price * (1 - discount_percent / 100)
            else:
                await message.answer(
                    "❌ Неверный формат. Введите: цена количество\nПример: 1000 50"
                )
                return
        else:
            # Format: "price discount% quantity"
            if len(parts) == 3:
                original_price = float(parts[0])
                discount_str = parts[1].replace("%", "")
                discount_percent = float(discount_str)
                quantity = int(parts[2])
                discount_price = original_price * (1 - discount_percent / 100)
            elif len(parts) == 2:
                # Just price and quantity - ask for discount
                builder = InlineKeyboardBuilder()
                builder.button(text="30%", callback_data="discount_30")
                builder.button(text="40%", callback_data="discount_40")
                builder.button(text="50%", callback_data="discount_50")
                builder.button(text="60%", callback_data="discount_60")
                builder.adjust(4)
                
                await message.answer(
                    f"{'Введите процент скидки или выберите кнопкой:' if lang == 'ru' else 'Chegirma foizini kiriting yoki tugmani tanlang:'}",
                    reply_markup=builder.as_markup(),
                )
                await state.update_data(
                    original_price=float(parts[0]), quantity=int(parts[1])
                )
                return
            else:
                await message.answer(
                    "❌ Неверный формат.\nВведите: цена скидка% количество\nПример: 1000 40% 50"
                )
                return
        
        # Validations
        if original_price <= 0 or discount_price <= 0 or quantity <= 0:
            await message.answer("❌ Все значения должны быть больше 0")
            return
        
        if discount_price >= original_price:
            await message.answer("❌ Цена со скидкой должна быть меньше обычной")
            return
        
        # Save data
        await state.update_data(
            original_price=original_price,
            discount_price=discount_price,
            quantity=quantity,
            unit="шт",
            description=data.get("title", "Описание не указано"),
        )
        
        # STEP 3: Category selection
        builder = InlineKeyboardBuilder()
        builder.button(text="🍞 Выпечка", callback_data="prodcat_bakery")
        builder.button(text="🥛 Молочка", callback_data="prodcat_dairy")
        builder.button(text="🥩 Мясо", callback_data="prodcat_meat")
        builder.button(text="🍎 Фрукты", callback_data="prodcat_fruits")
        builder.button(text="🥬 Овощи", callback_data="prodcat_vegetables")
        builder.button(text="🎯 Другое", callback_data="prodcat_other")
        builder.adjust(3, 3)
        
        uz_note = "(Kategoriyani tanlagandan keyin yaroqlilik muddatini ko'rsatasiz)"
        
        await message.answer(
            f"<b>{'ШАГ 3 из 3: КАТЕГОРИЯ' if lang == 'ru' else '3-QADAM 3 tadan: KATEGORIYA'}</b>\n\n"
            f"{'Выберите категорию товара:' if lang == 'ru' else 'Mahsulot kategoriyasini tanlang:'}\n\n"
            f"{'(После выбора категории укажете срок годности)' if lang == 'ru' else uz_note}",
            parse_mode="HTML",
            reply_markup=builder.as_markup(),
        )
        await state.set_state(CreateOffer.category)
        
    except ValueError:
        await message.answer("❌ Ошибка в формате чисел.\nПример: 1000 40% 50")
    except Exception as e:
        logger.error(f"Error in create_offer_prices_and_quantity: {e}")
        await message.answer("❌ Ошибка обработки. Попробуйте снова.")


@router.callback_query(F.data.startswith("prodcat_"), CreateOffer.category)
async def select_category_simple(
    callback: types.CallbackQuery, state: FSMContext
) -> None:
    """Category selected - show expiry date options."""
    if not db:
        await callback.answer("System error", show_alert=True)
        return
    
    lang = db.get_user_language(callback.from_user.id)
    category_key = callback.data.split("_")[1]
    
    await state.update_data(category=category_key)
    
    # Show expiry date options
    today = datetime.now()
    tomorrow = today + timedelta(days=1)
    
    builder = InlineKeyboardBuilder()
    builder.button(
        text=f"Сегодня {today.strftime('%d.%m')}", callback_data="exp_today"
    )
    builder.button(
        text=f"Завтра {tomorrow.strftime('%d.%m')}", callback_data="exp_tomorrow"
    )
    builder.button(text="Неделя", callback_data="exp_week")
    builder.button(text="📅 Другая дата", callback_data="exp_custom")
    builder.adjust(2, 2)
    
    category_names = {
        "bakery": "🍞 Выпечка",
        "dairy": "🥛 Молочка",
        "meat": "🥩 Мясо",
        "fruits": "🍎 Фрукты",
        "vegetables": "🥬 Овощи",
        "other": "🎯 Другое",
    }
    
    await callback.message.edit_text(
        f"<b>{'ШАГ 3 из 3: СРОК ГОДНОСТИ' if lang == 'ru' else '3-QADAM 3 tadan: YAROQLILIK MUDDATI'}</b>\n\n"
        f"✅ {'Категория:' if lang == 'ru' else 'Kategoriya:'} {category_names.get(category_key, '🎯 Другое')}\n\n"
        f"{'Выберите срок годности:' if lang == 'ru' else 'Yaroqlilik muddatini tanlang:'}",
        parse_mode="HTML",
        reply_markup=builder.as_markup(),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("exp_"))
async def select_expiry_simple(
    callback: types.CallbackQuery, state: FSMContext
) -> None:
    """Expiry date selected - create offer."""
    if not db or not bot:
        await callback.answer("System error", show_alert=True)
        return
    
    lang = db.get_user_language(callback.from_user.id)
    exp_key = callback.data.split("_")[1] if "_" in callback.data else "today"
    
    today = datetime.now()
    
    # Set expiry to END of day (23:59:59)
    if exp_key == "today":
        expiry_date = today.strftime("%Y-%m-%d")
    elif exp_key == "tomorrow":
        expiry_date = (today + timedelta(days=1)).strftime("%Y-%m-%d")
    elif exp_key == "week":
        expiry_date = (today + timedelta(days=7)).strftime("%Y-%m-%d")
    else:
        expiry_date = today.strftime("%Y-%m-%d")
    
    await _finalize_offer_creation(callback.message, state, expiry_date, lang)
    await callback.answer("✅ Готово!" if lang == "ru" else "✅ Tayyor!")


@router.callback_query(F.data == "exp_custom")
async def ask_custom_expiry(callback: types.CallbackQuery, state: FSMContext) -> None:
    """Ask for custom expiry date."""
    if not db:
        await callback.answer("System error", show_alert=True)
        return
    
    lang = db.get_user_language(callback.from_user.id)
    
    await callback.message.edit_text(
        f"📅 <b>{'ВВЕДИТЕ ДАТУ' if lang == 'ru' else 'SANANI KIRITING'}</b>\n\n"
        f"{'Введите дату окончания срока годности в формате:' if lang == 'ru' else 'Yaroqlilik muddati tugash sanasini formatda kiriting:'}\n"
        f"<code>DD.MM.YYYY</code> {'(например' if lang == 'ru' else '(masalan'} 31.12.2025)\n"
        f"{'Или просто' if lang == 'ru' else 'Yoki shunchaki'} <code>DD.MM</code> {'(текущий год)' if lang == 'ru' else '(joriy yil)'}",
        parse_mode="HTML"
    )
    await state.set_state(CreateOffer.expiry_date)
    await callback.answer()


@router.message(CreateOffer.expiry_date)
async def process_custom_expiry(message: types.Message, state: FSMContext) -> None:
    """Process custom expiry date input."""
    if not db:
        await message.answer("System error")
        return
    
    lang = db.get_user_language(message.from_user.id)
    text = message.text.strip()
    
    try:
        # Try parsing DD.MM.YYYY
        if len(text.split('.')) == 3:
            date_obj = datetime.strptime(text, "%d.%m.%Y")
        # Try parsing DD.MM (assume current year)
        elif len(text.split('.')) == 2:
            today = datetime.now()
            date_obj = datetime.strptime(f"{text}.{today.year}", "%d.%m.%Y")
            # If date is in the past, assume next year? Or just fail?
            # Let's assume if it's today or future, it's this year. If past, maybe user made mistake.
            if date_obj.date() < today.date():
                # If it's clearly past (e.g. entered 01.01 in December), maybe next year?
                # For safety, just warn.
                pass
        else:
            raise ValueError("Invalid format")
            
        if date_obj.date() < datetime.now().date():
            await message.answer(
                "❌ " + ("Дата не может быть в прошлом" if lang == "ru" else "Sana o'tmishda bo'lishi mumkin emas")
            )
            return
            
        expiry_date = date_obj.strftime("%Y-%m-%d")
        
        # Proceed to create offer (reuse logic from select_expiry_simple)
        # We need to call a common function or copy-paste logic. 
        # Since I cannot easily refactor into a common function without changing too much, 
        # I will call a helper method or just duplicate the creation logic (it's not too long).
        
        await _finalize_offer_creation(message, state, expiry_date, lang)
        
    except ValueError:
        await message.answer(
            "❌ " + ("Неверный формат даты. Используйте DD.MM.YYYY" if lang == "ru" else "Noto'g'ri sana formati. DD.MM.YYYY ishlating")
        )


async def _finalize_offer_creation(message: types.Message, state: FSMContext, expiry_date: str, lang: str):
    """Finalize offer creation with given expiry date."""
    data = await state.get_data()
    
    # Validate category and required data
    if not data or "category" not in data:
        await message.answer(
            "❌ Ошибка: категория не выбрана. Начните создание товара заново."
        )
        await state.clear()
        return
    
    required_fields = [
        "store_id",
        "title",
        "original_price",
        "discount_price",
        "quantity",
    ]
    missing_fields = [field for field in required_fields if field not in data]
    if missing_fields:
        await message.answer(
            f"❌ Ошибка: данные потеряны ({', '.join(missing_fields)}). Начните создание товара заново."
        )
        await state.clear()
        return
    
    # Create offer
    category = data.get("category", "other")
    photo = data.get("photo")
    
    offer_id = db.add_offer(
        data["store_id"],
        data["title"],
        data.get("description", data["title"]),
        data["original_price"],
        data["discount_price"],
        data["quantity"],
        "18:00",  # available_from
        "21:00",  # available_until
        photo,
        expiry_date,
        data.get("unit", "шт"),
        category,
    )
    
    logger.info(f"Offer created with ID: {offer_id}, category: {category}, photo: {photo}")
    
    await state.clear()
    
    discount_percent = int((1 - data["discount_price"] / data["original_price"]) * 100)
    
    category_names = {
        "bakery": "🍞 Выпечка",
        "dairy": "🥛 Молочка",
        "meat": "🥩 Мясо",
        "fruits": "🍎 Фрукты",
        "vegetables": "🥬 Овощи",
        "other": "🎯 Другое",
    }
    category_display = category_names.get(data.get("category", "other"), "🎯 Другое")
    
    await message.answer(
        f"✅ <b>{'ТОВАР СОЗДАН!' if lang == 'ru' else 'MAHSULOT YARATILDI!'}</b>\n\n"
        f"📦 {data['title']}\n"
        f"🏷️ {category_display}\n"
        f"💰 {int(data['original_price'])} ➜ {int(data['discount_price'])} сум (-{discount_percent}%)\n"
        f"📊 {data['quantity']} шт\n"
        f"📅 До: {expiry_date}\n"
        f"⏰ Забор: 18:00-21:00",
        parse_mode="HTML",
    )
    
    await message.answer(
        f"{'Что дальше?' if lang == 'ru' else 'Keyingi qadam?'}",
        reply_markup=main_menu_seller(lang),
    )
