"""Generate 100 test products with photos for testing."""
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Load environment variables
from dotenv import load_dotenv
load_dotenv()

# Check if we should use PostgreSQL or SQLite
use_postgres = os.getenv('DATABASE_URL') is not None

if use_postgres:
    from database_pg import Database
else:
    from database import Database

import random
from datetime import datetime, timedelta

# Note: This script works with both PostgreSQL (if DATABASE_URL is set) and SQLite (fallback)

# Sample product data
PRODUCTS = [
    # Bakery
    ("Хлеб белый", "Свежий белый хлеб", 5000, 4000, "bakery", "шт"),
    ("Хлеб черный", "Ржаной хлеб", 6000, 4500, "bakery", "шт"),
    ("Батон нарезной", "Классический батон", 4500, 3500, "bakery", "шт"),
    ("Булочки с изюмом", "Сдобные булочки", 8000, 6000, "bakery", "упак"),
    ("Круассаны", "Французские круассаны", 12000, 9000, "bakery", "упак"),
    ("Печенье овсяное", "Домашнее печенье", 15000, 12000, "bakery", "кг"),
    ("Торт медовик", "Классический торт", 45000, 35000, "bakery", "шт"),
    ("Пирожное эклер", "Заварные пирожные", 8000, 6000, "bakery", "шт"),
    ("Лепешка узбекская", "Свежая лепешка", 3000, 2500, "bakery", "шт"),
    ("Сомса с мясом", "Свежая сомса", 10000, 8000, "bakery", "шт"),
    
    # Dairy
    ("Молоко 3.2%", "Пастеризованное", 10000, 8500, "dairy", "л"),
    ("Кефир", "Натуральный кефир", 12000, 10000, "dairy", "л"),
    ("Йогурт натуральный", "Без добавок", 8000, 6500, "dairy", "шт"),
    ("Йогурт фруктовый", "С клубникой", 9000, 7000, "dairy", "шт"),
    ("Сметана 20%", "Густая сметана", 15000, 12000, "dairy", "кг"),
    ("Творог 9%", "Домашний творог", 18000, 15000, "dairy", "кг"),
    ("Сыр российский", "Твердый сыр", 50000, 40000, "dairy", "кг"),
    ("Сыр голландский", "Классический", 55000, 45000, "dairy", "кг"),
    ("Масло сливочное", "82.5% жирности", 60000, 50000, "dairy", "кг"),
    ("Мороженое пломбир", "Классическое", 8000, 6000, "dairy", "шт"),
    
    # Meat
    ("Курица целая", "Охлажденная", 28000, 24000, "meat", "кг"),
    ("Говядина", "Вырезка", 80000, 70000, "meat", "кг"),
    ("Баранина", "Свежая", 75000, 65000, "meat", "кг"),
    ("Колбаса докторская", "ГОСТ", 45000, 38000, "meat", "кг"),
    ("Сосиски молочные", "Высший сорт", 40000, 35000, "meat", "кг"),
    ("Пельмени домашние", "Ручная лепка", 35000, 30000, "meat", "кг"),
    ("Котлеты куриные", "Замороженные", 30000, 25000, "meat", "кг"),
    ("Фарш говяжий", "Свежий", 55000, 48000, "meat", "кг"),
    ("Шашлык маринованный", "Готов к жарке", 60000, 50000, "meat", "кг"),
    ("Манты с мясом", "Замороженные", 40000, 35000, "meat", "кг"),
    
    # Fruits
    ("Яблоки красные", "Импорт", 18000, 15000, "fruits", "кг"),
    ("Яблоки зеленые", "Местные", 15000, 12000, "fruits", "кг"),
    ("Бананы", "Эквадор", 20000, 17000, "fruits", "кг"),
    ("Апельсины", "Турция", 22000, 18000, "fruits", "кг"),
    ("Мандарины", "Свежие", 20000, 16000, "fruits", "кг"),
    ("Груши", "Сочные", 18000, 15000, "fruits", "кг"),
    ("Виноград белый", "Без косточек", 35000, 30000, "fruits", "кг"),
    ("Виноград черный", "Сладкий", 35000, 30000, "fruits", "кг"),
    ("Арбуз", "Сезонный", 5000, 4000, "fruits", "кг"),
    ("Дыня", "Ароматная", 8000, 6500, "fruits", "кг"),
    
    # Vegetables
    ("Помидоры", "Свежие", 15000, 12000, "vegetables", "кг"),
    ("Огурцы", "Местные", 12000, 10000, "vegetables", "кг"),
    ("Картофель", "Молодой", 8000, 6500, "vegetables", "кг"),
    ("Морковь", "Сочная", 7000, 5500, "vegetables", "кг"),
    ("Лук репчатый", "Крупный", 6000, 5000, "vegetables", "кг"),
    ("Капуста белокочанная", "Свежая", 7000, 5500, "vegetables", "кг"),
    ("Перец болгарский", "Разноцветный", 25000, 20000, "vegetables", "кг"),
    ("Баклажаны", "Местные", 12000, 10000, "vegetables", "кг"),
    ("Кабачки", "Молодые", 10000, 8000, "vegetables", "кг"),
    ("Зелень ассорти", "Свежая", 5000, 4000, "vegetables", "пучок"),
    
    # Drinks
    ("Вода минеральная", "Гидролайф 1.5л", 3000, 2500, "drinks", "шт"),
    ("Вода газированная", "Аква 1.5л", 3500, 3000, "drinks", "шт"),
    ("Сок апельсиновый", "Rich 1л", 12000, 10000, "drinks", "шт"),
    ("Сок яблочный", "Rich 1л", 12000, 10000, "drinks", "шт"),
    ("Coca-Cola", "1.5л", 10000, 8500, "drinks", "шт"),
    ("Pepsi", "1.5л", 10000, 8500, "drinks", "шт"),
    ("Fanta", "1.5л", 10000, 8500, "drinks", "шт"),
    ("Sprite", "1.5л", 10000, 8500, "drinks", "шт"),
    ("Компот ассорти", "Домашний 1л", 8000, 6500, "drinks", "шт"),
    ("Лимонад", "Домашний 1л", 7000, 5500, "drinks", "шт"),
    
    # Snacks
    ("Чипсы Lays", "Сметана-лук", 8000, 6500, "snacks", "упак"),
    ("Чипсы Pringles", "Оригинал", 15000, 12000, "snacks", "упак"),
    ("Сухарики", "Холодец хрен", 5000, 4000, "snacks", "упак"),
    ("Орехи миндаль", "Жареный", 40000, 35000, "snacks", "кг"),
    ("Орехи кешью", "Соленый", 45000, 40000, "snacks", "кг"),
    ("Семечки", "Жареные", 15000, 12000, "snacks", "кг"),
    ("Попкорн", "Соленый", 10000, 8000, "snacks", "упак"),
    ("Крекеры", "Сырные", 7000, 5500, "snacks", "упак"),
    ("Вафли", "Шоколадные", 12000, 10000, "snacks", "упак"),
    ("Батончик Snickers", "50г", 5000, 4000, "snacks", "шт"),
    
    # Frozen
    ("Пицца замороженная", "Маргарита", 30000, 25000, "frozen", "шт"),
    ("Наггетсы куриные", "Замороженные", 25000, 20000, "frozen", "кг"),
    ("Овощи замороженные", "Микс", 18000, 15000, "frozen", "кг"),
    ("Блины с творогом", "Замороженные", 20000, 17000, "frozen", "упак"),
    ("Вареники с картошкой", "Замороженные", 18000, 15000, "frozen", "кг"),
    ("Мороженое эскимо", "Шоколадное", 15000, 12000, "frozen", "упак"),
    ("Торт замороженный", "Наполеон", 35000, 30000, "frozen", "шт"),
    ("Рыбные палочки", "Замороженные", 28000, 24000, "frozen", "кг"),
    ("Креветки", "Варено-мороженые", 60000, 50000, "frozen", "кг"),
    ("Ягоды замороженные", "Ассорти", 25000, 20000, "frozen", "кг"),
    
    # Tea & Coffee
    ("Чай Ahmad", "Earl Grey 100пак", 35000, 30000, "drinks", "упак"),
    ("Чай Akbar", "Черный 100пак", 30000, 25000, "drinks", "упак"),
    ("Чай зеленый", "Китайский 100пак", 28000, 24000, "drinks", "упак"),
    ("Кофе Nescafe", "Classic 100г", 40000, 35000, "drinks", "банка"),
    ("Кофе Jacobs", "Monarch 100г", 45000, 40000, "drinks", "банка"),
    ("Кофе молотый", "Арабика 250г", 35000, 30000, "drinks", "упак"),
    ("Какао", "Несквик 250г", 25000, 20000, "drinks", "упак"),
    
    # Chocolate
    ("Шоколад Milka", "Молочный 90г", 12000, 10000, "snacks", "шт"),
    ("Шоколад Alpen Gold", "Орех-изюм 90г", 11000, 9000, "snacks", "шт"),
    ("Конфеты Raffaello", "150г", 35000, 30000, "snacks", "упак"),
    ("Конфеты Ferrero", "200г", 45000, 40000, "snacks", "упак"),
    ("Мармелад", "Фруктовый 500г", 18000, 15000, "snacks", "упак"),
]

