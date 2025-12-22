# План адаптации логики заказов и оплаты "как у Яндекс Лавки" под ваш проект

## Контекст и ограничения
- Самовывоз: оплата наличными, картой, Click, Payme.
- Доставка: наличных нет (только онлайн или по скриншоту, если нужно).
- Курьеры не свои: доставка силами заведений или через такси.

---

## 1. Единая модель заказов (бот, веб-клиент, партнер-панель)
Один источник правды: `unified_order_service`.

### Статусы заказа (order_status)
- `pending` — заказ создан, ждет подтверждения магазина.
- `preparing` — магазин принял и готовит.
- `ready` — заказ готов (внутренний статус, клиенту не слать).
- `delivering` — передан курьеру/такси (только доставка).
- `completed` — заказ завершен.
- `rejected` — магазин отклонил.
- `cancelled` — клиент отменил.

### Статусы оплаты (payment_status)
- `not_required` — наличные (только самовывоз).
- `awaiting_payment` — онлайн оплата еще не завершена (Click/Payme).
- `awaiting_proof` — оплата картой со скриншотом.
- `proof_submitted` — скрин загружен, ждем проверки админа.
- `confirmed` — оплата подтверждена.
- `rejected` — оплата отклонена.

---

## 2. Создание заказа (единый вход)
Все интерфейсы создают заказы только через `unified_order_service.create_order()`.

### Самовывоз
- `cash` -> `payment_status=not_required`, заказ создается сразу.
- `click/payme` -> `payment_status=awaiting_payment`, заказ создается сразу.
- `card` (скрин) -> `payment_status=awaiting_proof`, заказ создается сразу.

### Доставка (только онлайн)
- `click/payme` -> заказ создается с `awaiting_payment`.
- `card` (скрин) -> заказ создается только после скрина.
- `cash` запрещен.

---

## 3. Поток оплаты
### Click/Payme
1) Создаем заказ -> `awaiting_payment`.
2) Провайдер присылает webhook.
3) Обновляем `payment_status=confirmed`.
4) `order_status` остается `pending` (ждет подтверждения магазина).

### Карта со скриншотом
1) Клиент загружает скрин.
2) `payment_status=proof_submitted`.
3) Админ подтверждает -> `payment_status=confirmed`.

---

## 4. Переходы статусов заказа
- `pending -> preparing`: магазин принимает заказ.
- `pending -> rejected`: магазин отклоняет.
- `pending -> cancelled`: клиент отменяет до принятия.
- `preparing -> ready`: заказ готов.
- `ready -> delivering`: передача курьеру/такси (только доставка).
- `delivering -> completed`: заказ доставлен.
- `preparing/ready -> completed`: самовывоз получен (клиент подтвердил).

Запреты:
- Нельзя менять статус, если уже `completed/cancelled/rejected`.
- Нельзя `delivering` для самовывоза.
- Нельзя delivery с `payment_method=cash`.

---

## 5. Уведомления клиенту (минимум спама)
- Одно сообщение при создании.
- Редактируем его при статусах:
  - `preparing`
  - `delivering` (для доставки)
  - `completed`
  - `rejected/cancelled`
- `ready` не уведомляем.

---

## 6. Роли интерфейсов
### Бот
- Собирает данные (адрес, оплата, скрин).
- Вызывает unified-service.
- Не пишет напрямую в БД.

### Веб-приложение клиентов
- Повторяет логику бота.
- Не меняет статусы напрямую.

### Партнер-панель
- Управляет только `preparing`, `ready`, `delivering`, `completed`.
- Не управляет оплатой.

---

## 7. Куда привести логику (точки в коде)
- `handlers/customer/cart/checkout.py` -> только unified-service.
- `handlers/customer/orders/delivery.py` -> create order только после скрина.
- `app/api/webapp/routes_orders.py` -> общий поток, запрет cash delivery.
- `app/api/partner_panel_simple.py` -> смена статуса через unified-service.

---

## 8. Очистка/миграция
- Убрать прямое использование `db.create_order()`.
- Убрать/заморозить старую логику `order_service.py`.
- Проверить, что все статусы проходят через unified-service.

---

## 9. Минимальные тест-кейсы
- Самовывоз + наличные -> `pending`, `payment_status=not_required`.
- Самовывоз + Click/Payme -> `awaiting_payment` -> `confirmed`.
- Доставка + карта (скрин) -> `proof_submitted` -> `confirmed`.
- Доставка + Click/Payme -> `awaiting_payment` -> `confirmed`.
- Попытка доставки с `cash` -> ошибка.

---

## 10. Слоты доставки (если понадобятся)
Если появятся слоты, добавить:
- поле `delivery_slot` в заказ;
- UI выбора интервала;
- правила отмены/ограничения для слотов.
