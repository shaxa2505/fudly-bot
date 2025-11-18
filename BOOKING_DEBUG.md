# 🔍 ПРОВЕРКА БРОНИРОВАНИЯ

## Проблема
Пользователь сообщает, что бронирование не работает - таблица bookings пустая.

## Что мы знаем
✅ **Доставка работает** - заказ с доставкой попадает в таблицу `orders`  
❓ **Бронирование** - должно попадать в таблицу `bookings`

## Два разных типа заказов

### 1. 🚚 Доставка (Delivery)
- Кнопка: **"Заказать с доставкой"**
- Handler: `handlers/orders.py`
- Таблица: **`orders`**
- Процесс:
  1. Пользователь вводит адрес
  2. Загружает чек оплаты
  3. Запись сохраняется в `orders`

### 2. 📦 Бронирование (Pickup/Booking)
- Кнопка: **"Забронировать"**
- Handler: `handlers/bookings.py`
- Таблица: **`bookings`**
- Процесс:
  1. Пользователь выбирает количество
  2. Система генерирует код брони
  3. Запись сохраняется в `bookings`

## Добавлено логирование

### В `handlers/bookings.py`:
```python
logger.info(f"📦 BOOKING: User {user_id} entered quantity: {quantity}")
logger.info(f"📦 BOOKING: offer_id from state: {offer_id}")
logger.info(f"📦 BOOKING: offer retrieved: {offer is not None}")
logger.info(f"📦 BOOKING: Calling create_booking_atomic...")
logger.info(f"📦 BOOKING: Result - ok={ok}, booking_id={booking_id}, code={code}")
```

### В `database_pg.py > create_booking_atomic()`:
```python
logger.info(f"🔵 create_booking_atomic START: offer_id={offer_id}, user_id={user_id}, quantity={quantity}")
logger.info(f"🔵 Checking offer status...")
logger.info(f"🔵 Offer check result: {offer}")
logger.info(f"🔵 Updating quantity: {current_quantity} -> {new_quantity}")
logger.info(f"🔵 Quantity updated successfully")
logger.info(f"🔵 Creating booking with code={booking_code}")
logger.info(f"🔵 Booking created: booking_id={booking_id}")
logger.info(f"✅ create_booking_atomic SUCCESS: booking_id={booking_id}, code={booking_code}")
```

## Как протестировать

### Локально (требует PostgreSQL)
1. Установить PostgreSQL локально или через Docker
2. Раскомментировать `DATABASE_URL` в `.env`
3. Запустить бота: `python bot.py`
4. Открыть бота в Telegram
5. Найти товар
6. Нажать **"Забронировать"** (не "Заказать с доставкой"!)
7. Ввести количество
8. Смотреть логи в консоли

### На Railway (Production)
1. Задеплоить изменения на Railway
2. Открыть Railway Logs
3. Открыть бота в Telegram
4. Найти товар
5. Нажать **"Забронировать"**
6. Ввести количество
7. Смотреть логи в Railway

## Что искать в логах

### ✅ Успешное бронирование:
```
📦 BOOKING: User 253445521 entered quantity: 2
📦 BOOKING: offer_id from state: 5
📦 BOOKING: offer retrieved: True
📦 BOOKING: Calling create_booking_atomic - offer_id=5, user_id=253445521, quantity=2
🔵 create_booking_atomic START: offer_id=5, user_id=253445521, quantity=2
🔵 Checking offer status...
🔵 Offer check result: (100, 'active')
🔵 Updating quantity: 100 -> 98
🔵 Quantity updated successfully
🔵 Creating booking with code=ABC123
🔵 Booking created: booking_id=1
✅ create_booking_atomic SUCCESS: booking_id=1, code=ABC123
📦 BOOKING: create_booking_atomic result - ok=True, booking_id=1, code=ABC123
✅ BOOKING SUCCESS: booking_id=1, code=ABC123
```

### ❌ Ошибка:
```
📦 BOOKING: User 253445521 entered quantity: 2
❌ Ошибка: товар не выбран
```
или
```
🔵 Offer check result: None
🔵 Offer check FAILED: not available
📦 BOOKING FAILED: ok=False, booking_id=None, code=None
```

## Возможные причины проблемы

1. **Пользователь нажимает "Заказать с доставкой" вместо "Забронировать"**
   - ✅ Решение: Использовать кнопку "Забронировать"

2. **FSM state теряется между шагами**
   - Возможно, если долго между действиями или бот перезапущен
   - ✅ Решение: Использовать Redis для хранения FSM states

3. **Ошибка в базе данных**
   - Логи покажут: `❌ Error creating booking atomically: ...`
   - ✅ Решение: Проверить структуру таблицы, constraints

4. **Таблица bookings не создана**
   - ✅ Решение: Запустить миграцию/инициализацию БД

## Следующие шаги

1. ✅ Добавлено логирование
2. ⏳ Задеплоить на Railway
3. ⏳ Протестировать кнопку "Забронировать"
4. ⏳ Проверить логи
5. ⏳ Если нужно - исправить найденную проблему