def main():
    db = Database()
    
    # Find any store in Samarkand, preferably Cosmos
    stores = db.get_stores_by_city("Самарканд")
    
    if not stores:
        print("❌ No stores found in Самарканд!")
        print("📝 Available stores:")
        # Try to find any stores
        cursor = db.get_connection().cursor()
        cursor.execute("SELECT store_id, name, city FROM stores LIMIT 10")
        all_stores = cursor.fetchall()
        for s in all_stores:
            print(f"  - {s}")
        return
    
    # Look for Cosmos or use first available store
    target_store = None
    for store in stores:
        store_dict = dict(store) if hasattr(store, '_asdict') else store
        print(f"Found store: {store_dict}")
        if 'osmos' in store_dict.get('name', '').lower():
            target_store = store_dict
            break
    
    if not target_store:
        # Use first available store
        target_store = dict(stores[0]) if hasattr(stores[0], '_asdict') else stores[0]
    
    store_id = target_store['store_id']
    store_name = target_store.get('name', 'Unknown')
    print(f"✅ Using store: {store_name} (ID: {store_id})")
    
    # Generate expiry dates (3-7 days from now)
    today = datetime.now()
    
    added_count = 0
    for title, description, original_price, discount_price, category, unit in PRODUCTS:
        # Random quantity between 5 and 50
        quantity = random.randint(5, 50)
        
        # Expiry date 3-7 days from now - use YYYY-MM-DD format for PostgreSQL
        days_ahead = random.randint(3, 7)
        expiry_date = (today + timedelta(days=days_ahead)).strftime("%Y-%m-%d")
        
        # Available times (now to end of day) - use YYYY-MM-DD HH:MM format
        available_from = today.strftime("%Y-%m-%d %H:%M")
        available_until = (today.replace(hour=23, minute=59)).strftime("%Y-%m-%d %H:%M")
        
        try:
            if use_postgres:
                # PostgreSQL version doesn't require available_from/until
                offer_id = db.add_offer(  # type: ignore
                    store_id=store_id,
                    title=title,
                    description=description,
                    original_price=original_price,
                    discount_price=discount_price,
                    quantity=quantity,
                    expiry_date=expiry_date,
                    unit=unit,
                    category=category
                    # photo_id not specified - will use default None
                )
            else:
                # SQLite version requires available_from/until
                offer_id = db.add_offer(  # type: ignore
                    store_id=store_id,
                    title=title,
                    description=description,
                    original_price=original_price,
                    discount_price=discount_price,
                    quantity=quantity,
                    available_from=available_from,
                    available_until=available_until,
                    expiry_date=expiry_date,
                    unit=unit,
                    category=category
                )
            added_count += 1
            print(f"✅ Added: {title} (ID: {offer_id})")
        except Exception as e:
            print(f"❌ Error adding {title}: {e}")
    
    print(f"\n🎉 Successfully added {added_count} products!")
    print(f"📊 Total products: {len(PRODUCTS)}")

if __name__ == "__main__":
    main()
