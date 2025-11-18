# 📊 Массовый импорт товаров - Техническое задание

## Проблема
Партнерам неудобно добавлять 100+ товаров по одному через диалог с ботом.

## Решение
Добавить функцию импорта товаров из CSV/Excel файла.

---

## 🎯 Функционал

### Для партнера:
1. В меню партнера кнопка **"📦 Массовый импорт"**
2. Бот отправляет:
   - Шаблон Excel файла (пример заполнения)
   - Инструкцию по заполнению
3. Партнер скачивает шаблон → заполняет → отправляет обратно
4. Бот проверяет файл → показывает превью → подтверждает импорт
5. Все товары добавляются автоматически

### Формат CSV:
```csv
название,описание,цена_обычная,цена_со_скидкой,количество,срок_годности,единица,категория
Молоко 2.5%,Свежее молоко,8000,6000,50,2025-11-20,л,dairy
Хлеб белый,Свежий хлеб,3000,2000,100,2025-11-18,шт,bakery
Яблоки,Красные,12000,9000,30,2025-11-25,кг,fruits
```

---

## 📋 Реализация

### 1. Добавить в партнерское меню
```python
# app/keyboards/seller.py
def main_menu_seller(lang: str = 'ru') -> ReplyKeyboardMarkup:
    builder = ReplyKeyboardBuilder()
    
    # ... existing buttons ...
    
    builder.button(text="📦 Массовый импорт" if lang == 'ru' else "📦 Ommaviy import")
    
    builder.adjust(2, 2, 2, 1)  # Новая строка для импорта
    return builder.as_markup(resize_keyboard=True)
```

### 2. Создать handler
```python
# handlers/seller/bulk_import.py

from aiogram import Router, F, types
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
import csv
import io
import openpyxl  # pip install openpyxl

router = Router()

class BulkImport(StatesGroup):
    waiting_file = State()

@router.message(F.text.contains("Массовый импорт"))
async def start_bulk_import(message: types.Message, state: FSMContext):
    """Начало массового импорта"""
    
    # Создаем шаблон CSV
    template_csv = """название,описание,цена_обычная,цена_со_скидкой,количество,срок_годности,единица,категория
Молоко 2.5%,Свежее молоко,8000,6000,50,2025-11-20,л,dairy
Хлеб белый,Свежий хлеб,3000,2000,100,2025-11-18,шт,bakery"""
    
    # Отправляем шаблон
    file_bytes = template_csv.encode('utf-8-sig')  # BOM для Excel
    template_file = types.BufferedInputFile(file_bytes, filename="template.csv")
    
    await message.answer_document(
        document=template_file,
        caption=(
            "📦 <b>Массовый импорт товаров</b>\n\n"
            "1️⃣ Скачайте шаблон выше\n"
            "2️⃣ Заполните данные о товарах\n"
            "3️⃣ Отправьте файл обратно\n\n"
            "📝 <b>Формат:</b>\n"
            "• Цены в сумах (без пробелов)\n"
            "• Срок годности: YYYY-MM-DD\n"
            "• Категории: dairy, bakery, meat, vegetables, fruits\n\n"
            "❌ Отмена - отправьте /cancel"
        ),
        parse_mode="HTML"
    )
    
    await state.set_state(BulkImport.waiting_file)


@router.message(BulkImport.waiting_file, F.document)
async def process_bulk_file(message: types.Message, state: FSMContext):
    """Обработка загруженного CSV/Excel"""
    
    if not message.document:
        await message.answer("❌ Отправьте файл CSV или Excel")
        return
    
    # Скачиваем файл
    file = await message.bot.download(message.document)
    
    try:
        # Читаем CSV
        content = file.read().decode('utf-8-sig')
        reader = csv.DictReader(io.StringIO(content))
        
        offers = []
        errors = []
        
        for idx, row in enumerate(reader, start=2):  # Строка 1 = заголовки
            try:
                # Валидация
                if not row['название'] or not row['цена_обычная']:
                    errors.append(f"Строка {idx}: Не указано название или цена")
                    continue
                
                offer = {
                    'title': row['название'].strip(),
                    'description': row.get('описание', '').strip(),
                    'original_price': float(row['цена_обычная']),
                    'discount_price': float(row['цена_со_скидкой']),
                    'quantity': int(row['количество']),
                    'expiry_date': row['срок_годности'],
                    'unit': row.get('единица', 'шт'),
                    'category': row.get('категория', 'other')
                }
                
                # Проверка скидки
                if offer['discount_price'] >= offer['original_price']:
                    errors.append(f"Строка {idx}: Цена со скидкой >= обычной цены")
                    continue
                
                offers.append(offer)
                
            except Exception as e:
                errors.append(f"Строка {idx}: {str(e)}")
        
        # Показываем результат валидации
        if errors:
            error_text = "⚠️ <b>Найдены ошибки:</b>\n\n" + "\n".join(errors[:10])
            if len(errors) > 10:
                error_text += f"\n\n...и еще {len(errors)-10} ошибок"
            await message.answer(error_text, parse_mode="HTML")
        
        if not offers:
            await message.answer("❌ Не найдено корректных товаров для импорта")
            await state.clear()
            return
        
        # Превью
        preview = f"✅ <b>Готово к импорту: {len(offers)} товаров</b>\n\n"
        preview += "<b>Первые 5 товаров:</b>\n\n"
        
        for i, offer in enumerate(offers[:5], 1):
            discount = int((1 - offer['discount_price']/offer['original_price']) * 100)
            preview += f"{i}. {offer['title']}\n"
            preview += f"   💰 {int(offer['discount_price']):,} сум (скидка {discount}%)\n\n"
        
        if len(offers) > 5:
            preview += f"...и еще {len(offers)-5} товаров\n\n"
        
        preview += "Подтвердить импорт?"
        
        # Сохраняем в state
        await state.update_data(offers=offers)
        
        # Кнопки подтверждения
        kb = InlineKeyboardBuilder()
        kb.button(text="✅ Да, импортировать", callback_data="confirm_bulk_import")
        kb.button(text="❌ Отменить", callback_data="cancel_bulk_import")
        kb.adjust(2)
        
        await message.answer(preview, parse_mode="HTML", reply_markup=kb.as_markup())
        
    except Exception as e:
        await message.answer(f"❌ Ошибка чтения файла: {str(e)}")
        await state.clear()


@router.callback_query(F.data == "confirm_bulk_import")
async def confirm_import(callback: types.CallbackQuery, state: FSMContext):
    """Подтверждение импорта"""
    
    data = await state.get_data()
    offers = data.get('offers', [])
    
    if not offers:
        await callback.answer("❌ Данные утеряны, начните заново", show_alert=True)
        await state.clear()
        return
    
    await callback.answer()
    await callback.message.edit_text("⏳ Импортирую товары...")
    
    # Получаем store_id партнера
    user_id = callback.from_user.id
    store = db.get_store_by_owner(user_id)
    
    if not store:
        await callback.message.answer("❌ У вас нет магазина")
        await state.clear()
        return
    
    store_id = store['store_id'] if isinstance(store, dict) else store[0]
    
    # Массовое добавление
    success_count = 0
    failed_count = 0
    
    for offer in offers:
        try:
            db.add_offer(
                store_id=store_id,
                title=offer['title'],
                description=offer['description'],
                original_price=offer['original_price'],
                discount_price=offer['discount_price'],
                quantity=offer['quantity'],
                expiry_date=offer['expiry_date'],
                unit=offer['unit'],
                category=offer['category']
            )
            success_count += 1
        except Exception as e:
            failed_count += 1
            logger.error(f"Failed to import offer: {e}")
    
    # Результат
    result_text = f"✅ <b>Импорт завершен!</b>\n\n"
    result_text += f"✅ Успешно: {success_count}\n"
    if failed_count:
        result_text += f"❌ Ошибок: {failed_count}\n"
    
    await callback.message.answer(result_text, parse_mode="HTML")
    await state.clear()


@router.callback_query(F.data == "cancel_bulk_import")
async def cancel_import(callback: types.CallbackQuery, state: FSMContext):
    """Отмена импорта"""
    await callback.answer()
    await callback.message.edit_text("❌ Импорт отменен")
    await state.clear()
```

