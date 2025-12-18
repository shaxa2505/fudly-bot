# 🔍 ПОЛНЫЙ АНАЛИЗ СИСТЕМЫ ЗАКАЗОВ И УВЕДОМЛЕНИЙ

**Дата:** 18 декабря 2025  
**Версия:** v22.0  
**Цель:** Унификация и оптимизация системы управления заказами

---

## 📊 ТЕКУЩЕЕ СОСТОЯНИЕ СИСТЕМЫ

### 1. АРХИТЕКТУРА ЗАКАЗОВ

#### 1.1 База данных
```
📦 ТАБЛИЦЫ:
├── orders (основная таблица заказов)
│   ├── order_id (PK)
│   ├── user_id (FK → users)
│   ├── store_id (FK → stores)
│   ├── offer_id (FK → offers)
│   ├── order_type (pickup | delivery)
│   ├── order_status (pending, preparing, ready, delivering, completed, cancelled)
│   ├── cancel_reason (v22.0 NEW) ✅
│   ├── cancel_comment (v22.0 NEW) ✅
│   ├── delivery_address
│   └── total_price
│
└── bookings (старая таблица самовывоза)
    ├── booking_id (PK)
    ├── offer_id (FK → offers)
    ├── user_id (FK → users)
    ├── status (pending, confirmed, completed, cancelled)
    └── booking_code (код самовывоза)
```

**СТАТУСЫ ЗАКАЗОВ:**
- `pending` - ожидает подтверждения продавца
- `preparing` - продавец принял, готовит заказ
- `ready` - готов к выдаче/доставке
- `delivering` - курьер доставляет (только delivery)
- `completed` - завершён
- `cancelled` - отменён
- `rejected` - отклонён продавцом

#### 1.2 Сервисы

**UnifiedOrderService** (`app/services/unified_order_service.py`):
```python
✅ ФУНКЦИИ:
- create_order() - создание заказов (и pickup, и delivery)
- confirm_order() - подтверждение продавцом
- cancel_order() - отмена заказа
- mark_ready() - готов к выдаче
- start_delivery() - начало доставки
- complete_order() - завершение
- update_status() - обновление статуса с уведомлениями
```

**Особенности:**
- ✅ Единая точка входа для всех операций
- ✅ Автоматические уведомления клиентам
- ✅ Поддержка RU/UZ языков
- ✅ Прогресс-бар для отслеживания
- ⚠️ НО: продавец НЕ получает уведомления о новых заказах в реальном времени

---

### 2. КОМПОНЕНТЫ СИСТЕМЫ

#### 2.1 Backend API (FastAPI)

**Файл:** `app/api/partner_panel_simple.py`

**Endpoints:**
```python
GET  /api/partner/orders              # Список заказов партнёра ✅
POST /api/partner/orders/{id}/status  # Обновить статус ✅
POST /api/partner/orders/{id}/cancel  # Отменить заказ (v22.0) ✅
POST /api/partner/orders/{id}/confirm # Подтвердить заказ ✅
```

**ПРОБЛЕМЫ:**
1. ❌ **ДУБЛИРОВАНИЕ**: Есть 2 cancel endpoints (строка 652 и 976)
2. ⚠️ **НОТИФИКАЦИИ**: API не отправляет уведомления партнёру о новых заказах
3. ⚠️ **РАЗНЫЕ ТАБЛИЦЫ**: Работает и с `orders`, и с `bookings` → сложность
4. ⚠️ **entity_type путаница**: Используется "booking" для pickup, "order" для delivery

#### 2.2 Telegram Bot

**Файлы:**
- `handlers/seller/order_management.py` - старая система
- `handlers/seller/management/orders.py` - новая унифицированная система

**ПРОБЛЕМЫ:**
1. ❌ **ДВА ОБРАБОТЧИКА**: Старый и новый код сосуществуют
2. ⚠️ **РАЗНАЯ ЛОГИКА**: 
   - Старый: direct DB updates + ручные уведомления
   - Новый: использует UnifiedOrderService
