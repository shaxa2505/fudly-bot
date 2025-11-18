"""Bulk import of offers via media group (photo albums) and CSV+ZIP."""
from aiogram import Router, F, types
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder
import re
import csv
import io
import zipfile
from typing import List, Dict, Any
from datetime import datetime
from localization import get_text

# Module-level dependencies
db: Any = None
bot: Any = None

router = Router()


def setup_dependencies(database: Any, bot_instance: Any) -> None:
    """Setup module dependencies."""
    global db, bot
    db = database
    bot = bot_instance


class BulkImport(StatesGroup):
    waiting_photos = State()
    waiting_csv = State()
    waiting_zip = State()


@router.message(F.text.in_(["📦 Массовый импорт", "📦 Ommaviy import"]))
async def start_bulk_import(message: types.Message, state: FSMContext):
    """Start bulk import process"""
    
    if not db:
        await message.answer("❌ System error")
        return
    
    user_id = message.from_user.id
    lang = db.get_user_language(user_id)
    
    # Check if user has a store
    store = db.get_store_by_owner(user_id)
    if not store:
        await message.answer(
            "❌ У вас нет магазина. Сначала зарегистрируйтесь как партнер."
            if lang == 'ru' else
            "❌ Sizda do'kon yo'q. Avval hamkor sifatida ro'yxatdan o'ting."
        )
        return
    
    # Check store status
    store_status = store.get('status') if isinstance(store, dict) else store[8]
    if store_status != 'active':
        await message.answer(
            "❌ Ваш магазин еще не одобрен администратором"
            if lang == 'ru' else
            "❌ Do'koningiz hali administrator tomonidan tasdiqlanmagan"
        )
        return
    
    # Keyboard with import options
    kb = InlineKeyboardBuilder()
    kb.button(
        text="📸 Альбом фото" if lang == 'ru' else "📸 Rasm albomi",
        callback_data="import_method_photos"
    )
    kb.button(
        text="📄 CSV + ZIP" if lang == 'ru' else "📄 CSV + ZIP",
        callback_data="import_method_csv"
    )
    kb.adjust(1)
    
    instructions = """📦 <b>Массовый импорт товаров</b>

Выберите способ импорта:

<b>📸 Альбом фото</b>
• До 10 товаров за раз
• Быстрый ввод данных
• Добавьте описание к каждому фото

<b>📄 CSV + ZIP</b>
• Любое количество товаров
• Загрузите CSV файл с данными
• Загрузите ZIP архив с фото
• <b>Я отправлю пример файлов!</b>

Что выбираете?"""

    if lang != 'ru':
        instructions = """📦 <b>Ommaviy import</b>

Import usulini tanlang:

<b>📸 Rasm albomi</b>
• Bir vaqtda 10 tagacha mahsulot
• Tez ma'lumot kiritish

<b>📄 CSV + ZIP</b>
• Istalgan miqdorda mahsulot
• <b>Misol fayllarni yuboraman!</b>

Qaysi usulni tanlaysiz?"""
    
    await message.answer(instructions, parse_mode="HTML", reply_markup=kb.as_markup())


