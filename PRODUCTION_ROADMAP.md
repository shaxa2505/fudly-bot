# 🚀 Fudly Production Roadmap

## ✅ ЗАВЕРШЕНО (15.12.2024)

### Phase 1: Критические исправления
- ✅ Admin verification для delivery orders
- ✅ Payment proof upload flow
- ✅ Убран обязательный upload чека (теперь можно загрузить позже)
- ✅ История заказов (YanaPage с delivery + booking orders)
- ✅ Улучшен payment flow (показ реквизитов карты)

---

## 📋 ROADMAP ДЛЯ ПОЛНОЦЕННОЙ РАБОТЫ

### 🔴 Priority 1: КРИТИЧНО для запуска (1-2 дня)

#### 1.1 Система уведомлений ⚡
**Проблема:** Клиенты не знают статус заказа в реальном времени

**Решение опция A - Telegram Notifications (РЕКОМЕНДОВАНО)**
```javascript
// webapp: использовать Telegram WebApp API
if (window.Telegram?.WebApp) {
  window.Telegram.WebApp.enableClosingConfirmation()

  // Bot отправляет уведомления напрямую пользователю
  await bot.sendMessage(userId, "✅ Ваш заказ #123 подтвержден!")
}
```

**Решение опция B - Polling**
```javascript
// Периодически проверять статус
useEffect(() => {
  const interval = setInterval(() => {
    if (activeOrder) {
      api.getOrderStatus(activeOrder.id)
        .then(status => setOrderStatus(status))
    }
  }, 10000) // каждые 10 секунд
  return () => clearInterval(interval)
}, [activeOrder])
```

**Что делать:**
- [ ] Bot: Добавить уведомления при смене статуса заказа
  - Заказ подтвержден продавцом
  - Заказ готов к выдаче
  - Заказ отменен
- [ ] WebApp: Добавить polling статуса на странице заказа
- [ ] WebApp: Показывать badge с количеством активных заказов

**Файлы для изменения:**
- `handlers/seller/management/orders.py` - добавить уведомления при confirm/reject
- `webapp/src/pages/YanaPage.jsx` - добавить polling
- `webapp/src/components/BottomNav.jsx` - badge активных заказов

---

#### 1.2 Детали заказа и управление 📦
**Проблема:** Нельзя посмотреть детали или отменить заказ

**Что добавить:**
- [ ] Страница деталей заказа (или модальное окно)
  - Полная информация о заказе
  - Список items с фото
  - Timeline статусов
  - Информация о продавце
  - Кнопка "Отменить заказ" (если pending)
  - Кнопка "Загрузить чек" (если awaiting_payment)
- [ ] Возможность отмены заказа
- [ ] Подтверждение получения (для pickup orders)

**Файлы:**
- Создать `webapp/src/pages/OrderDetailPage.jsx`
- Или добавить в `webapp/src/pages/OrderTrackingPage.jsx`
- Backend: `app/core/webhook_server.py` - endpoint для отмены

---

#### 1.3 Upload чека из истории заказов 📸
**Проблема:** Сейчас невозможно загрузить чек после создания заказа

**Решение:**
```jsx
// YanaPage.jsx - добавить кнопку для awaiting_payment заказов
{order.status === 'awaiting_payment' && (
  <button onClick={() => navigate(`/order/${order.id}/upload-proof`)}>
    📸 Загрузить чек
  </button>
)}
```

**Что делать:**
- [ ] Добавить кнопку "Загрузить чек" для awaiting_payment заказов
- [ ] Создать отдельную страницу или модалку для upload
- [ ] Использовать Telegram WebApp API для camera access:
```javascript
window.Telegram.WebApp.requestWriteAccess()
// Или открыть камеру через бота command
bot.sendMessage(userId, "Отправьте фото чека в ответ на это сообщение")
```

---

### 🟡 Priority 2: ВАЖНО для UX (3-5 дней)

#### 2.1 Push-уведомления и badges 🔔
- [ ] WebApp badge на иконке Buyurtmalarim (количество активных)
- [ ] Browser push notifications (если поддерживается)
- [ ] Vibration feedback при получении уведомления

#### 2.2 Поиск и фильтры 🔍
- [ ] Поиск по названию продукта
- [ ] Фильтр по категориям
- [ ] Фильтр по цене
- [ ] Сортировка (цена, скидка, расстояние)

#### 2.3 Избранное и рекомендации ⭐
- [ ] Добавление в избранное (уже есть backend)
- [ ] Показ избранного на главной
- [ ] "Вам может понравиться" на основе истории

#### 2.4 Отзывы и рейтинги ⭐⭐⭐⭐⭐
- [ ] Возможность оценить заказ после получения
- [ ] Отзывы о продавцах
- [ ] Показ рейтинга на карточках товаров

---

### 🟢 Priority 3: УЛУЧШЕНИЯ (неделя)

#### 3.1 Онбординг и помощь 📚
- [ ] Welcome tour для новых пользователей
- [ ] FAQ страница
- [ ] Чат поддержки (Telegram direct link)
- [ ] Видео-гайды

#### 3.2 Промо и маркетинг 🎁
- [ ] Промокоды
- [ ] Реферальная система
- [ ] Cashback/бонусы
- [ ] Special offers banner

