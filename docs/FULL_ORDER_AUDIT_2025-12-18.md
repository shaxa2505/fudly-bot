# Полный аудит подсистемы заказов (Fudly Bot)

**Дата:** 18 декабря 2025  
**Объект аудита:** всё, что создаёт/изменяет заказы и брони (Bot + Mini App + Partner Panel + DB слой)  
**Цель:** выявить расхождения в моделях данных, жизненном цикле, транзакционности, идемпотентности и безопасности; дать план исправлений.

---

## 0) Executive Summary

Подсистема заказов находится в **переходном состоянии**: параллельно существуют *bookings* (самовывоз) и *orders* (доставка + часть самовывоза), а «унифицированные» обработчики/сервис местами предполагают, что **всё уже в таблице `orders`**.

Главные риски сейчас:

### P0 (критично, влияет на деньги/склад/прод)
1) **Cart delivery = несколько строк `orders` вместо одного заказа**, но UX/оплата/админ‑пруф/уведомления написаны как будто `order_id` один. Итог: чек/статусы/уведомления привязываются к *первому* order_id, продавец/админ могут видеть неполный состав заказа.  
2) **UnifiedOrderService.update_status не поддерживает `booking` как сущность в таблице `bookings`** (всегда читает/обновляет `orders`). При включённом `handlers/common/unified_order_handlers.py` это делает `booking_confirm_*` / `booking_reject_*` потенциально нерабочими или обновляющими «чужую» запись `orders` с тем же id.  
3) **HTTP Mini App API без проверки Telegram initData** в `app/core/webhook_server.py`: можно создавать заказы/дергать статусы/грузить «чеки» на чужие `user_id`/`order_id` (IDOR + спам админу + списание остатков).  
4) **Пруф оплаты (фото) не сохраняется в БД в части потоков**, из‑за чего теряется «аудит‑трейл» и невозможна корректная пересылка пруфа продавцу из админ‑хендлера.

### P1 (высокий приоритет, ломает UX/поддержку/сопровождение)
- Дублирование хендлеров подтверждения оплаты админом (`handlers/customer/orders/delivery_admin.py` и `handlers/admin/delivery_orders.py`) с одинаковыми callback‑паттернами.  
- `handlers/seller/order_management.py` содержит вызовы UnifiedOrderService с **неверной сигнатурой** (TypeError при реальном вызове), плюс конфликтующие callback‑префиксы с unified обработчиками.  
- `app/api/orders.py` (Order Tracking API) содержит очевидные баги сериализации (например, `booking_code` не определён в ответе `/qr`, и чтение `booking_dict["id"]` не соответствует схеме `orders` с `order_id`).

---

## 1) Карта системы заказов (текущее состояние)

### 1.1 Каналы создания заказов

**Telegram Bot**
- Самовывоз «бронь» (одиночный товар): `handlers/bookings/customer.py` → `db.create_booking_atomic()` → таблица `bookings`
- Корзина самовывоз: `handlers/customer/cart/checkout.py` → `UnifiedOrderService.create_order(order_type="pickup")` → `db.create_cart_order()` → таблица `orders`
- Доставка (одиночный товар): `handlers/customer/orders/delivery.py` (создание после скрина) → `UnifiedOrderService.create_order(order_type="delivery")` **или** fallback `db.create_order()`
- Доставка (корзина): `handlers/customer/cart/payment.py` (после скрина) → `UnifiedOrderService.create_order(order_type="delivery")`

**Mini App / Web**
- Aiohttp API: `app/core/webhook_server.py` (`POST /api/v1/orders`, `POST /api/v1/orders/{order_id}/payment-proof`, `GET /api/v1/orders?user_id=...`)
- FastAPI WebApp API: `app/api/webapp/routes_orders.py` (`POST /orders`)
- Partner Panel API: `app/api/partner_panel_simple.py` (обновления статусов через UnifiedOrderService частично)

### 1.2 Каналы изменения статусов

- Унифицированные callback‑обработчики продавца: `handlers/common/unified_order/seller.py` (много legacy‑паттернов)
- Унифицированные callback‑обработчики клиента: `handlers/common/unified_order/customer.py` (`customer_received_*`, `booking_received_*`)
- Админ подтверждение/отклонение оплаты: минимум 2 реализации (`handlers/customer/orders/delivery_admin.py`, `handlers/admin/delivery_orders.py`)
- Прямые `db.update_order_status(...)` остаются в отдельных местах (см. `tests/test_status_update_guards.py` allowlist)

---

## 2) Модель данных и инварианты

