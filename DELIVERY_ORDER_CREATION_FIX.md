# Исправление: Заказ создается только после скрина чека

## Проблема

**Пользователь сообщил:** "доставка создается даже если не отправить скрин чека. это потому что и доставка создается как самовывоз помоему"

### Анализ

Действительно, заказ создавался **сразу после ввода адреса** (или выбора сохраненного адреса), **ДО отправки скриншота чека**.

#### Старый flow:
1. Пользователь вводит адрес → **ЗАКАЗ СОЗДАЕТСЯ** (stock decrement)
2. Переход к выбору способа оплаты
3. Выбор "Карта"
4. Отправка скрина чека → только прикрепляется к существующему заказу

**Проблема:** Если пользователь не отправлял скрин, заказ уже существовал в БД со статусом `pending`, товар уже был списан!

## Решение

### Новый flow:
1. Пользователь вводит адрес → сохраняется в FSM (заказ НЕ создается)
2. Переход к выбору способа оплаты
3. Выбор "Карта"
4. **Отправка скрина чека → ЗАКАЗ СОЗДАЕТСЯ** (stock decrement + attach photo)

Теперь заказ создается **ТОЛЬКО** когда пользователь отправил скриншот чека!

## Изменения в коде

### 1. `dlv_address_input()` - строка ~685

**Было:**
```python
# CREATE ORDER NOW (before payment selection) - prevents FSM data loss
order_id: int | None = None
# ... создание заказа через unified_order_service или db.create_order
await state.update_data(order_id=order_id)
```

**Стало:**
```python
# DON'T CREATE ORDER YET - wait for payment screenshot
# Order will be created in dlv_payment_proof after screenshot is received
logger.info(f"✅ User {user_id} saved address, waiting for payment screenshot")
```

### 2. `dlv_use_saved_address()` - строка ~455

**Было:**
```python
# CREATE ORDER NOW (same as in dlv_address_input)
order_id: int | None = None
# ... создание заказа
await state.update_data(order_id=order_id)
```

**Стало:**
```python
# DON'T CREATE ORDER YET - wait for payment screenshot
logger.info(f"✅ User {user_id} selected saved address, waiting for payment screenshot")
```

### 3. `dlv_payment_proof()` - строка ~830

**Было:**
```python
# Get order_id - ORDER ALREADY EXISTS
order_id = data.get("order_id")
# ... fallback поиск
# ... update_payment_status
```

**Стало:**
```python
# Get data from FSM
offer_id = data.get("offer_id")
store_id = data.get("store_id")
quantity = data.get("quantity", 1)
address = data.get("address", "")
delivery_price = data.get("delivery_price", 0)

# CREATE ORDER NOW (after screenshot received)
order_id: int | None = None
order_service = get_unified_order_service()

if order_service and hasattr(db, "create_cart_order"):
    # ... создание через unified_order_service
    
if not order_id:
    # Fallback to legacy single-order creation
    order_id = db.create_order(...)

# Update payment status with photo
db.update_payment_status(order_id, "pending", photo_id)
```

### 4. Удалены fallback-механизмы

Удалены:
- Функция `_find_recent_unpaid_order()` - больше не нужна
- Fallback логика в `dlv_pay_click()` - упрощено до редиректа на карту
- Fallback логика в `dlv_pay_card()` - удалена, так как order_id не существует до скрина

## Результат

✅ **Заказ создается ТОЛЬКО после отправки скрина чека**

✅ **Stock decrement происходит один раз** - в момент создания заказа

✅ **Нет "висящих" заказов** без payment proof

## Тестирование

Проверить:
1. ✅ Создать заказ с доставкой
2. ✅ Ввести адрес
3. ✅ Выбрать "Карта"
4. ❌ **НЕ отправлять скрин** → проверить БД - заказа НЕ должно быть
5. ✅ Отправить скрин чека → заказ должен создаться с прикрепленным скрином

## Связанные файлы

- `handlers/customer/orders/delivery.py` - основной файл с изменениями
- `ORDER_SYSTEM_FIXES.md` - предыдущие исправления системы заказов
- `PICKUP_DELIVERY_FIX.md` - исправление путаницы pickup/delivery в уведомлениях
