"""
Скрипт для добавления 100 тестовых товаров в базу данных
"""
import sqlite3
import random
from datetime import datetime, timedelta

# Подключаемся к базе данных
conn = sqlite3.connect('fudly.db')
cursor = conn.cursor()

# Проверяем есть ли магазины
cursor.execute("SELECT store_id, name, city FROM stores WHERE status = 'active' OR status = 'approved' LIMIT 5")
stores = cursor.fetchall()

if not stores:
    print("❌ Нет активных магазинов! Сначала создайте магазин через бота.")
    conn.close()
    exit(1)

print(f"✅ Найдено {len(stores)} магазинов")
for store in stores:
    print(f"   - {store[1]} ({store[2]})")

# Категории товаров
categories = ['dairy', 'bakery', 'meat', 'fruits', 'vegetables', 'ready_food']
category_names = {
    'dairy': ['Молоко', 'Кефир', 'Творог', 'Сметана', 'Йогурт', 'Сыр', 'Масло сливочное'],
    'bakery': ['Хлеб белый', 'Хлеб черный', 'Батон', 'Булочка', 'Круассан', 'Пирожок', 'Лаваш'],
    'meat': ['Курица', 'Говядина', 'Баранина', 'Колбаса', 'Сосиски', 'Фарш', 'Котлеты'],
    'fruits': ['Яблоки', 'Бананы', 'Апельсины', 'Мандарины', 'Груши', 'Виноград', 'Киви'],
    'vegetables': ['Помидоры', 'Огурцы', 'Картофель', 'Морковь', 'Капуста', 'Лук', 'Перец'],
    'ready_food': ['Салат', 'Суп', 'Плов', 'Шашлык', 'Манты', 'Самса', 'Лагман']
}

units = ['шт', 'кг', 'л', 'уп']

# Генерируем 100 товаров
added_count = 0
for i in range(100):
    # Выбираем случайный магазин
    store = random.choice(stores)
    store_id = store[0]
    
    # Выбираем случайную категорию
    category = random.choice(categories)
    product_names = category_names[category]
    product_name = random.choice(product_names)
    
    # Добавляем вариацию к названию
    variations = ['', ' премиум', ' эконом', ' свежий', ' домашний', ' фермерский']
    product_name += random.choice(variations)
    
    # Генерируем описание
    descriptions = [
        'Свежий продукт высокого качества',
        'Лучшая цена в городе',
        'Остатки от производства',
        'Срок годности истекает',
        'Супер предложение дня',
        'Акция - только сегодня'
    ]
    description = random.choice(descriptions)
    
    # Генерируем цены
    original_price = random.randint(5, 50) * 1000  # От 5000 до 50000
    discount_percent = random.randint(20, 70)  # От 20% до 70%
    discount_price = int(original_price * (100 - discount_percent) / 100)
    
    # Количество
    quantity = random.randint(1, 20)
    
    # Единица измерения
    unit = random.choice(units)
    
    # Даты
    now = datetime.now()
    available_from = now.strftime('%Y-%m-%d %H:%M:%S')
    available_until = (now + timedelta(hours=random.randint(6, 24))).strftime('%Y-%m-%d %H:%M:%S')
    expiry_date = (now + timedelta(days=random.randint(1, 7))).strftime('%Y-%m-%d %H:%M:%S')
    
    # Вставляем товар
    try:
        cursor.execute('''
            INSERT INTO offers (
                store_id, title, description, original_price, discount_price,
                quantity, unit, category, available_from, available_until,
                expiry_date, status, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'active', CURRENT_TIMESTAMP)
        ''', (
            store_id, product_name, description, original_price, discount_price,
            quantity, unit, category, available_from, available_until, expiry_date
        ))
        added_count += 1
        if (i + 1) % 10 == 0:
            print(f"✅ Добавлено {i + 1}/100 товаров...")
    except Exception as e:
        print(f"❌ Ошибка при добавлении товара {i + 1}: {e}")

conn.commit()
conn.close()

print(f"\n🎉 Успешно добавлено {added_count} тестовых товаров!")
print(f"📊 Теперь можете проверить кнопку '🔥 Горячее' в боте")