3. ⚠️ **НЕТ ПУШ-УВЕДОМЛЕНИЙ**: Продавец должен сам зайти и проверить заказы

#### 2.3 Frontend (веб-панель)

**Файл:** `webapp/partner-panel/index.html`

**Функционал:**
```javascript
✅ loadOrders() - загрузка заказов
✅ renderOrders() - отображение с фильтрами (активные/завершенные/отменённые)
✅ updateOrderStatus() - обновление статуса
✅ cancelOrder() - отмена с причиной (v22.0)
✅ viewOrderDetails() - детали заказа в модалке
```

**ПРОБЛЕМЫ:**
1. ❌ **НЕТ LIVE-ОБНОВЛЕНИЯ**: Нужно вручную нажимать "Обновить"
2. ⚠️ **УВЕДОМЛЕНИЯ**: `notification-badge` есть, но не работает
3. ⚠️ **ФИЛЬТРЫ**: Работают локально (только фронт), не по API

---

## 🚨 КРИТИЧЕСКИЕ ПРОБЛЕМЫ

### ПРОБЛЕМА #1: Партнёр НЕ УЗНАЁТ о новых заказах

**Как сейчас:**
1. Клиент делает заказ через бота/веб-приложение
2. `UnifiedOrderService.create_order()` создаёт заказ в БД
3. ✅ Клиент получает уведомление
4. ❌ **ПАРТНЁР НЕ ПОЛУЧАЕТ УВЕДОМЛЕНИЕ**
5. Партнёр должен сам зайти в панель и проверить

**Почему так:**
```python
# app/services/unified_order_service.py:862
if notify_sellers and stores_orders:
    await self._notify_sellers_new_order(...)  # ← Вызывается!
```

Но метод `_notify_sellers_new_order()` отправляет уведомление через Telegram:
```python
# Строка ~200-300
await self.bot.send_message(store.owner_id, msg, ...)
```

**ПРОБЛЕМА:** Работает ТОЛЬКО если партнёр зарегистрирован в боте. Если он работает ТОЛЬКО через веб-панель → уведомления не приходят!

### ПРОБЛЕМА #2: Дублирование cancel endpoints

```python
# Строка 652
@router.post("/orders/{order_id}/cancel")
async def cancel_order(...):  # v22.0 - новый с причиной
    
# Строка 976  
@router.post("/orders/{order_id}/cancel")  
async def cancel_order_legacy(...):  # старый без причины
```

❌ **КОНФЛИКТ РОУТИНГА**: FastAPI возьмёт первый, второй никогда не вызовется!

### ПРОБЛЕМА #3: Несогласованность статусов

**В разных местах разные статусы:**

| Место | Статусы |
|-------|---------|
| UnifiedOrderService | pending, preparing, ready, delivering, completed, rejected, cancelled |
| Database orders | pending, confirmed, ready, delivering, completed, cancelled |
| Database bookings | pending, confirmed, completed, cancelled |
| Frontend | pending, new, preparing, ready, completed, cancelled |

⚠️ `confirmed` vs `preparing` - РАЗНЫЕ названия для ОДНОГО состояния!

### ПРОБЛЕМА #4: Разделение orders + bookings

**2 таблицы для одной сущности:**
- `bookings` - самовывоз (старая система)
- `orders` - и самовывоз, и доставка (новая система)

**Следствия:**
1. Каждый запрос дублируется (get_store_bookings + get_store_orders)
2. Разная структура данных (разные колонки)
3. Сложность поддержки кода
4. Риск рассинхронизации

---

## 💡 ПЛАН УНИФИКАЦИИ И ОПТИМИЗАЦИИ

### ЭТАП 1: Уведомления в реальном времени (ПРИОРИТЕТ #1)

#### 1.1 WebSocket для веб-панели

