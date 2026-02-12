# Глубокий аудит: Заказы и оплата (Bot + WebApp)

Дата: 2026-02-12

## Область
- Telegram Bot: создание/подтверждение оплат, pre-checkout, post-payment обработка.
- WebApp API: создание заказа, получение заказов, отмены, статусы.
- Payment API: генерация ссылок (`/api/v1/payment/*`), Click callbacks, merchant webhooks.
- Исключено: Partner Panel (по вашему решению).

## Краткий вывод
- Безопасность заказа/оплаты: **ниже целевого уровня** из-за нескольких критичных разрывов в консистентности потоков.
- Масштабирование: **частично готово** (PostgreSQL + пул + idempotency есть), но текущая split-архитектура (`aiohttp + FastAPI`) создает операционные риски и расхождение поведения по режимам запуска.

---

## Критические проблемы

### C1. Telegram pre-checkout подтверждается без валидации, а при ошибке post-payment пользователю отправляется "успех"
- Доказательства:
  - `handlers/customer/payments.py:224` — безусловный `pre_checkout_query.answer(ok=True)`.
  - `handlers/customer/payments.py:255` — сумма читается, но не валидируется против заказа.
  - `handlers/customer/payments.py:618` — в `except` отправляется сообщение об успешной оплате даже при ошибке обработки.
- Риск:
  - Возможен случай "деньги списались / заказ не подтвержден".
  - Ложное подтверждение пользователю ухудшает обнаружение инцидента и повышает финансовый риск.
- Приоритет: **немедленно исправить**.

### C2. WebApp-оплата зависит от режима запуска (polling vs webhook), в polling FastAPI нет `/payment/providers` и `/payment/create`
- Доказательства:
  - Фронт ожидает endpoints: `webapp/src/api/client.js:630`, `webapp/src/api/client.js:644`.
  - Эти endpoints зарегистрированы в webhook-сервере: `app/core/webhook_server.py:430`, `app/core/webhook_server.py:433`.
  - FastAPI app их не включает: `app/api/api_server.py:351`, `app/api/api_server.py:356`.
  - В polling запускается standalone FastAPI: `bot.py:790`, `bot.py:793`.
- Риск:
  - Заказы создаются, но онлайн-оплата может отваливаться в зависимости от режима/окружения.
  - Непредсказуемое поведение между staging/prod.
- Приоритет: **немедленно исправить**.

---

## Высокие проблемы

### H1. Два разных `GET /api/v1/orders` с разным контрактом ответа
- Доказательства:
  - WebApp router: `app/api/webapp/routes_orders.py:476` (возвращает объект с `orders/bookings/limit/offset/...`, см. `app/api/webapp/routes_orders.py:883`).
  - Orders router: `app/api/orders.py:490` (возвращает список заказов, см. `app/api/orders.py:650`).
  - Оба роутера подключены: `app/api/api_server.py:352`, `app/api/api_server.py:353`.
- Риск:
  - Хрупкий API-контракт; изменение порядка include_router ломает фронт без изменения кода фронта.

### H2. API-путь загрузки чека отключен, но bot-поток proof оплаты все еще активен
- Доказательства:
  - API возвращает 410: `app/api/orders.py:653`, `app/api/orders.py:662`; `app/core/webhook_orders_routes.py:678`, `app/core/webhook_orders_routes.py:683`.
  - Bot flow для чеков активен: `handlers/customer/payment_proof.py:73`, `handlers/customer/payment_proof.py:212`.
  - Use-cases proof/review продолжают жить: `app/application/orders/submit_payment_proof.py:18`, `app/application/orders/confirm_payment.py:18`, `app/application/orders/reject_payment.py:10`.
- Риск:
  - Две несовместимые модели оплаты (Click-only в API и legacy-proof в bot).
  - Повышенный риск регрессий и ошибок в статусах оплаты.

### H3. Несогласованность статусов оплаты `rejected` vs `payment_rejected` (frontend/backend)
- Доказательства:
  - Нормализация в фронте переводит `payment_rejected -> rejected`: `webapp/src/utils/orderStatus.js:36`.
  - Но `OrderDetailsPage` обрабатывает `payment_rejected`, не `rejected`: `webapp/src/pages/OrderDetailsPage.jsx:601`.
  - `OrdersPage` также завязан на `payment_rejected`: `webapp/src/pages/OrdersPage.jsx:25`.