@router.callback_query(F.data == "import_method_photos")
async def import_via_photos(callback: types.CallbackQuery, state: FSMContext):
    """Start photo album import"""
    
    lang = db.get_user_language(callback.from_user.id) if db else 'ru'
    
    await callback.answer()
    
    instructions = """📸 <b>Импорт альбомом фото</b>

<b>Как это работает:</b>
1️⃣ Отправьте альбом фото (до 10 фото за раз)
2️⃣ К каждому фото добавьте описание в формате:
   <code>Название | Цена | Скидка | Количество | Срок</code>

<b>Пример:</b>
<code>Молоко 2.5% | 8000 | 6000 | 50 | 2025-11-20</code>
<code>Хлеб белый | 3000 | 2000 | 100 | 2025-11-18</code>

<b>Правила:</b>
• Цены в сумах (без пробелов)
• Срок годности: ГГГГ-ММ-ДД
• Количество - целое число
• Скидка должна быть меньше обычной цены

<b>Дополнительно (необязательно):</b>
Можно добавить описание и единицу измерения:
<code>Молоко | Описание | 8000 | 6000 | 50 | 2025-11-20 | л</code>

💡 Отправьте сразу несколько фото альбомом!
❌ Отмена - /cancel"""

    if lang != 'ru':
        instructions = """📸 <b>Rasm albomi bilan import</b>

<b>Qanday ishlaydi:</b>
1️⃣ Albom sifatida rasmlar yuboring (bir vaqtning o'zida 10 tagacha)
2️⃣ Har bir rasmga tavsif qo'shing:
   <code>Nomi | Narx | Chegirma | Soni | Muddat</code>

<b>Misol:</b>
<code>Sut 2.5% | 8000 | 6000 | 50 | 2025-11-20</code>
<code>Oq non | 3000 | 2000 | 100 | 2025-11-18</code>

💡 Bir vaqtning o'zida ko'p rasmlar yuboring!
❌ Bekor qilish - /cancel"""
    
    await callback.message.answer(instructions, parse_mode="HTML")
    await state.set_state(BulkImport.waiting_photos)
    await state.update_data(media_group_id=None, photos=[])


@router.message(BulkImport.waiting_photos, F.photo)
async def collect_photos(message: types.Message, state: FSMContext):
    """Collect photos from media group"""
    
    if not db:
        return
    
    data = await state.get_data()
    photos = data.get('photos', [])
    current_group = data.get('media_group_id')
    
    # Get photo info
    photo = message.photo[-1]  # Largest photo
    caption = message.caption or ""
    media_group_id = message.media_group_id
    
    # If this is a new media group or single photo
    if media_group_id != current_group and current_group is not None:
        # Process previous group
        await process_media_group(message, state, photos)
        photos = []
    
    # Add photo to collection
    photos.append({
        'file_id': photo.file_id,
        'caption': caption,
        'width': photo.width,
        'height': photo.height
    })
    
    await state.update_data(
        photos=photos,
        media_group_id=media_group_id
    )
    
    # If single photo (no media group), process immediately
    if not media_group_id:
        await process_media_group(message, state, photos)


async def process_media_group(message: types.Message, state: FSMContext, photos: List[Dict]):
    """Process collected photos and create offers"""
    
    if not db:
        return
    
    user_id = message.from_user.id
    lang = db.get_user_language(user_id)
    
    # Get store
    store = db.get_store_by_owner(user_id)
    if not store:
        await message.answer("❌ Магазин не найден" if lang == 'ru' else "❌ Do'kon topilmadi")
        await state.clear()
        return
    
    store_id = store.get('store_id') if isinstance(store, dict) else store[0]
    
    # Parse offers from captions
    offers = []
    errors = []
    
    for idx, photo in enumerate(photos, 1):
        caption = photo['caption'].strip()
        
        if not caption:
            errors.append(f"Фото {idx}: нет описания")
            continue
        
        try:
            offer_data = parse_offer_caption(caption)
            offer_data['photo_file_id'] = photo['file_id']
            offers.append(offer_data)
        except ValueError as e:
            errors.append(f"Фото {idx}: {str(e)}")
    
    # Show results
    if errors:
        error_text = "⚠️ <b>Ошибки:</b>\n" + "\n".join(errors[:5])
        if len(errors) > 5:
            error_text += f"\n\n...и еще {len(errors)-5} ошибок"
        await message.answer(error_text, parse_mode="HTML")
    
    if not offers:
        await message.answer(
            "❌ Не найдено корректных товаров. Проверьте формат описаний."
            if lang == 'ru' else
            "❌ To'g'ri mahsulotlar topilmadi. Tavsif formatini tekshiring."
        )
        await state.clear()
        return
    
    # Show preview
    preview = f"✅ <b>Готово к импорту: {len(offers)} товаров</b>\n\n"
    
    for i, offer in enumerate(offers[:3], 1):
        discount = int((1 - offer['discount_price']/offer['original_price']) * 100)
        preview += f"{i}. <b>{offer['title']}</b>\n"
        preview += f"   💰 {int(offer['discount_price']):,} сум (скидка {discount}%)\n"
        preview += f"   📦 {offer['quantity']} {offer.get('unit', 'шт')}\n\n"
    
    if len(offers) > 3:
        preview += f"...и еще {len(offers)-3} товаров\n\n"
    
    preview += "Подтвердить импорт?" if lang == 'ru' else "Importni tasdiqlaysizmi?"
    
    # Save to state
    await state.update_data(offers=offers, store_id=store_id)
    
    # Confirmation buttons
    kb = InlineKeyboardBuilder()
    kb.button(
        text="✅ Да, импортировать" if lang == 'ru' else "✅ Ha, import qilish",
        callback_data="confirm_bulk_import"
    )
    kb.button(
        text="❌ Отменить" if lang == 'ru' else "❌ Bekor qilish",
        callback_data="cancel_bulk_import"
    )
    kb.adjust(2)
    
    await message.answer(preview, parse_mode="HTML", reply_markup=kb.as_markup())


