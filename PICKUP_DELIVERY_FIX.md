# ИСПРАВЛЕНИЕ: Путаница Самовывоз/Доставка

**Дата:** 10 декабря 2025  
**Проблема:** Заказы самовывоза отображаются как доставка

---

## 🐛 ПРОБЛЕМА

По скриншотам видно:
1. Заказ #85 создан пользователем "Gevfrygggghhh"
2. Продавец получил уведомление: **"🚚 Yetkazish"** (Доставка)
3. Клиент отправил чек об оплате
4. Но адрес доставки = имя пользователя "Gevfrygggghhh" (явно не адрес!)

**Вывод:** Пользователь выбрал **"Самовывоз"** (🏪), но система создала заказ с типом **"delivery"** (доставка).

---

## 🔍 ПРИЧИНА

### Путь заказа:

1. Пользователь нажимает "🏪 Olib ketish" (Самовывоз)
   - Callback: `pbook_method_{offer_id}_pickup`

2. В `handlers/bookings/customer.py` (строка 446):
   ```python
   @router.callback_query(F.data.startswith("pbook_method_"))
   async def pbook_select_method(...):
       method = parts[3]  # "pickup" or "delivery"
       await state.update_data(selected_delivery=method)  # ✅ Сохраняется правильно
   ```

3. При подтверждении (`pbook_confirm_`, строка 834):
   ```python
   if selected_delivery == "delivery":
       # Переход в delivery flow
       await state.update_data(
           offer_id=offer_id,
           # ... другие данные ...
           # ❌ НЕТ order_type!
       )
       await state.set_state(OrderDelivery.address)
   ```

4. В `handlers/customer/orders/delivery.py` заказы создаются:
   ```python
   # ❌ БЫЛО - всегда "delivery":
   result = await order_service.create_order(
       order_type="delivery",  # Hardcoded!
   ```

**Проблема:** `order_type` не передавался в FSM состояние, поэтому все заказы через `delivery.py` создавались как "delivery"!

---

## ✅ РЕШЕНИЕ

### 1. Добавлен `order_type` в FSM при переходе в delivery flow

**Файл:** `handlers/bookings/customer.py` (строка ~848)

```python
await state.update_data(
    offer_id=offer_id,
    store_id=store_id,
    quantity=quantity,
    # ... другие поля ...
    order_type="delivery",  # ✅ FIXED: Explicitly mark as delivery order
)
```

### 2. Использование `order_type` из FSM при создании заказа

**Файл:** `handlers/customer/orders/delivery.py`

#### В `dlv_use_saved_address` (строка ~491):
```python
# ✅ FIXED: Get order_type from FSM
order_type = data.get("order_type", "delivery")
result = await order_service.create_order(
    user_id=user_id,
    items=[order_item],
    order_type=order_type,  # Используем из FSM
    delivery_address=saved_address if order_type == "delivery" else None,
)
```

#### В `dlv_use_saved_address` fallback (строка ~507):
```python
order_type = data.get("order_type", "delivery")
order_id = db.create_order(
    order_type=order_type,
    delivery_address=saved_address if order_type == "delivery" else None,
    delivery_price=delivery_price if order_type == "delivery" else 0,
)
```

#### В `dlv_address_input` (строка ~712):
```python
order_type = data.get("order_type", "delivery")
result = await order_service.create_order(
    order_type=order_type,
    delivery_address=text if order_type == "delivery" else None,
)
```

#### В `dlv_address_input` fallback (строка ~730):
```python
order_type = data.get("order_type", "delivery")
order_id = db.create_order(
    order_type=order_type,
    delivery_address=text if order_type == "delivery" else None,
    delivery_price=delivery_price if order_type == "delivery" else 0,
)
```

---

## 📊 ИЗМЕНЕНИЯ

### До исправления:
```
Самовывоз → pbook_method_pickup → pbook_confirm → delivery flow → order_type="delivery" ❌
Доставка  → pbook_method_delivery → pbook_confirm → delivery flow → order_type="delivery" ✅
```

### После исправления:
```
Самовывоз → pbook_method_pickup → НЕ ДОЛЖЕН идти в delivery flow! ❌
Доставка  → pbook_method_delivery → delivery flow → order_type="delivery" ✅
```

---

## ⚠️ ВАЖНО!

**ПРОБЛЕМА ОСТАЕТСЯ:** Когда пользователь выбирает "Самовывоз" (pickup), НЕ должен запускаться `delivery flow`!

В `handlers/bookings/customer.py` строка 834:
```python
if selected_delivery == "delivery":
    # Delivery flow
    await state.set_state(OrderDelivery.address)
else:
    # Pickup - create booking directly  ✅ Правильно!
    await create_booking(callback.message, state, real_user_id=user_id)
```

**Но!** Если пользователь каким-то образом попадает в `delivery flow` при выборе самовывоза, теперь хотя бы `order_type` будет правильным.

---

## 🧪 ТЕСТИРОВАНИЕ

1. ✅ Выбрать товар
2. ✅ Нажать "🏪 Olib ketish" (Самовывоз)
3. ✅ Подтвердить - должен создаться **booking** (не order!)
4. ✅ Продавец должен получить: **"🏪 O'zi olib ketadi"** с кодом

5. ✅ Выбрать товар
6. ✅ Нажать "🚚 Yetkazish" (Доставка)
7. ✅ Ввести адрес
8. ✅ Подтвердить - должен создаться **order** с типом "delivery"
9. ✅ Продавец должен получить: **"🚚 Yetkazish"** с адресом

---

## 📝 СЛЕДУЮЩИЕ ШАГИ

1. Проверить почему пользователь попадает в `delivery flow` при выборе самовывоза
2. Добавить логирование для отладки flow
3. Убедиться что `create_booking()` работает правильно для самовывоза

**Исправление применено! 🎉**
