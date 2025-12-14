# 📱 Mini App: Система заказов - Полная документация

## 🎯 Обзор

Mini App полностью синхронизирована с системой заказов бота через **UnifiedOrderService**.

### Двойная система заказов

В проекте существует **две таблицы** для заказов:

1. **`bookings`** - используется для заказов **САМОВЫВОЗ** (🏪 pickup)
2. **`orders`** - используется для заказов **ДОСТАВКА** (🚚 delivery)

**ВАЖНО**: Новая логика также создает заказы самовывоз в таблице `orders` с `order_type='pickup'`!

---

## 📊 Как определяется тип заказа

### В базе данных

#### Таблица `bookings`:
- **Всегда** самовывоз
- Имеет поля: `booking_id`, `offer_id`, `user_id`, `status`, `booking_code`
- `booking_code` - 6-символьный код для получения

#### Таблица `orders`:
- **Может быть** самовывоз ИЛИ доставка
- Поле `order_type` определяет тип:
  - `order_type = 'pickup'` → самовывоз 🏪
  - `order_type = 'delivery'` → доставка 🚚
- Имеет поля: `order_id`, `offer_id`, `user_id`, `order_status`, `order_type`, `delivery_address`, `pickup_code`

### В API Mini App

API возвращает поле `type` для каждого заказа:

```json
{
  "order_id": 19,
  "type": "booking",  // ← 'booking' для pickup, 'order' для delivery
  "order_type": "pickup",  // ← реальный тип из БД
  "status": "pending"
}
```

**Логика определения `type`:**

1. Если заказ из таблицы `bookings` → `type = "booking"`
2. Если заказ из таблицы `orders`:
   - Если `order_type = "pickup"` → `type = "booking"`
   - Если `order_type = "delivery"` → `type = "order"`

---

## 🔄 Жизненный цикл заказа

### Статусы заказа

```
PENDING     → Ожидает подтверждения партнера
    ↓
PREPARING   → Партнер подтвердил, готовит заказ
    ↓
READY       → Готов к получению/отправке
    ↓
DELIVERING  → В пути (только для delivery)
    ↓
COMPLETED   → Завершен
```

**Отклонение/отмена на любом этапе:**
```
ANY STATUS → REJECTED (партнер отклонил)
         → CANCELLED (клиент отменил)
```

### Статусы для разных типов

#### Самовывоз (pickup):
```
PENDING → PREPARING → COMPLETED
```
✅ **READY статус пропускается** - клиенту не отправляется уведомление

#### Доставка (delivery):
```
PENDING → PREPARING → READY → DELIVERING → COMPLETED
```
✅ Все статусы с уведомлениями

---

## 🔔 Уведомления клиентам

### Когда отправляются

| Статус | Pickup 🏪 | Delivery 🚚 | Сообщение клиенту |
|--------|-----------|-------------|-------------------|
| **PENDING** | ❌ | ❌ | - |
| **PREPARING** | ✅ | ✅ | "✅ Ваш заказ подтверждён! Магазин готовит заказ" |
| **READY** | ❌ | ✅ | "📦 Ваш заказ готов!" |
| **DELIVERING** | ❌ | ✅ | "🚚 Ваш заказ в пути!" |
| **COMPLETED** | ✅ | ✅ | "✅ Заказ завершён!" |
| **REJECTED** | ✅ | ✅ | "❌ Заказ отклонён" |
| **CANCELLED** | ✅ | ✅ | "❌ Заказ отменён" |

### Live-уведомления

Система использует **редактирование сообщений** для live-обновлений:

1. При первом уведомлении (PREPARING) - отправляется новое сообщение
2. При последующих статусах - **редактируется** это же сообщение
3. `message_id` сохраняется в БД: `customer_message_id`

**Механизм:**
```python
# Попытка 1: Редактировать caption (если было фото)
await bot.edit_message_caption(...)

# Попытка 2: Редактировать текст (если текстовое сообщение)
await bot.edit_message_text(...)

# Если не удалось - отправить новое
await bot.send_message(...)
```

---

## 🛠️ API Endpoints Mini App

### 1. Получить список заказов

```http
GET /api/partner/orders
Authorization: dev_8078537262
```

**Query параметры:**
- `status` (опционально) - фильтр по статусу: `pending`, `preparing`, `ready`, `delivering`, `completed`, `cancelled`, `all`

**Response:**
```json
[
  {
    "order_id": 19,
    "type": "booking",           // ← 'booking' или 'order'
    "offer_title": "йогурт",
    "quantity": 1,
    "price": 8000,
    "order_type": "pickup",      // ← 'pickup' или 'delivery'
    "status": "pending",
    "delivery_address": null,
    "created_at": "2025-12-13 17:15:40",
    "customer_name": "Шохрух",
    "customer_phone": "+998901234567"
  }
]
```