def parse_offer_caption(caption: str) -> Dict[str, Any]:
    """Parse offer data from photo caption
    
    Format: Название | Цена | Скидка | Количество | Срок
    или: Название | Описание | Цена | Скидка | Количество | Срок | Единица
    """
    parts = [p.strip() for p in caption.split('|')]
    
    if len(parts) < 5:
        raise ValueError("Недостаточно данных. Минимум: Название | Цена | Скидка | Количество | Срок")
    
    # Basic format: 5 parts
    if len(parts) == 5:
        title, price_str, discount_str, qty_str, expiry = parts
        description = ""
        unit = "шт"
    # Extended format: 6 parts (with unit)
    elif len(parts) == 6:
        title, price_str, discount_str, qty_str, expiry, unit = parts
        description = ""
    # Full format: 7 parts (with description)
    elif len(parts) >= 7:
        title, description, price_str, discount_str, qty_str, expiry, unit = parts[:7]
    else:
        title = parts[0]
        description = ""
        price_str = parts[-4]
        discount_str = parts[-3]
        qty_str = parts[-2]
        expiry = parts[-1]
        unit = "шт"
    
    # Parse numbers
    try:
        original_price = float(price_str.replace(',', '').replace(' ', ''))
        discount_price = float(discount_str.replace(',', '').replace(' ', ''))
        quantity = int(qty_str.replace(',', '').replace(' ', ''))
    except ValueError:
        raise ValueError("Неверный формат цены или количества")
    
    # Validate
    if discount_price >= original_price:
        raise ValueError("Цена со скидкой должна быть меньше обычной цены")
    
    if quantity <= 0:
        raise ValueError("Количество должно быть больше 0")
    
    # Validate date format
    try:
        datetime.strptime(expiry, '%Y-%m-%d')
    except ValueError:
        raise ValueError("Неверный формат даты. Используйте ГГГГ-ММ-ДД")
    
    return {
        'title': title,
        'description': description,
        'original_price': original_price,
        'discount_price': discount_price,
        'quantity': quantity,
        'expiry_date': expiry,
        'unit': unit
    }


