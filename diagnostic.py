import sqlite3

conn = sqlite3.connect('fudly.db')
cursor = conn.cursor()

print("=" * 60)
print("🔍 ДИАГНОСТИКА БАЗЫ ДАННЫХ FUDLY BOT")
print("=" * 60)

# Проверка таблиц
cursor.execute('SELECT name FROM sqlite_master WHERE type="table"')
tables = cursor.fetchall()
print('\n📊 Таблицы в БД:')
for t in tables:
    print(f'  ✅ {t[0]}')

# Статистика
print('\n📦 Статистика:')
cursor.execute('SELECT COUNT(*) FROM users')
print(f'  Пользователей: {cursor.fetchone()[0]}')

cursor.execute('SELECT COUNT(*) FROM stores')
print(f'  Магазинов: {cursor.fetchone()[0]}')

cursor.execute('SELECT COUNT(*) FROM offers')
print(f'  Товаров: {cursor.fetchone()[0]}')

cursor.execute('SELECT COUNT(*) FROM bookings')
print(f'  Бронирований: {cursor.fetchone()[0]}')

cursor.execute('SELECT COUNT(*) FROM orders')
print(f'  Заказов доставки: {cursor.fetchone()[0]}')

# Карта платформы
cursor.execute('SELECT * FROM payment_settings')
payment = cursor.fetchone()
print(f'\n💳 Карта платформы:')
if payment:
    print(f'  Номер: {payment[1]}')
    print(f'  Держатель: {payment[2]}')
else:
    print('  ❌ Не настроена')

# Статус доставки для магазинов
cursor.execute('SELECT store_id, name, delivery_enabled, delivery_price, min_order_amount FROM stores')
stores = cursor.fetchall()
print('\n🚚 Статус доставки по магазинам:')
for s in stores:
    status = "✅ ВКЛЮЧЕНА" if s[2] else "❌ ВЫКЛЮЧЕНА"
    print(f'  {s[1]} (ID: {s[0]})')
    print(f'    Статус: {status}')
    print(f'    Стоимость доставки: {s[3]:,} сум')
    print(f'    Минимальная сумма заказа: {s[4]:,} сум')

# Проверка товаров с доставкой
cursor.execute('''
    SELECT o.offer_id, o.title, s.name, s.delivery_enabled 
    FROM offers o 
    JOIN stores s ON o.store_id = s.store_id 
    WHERE o.status = 'active'
''')
offers = cursor.fetchall()
print(f'\n🛍 Активные товары: {len(offers)}')
for o in offers:
    delivery_status = "✅ с доставкой" if o[3] else "❌ без доставки"
    print(f'  {o[1]} ({o[2]}) - {delivery_status}')

conn.close()

print("\n" + "=" * 60)
print("✅ Диагностика завершена")
print("=" * 60)