#### 3.3 Аналитика 📊
- [ ] Отслеживание популярных товаров
- [ ] Конверсия воронки (просмотр → корзина → заказ)
- [ ] A/B тестирование
- [ ] Метрики по продавцам

#### 3.4 Оптимизация производительности ⚡
- [ ] Lazy loading изображений
- [ ] Кэширование данных (IndexedDB)
- [ ] Prefetching популярных страниц
- [ ] Compression оптимизация

---

## 🛠 ТЕХНИЧЕСКАЯ РЕАЛИЗАЦИЯ

### Система уведомлений (детально)

**Вариант 1: Telegram Bot Notifications (ЛУЧШИЙ для MVP)**

```python
# handlers/seller/management/orders.py
@router.callback_query(F.data.startswith("order_confirm_"))
async def confirm_order_callback(callback: CallbackQuery):
    order_id = int(callback.data.split("_")[-1])

    # Existing logic...
    db.update_order_status(order_id, "confirmed")

    # ✅ NEW: Notify customer
    order = db.get_order(order_id)
    customer_id = order.user_id

    await bot.send_message(
        chat_id=customer_id,
        text=(
            "✅ <b>Buyurtmangiz tasdiqlandi!</b>\n\n"
            f"📦 Buyurtma #{order_id}\n"
            f"🏪 {order.store_name}\n\n"
            "Tayyor bo'lganda xabar beramiz! 🎉"
        ),
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(
                text="📦 Buyurtmalarimni ko'rish",
                web_app=WebAppInfo(url=f"{WEBAPP_URL}/profile")
            )]
        ])
    )
```

**Вариант 2: WebApp Polling**

```javascript
// webapp/src/hooks/useOrderPolling.js
export function useOrderPolling(orderId, interval = 10000) {
  const [status, setStatus] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    if (!orderId) return

    const fetchStatus = async () => {
      try {
        const data = await api.getOrderStatus(orderId)
        setStatus(data)
      } catch (error) {
        console.error('Polling error:', error)
      } finally {
        setLoading(false)
      }
    }

    fetchStatus() // Initial fetch
    const timer = setInterval(fetchStatus, interval)

    return () => clearInterval(timer)
  }, [orderId, interval])

  return { status, loading }
}

// Usage in OrderTrackingPage.jsx
const { status } = useOrderPolling(orderId, 10000)
```

**Вариант 3: WebSocket (для будущего)**

```javascript
// webapp/src/utils/websocket.js
const ws = new WebSocket('wss://your-server.com/ws')

ws.onmessage = (event) => {
  const data = JSON.parse(event.data)

  if (data.type === 'ORDER_UPDATE') {
    // Update UI
    showNotification(`Заказ #${data.orderId} - ${data.status}`)
  }
}
```

---

### Upload чека из истории

**Решение через Telegram Bot Command**

```python
# bot.py - добавить handler
@router.message(Command("upload_proof"))
async def upload_proof_command(message: Message, state: FSMContext):
    """Start payment proof upload flow"""
    await message.answer(
        "Отправьте фото чека оплаты для вашего заказа.\n"
        "Или нажмите /cancel для отмены."
    )
    await state.set_state(UploadProofStates.waiting_for_photo)

@router.message(UploadProofStates.waiting_for_photo, F.photo)
async def receive_proof_photo(message: Message, state: FSMContext):
    # Get order_id from state
    data = await state.get_data()
    order_id = data.get("order_id")

    # Upload proof
    photo = message.photo[-1]
    # Send to admin...

    await message.answer("✅ Chek yuklandi! Admin tekshiradi.")
    await state.clear()
```

**WebApp Integration**

```jsx
// YanaPage.jsx
const handleUploadProof = (orderId) => {
  // Option 1: Open bot
  window.Telegram.WebApp.openTelegramLink(
    `https://t.me/your_bot?start=upload_${orderId}`
  )

  // Option 2: Use deep link
  window.location.href = `tg://resolve?domain=your_bot&start=upload_${orderId}`
}

<button onClick={() => handleUploadProof(order.id)}>
  📸 Загрузить чек через бота
</button>
```

---

## 📅 TIMELINE

| Неделя | Задачи | Статус |
|--------|--------|--------|
| Week 1 | ✅ Admin verification, Payment flow | DONE |
| Week 2 | 🔔 Notifications, 📦 Order details, 📸 Upload fix | IN PROGRESS |
| Week 3 | ⭐ Reviews, 🔍 Search, 📊 Analytics | PLANNED |
| Week 4 | 🎁 Promo, 📚 Help, ⚡ Optimization | PLANNED |

---

## 🎯 MVP CHECKLIST (для запуска)

- [x] Создание заказа
- [x] История заказов
- [x] Payment flow
- [ ] **Уведомления о статусе** ⚠️ КРИТИЧНО
- [ ] **Детали заказа** ⚠️ КРИТИЧНО
- [ ] **Upload чека из истории** ⚠️ КРИТИЧНО
- [ ] Отмена заказа
- [ ] FAQ/Support
- [ ] Тестирование E2E

**Готовность к запуску: 70%**

После реализации 3 критичных пунктов → **100% готово к бета-запуску** 🚀

---

_Документ обновлен: 15.12.2024_
