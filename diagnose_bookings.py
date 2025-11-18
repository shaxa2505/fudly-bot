"""
Диагностика: Почему не работает бронирование
Проверяем структуру таблицы bookings и пытаемся создать тестовую запись
"""
import os
import sys

# Используем Railway DATABASE_URL
DATABASE_URL = 'postgresql://postgres:baScPxSSKfaecKWNtCLvwpUzbpclLGSt@interchange.proxy.rlwy.net:52990/railway'

try:
    import psycopg2
    from psycopg2.extras import RealDictCursor
    
    print("🔍 Подключаемся к Railway PostgreSQL...")
    conn = psycopg2.connect(DATABASE_URL)
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    print("✅ Подключение успешно!\n")
    
    # 1. Проверяем структуру таблицы bookings
    print("=" * 60)
    print("📋 СТРУКТУРА ТАБЛИЦЫ BOOKINGS:")
    print("=" * 60)
    cursor.execute("""
        SELECT column_name, data_type, is_nullable, column_default
        FROM information_schema.columns
        WHERE table_name = 'bookings'
        ORDER BY ordinal_position
    """)
    columns = cursor.fetchall()
    
    if not columns:
        print("❌ Таблица bookings не найдена!")
        sys.exit(1)
    
    for col in columns:
        nullable = "NULL" if col['is_nullable'] == 'YES' else "NOT NULL"
        default = f"DEFAULT {col['column_default']}" if col['column_default'] else ""
        print(f"  • {col['column_name']:20} {col['data_type']:15} {nullable:10} {default}")
    
    # 2. Проверяем текущие записи
    print("\n" + "=" * 60)
    print("📊 ТЕКУЩИЕ ЗАПИСИ В BOOKINGS:")
    print("=" * 60)
    cursor.execute("SELECT COUNT(*) as count FROM bookings")
    count = cursor.fetchone()['count']
    print(f"Всего записей: {count}")
    
    if count > 0:
        cursor.execute("SELECT * FROM bookings ORDER BY created_at DESC LIMIT 5")
        bookings = cursor.fetchall()
        print("\nПоследние 5 записей:")
        for b in bookings:
            print(f"\n  Booking ID: {b.get('booking_id')}")
            print(f"  Offer ID: {b.get('offer_id')}")
            print(f"  User ID: {b.get('user_id')}")
            print(f"  Code: {b.get('booking_code')}")
            print(f"  Status: {b.get('status')}")
            print(f"  Quantity: {b.get('quantity')}")
            print(f"  Created: {b.get('created_at')}")
    
    # 3. Ищем активный оффер для теста
    print("\n" + "=" * 60)
    print("🔍 ПОИСК АКТИВНОГО ОФФЕРА ДЛЯ ТЕСТА:")
    print("=" * 60)
    cursor.execute("""
        SELECT offer_id, title, quantity, discount_price, status
        FROM offers
        WHERE status = 'active' AND quantity > 0
        ORDER BY created_at DESC
        LIMIT 1
    """)
    offer = cursor.fetchone()
    
    if not offer:
        print("❌ Нет активных офферов с quantity > 0")
        cursor.close()
        conn.close()
        sys.exit(1)
    
    print(f"✅ Найден оффер:")
    print(f"  ID: {offer['offer_id']}")
    print(f"  Название: {offer['title']}")
    print(f"  Количество: {offer['quantity']}")
    print(f"  Цена: {offer['discount_price']}")
    print(f"  Статус: {offer['status']}")
    
    # 4. Пробуем создать тестовое бронирование
    print("\n" + "=" * 60)
    print("🧪 ТЕСТ: СОЗДАНИЕ БРОНИРОВАНИЯ")
    print("=" * 60)
    
    test_user_id = 253445521  # Ваш user_id
    test_code = "TEST99"
    test_quantity = 1
    
    try:
        conn.autocommit = False  # Начинаем транзакцию
        
        cursor.execute("""
            INSERT INTO bookings (offer_id, user_id, booking_code, status, quantity)
            VALUES (%s, %s, %s, 'pending', %s)
            RETURNING booking_id, created_at
        """, (offer['offer_id'], test_user_id, test_code, test_quantity))
        
        result = cursor.fetchone()
        booking_id = result['booking_id']
        created_at = result['created_at']
        
        print(f"✅ Тестовое бронирование создано!")
        print(f"  Booking ID: {booking_id}")
        print(f"  Created at: {created_at}")
        
        # Проверяем что оно действительно в базе
        cursor.execute("SELECT * FROM bookings WHERE booking_id = %s", (booking_id,))
        check = cursor.fetchone()
        
        if check:
            print(f"\n✅ Проверка: запись найдена в базе")
            print(f"  Данные: {dict(check)}")
        else:
            print(f"\n❌ Проверка: запись НЕ найдена в базе!")
        
        # Удаляем тестовую запись
        cursor.execute("DELETE FROM bookings WHERE booking_id = %s", (booking_id,))
        conn.commit()
        print(f"\n🧹 Тестовая запись удалена (COMMIT выполнен)")
        
    except Exception as e:
        conn.rollback()
        print(f"❌ Ошибка при создании бронирования:")
        print(f"  {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
    
    # 5. Проверяем constraints и indexes
    print("\n" + "=" * 60)
    print("🔒 CONSTRAINTS И INDEXES:")
    print("=" * 60)
    
    cursor.execute("""
        SELECT conname, contype, pg_get_constraintdef(oid)
        FROM pg_constraint
        WHERE conrelid = 'bookings'::regclass
    """)
    constraints = cursor.fetchall()
    
    if constraints:
        for c in constraints:
            contype_map = {'p': 'PRIMARY KEY', 'f': 'FOREIGN KEY', 'u': 'UNIQUE', 'c': 'CHECK'}
            contype = contype_map.get(c['contype'], c['contype'])
            print(f"  • {c['conname']}: {contype}")
            print(f"    {c['pg_get_constraintdef']}")
    else:
        print("  Нет constraints")
    
    cursor.close()
    conn.close()
    
    print("\n" + "=" * 60)
    print("✅ Диагностика завершена")
    print("=" * 60)
    
except ImportError:
    print("❌ psycopg2 не установлен. Установите: pip install psycopg2-binary")
except Exception as e:
    print(f"❌ Ошибка: {type(e).__name__}: {e}")
    import traceback
    traceback.print_exc()
