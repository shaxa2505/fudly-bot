# 🔄 API Synchronization Documentation - v20.0

## Обзор
Документация по унифицированному управлению заказами и товарами между тремя системами:
- 📱 Мини-приложение клиента (webapp)
- 🤖 Telegram бот
- 👨‍💼 Партнер-панель (partner-panel)

---

## 📊 Статусы заказов

### Единая схема статусов
```
pending → new → preparing → ready → completed
   ↓                                    ↓
cancelled ← ← ← ← ← ← ← ← ← ← ← ← ← ← ← ←
```

### Описание статусов
| Статус | Название | Описание | Действия |
|--------|----------|----------|----------|
| `pending` | Ожидает | Заказ создан, ожидает подтверждения | Принять → `preparing` / Отменить → `cancelled` |
| `new` | Новый | Заказ подтвержден системой | Принять → `preparing` / Отменить → `cancelled` |
| `preparing` | Готовится | Партнер готовит заказ | Готов → `ready` |
| `ready` | Готов | Заказ готов к выдаче/доставке | Выдан → `completed` |
| `completed` | Завершен | Заказ выполнен | Финальный статус |
| `cancelled` | Отменен | Заказ отменен | Финальный статус |

---

## 📦 Структура данных заказа

### Унифицированные поля (обязательные для всех систем)
```json
{
  "order_id": 123,                    // ID заказа
  "status": "pending",                // Статус из списка выше
  "offer_title": "Пицца Маргарита",   // Название товара
  "offer_photo_url": "https://...",   // Фото товара (обязательно)
  "photo_url": "https://...",         // Альтернативное поле фото
  "quantity": 2,                       // Количество
  "price": 1200.00,                   // Цена заказа
  "customer_name": "Иван",            // Имя клиента
  "customer_phone": "+79991234567",   // Телефон клиента
  "order_type": "pickup",             // pickup или delivery
  "delivery_address": "ул. Ленина 10", // Адрес (если delivery)
  "created_at": "2024-12-17T12:00:00Z" // Дата создания
}
```

### Критические правила
1. ✅ **Всегда отправляйте `offer_photo_url` и `photo_url`** - хотя бы одно должно быть заполнено
2. ✅ **`pending` и `new` обрабатываются одинаково** - обе имеют кнопки "Принять"/"Отменить"
3. ✅ **Используйте `order_id` или `id`** - система поддерживает оба
4. ✅ **Всегда передавайте `order_type`** - это влияет на отображение иконок

---

## 🎯 API Endpoints

### Партнер-панель
```javascript
// Получить все заказы
GET /api/partner/orders
Headers: { 'Authorization': 'Bearer {token}' }
Response: [{ ...order }, ...]

// Обновить статус
PUT /api/orders/{order_id}/status
Body: { "status": "preparing" }
Response: { "success": true, "order": {...} }

// Получить товары
GET /api/partner/products
Response: [{ ...product }, ...]
```

### Telegram бот
```python
# Уведомление партнера о новом заказе
await notify_seller(
    order_id=123,
    status='pending',
    offer_title='Пицца',
    photo_url='https://...',
    customer_name='Иван',
    price=1200
)

# Уведомление клиента об изменении статуса
await notify_customer(
    order_id=123,
    new_status='ready',
    message='Ваш заказ готов!'
)
```

---

## 🔧 Исправления в v20.0

### 1. ✅ Pending заказы теперь видны
**Проблема:** `pending` не попадали в "Активные"
**Решение:** Добавлено в фильтр активных заказов
```javascript
active: orders.filter(o => ['pending', 'new', 'preparing', 'ready'].includes(o.status))
```

### 2. ✅ Кнопки управления для pending
**Проблема:** Для `pending` не было кнопок
**Решение:** Добавлена обработка
```javascript
${order.status === 'pending' || order.status === 'new' ? `
    <button onclick="handleStatusUpdate(${orderId}, 'preparing', this)">✓ Принять</button>
    <button onclick="handleCancelOrder(${orderId}, this)">✕ Отменить</button>