### 2. Подтвердить заказ

```http
POST /api/partner/orders/{order_id}/confirm
Authorization: dev_8078537262
```

**Body:** Нет (или `order_type` для legacy, но игнорируется)

**Логика:**
1. Ищет заказ в таблице `bookings`
2. Если не найден - ищет в таблице `orders`
3. Определяет `entity_type` из `order_type` в БД
4. Вызывает `UnifiedOrderService.confirm_order(order_id, entity_type)`
5. Клиент получает уведомление: "✅ Ваш заказ подтверждён!"

**Response:**
```json
{
  "order_id": 19,
  "status": "confirmed",
  "type": "booking"  // или "order"
}
```

### 3. Отменить заказ

```http
POST /api/partner/orders/{order_id}/cancel
Authorization: dev_8078537262
```

**Логика:** Аналогична confirm, вызывает `UnifiedOrderService.cancel_order()`

**Response:**
```json
{
  "order_id": 19,
  "status": "cancelled",
  "type": "booking"
}
```

### 4. Обновить статус заказа

```http
POST /api/partner/orders/{order_id}/status?status=ready
Authorization: dev_8078537262
```

**Query параметры:**
- `status` (обязательно) - новый статус: `ready`, `delivering`, `completed`
- `order_type` (опционально, игнорируется) - для legacy

**Логика по статусам:**

| Status | Вызов UnifiedOrderService | Уведомление клиенту |
|--------|---------------------------|---------------------|
| `ready` | `mark_ready(order_id, entity_type)` | Только для delivery |
| `delivering` | `start_delivery(order_id)` | ✅ Да |
| `completed` | `complete_order(order_id, entity_type)` | ✅ Да |

**Response:**
```json
{
  "order_id": 19,
  "status": "ready",
  "type": "booking"
}
```

---

## ⚙️ Внутренняя логика API

### Определение entity_type из БД

```python
# 1. Проверяем bookings
booking = db.get_booking(order_id)
if booking:
    entity_type = "booking"
    # работаем с booking

# 2. Проверяем orders
order = db.get_order(order_id)
if order:
    # Читаем order_type из БД
    db_order_type = order.get('order_type')  # 'pickup' или 'delivery'
    
    # Определяем entity_type
    entity_type = "booking" if db_order_type == "pickup" else "order"
    
    # Вызываем unified service с правильным типом
    await unified_service.confirm_order(order_id, entity_type)
```

### Почему важно использовать БД, а не параметр?

**ПРОБЛЕМА (старая версия):**
```javascript
// Frontend передавал
fetch(`/orders/${orderId}/confirm?order_type=order`)

// API использовал параметр напрямую
if (order_type == "booking") {
    // обработка booking
} else {
    // обработка order - НЕВЕРНО для pickup!
}
```

**РЕШЕНИЕ (новая версия):**
```python
# API игнорирует параметр и читает из БД
order = db.get_order(order_id)
db_order_type = order.get('order_type')  # Истина из БД!

entity_type = "booking" if db_order_type == "pickup" else "order"
await unified_service.confirm_order(order_id, entity_type)
```

---

## 🎨 Frontend Mini App

### Отображение заказов

```javascript
// Тип заказа определяется по `type` из API
function renderOrders(orders) {
  orders.forEach(order => {
    const icon = order.order_type === 'pickup' ? '🏪' : '🚚';
    const typeLabel = order.order_type === 'pickup' ? 'Самовывоз' : 'Доставка';
    
    // Кнопки зависят от статуса
    let buttons = '';
    if (order.status === 'pending') {
      buttons = `
        <button onclick="confirmOrder(${order.order_id}, '${order.type}')">
          ✅ Подтвердить
        </button>
        <button onclick="cancelOrder(${order.order_id}, '${order.type}')">
          ❌ Отменить
        </button>
      `;
    } else if (order.status === 'preparing') {
      buttons = `
        <button onclick="markReady(${order.order_id}, '${order.type}')">
          📦 Готов
        </button>
        <button onclick="cancelOrder(${order.order_id}, '${order.type}')">
          ❌ Отменить
        </button>
      `;
    } else if (order.status === 'ready' && order.order_type === 'delivery') {
      buttons = `
        <button onclick="markDelivering(${order.order_id}, '${order.type}')">
          🚚 В пути
        </button>
      `;
    }
    
    // Рендер...
  });
}
```