### 2.1 Таблица `orders` (PostgreSQL)
Создаётся в `database_pg_module/schema.py`. Ключевые поля:  
`order_id`, `user_id`, `store_id`, `offer_id`, `quantity`, `total_price`, `order_status`, `payment_method`, `payment_status`, `payment_proof_photo_id`, `pickup_code`, `order_type`, `cart_items`, `is_cart_order`, `customer_message_id`, `seller_message_id`.

### 2.2 Таблица `bookings`
Создаётся в `database_pg_module/schema.py`. Используется `db.create_booking_atomic()` в `database_pg_module/mixins/bookings.py`.

### 2.3 Статусы (фактически используются в коде)
- «Унифицированные» статусы исполнения: `pending`, `preparing`, `ready`, `delivering`, `completed`, `rejected`, `cancelled` (`app/services/unified_order_service.py: OrderStatus`)
- «Непереехавшие/временные» статусы в коде и UI: `confirmed`, `awaiting_payment`, `awaiting_admin_confirmation`
- Миграция `migrations/v23_unify_statuses.sql` добавляет CHECK, который **НЕ включает awaiting_\*** → риск несовместимости при применении миграций.

---

## 3) Критические несоответствия (P0)

### P0.1 Cart delivery создаёт несколько `orders`, но поток оплаты/пруфа рассчитан на один `order_id`

**Где видно:**
- Создание через сервис: `app/services/unified_order_service.py` → `_create_delivery_orders()` вызывает `db.create_cart_order(...)`  
- DB метод: `database_pg_module/mixins/orders.py:create_cart_order()` вставляет **по одной строке `orders` на каждый item** и добавляет delivery_fee в `total_amount` на каждый item
- Поток пруфа в корзине: `handlers/customer/cart/payment.py` берёт `order_id = result.order_ids[0]`, обновляет оплату и уведомляет админа **только для первого id**

**Чем опасно:**
- Несостыковка суммы/состава заказа между клиентом, админом и продавцом
- Потенциально «висячие» order_id без пруфа и без дальнейшей обработки
- Склад/возвраты/отмена могут работать частично

**Рекомендуемое решение (выбрать одно и довести до конца):**
1) **Рекомендуемо:** «настоящий cart order» = 1 строка `orders` на магазин, `cart_items` JSONB + `is_cart_order=1`, delivery_fee один раз.  
2) Альтернатива: оставить по‑item ордера, но тогда UI/админ‑пруф/статусы должны работать с *множеством* `order_ids` (пруф/оплата/подтверждение/отмена по каждому) — это сильно усложняет UX.

---

### P0.2 UnifiedOrderService.update_status не поддерживает `booking` в таблице `bookings`

**Где видно:**
- `handlers/common/unified_order/seller.py` для `booking_confirm_*` определяет entity_type="booking" и вызывает `UnifiedOrderService.confirm_order(entity_id, "booking")`
- `app/services/unified_order_service.py:update_status()` всегда делает `entity = self.db.get_order(entity_id)` и `self.db.update_order_status(...)`, игнорируя `bookings`

**Чем опасно:**
- Подтверждение/отмена брони продавцом может не работать
- При совпадении id (booking_id == order_id) может обновиться «чужой» заказ

**Рекомендуемое решение:**
- Либо **доделать v24‑унификацию** и перестать использовать `bookings` в рантайме (все pickup‑заказы в `orders`)
- Либо **вернуть поддержку `booking`** в `UnifiedOrderService.update_status()` (ветка `if entity_type=="booking": get_booking/update_booking_status`, отдельные поля статуса и message_id)

---

### P0.3 Mini App HTTP API без аутентификации (IDOR)

**Где видно:**
- `app/core/webhook_server.py`:
  - `POST /api/v1/orders` принимает `user_id` из JSON без проверки подписи Telegram
  - `GET /api/v1/orders?user_id=...` отдаёт историю заказов по произвольному `user_id`
  - `POST /api/v1/orders/{order_id}/payment-proof` позволяет грузить фото по произвольному `order_id`

**Чем опасно:**
- Любой внешний клиент может списывать остатки, создавать фейковые заказы, спамить админа «чеками», читать чужие заказы

**Рекомендуемое решение:**
- Требовать `X-Telegram-Init-Data` и валидировать (как в `app/api/webapp/common.py`)
- Привязать `user_id` к initData.user.id и **игнорировать** `user_id` из body
- Для payment‑proof: проверять, что order.user_id == initData.user.id

---

### P0.4 Пруф оплаты не сохраняется в БД в части потоков

**Где видно:**
- `app/core/webhook_server.py:api_upload_payment_proof` получает file_id из Telegram, но не пишет его в `orders.payment_proof_photo_id`/`payment_status`
- `handlers/customer/payment_proof.py` отправляет фото админам, но не фиксирует `payment_proof_photo_id` в БД