` : ''}
```

### 3. ✅ Фото товаров в карточках заказов
**Проблема:** Фото не отображались
**Решение:** Добавлен блок `order-image`
```javascript
const photoUrl = order.offer_photo_url || order.photo_url;
${photoUrl ? `
    <div class="order-image">
        <img src="${photoUrl}" alt="${order.offer_title}" loading="lazy">
    </div>
` : ''}
```

### 4. ✅ Улучшенные стили статусов
**Проблема:** Агрессивный желтый цвет для ready/new
**Решение:** Мягкие градиенты с границами
```css
.status-pending {
    background: linear-gradient(135deg, #FFF9E6 0%, #FFF4D5 100%);
    color: #D68910;
    border: 1px solid #F9E79F;
}
```

### 5. ✅ Отмененные заказы
**Проблема:** "За пределами" - не отображались в табе
**Решение:** Проверка группировки
```javascript
cancelled: orders.filter(o => o.status === 'cancelled')
```

---

## 🚀 Рекомендации для бекенда

### Обязательные изменения в API
```python
# app/services/unified_order_service.py

async def create_order(...):
    """При создании заказа всегда устанавливайте статус 'pending'"""
    order = Order(
        status='pending',  # ← Важно!
        offer_photo_url=offer.photo_url,  # ← Обязательно
        ...
    )
    
    # Уведомления
    await notify_seller(order)  # Партнер получает push
    await notify_customer(order)  # Клиент получает подтверждение

async def update_order_status(order_id: int, new_status: str):
    """При изменении статуса уведомляем обе стороны"""
    order = await get_order(order_id)
    old_status = order.status
    order.status = new_status
    await db.commit()
    
    # Уведомления
    if new_status == 'ready':
        await notify_customer(order, "Ваш заказ готов! 🎉")
    if new_status == 'completed':
        await notify_customer(order, "Спасибо за заказ! ⭐")
```

### Проверка полей перед отправкой
```python
def serialize_order(order: Order) -> dict:
    """Всегда проверяйте наличие критических полей"""
    return {
        'order_id': order.id,
        'status': order.status or 'pending',
        'offer_photo_url': order.offer_photo_url or order.photo_url or '',
        'photo_url': order.photo_url or order.offer_photo_url or '',
        'offer_title': order.offer_title or 'Товар',
        'quantity': order.quantity or 1,
        'price': float(order.price) if order.price else 0.0,
        'customer_name': order.customer_name or 'Клиент',
        'customer_phone': order.customer_phone or '',
        'order_type': order.order_type or 'pickup',
        'delivery_address': order.delivery_address if order.order_type == 'delivery' else None,
        'created_at': order.created_at.isoformat()
    }
```

---

## 📱 Frontend Integration

### Партнер-панель (webapp/partner-panel/index.html)
```javascript
// Загрузка заказов с правильной обработкой
async function loadOrders() {
    const response = await fetch('/api/partner/orders', {
        headers: { 'Authorization': `Bearer ${state.token}` }
    });
    const orders = await response.json();
    
    // Убедитесь что все поля есть
    state.orders = orders.map(order => ({
        ...order,
        photo_url: order.offer_photo_url || order.photo_url || '',
        offer_title: order.offer_title || 'Товар',
        quantity: order.quantity || 1
    }));
    
    renderOrders();
}
```

### Telegram бот (handlers/)
```python
async def handle_new_order(message: Message, order_data: dict):
    """Обработка нового заказа от клиента"""
    order = await order_service.create_order(
        customer_id=message.from_user.id,
        offer_id=order_data['offer_id'],
        quantity=order_data['quantity'],
        order_type=order_data['type'],  # pickup или delivery
        delivery_address=order_data.get('address')
    )
    
    # Уведомление партнера (с фото!)
    await bot.send_photo(
        chat_id=seller_id,
        photo=order.offer_photo_url,
        caption=f"🔔 Новый заказ #{order.id}\n"
                f"📦 {order.offer_title}\n"
                f"👤 {order.customer_name}\n"
                f"💰 {order.price} ₽",
        reply_markup=get_order_keyboard(order.id)
    )
```

