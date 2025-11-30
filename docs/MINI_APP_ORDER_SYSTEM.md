# Полная система заказов в Mini App

## Текущий Flow (упрощённый)

```
[Mini App]                    [Bot/Backend]                [Продавец]
    │                              │                            │
    ├─────── POST /orders ─────────►                           │
    │                              │                            │
    │                         create_booking()                  │
    │                              │                            │
    │                              ├──── Уведомление ───────────►
    │                              │   [✅ Принять] [❌ Отклонить]
    │                              │                            │
    │                              │◄──── Нажимает кнопку ──────┤
    │                              │                            │
    │                         update_status()                   │
    │                              │                            │
    │◄───── (нет уведомления) ─────│                            │
```

## Полный Flow (как в боте)

```
[Mini App]                    [Bot/Backend]                [Продавец]        [Покупатель]
    │                              │                            │                 │
    ├─────── POST /orders ─────────►                           │                 │
    │  {order_type, address, ...}  │                            │                 │
    │                              │                            │                 │
    │                         create_booking()                  │                 │
    │                         save delivery_type                │                 │
    │                              │                            │                 │
    │                              ├──── Уведомление ───────────►                 │
    │                              │  📦 Товар: X               │                 │
    │                              │  🚚 Тип: Доставка          │                 │
    │                              │  📍 Адрес: Y               │                 │
    │                              │  📱 Тел: Z                 │                 │
    │                              │  [✅ Принять] [❌ Отклон.]  │                 │
    │                              │                            │                 │
    │                              │◄──── Нажимает ✅ ───────────┤                 │
    │                              │                            │                 │
    │                         status = 'confirmed'              │                 │
    │                              │                            │                 │
    │                              ├─────────────────────────────────────────────►│
    │                              │   🎉 Ваш заказ принят!     │                 │
    │                              │   🎫 Код: ABC123           │                 │
    │                              │   + QR код (для самовывоза)│                 │
    │                              │                            │                 │
    │                              ├──── Продавцу ──────────────►                 │
    │                              │  [✅ Выдано] [❌ Отменить]  │                 │
    │                              │                            │                 │
    │  (Открывает страницу заказов)│                            │                 │
    │◄────── GET /orders ──────────┤                            │                 │
    │    status: 'confirmed'       │                            │                 │
    │                              │                            │                 │
    │                              │◄──── Нажимает Выдано ──────┤                 │
    │                              │                            │                 │
    │                         status = 'completed'              │                 │
    │                              │                            │                 │
    │                              ├─────────────────────────────────────────────►│
    │                              │   ✅ Заказ выполнен!       │                 │
    │                              │   🌟 Оцените продавца      │                 │
```

## Что нужно добавить

### 1. В базу данных (bookings table):

```sql
ALTER TABLE bookings ADD COLUMN delivery_type VARCHAR(20) DEFAULT 'pickup';
ALTER TABLE bookings ADD COLUMN delivery_address TEXT;
ALTER TABLE bookings ADD COLUMN customer_phone VARCHAR(20);
ALTER TABLE bookings ADD COLUMN delivery_cost INTEGER DEFAULT 0;
```

### 2. Обновить create_booking_atomic в database.py:

```python
def create_booking_atomic(
    self,
    offer_id: int,
    user_id: int,
    quantity: int,
    pickup_time: str = None,
    pickup_address: str = None,
    delivery_type: str = "pickup",      # NEW
    delivery_address: str = None,        # NEW
    customer_phone: str = None,          # NEW
    delivery_cost: int = 0,              # NEW
):
    # ... save all fields
```

### 3. Обновить webhook_server.py для сохранения типа доставки:

```python
result = db.create_booking_atomic(
    offer_id=int(offer_id),
    user_id=int(user_id),
    quantity=int(quantity),
    delivery_type=delivery_type,        # NEW
    delivery_address=address,            # NEW
    customer_phone=phone,                # NEW
    delivery_cost=delivery_fee,          # NEW
)
```

### 4. Добавить WebSocket/Polling для real-time обновлений в Mini App:

```javascript
// В Mini App - polling каждые 30 секунд
useEffect(() => {
  const interval = setInterval(async () => {
    if (orderId) {
      const status = await api.getOrderStatus(orderId)
      if (status.status !== currentStatus) {
        setCurrentStatus(status.status)
        showNotification(status)
      }
    }
  }, 30000)
  return () => clearInterval(interval)
}, [orderId])
```

### 5. Push уведомления через Telegram:

Покупатель уже получает уведомления в боте. Для Mini App можно:

1. **Использовать Telegram WebApp.sendData()** - но только при закрытии приложения
2. **Polling статуса** - как описано выше
3. **Telegram Bot уведомления** - уже работает!

## Текущее состояние реализации

| Функция | Статус | Где |
|---------|--------|-----|
| Создание заказа | ✅ Работает | CartPage.jsx → webhook_server.py |
| Тип доставки | ✅ Исправлено | webhook_server.py читает order_type |
| Уведомление продавцу | ✅ Работает | webhook_server.py → bot.send_message |
| Кнопки принять/отклонить | ✅ Работает | bot.py order_accept:/order_reject: |
| Обновление статуса | ✅ Исправлено | bot.py → db.update_booking_status |
| Уведомление покупателю | ✅ Работает | bot.py → send_message to customer |
| История заказов | ✅ Работает | YanaPage.jsx → GET /orders |
| Real-time обновления | ❌ Нет | Нужен polling или WebSocket |
| QR код для самовывоза | ⚠️ Частично | Отправляется в бот, не в Mini App |

## Рекомендации

1. **Добавить страницу отслеживания заказа** с polling статуса
2. **Сохранять delivery_type в БД** для корректной истории
3. **Push уведомления** - использовать Telegram Bot для всех уведомлений
4. **Добавить кнопку "Связаться с продавцом"** в Mini App

## Пример улучшенного OrderTrackingPage

```jsx
function OrderTrackingPage({ orderId }) {
  const [order, setOrder] = useState(null)

  useEffect(() => {
    const fetchStatus = async () => {
      const data = await api.getOrderStatus(orderId)
      setOrder(data)
    }

    fetchStatus()
    const interval = setInterval(fetchStatus, 30000) // каждые 30 сек

    return () => clearInterval(interval)
  }, [orderId])

  return (
    <div className="order-tracking">
      <StatusTimeline status={order?.status} />

      {order?.status === 'confirmed' && order?.delivery_type === 'pickup' && (
        <QRCode value={order.booking_code} />
      )}

      {order?.status === 'confirmed' && order?.delivery_type === 'delivery' && (
        <DeliveryInfo address={order.delivery_address} />
      )}

      <ContactSeller storePhone={order?.store_phone} />
    </div>
  )
}
```