**Чем опасно:**
- Нет «аудит‑следа» оплаты в базе
- Админ‑хендлеры/продавец не могут получить пруф из БД

**Рекомендуемое решение:**
- Везде, где получен `file_id`, выполнять `db.update_payment_status(order_id, "<proof_submitted|pending>", photo_id=file_id)` и/или `db.update_order_payment_proof(...)`.

---

## 4) Важные проблемы (P1)

### P1.1 Дублирование админ‑хендлеров подтверждения оплаты

**Где видно:**
- `handlers/customer/orders/delivery_admin.py` и `handlers/admin/delivery_orders.py` оба слушают `admin_confirm_payment_*` / `admin_reject_payment_*`

**Риск:**
- Сложность сопровождения, непредсказуемость (кто «победит» зависит от порядка router/include)

**Решение:**
- Оставить одну реализацию и удалить/отключить вторую (или сделать одну thin‑обвязку).

---

### P1.2 Legacy seller handler с неверными вызовами UnifiedOrderService

**Где видно:**
- `handlers/seller/order_management.py` вызывает:
  - `cancel_order(..., "Отменено продавцом", "Seller cancelled")` (сигнатура не совпадает)
  - `reject_order(order_id, "<reason>")` без `entity_type`

**Риск:**
- Runtime TypeError при реальном срабатывании callback‑ов (`reject_payment_`, `cancel_order_`)

**Решение:**
- Либо удалить конфликтующие callback‑префиксы (пусть всё ведёт unified handlers),
  либо привести вызовы к актуальным сигнатурам UnifiedOrderService.

---

### P1.3 Баги Order Tracking API

**Где видно:**
- `app/api/orders.py`:
  - `format_booking_to_order_status()` использует `booking_dict["id"]`, хотя в `orders` ключ обычно `order_id`
  - `/qr` возвращает поле `booking_code`, но переменная в функции называется иначе → 500

**Решение:**
- Привести сериализацию к реальной схеме `orders` и добавить минимальные тесты/health‑проверку.

---

## 5) Рекомендации и план работ

### 5.1 Целевое состояние (рекомендуемо)
1) **Одна сущность “Order”** в таблице `orders` для pickup+delivery  
2) **Один заказ на магазин**: для корзины хранить состав в `cart_items` + `is_cart_order=1`  
3) `order_status` = только статусы исполнения (pending/preparing/ready/delivering/...)  
4) `payment_status` = статусы оплаты (awaiting_proof/proof_submitted/confirmed/rejected/...)  
5) Все изменения статуса — через UnifiedOrderService (и guard‑тесты это enforce)

### 5.2 Quick wins (1–2 дня)
- Закрыть IDOR в `app/core/webhook_server.py` (initData + ownership checks)
- Везде сохранять payment proof в БД (webhook_server + payment_proof handler)
- Убрать/починить дубли админ‑хендлеров
- Починить очевидные баги `app/api/orders.py` (сериализация + `/qr`)

### 5.3 Среднесрочно (3–7 дней)
- Реализовать «cart order = 1 row» и мигрировать `handlers/customer/cart/*` и Mini App на него
- Определиться с `bookings`: либо миграция в `orders` (v24), либо полноценная поддержка в UnifiedOrderService
- Согласовать статусы с `migrations/v23_unify_statuses.sql` (или обновить CHECK‑constraint под реальную модель)

### 5.4 Минимальный набор тестов (после рефактора)
- Cart delivery: один order_id, корректные `cart_items`, delivery fee один раз, пруф сохраняется, админ подтверждает, продавец видит весь состав
- Booking confirm/reject: корректная таблица/статус/восстановление остатков
- API auth: нельзя получить/изменить чужой заказ без валидного initData

---

## 6) Приложение: ключевые точки входа (для ревизии)

- `handlers/bookings/customer.py` (создание брони самовывоза)
- `handlers/customer/cart/checkout.py`, `handlers/customer/cart/delivery.py`, `handlers/customer/cart/payment.py` (корзина)
- `handlers/customer/orders/delivery.py` (доставка одиночного товара)
- `handlers/common/unified_order/seller.py`, `handlers/common/unified_order/customer.py` (унифицированные callbacks)
- `app/services/unified_order_service.py` (core)
- `database_pg_module/mixins/orders.py`, `database_pg_module/mixins/bookings.py` (DB слой)
- `app/core/webhook_server.py` (Mini App aiohttp API)
- `app/api/webapp/routes_orders.py` и `app/api/orders.py` (FastAPI API)
- `app/api/partner_panel_simple.py` (Partner Panel)