**Добавить:**
```python
# app/api/websocket.py (новый файл)
from fastapi import WebSocket
from typing import Dict, Set

class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[int, Set[WebSocket]] = {}
    
    async def connect(self, store_id: int, websocket: WebSocket):
        await websocket.accept()
        if store_id not in self.active_connections:
            self.active_connections[store_id] = set()
        self.active_connections[store_id].add(websocket)
    
    async def notify_new_order(self, store_id: int, order_data: dict):
        if store_id in self.active_connections:
            for ws in self.active_connections[store_id]:
                await ws.send_json({
                    "type": "new_order",
                    "data": order_data
                })
```

**Frontend (index.html):**
```javascript
// Подключение WebSocket
const ws = new WebSocket(`wss://${API_URL}/ws/partner/${storeId}`);

ws.onmessage = (event) => {
    const data = JSON.parse(event.data);
    if (data.type === 'new_order') {
        // Показать уведомление
        toast('🔔 Новый заказ #' + data.data.order_id, 'info');
        playSound();
        showNotificationBadge();
        
        // Автообновить список
        if (state.currentView === 'orders') {
            loadOrders();
        }
    }
};
```

#### 1.2 Push-уведомления через Telegram Bot

**Исправить:** Убедиться что `_notify_sellers_new_order()` вызывается ВСЕГДА:

```python
# app/services/unified_order_service.py
async def create_order(...):
    # ...
    
    # ВСЕГДА отправлять уведомления партнёрам
    if stores_orders:
        await self._notify_sellers_new_order(...)
    
    # + дополнительно WebSocket для веб-панели
    await self._notify_websocket_new_order(stores_orders)
```

### ЭТАП 2: Удалить дублирование

#### 2.1 Удалить дубликат cancel endpoint

**Действие:**
1. Удалить старый endpoint (строка 976)
2. Оставить только v22.0 с причиной (строка 652)
3. Обновить frontend для обязательного указания причины

#### 2.2 Унифицировать статусы

**Решение:** Использовать ТОЛЬКО статусы из `OrderStatus` класса:

```python
# database.py - добавить миграцию
UPDATE orders SET order_status = 'preparing' WHERE order_status = 'confirmed';
UPDATE bookings SET status = 'preparing' WHERE status = 'confirmed';

# Удалить поддержку 'confirmed' везде в коде
```

**Заменить:**
- `confirmed` → `preparing`
- `new` → `pending`

### ЭТАП 3: Миграция bookings → orders

**План:**
1. Скопировать все `bookings` в `orders` с `order_type='pickup'`
2. Обновить все ссылки в коде
3. Переименовать `bookings` → `bookings_archive`
4. Удалить методы `get_store_bookings()`, `update_booking_status()`

**SQL:**
```sql
-- Миграция данных
INSERT INTO orders (
    user_id, store_id, offer_id, quantity, 
    order_type, order_status, total_price, created_at
)
SELECT 
    user_id, 
    (SELECT store_id FROM offers WHERE offer_id = b.offer_id),
    offer_id,
    quantity,
    'pickup',
    CASE status 
        WHEN 'confirmed' THEN 'preparing'
        ELSE status 
    END,
    (SELECT discount_price * b.quantity FROM offers WHERE offer_id = b.offer_id),
    created_at
FROM bookings b
WHERE NOT EXISTS (
    SELECT 1 FROM orders o 
    WHERE o.user_id = b.user_id 
    AND o.offer_id = b.offer_id 
    AND o.created_at = b.created_at
);

-- Архивировать
ALTER TABLE bookings RENAME TO bookings_archive;
```

### ЭТАП 4: Live-обновления в веб-панели

**Polling (быстрое решение):**
```javascript
// Auto-refresh каждые 30 секунд
setInterval(() => {
    if (state.currentView === 'orders') {
        loadOrders();
    }
}, 30000);