@router.callback_query(F.data == "confirm_bulk_import")
async def confirm_bulk_import(callback: types.CallbackQuery, state: FSMContext):
    """Confirm and execute bulk import"""
    
    if not db:
        await callback.answer("❌ System error", show_alert=True)
        return
    
    lang = db.get_user_language(callback.from_user.id)
    data = await state.get_data()
    offers = data.get('offers', [])
    store_id = data.get('store_id')
    
    if not offers or not store_id:
        await callback.answer(
            "❌ Данные утеряны" if lang == 'ru' else "❌ Ma'lumotlar yo'qoldi",
            show_alert=True
        )
        await state.clear()
        return
    
    await callback.answer()
    await callback.message.edit_text("⏳ Импортирую товары..." if lang == 'ru' else "⏳ Import qilinmoqda...")
    
    # Import offers
    success_count = 0
    failed_count = 0
    
    for offer in offers:
        try:
            db.add_offer(
                store_id=store_id,
                title=offer['title'],
                description=offer.get('description', ''),
                original_price=offer['original_price'],
                discount_price=offer['discount_price'],
                quantity=offer['quantity'],
                expiry_date=offer['expiry_date'],
                unit=offer.get('unit', 'шт'),
                photo=offer.get('photo_file_id')
            )
            success_count += 1
        except Exception as e:
            failed_count += 1
            print(f"Failed to import offer: {e}")
    
    # Result
    result_text = f"✅ <b>Импорт завершен!</b>\n\n" if lang == 'ru' else f"✅ <b>Import tugadi!</b>\n\n"
    result_text += f"✅ Успешно: {success_count}\n" if lang == 'ru' else f"✅ Muvaffaqiyatli: {success_count}\n"
    if failed_count:
        result_text += f"❌ Ошибок: {failed_count}\n" if lang == 'ru' else f"❌ Xatolar: {failed_count}\n"
    
    await callback.message.answer(result_text, parse_mode="HTML")
    await state.clear()


@router.callback_query(F.data == "cancel_bulk_import")
async def cancel_bulk_import(callback: types.CallbackQuery, state: FSMContext):
    """Cancel bulk import"""
    
    lang = db.get_user_language(callback.from_user.id) if db else 'ru'
    
    await callback.answer()
    await callback.message.edit_text(
        "❌ Импорт отменен" if lang == 'ru' else "❌ Import bekor qilindi"
    )
    await state.clear()


@router.callback_query(F.data == "import_method_csv")
async def import_via_csv(callback: types.CallbackQuery, state: FSMContext):
    """Start CSV + ZIP import"""
    
    lang = db.get_user_language(callback.from_user.id) if db else 'ru'
    
    await callback.answer()
    
    # Send example CSV file
    example_csv = """photo_file,title,description,original_price,discount_price,quantity,expiry_date,unit
milk.jpg,Молоко 2.5%,Свежее молоко высшего качества,8000,6000,50,2025-11-25,л
bread.jpg,Хлеб белый,Свежий хлеб из пшеницы,3000,2000,100,2025-11-19,шт
cheese.jpg,Сыр российский,Натуральный сыр,15000,12000,30,2025-12-01,кг
yogurt.jpg,Йогурт клубничный,Йогурт со вкусом клубники,4500,3500,80,2025-11-22,шт
butter.jpg,Масло сливочное,Масло 82.5%,12000,9500,40,2025-11-30,кг"""
    
    # Create CSV file in memory
    csv_file = types.BufferedInputFile(
        example_csv.encode('utf-8-sig'),  # UTF-8 with BOM for Excel
        filename="example_import.csv"
    )
    
    instructions = """📄 <b>Импорт через CSV + ZIP</b>

<b>Шаг 1:</b> Скачайте пример CSV файла ⬆️

<b>Шаг 2:</b> Заполните CSV файл вашими товарами
• <code>photo_file</code> - имя файла фото (milk.jpg)
• <code>title</code> - название товара
• <code>description</code> - описание (можно пусто)
• <code>original_price</code> - обычная цена
• <code>discount_price</code> - цена со скидкой
• <code>quantity</code> - количество
• <code>expiry_date</code> - срок годности (ГГГГ-ММ-ДД)
• <code>unit</code> - единица измерения (шт, кг, л)

<b>Шаг 3:</b> Создайте ZIP архив с фотографиями
📁 Имена файлов должны совпадать с CSV
📸 Например: milk.jpg, bread.jpg, cheese.jpg

<b>Шаг 4:</b> Отправьте CSV файл

❌ Отмена - /cancel"""

    if lang != 'ru':
        instructions = """📄 <b>CSV + ZIP orqali import</b>

<b>1-qadam:</b> Misol CSV faylini yuklab oling ⬆️

<b>2-qadam:</b> CSV faylni to'ldiring

<b>3-qadam:</b> Rasmlar bilan ZIP arxiv yarating

<b>4-qadam:</b> CSV faylni yuboring

❌ Bekor qilish - /cancel"""
    
    await callback.message.answer_document(
        csv_file,
        caption=instructions,
        parse_mode="HTML"
    )
    
    await state.set_state(BulkImport.waiting_csv)