- Риск:
  - Неправильные бейджи/экраны действий, потеря корректной UX-логики в отклоненных оплатах.

### H4. `/api/v1/payment/create` в aiohttp проверяет сырые статусы и может отклонять legacy-заказы
- Доказательства:
  - Проверка без `PaymentStatus.normalize`: `app/core/webhook_payment_routes.py:149`, `app/core/webhook_payment_routes.py:163`.
  - Разрешены только `awaiting_payment` или пусто.
- Риск:
  - Заказы с legacy `pending`/переходными статусами могут блокироваться от повторной оплаты.

### H5. Утечки внутренних ошибок в ответы API
- Доказательства:
  - `app/api/webapp/routes_orders.py:470` (`detail=str(e)`).
  - `app/api/orders.py:546` (`detail=str(e)`).
  - `app/core/webhook_payment_routes.py:204` (`{"error": str(e)}`).
- Риск:
  - Информационная утечка (SQL/внутренние сообщения), упрощение разведки для атакующего.

---

## Средние риски (безопасность + масштабирование)

### M1. Денежные поля в заказе как `REAL/FLOAT`
- Доказательства:
  - `database_pg_module/schema.py:426` (`total_price REAL`).
  - `migrations_alembic/models.py:273` (`total_price = Column(Float, ...)`).
- Риск:
  - Ошибки округления, проблемы сверки платежей и отчетности.

### M2. Нет лимитов на payment endpoints в aiohttp-слое
- Доказательства:
  - Регистрация платежных роутов без limiter: `app/core/webhook_server.py:430`, `app/core/webhook_server.py:433`.
  - Хендлеры `app/core/webhook_payment_routes.py:21`, `app/core/webhook_payment_routes.py:42` без встроенного throttle.
- Риск:
  - Abuse/DoS через массовую генерацию payment links.

### M3. Idempotency-таблица без TTL/cleanup
- Доказательства:
  - Создание таблицы: `app/core/idempotency.py:48`.
  - Нет удаления старых записей (только insert/update paths).
- Риск:
  - Рост таблицы, деградация скорости create-order при долгой эксплуатации.

### M4. Тяжелые read-path с N+1 в legacy orders history
- Доказательства:
  - Цикл по booking + отдельные обращения к offer/store: `app/api/auth.py:412`, `app/api/auth.py:433`, `app/api/auth.py:447`.
- Риск:
  - Рост latency и нагрузки БД на больших объемах истории.

---

## Оценка масштабируемости (заказ/оплата)
- Что уже хорошо:
  - Есть idempotency для create-order.
  - Есть пул PostgreSQL (`DB_MIN_CONN/DB_MAX_CONN`) и атомарный cart-order для PG.
  - Есть нормализация статусов оплаты в домене.
- Что ограничивает масштаб:
  - Разделение API-поверхности между FastAPI и aiohttp.
  - Разная функциональность по режимам запуска (webhook/polling).
  - Часть read-путей остается синхронной/legacy и с N+1-паттернами.

Итог: на **среднюю нагрузку** система пойдет, но для устойчивого роста нужен быстрый техдолг-спринт по унификации order/payment surface.

---

## План исправлений (по порядку)

1. Исправить C1:
- В `pre_checkout` валидировать `invoice_payload`, order status, ownership, сумму.
- В `successful_payment` убрать "успех" в fallback; вместо этого отправлять "payment received, processing" + алерт в админ-канал.

2. Исправить C2:
- Вынести `/api/v1/payment/providers` и `/api/v1/payment/create` в FastAPI router (единый контракт).
- Оставить aiohttp только как прокси/транспорт, без отдельной бизнес-логики.

3. Исправить H1/H2/H3:
- Убрать дубликат `GET /api/v1/orders` (оставить один источник истины).
- Финализировать один payment-flow (Click-only) и удалить/изолировать legacy proof-поток.
- Привести frontend к единому статусу `rejected` (без `payment_rejected` в логике).

4. Исправить H4/H5:
- В `payment/create` использовать `PaymentStatus.normalize(...)`.
- На 5xx отдавать унифицированный `internal_error`, детали — только в логи.

5. Исправить M1/M2/M3/M4:
- Миграция денег на целые (`INTEGER` в minor units или `NUMERIC(12,2)`).
- Добавить rate limits на payment routes.
- Добавить retention cleanup для `idempotency_keys`.
- Переписать legacy history read-path на batched/join запросы.

