"""
Миграция БД: добавление функционала доставки
"""
import sqlite3
import os

DB_PATH = 'fudly.db'

def migrate():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    print("🔄 Начинаем миграцию БД для добавления доставки...")
    
    try:
        # 1. Добавляем поля в таблицу stores
        print("\n📦 Добавляем поля доставки в таблицу stores...")
        
        cursor.execute("PRAGMA table_info(stores)")
        columns = [col[1] for col in cursor.fetchall()]
        
        if 'delivery_enabled' not in columns:
            cursor.execute("ALTER TABLE stores ADD COLUMN delivery_enabled INTEGER DEFAULT 0")
            print("  ✅ Добавлено поле delivery_enabled")
        
        if 'delivery_price' not in columns:
            cursor.execute("ALTER TABLE stores ADD COLUMN delivery_price INTEGER DEFAULT 10000")
            print("  ✅ Добавлено поле delivery_price")
        
        if 'min_order_amount' not in columns:
            cursor.execute("ALTER TABLE stores ADD COLUMN min_order_amount INTEGER DEFAULT 20000")
            print("  ✅ Добавлено поле min_order_amount")
        
        # 2. Создаём таблицу orders (если не существует)
        print("\n📦 Создаём таблицу orders...")
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS orders (
                order_id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                store_id INTEGER NOT NULL,
                offer_id INTEGER NOT NULL,
                quantity INTEGER DEFAULT 1,
                
                -- Тип заказа
                order_type TEXT DEFAULT 'pickup',
                
                -- Данные доставки
                delivery_address TEXT,
                delivery_price INTEGER DEFAULT 0,
                
                -- Оплата
                payment_method TEXT,
                payment_status TEXT DEFAULT 'pending',
                payment_screenshot TEXT,
                
                -- Статусы
                order_status TEXT DEFAULT 'pending',
                
                -- Коды и суммы
                pickup_code TEXT,
                total_amount INTEGER,
                
                -- Временные метки
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                paid_at TIMESTAMP,
                confirmed_at TIMESTAMP,
                completed_at TIMESTAMP,
                cancelled_at TIMESTAMP,
                
                FOREIGN KEY (user_id) REFERENCES users(user_id),
                FOREIGN KEY (store_id) REFERENCES stores(store_id),
                FOREIGN KEY (offer_id) REFERENCES offers(offer_id)
            )
        """)
        print("  ✅ Таблица orders создана/существует")
        
        # 3. Создаём таблицу payment_settings (для карты платформы)
        print("\n💳 Создаём таблицу payment_settings...")
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS payment_settings (
                setting_id INTEGER PRIMARY KEY AUTOINCREMENT,
                card_number TEXT NOT NULL,
                card_holder_name TEXT NOT NULL,
                card_type TEXT DEFAULT 'uzcard',
                is_active INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        print("  ✅ Таблица payment_settings создана/существует")
        
        # 4. Добавляем дефолтную карту платформы (пример)
        cursor.execute("SELECT COUNT(*) FROM payment_settings WHERE is_active = 1")
        if cursor.fetchone()[0] == 0:
            cursor.execute("""
                INSERT INTO payment_settings (card_number, card_holder_name, card_type)
                VALUES ('8600 0000 0000 0000', 'FUDLY PLATFORM', 'uzcard')
            """)
            print("  ✅ Добавлена дефолтная карта платформы (измените через админ-панель)")
        
        # 5. Создаём индексы для производительности
        print("\n⚡ Создаём индексы...")
        
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_orders_user_id ON orders(user_id)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_orders_store_id ON orders(store_id)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(order_status)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_orders_created ON orders(created_at)
        """)
        print("  ✅ Индексы созданы")
        
        conn.commit()
        print("\n✅ Миграция успешно завершена!")
        
        # Выводим статистику
        cursor.execute("SELECT COUNT(*) FROM stores WHERE delivery_enabled = 1")
        delivery_stores = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM orders")
        orders_count = cursor.fetchone()[0]
        
        print(f"\n📊 Статистика:")
        print(f"  Магазинов с доставкой: {delivery_stores}")
        print(f"  Всего заказов: {orders_count}")
        
    except Exception as e:
        print(f"\n❌ Ошибка миграции: {e}")
        conn.rollback()
        raise
    finally:
        conn.close()

if __name__ == "__main__":
    if not os.path.exists(DB_PATH):
        print(f"❌ База данных {DB_PATH} не найдена!")
        exit(1)
    
    migrate()
    print("\n✅ Готово! Теперь можно запускать бота.")