@router.message(BulkImport.waiting_csv, F.document)
async def receive_csv(message: types.Message, state: FSMContext):
    """Receive CSV file"""
    
    if not db:
        return
    
    lang = db.get_user_language(message.from_user.id)
    
    # Check if it's a CSV file
    if not message.document.file_name.endswith(('.csv', '.CSV')):
        await message.answer(
            "❌ Отправьте CSV файл" if lang == 'ru' else "❌ CSV fayl yuboring"
        )
        return
    
    try:
        # Download CSV file
        file = await bot.download(message.document)
        csv_content = file.read().decode('utf-8-sig')  # Handle BOM
        
        # Parse CSV
        csv_reader = csv.DictReader(io.StringIO(csv_content))
        products = list(csv_reader)
        
        if not products:
            await message.answer(
                "❌ CSV файл пустой" if lang == 'ru' else "❌ CSV fayl bo'sh"
            )
            return
        
        # Validate CSV structure
        required_fields = ['photo_file', 'title', 'original_price', 'discount_price', 'quantity', 'expiry_date']
        missing_fields = [f for f in required_fields if f not in products[0]]
        
        if missing_fields:
            await message.answer(
                f"❌ В CSV отсутствуют обязательные поля: {', '.join(missing_fields)}"
                if lang == 'ru' else
                f"❌ CSV da majburiy maydonlar yo'q: {', '.join(missing_fields)}"
            )
            return
        
        # Save products to state
        await state.update_data(products=products)
        
        await message.answer(
            f"✅ CSV загружен: {len(products)} товаров\n\n"
            f"<b>Теперь отправьте ZIP архив с фотографиями</b>\n"
            f"📁 Имена файлов должны совпадать с CSV\n\n"
            f"❌ Отмена - /cancel"
            if lang == 'ru' else
            f"✅ CSV yuklandi: {len(products)} mahsulot\n\n"
            f"<b>Endi rasmlar bilan ZIP arxivni yuboring</b>\n\n"
            f"❌ Bekor qilish - /cancel",
            parse_mode="HTML"
        )
        
        await state.set_state(BulkImport.waiting_zip)
        
    except Exception as e:
        print(f"Error parsing CSV: {e}")
        await message.answer(
            "❌ Ошибка при чтении CSV файла. Проверьте формат."
            if lang == 'ru' else
            "❌ CSV faylni o'qishda xato. Formatni tekshiring."
        )


