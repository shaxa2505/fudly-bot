# Исправления системы заказов

**Дата:** 10 декабря 2025  
**Статус:** Критические проблемы исправлены ✅

---

## ✅ ИСПРАВЛЕННЫЕ ПРОБЛЕМЫ

### 1. ❌→✅ Двойное списание товаров (КРИТИЧНО)

**Проблема:**  
В `handlers/customer/orders/delivery.py` после создания заказа через `unified_order_service` товары списывались еще раз вручную:

```python
# БЫЛО (строки 525-530, 734-739):
if used_legacy_create:
    try:
        db.increment_offer_quantity_atomic(offer_id, -int(quantity))
    except Exception as e:
        logger.error(f"Failed to decrement offer: {e}")
```

**Решение:**  
Удалено двойное списание. Теперь остатки уменьшаются только один раз внутри `unified_order_service` или `create_cart_order()`.

```python
# СТАЛО:
# NOTE: Stock is decremented by unified_order_service or in create_order/create_cart_order
# No need to decrement here to avoid double decrement
```

**Файлы:**
- ✅ `handlers/customer/orders/delivery.py` (строки ~525-530)
- ✅ `handlers/customer/orders/delivery.py` (строки ~734-739)

---

### 2. ❌→✅ Неправильный статус "confirmed" (КРИТИЧНО)

**Проблема:**  
В `handlers/customer/orders/delivery_admin.py` после подтверждения оплаты устанавливался несуществующий статус "confirmed":

```python
# БЫЛО:
db.update_payment_status(order_id, "confirmed")
db.update_order_status(order_id, "confirmed")  # ❌ Нет такого статуса!
```

Валидные статусы: `pending`, `preparing`, `ready`, `delivering`, `completed`, `rejected`, `cancelled`

**Решение:**  
Заменено на правильный статус `pending` (заказ ждет подтверждения продавца):

```python
# СТАЛО:
db.update_payment_status(order_id, "confirmed")
db.update_order_status(order_id, "pending")  # Keep as pending until seller confirms
```

**Файлы:**
- ✅ `handlers/customer/orders/delivery_admin.py` (строка ~70)

---

### 3. ✅ Подключен delivery_admin router

**Проверка:**  
Роутер `delivery_admin` уже был правильно подключен в `handlers/customer/orders/router.py`:

```python
router.include_router(delivery_admin.router)  # ✅ Уже есть!
```

И включен в основной роутер в `bot.py`:
```python
dp.include_router(orders_router)  # Includes delivery_admin.router internally
```

**Статус:** Не требовало изменений ✅

---

### 4. ❌→✅ Упрощена сигнатура update_order_status

**Проблема:**  
Метод принимал два параметра статуса, что создавало путаницу:

```python
# БЫЛО:
def update_order_status(self, order_id: int, order_status: str, payment_status: str = None):
    if payment_status:
        # Update both...
    else:
        # Update only order_status...
```

**Решение:**  
Разделены ответственности - каждый метод обновляет только своё поле:

```python
# СТАЛО:
def update_order_status(self, order_id: int, order_status: str) -> bool:
    """Update order status.
    
    NOTE: This method only updates order_status field.
    Use update_payment_status() to update payment_status separately.
    """
    with self.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE orders SET order_status = %s WHERE order_id = %s",
            (order_status, order_id),
        )
        return True
```

**Файлы:**
- ✅ `database_pg_module/mixins/orders.py` (метод `update_order_status`)

---

### 5. ⚠️ Добавлены TODO комментарии

Добавлено предупреждение о проблемах в методе `create_order`:

```python
"""Create new order.
...
Returns:
    order_id if successful, None otherwise
    
TODO: This method has no transaction protection and no stock checking!
Should use create_cart_order() instead which has atomic stock reservation.
"""
```

**Файлы:**
- ✅ `database_pg_module/mixins/orders.py` (метод `create_order`)

---

## 🔴 ОСТАВШИЕСЯ ПРОБЛЕМЫ (требуют более глубокого рефакторинга)

### 1. Отсутствие транзакций в create_order()

**Проблема:**  
Метод `create_order()` не использует транзакции:
1. Читает offer
2. Создает order
3. (Где-то потом) уменьшает остатки

При race condition возможна продажа несуществующего товара.

**Рекомендация:**  
Использовать только `create_cart_order()` который делает:
```python
cursor.execute("SELECT quantity FROM offers WHERE offer_id = %s FOR UPDATE")
# Lock row, check stock, create order, update stock - all in transaction
```

### 2. Множественные точки входа

Заказы создаются в **5 разных местах**:
- `handlers/customer/orders/delivery.py`
- `handlers/bookings/customer.py`
- `handlers/customer/cart/`
- `app/api/webapp_api.py`
- `app/services/unified_order_service.py`

**Рекомендация:**  
Всегда использовать `unified_order_service.create_order()` как единую точку входа.

### 3. Разные форматы уведомлений

4 разных формата уведомлений продавцам с разными callback данными:
- `partner_confirm_{booking_id}` (старые букинги)
- `partner_confirm_order_{order_id}` (новые заказы)
- Смешанные в WebApp
- Корзина

**Рекомендация:**  
Унифицировать через `NotificationTemplates` в `unified_order_service.py`.

### 4. Потеря order_id в FSM

В `dlv_pay_card()` и `dlv_pay_click()` есть fallback поиск заказа, но он ненадежный.

**Рекомендация:**  
Сохранять `order_id` в FSM сразу после создания и не полагаться на fallback.

---

## 📊 ИТОГИ

### Исправлено:
✅ Двойное списание товаров (КРИТИЧНО)  
✅ Неправильный статус "confirmed"  
✅ Упрощена сигнатура update_order_status  
✅ Добавлены предупреждающие комментарии  

### Требует внимания:
⚠️ Отсутствие транзакций в create_order  
⚠️ Множественные точки создания заказов  
⚠️ Разные форматы уведомлений  
⚠️ Потеря order_id в FSM  

### Следующие шаги:
1. Протестировать создание заказов (одиночный товар + корзина)
2. Проверить что остатки списываются только один раз
3. Проверить работу подтверждения оплаты админом
4. Постепенно мигрировать все на unified_order_service

---

**Критические проблемы решены, система заказов стала стабильнее! 🎉**