---

## ✅ Чеклист синхронизации

### Backend
- [ ] Поддержка статуса `pending`
- [ ] Всегда передавать `offer_photo_url` в ответах API
- [ ] Уведомления при смене статуса (бот + push)
- [ ] Валидация полей перед сохранением
- [ ] Логирование всех изменений статусов

### Partner Panel
- [x] Отображение pending заказов
- [x] Кнопки управления для pending
- [x] Фото товаров в карточках
- [x] Улучшенные стили статусов
- [x] Правильная группировка cancelled

### Telegram Bot
- [ ] Отправка `pending` статуса при создании
- [ ] Push уведомления партнеру
- [ ] Отправка фото в уведомлениях
- [ ] Кнопки управления статусом
- [ ] Обновление статуса в реальном времени

### Testing
- [ ] Создание заказа → статус `pending`
- [ ] Pending виден в "Активные"
- [ ] Кнопки работают для pending/new
- [ ] Фото загружаются корректно
- [ ] Отмененные в правильном табе
- [ ] Уведомления приходят обеим сторонам

---

## 🎨 UI/UX Guidelines

### Карточка заказа (обязательная структура)
```html
<div class="order-card" data-order-id="123" data-status="pending">
    <!-- Фото (если есть) -->
    <div class="order-image">
        <img src="..." alt="..." loading="lazy">
    </div>
    
    <!-- Заголовок -->
    <div class="order-header">
        <div class="order-id">#123</div>
        <div class="order-status status-pending">Ожидает</div>
    </div>
    
    <!-- Мета -->
    <div class="order-meta">
        <span>🏃 Самовывоз</span>
        <span>Иван</span>
    </div>
    
    <!-- Футер -->
    <div class="order-footer">
        <span class="order-time">10:30</span>
        <span class="order-total">1 200 ₽</span>
    </div>
    
    <!-- Кнопки (для активных) -->
    <div class="order-actions">
        <button class="btn btn-success">✓ Принять</button>
        <button class="btn btn-danger">✕ Отменить</button>
    </div>
</div>
```

### Цветовая схема статусов
| Статус | Фон | Текст | Бордер |
|--------|-----|-------|--------|
| pending | #FFF9E6 → #FFF4D5 | #D68910 | #F9E79F |
| new | #FFF3E0 → #FFE0B2 | #E65100 | #FFB74D |
| preparing | #E3F2FD → #BBDEFB | #0D47A1 | #64B5F6 |
| ready | #E8F5E9 → #C8E6C9 | #1B5E20 | #81C784 |
| completed | #F5F5F5 → #EEEEEE | #616161 | #BDBDBD |
| cancelled | #FFEBEE → #FFCDD2 | #B71C1C | #EF5350 |

---

## 🔧 Debugging

### Проверка API ответа
```bash
# Получить заказы
curl -H "Authorization: Bearer YOUR_TOKEN" \
     https://your-api.com/api/partner/orders

# Проверьте что есть:
# - offer_photo_url или photo_url
# - status (один из: pending, new, preparing, ready, completed, cancelled)
# - order_type (pickup или delivery)
```

### Логирование в консоли
```javascript
// В partner-panel/index.html добавьте:
console.log('Orders loaded:', state.orders);
console.log('Grouped:', groupOrdersByStatus(state.orders));

// Проверьте:
// - active содержит pending
// - У всех заказов есть photo_url
// - Статусы корректные
```

---

## 📞 Support

При проблемах проверьте:
1. ✅ Бекенд возвращает все обязательные поля
2. ✅ Фото доступны по URL (не 404)
3. ✅ Статусы из допустимого списка
4. ✅ Token авторизации валиден
5. ✅ Уведомления настроены в боте

**Версия:** v20.0  
**Дата:** 2024-12-17  
**Автор:** GitHub Copilot