@router.message(BulkImport.waiting_zip, F.document)
async def receive_zip(message: types.Message, state: FSMContext):
    """Receive ZIP archive with photos"""
    
    if not db:
        return
    
    lang = db.get_user_language(message.from_user.id)
    user_id = message.from_user.id
    
    # Check if it's a ZIP file
    if not message.document.file_name.endswith(('.zip', '.ZIP')):
        await message.answer(
            "❌ Отправьте ZIP архив" if lang == 'ru' else "❌ ZIP arxiv yuboring"
        )
        return
    
    try:
        # Get store
        store = db.get_store_by_owner(user_id)
        if not store:
            await message.answer("❌ Магазин не найден" if lang == 'ru' else "❌ Do'kon topilmadi")
            await state.clear()
            return
        
        store_id = store.get('store_id') if isinstance(store, dict) else store[0]
        
        # Download ZIP file
        file = await bot.download(message.document)
        zip_content = file.read()
        
        # Parse ZIP
        with zipfile.ZipFile(io.BytesIO(zip_content)) as zip_file:
            photo_files = {name: zip_file.read(name) for name in zip_file.namelist() 
                          if name.lower().endswith(('.jpg', '.jpeg', '.png'))}
        
        if not photo_files:
            await message.answer(
                "❌ В ZIP архиве нет фотографий" if lang == 'ru' else "❌ ZIP arxivda rasmlar yo'q"
            )
            return
        
        # Get products from state
        data = await state.get_data()
        products = data.get('products', [])
        
        if not products:
            await message.answer(
                "❌ Сначала отправьте CSV файл" if lang == 'ru' else "❌ Avval CSV fayl yuboring"
            )
            await state.set_state(BulkImport.waiting_csv)
            return
        
        await message.answer("⏳ Обрабатываю..." if lang == 'ru' else "⏳ Qayta ishlanmoqda...")
        
        # Process each product
        success_count = 0
        failed_count = 0
        errors = []
        
        for idx, product in enumerate(products, 1):
            try:
                photo_name = product['photo_file'].strip()
                
                # Find photo in ZIP (case insensitive)
                photo_data = None
                for zip_name, data in photo_files.items():
                    if zip_name.lower().endswith(photo_name.lower()) or photo_name.lower() in zip_name.lower():
                        photo_data = data
                        break
                
                if not photo_data:
                    errors.append(f"{idx}. {product['title']}: фото {photo_name} не найдено")
                    failed_count += 1
                    continue
                
                # Upload photo to Telegram
                photo_file = types.BufferedInputFile(photo_data, filename=photo_name)
                photo_msg = await message.answer_photo(photo_file)
                photo_file_id = photo_msg.photo[-1].file_id
                await photo_msg.delete()  # Clean up
                
                # Parse product data
                title = product['title']
                description = product.get('description', '')
                original_price = float(product['original_price'])
                discount_price = float(product['discount_price'])
                quantity = int(product['quantity'])
                expiry_date = product['expiry_date']
                unit = product.get('unit', 'шт')
                
                # Validate
                if discount_price >= original_price:
                    errors.append(f"{idx}. {title}: цена со скидкой >= обычной")
                    failed_count += 1
                    continue
                
                # Add to database
                db.add_offer(
                    store_id=store_id,
                    title=title,
                    description=description,
                    original_price=original_price,
                    discount_price=discount_price,
                    quantity=quantity,
                    expiry_date=expiry_date,
                    unit=unit,
                    photo=photo_file_id
                )
                
                success_count += 1
                
            except Exception as e:
                errors.append(f"{idx}. {product.get('title', '?')}: {str(e)}")
                failed_count += 1
        
        # Result
        result_text = f"✅ <b>Импорт завершен!</b>\n\n" if lang == 'ru' else f"✅ <b>Import tugadi!</b>\n\n"
        result_text += f"✅ Успешно: {success_count}\n" if lang == 'ru' else f"✅ Muvaffaqiyatli: {success_count}\n"
        
        if failed_count:
            result_text += f"❌ Ошибок: {failed_count}\n" if lang == 'ru' else f"❌ Xatolar: {failed_count}\n"
            if errors:
                result_text += f"\n<b>Детали:</b>\n" + "\n".join(errors[:10])
                if len(errors) > 10:
                    result_text += f"\n\n...и еще {len(errors)-10} ошибок"
        
        await message.answer(result_text, parse_mode="HTML")
        await state.clear()
        
    except zipfile.BadZipFile:
        await message.answer(
            "❌ Поврежденный ZIP архив" if lang == 'ru' else "❌ Buzilgan ZIP arxiv"
        )
    except Exception as e:
        print(f"Error processing ZIP: {e}")
        await message.answer(
            "❌ Ошибка при обработке архива" if lang == 'ru' else "❌ Arxivni qayta ishlashda xato"
        )


@router.message(BulkImport.waiting_photos, F.text == "/cancel")
@router.message(BulkImport.waiting_csv, F.text == "/cancel")
@router.message(BulkImport.waiting_zip, F.text == "/cancel")
async def cancel_import_command(message: types.Message, state: FSMContext):
    """Cancel import via command"""
    
    lang = db.get_user_language(message.from_user.id) if db else 'ru'
    
    await message.answer(
        "❌ Импорт отменен" if lang == 'ru' else "❌ Import bekor qilindi"
    )
    await state.clear()