### API вызовы

```javascript
async function confirmOrder(orderId, orderType) {
  const response = await fetch(`${API_BASE_URL}/orders/${orderId}/confirm`, {
    method: 'POST',
    headers: {
      'Authorization': `dev_${SELLER_ID}`,
      'Content-Type': 'application/json'
    }
    // orderType не передаем - API сам определит из БД
  });
  
  if (response.ok) {
    Telegram.WebApp.showAlert('✅ Заказ подтверждён');
    loadOrders(); // Перезагрузить список
  }
}

async function markReady(orderId, orderType) {
  const response = await fetch(
    `${API_BASE_URL}/orders/${orderId}/status?status=ready`,
    {
      method: 'POST',
      headers: {
        'Authorization': `dev_${SELLER_ID}`
      }
    }
  );
  
  if (response.ok) {
    Telegram.WebApp.showAlert('📦 Заказ готов');
    loadOrders();
  }
}

async function markDelivering(orderId, orderType) {
  const response = await fetch(
    `${API_BASE_URL}/orders/${orderId}/status?status=delivering`,
    {
      method: 'POST',
      headers: {
        'Authorization': `dev_${SELLER_ID}`
      }
    }
  );
  
  if (response.ok) {
    Telegram.WebApp.showAlert('🚚 Заказ в пути');
    loadOrders();
  }
}
```

---

## 🔍 Дебаггинг

### Проверить тип заказа в БД

```sql
-- Проверить в orders
SELECT order_id, order_type, order_status, delivery_address 
FROM orders 
WHERE order_id = 19;

-- Если order_type = 'pickup' → должен обрабатываться как booking
-- Если order_type = 'delivery' → обрабатывается как order
```

### Логи UnifiedOrderService

При обработке заказа смотрите логи:

```
Order type from DB for order#19: pickup
Notification check for order#19: status=preparing, order_type=pickup, ...
📤 Sent NEW message for order#19
💾 Saved message_id=31961 for order#19
STATUS_UPDATE: order#19 -> preparing
```

**Ключевые моменты:**
- `Order type from DB` - реальный тип из БД
- `Skipping READY notification for pickup` - READY пропущен для самовывоза (норма)
- `Sent NEW message` или `Edited TEXT/CAPTION` - способ уведомления

---

## ✅ Чеклист: Заказ работает правильно

- [ ] Заказ самовывоз отображается с иконкой 🏪
- [ ] Заказ доставка отображается с иконкой 🚚
- [ ] При нажатии "Подтвердить" клиент получает уведомление
- [ ] Уведомление редактируется (не новое сообщение)
- [ ] Для pickup READY статус не отправляет уведомление
- [ ] Для delivery READY статус отправляет уведомление
- [ ] Кнопки меняются в зависимости от статуса
- [ ] После статуса `delivering` для pickup - ошибка (pickup не может быть delivering)

---

## 🚨 Частые проблемы

### 1. Клиент не получает уведомления

**Причина:** API использует неправильный `entity_type`

**Решение:** API теперь определяет `entity_type` из БД, а не из параметра

### 2. Заказ самовывоз показывается как доставка

**Причина:** В `list_orders` не проверялся `order_type` из БД

**Решение:** 
```python
entity_type = "booking" if order_type == "pickup" else "order"
```

### 3. Live-уведомления не работают

**Причина:** `message_id` не сохраняется или не передается

**Решение:** UnifiedOrderService автоматически сохраняет `message_id` при первом уведомлении

### 4. Уведомление READY для pickup

**Причина:** Логика не скипала READY для pickup

**Решение:** В UnifiedOrderService добавлена проверка:
```python
if order_type == "pickup" and target_status == OrderStatus.READY:
    should_notify = False
```

---

## 📚 Связанные файлы

- `app/api/partner_panel_simple.py` - API endpoints
- `app/services/unified_order_service.py` - Единая логика заказов
- `webapp/partner-panel/app.js` - Frontend Mini App
- `database_pg_module/mixins/bookings.py` - Таблица bookings
- `database_pg_module/mixins/orders.py` - Таблица orders
- `handlers/common/unified_order/seller.py` - Обработчики бота для партнера
- `handlers/common/unified_order/customer.py` - Обработчики бота для клиента

---

## 🎉 Итог

Mini App теперь **полностью синхронизирована** с ботом:

✅ Правильно определяет тип заказа из БД  
✅ Использует UnifiedOrderService для всех операций  
✅ Клиенты получают live-уведомления  
✅ READY статус правильно обрабатывается для pickup/delivery  
✅ Партнер видит корректные иконки и типы заказов  