// + Badge показывать количество новых
function updateNotificationBadge() {
    const newCount = state.orders.filter(o => 
        o.status === 'pending' && !o.viewed
    ).length;
    
    const badge = document.getElementById('notificationCount');
    if (newCount > 0) {
        badge.textContent = newCount;
        badge.style.display = 'flex';
    } else {
        badge.style.display = 'none';
    }
}
```

### ЭТАП 5: API оптимизация

#### 5.1 Один endpoint для списка заказов

**Сейчас:** `GET /orders` возвращает ВСЁ

**Лучше:** Добавить пагинацию и фильтры:
```python
@router.get("/orders")
async def list_orders(
    authorization: str = Header(None),
    status: Optional[str] = None,  # pending, preparing, ready, completed, cancelled
    order_type: Optional[str] = None,  # pickup, delivery
    page: int = 1,
    per_page: int = 20,
    sort_by: str = "created_at",
    sort_order: str = "desc"
):
    # Pagination
    offset = (page - 1) * per_page
    
    # Фильтрация в SQL
    query = """
        SELECT * FROM orders o
        JOIN users u ON o.user_id = u.user_id
        JOIN offers off ON o.offer_id = off.offer_id
        WHERE o.store_id = %s
    """
    params = [store_id]
    
    if status:
        query += " AND o.order_status = %s"
        params.append(status)
    
    if order_type:
        query += " AND o.order_type = %s"
        params.append(order_type)
    
    query += f" ORDER BY {sort_by} {sort_order} LIMIT %s OFFSET %s"
    params.extend([per_page, offset])
```

#### 5.2 Batch status updates

Если нужно обновить несколько заказов сразу:
```python
@router.post("/orders/batch/status")
async def batch_update_status(
    order_ids: list[int],
    new_status: str,
    authorization: str = Header(None)
):
    for order_id in order_ids:
        await unified_service.update_status(order_id, "order", new_status)
```

---

## 📋 ПРИОРИТЕТЫ РЕАЛИЗАЦИИ

### 🔴 КРИТИЧЕСКИЙ (Сделать первым)
1. **Уведомления партнёра о новых заказах** (WebSocket + Telegram)
2. **Удалить дубликат cancel endpoint**
3. **Унифицировать статусы** (confirmed → preparing)

### 🟡 ВЫСОКИЙ
4. **Миграция bookings → orders**
5. **Live-обновления в веб-панели** (polling/WebSocket)
6. **API пагинация и фильтры**

### 🟢 СРЕДНИЙ
7. Batch operations для массовых действий
8. История изменений статусов (audit log)
9. Аналитика времени обработки заказов

---

## 🎯 РЕЗУЛЬТАТ ПОСЛЕ УНИФИКАЦИИ

### ДО (сейчас):
```
❌ 2 таблицы (orders + bookings)
❌ 2 набора методов API
❌ Разные статусы в разных местах
❌ Нет уведомлений партнёру
❌ Нет live-обновлений
❌ Дублирование endpoints
```

### ПОСЛЕ:
```
✅ 1 таблица (orders)
✅ 1 унифицированный API
✅ Единые статусы везде
✅ Real-time уведомления (WebSocket + Telegram)
✅ Live-обновления в панели
✅ Чистый код без дублирования
✅ Быстрее работает
✅ Легче поддерживать
```

---

## 📝 ЧЕКЛИСТ РЕАЛИЗАЦИИ

- [ ] Создать WebSocket endpoint для real-time уведомлений
- [ ] Добавить ConnectionManager для управления соединениями
- [ ] Интегрировать WebSocket в frontend панели
- [ ] Исправить _notify_sellers_new_order() для гарантированной отправки
- [ ] Удалить дубликат POST /orders/{id}/cancel (строка 976)
- [ ] Создать миграцию SQL: confirmed → preparing
- [ ] Обновить весь код: заменить 'confirmed' на 'preparing'
- [ ] Создать миграцию bookings → orders
- [ ] Удалить методы работы с bookings
- [ ] Добавить пагинацию в GET /orders
- [ ] Добавить фильтры на уровне SQL
- [ ] Добавить auto-refresh в frontend (polling 30s)
- [ ] Обновить notification badge логику
- [ ] Написать тесты для новых endpoints
- [ ] Обновить документацию API

---

**Автор:** GitHub Copilot  
**Статус:** Готов к реализации  