### 3. Зарегистрировать router
```python
# bot.py

from handlers.seller import bulk_import

# ...

# Register routers
dp.include_router(bulk_import.router)
```

---

## 🚀 Дополнительные фичи

### Excel шаблон с форматированием
```python
def create_excel_template():
    """Создает красивый Excel шаблон"""
    wb = openpyxl.Workbook()
    ws = wb.active
    
    # Заголовки
    headers = ['Название', 'Описание', 'Цена обычная', 'Цена со скидкой', 
               'Количество', 'Срок годности', 'Единица', 'Категория']
    ws.append(headers)
    
    # Примеры
    ws.append(['Молоко 2.5%', 'Свежее молоко', 8000, 6000, 50, '2025-11-20', 'л', 'dairy'])
    ws.append(['Хлеб белый', 'Свежий хлеб', 3000, 2000, 100, '2025-11-18', 'шт', 'bakery'])
    
    # Сохраняем в BytesIO
    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    
    return buffer.getvalue()
```

### Валидация категорий
```python
ALLOWED_CATEGORIES = {
    'dairy': 'Молочные продукты',
    'bakery': 'Выпечка',
    'meat': 'Мясо',
    'fish': 'Рыба',
    'vegetables': 'Овощи',
    'fruits': 'Фрукты',
    'ready_food': 'Готовая еда',
    'beverages': 'Напитки',
    'other': 'Другое'
}
```

---

## ⚡ Альтернатива: Быстрое дублирование

Для похожих товаров (например, молоко разной жирности):
```python
@router.callback_query(F.data.startswith("duplicate_offer_"))
async def duplicate_offer(callback: types.CallbackQuery):
    """Дублирует товар для быстрого редактирования"""
    offer_id = int(callback.data.split("_")[2])
    
    # Копируем offer
    original = db.get_offer(offer_id)
    new_id = db.add_offer(
        store_id=original['store_id'],
        title=original['title'] + " (копия)",
        description=original['description'],
        original_price=original['original_price'],
        discount_price=original['discount_price'],
        quantity=original['quantity']
    )
    
    await callback.answer("✅ Товар продублирован. Отредактируйте название и цену")
```

---

## 📊 Статистика импорта

После импорта показывать:
- ✅ Импортировано товаров
- 💰 Общая стоимость по скидке
- 📦 Общее количество единиц
- 🏷️ Распределение по категориям

---

**Хотите, чтобы я реализовал массовый CSV импорт?** Это займет ~30 минут.
