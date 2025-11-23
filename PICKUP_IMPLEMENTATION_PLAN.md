# План реализации и улучшения системы самовывоза (Pickup)

Документ содержит конкретные шаги, изменения в БД и коде, тесты и план развёртывания для приведения системы самовывоза в согласованное, надёжное состояние.

## Краткая цель
- Сделать работу самовывоза предсказуемой и безопасной: резервирование товара, выбор слота (pickup_time), генерация и проверка кода выдачи, напоминания и отмены по истечении срока.

## Предпосылки и текущая ситуация
- В проекте уже есть: `bookings` (бронь) с атомарным созданием (`create_booking_atomic`) и `orders` (заказы) с генерацией `pickup_code`.
- Наблюдаемая проблема: `pickup_time` упоминается в коде/запросах, но не передаётся/не сохраняется при создании брони в `database.py` — несогласованность данных.

## Основные требования
1. При создании брони поддерживать `pickup_time` (опционально) и `pickup_address`.
2. Резервирование количества должно быть атомарным (уже реализовано в `create_booking_atomic`).
3. Возможность ограничения capacity по слоту (количество выдач в конкретное окно времени).
4. Генерация криптографически ненадёжного, но уникального `booking_code` и/или отдельного `pickup_code` при конвертации в заказ.
5. Подтверждение выдачи продавцом по коду (или QR/HMAC) и логирование попыток.
6. Напоминания пользователю и автоматическая отмена просроченных броней (expiry worker).

## Результат (deliverables)
- Файл миграции/скриптов для добавления полей `pickup_time`, `pickup_address` в `bookings`.
- Обновлённые методы в `database_protocol.py`, `database.py`, `database_pg.py` для передачи и сохранения `pickup_time`/`pickup_address`.
- Обновлённые handler'ы: сбор времени в процессе бронирования, отображение и проверка в `handlers/bookings_flow.py` и месте создания брони (`handlers/bookings_create.py` или аналог).
- Handler подтверждения выдачи у партнёра (в `handlers/seller/management.py`) и проверка `pickup_code`.
- Unit и интеграционные тесты для новых сценариев.

## Пошаговый план внедрения (микрозадачи)

1) Схема БД (миграции)
   - Добавить в `bookings` поля:
     - `pickup_time TEXT NULL` — формат ISO или timestamp
     - `pickup_address TEXT NULL`
     - (опционально) `pickup_code TEXT NULL`
   - SQL-примеры:
     - SQLite:
       ```sql
       ALTER TABLE bookings ADD COLUMN pickup_time TEXT;
       ALTER TABLE bookings ADD COLUMN pickup_address TEXT;
       ALTER TABLE bookings ADD COLUMN pickup_code TEXT;
       ```
     - Postgres:
       ```sql
       ALTER TABLE bookings ADD COLUMN pickup_time TIMESTAMP NULL;
       ALTER TABLE bookings ADD COLUMN pickup_address TEXT NULL;
       ALTER TABLE bookings ADD COLUMN pickup_code VARCHAR(32) NULL;
       ```

2) API / DB layer
   - Обновить `database_protocol.py`:
     - `create_booking_atomic(self, offer_id, user_id, quantity=1, pickup_time=None, pickup_address=None) -> Tuple[bool, Optional[int], Optional[str]]`
   - В `database.py` и `database_pg.py`:
     - Принять новые параметры и вставить их в `INSERT INTO bookings (...)`.
     - При создании брони возвращать `(ok, booking_id, booking_code)` (как сейчас).
     - При конвертации брони в заказ (оплата): генерировать `pickup_code` и сохранять в `orders`.

3) Handlers (пользовательский поток)
   - В `handlers/bookings_create.py` (или месте, где инициируется бронь):
     - Запросить у пользователя выбор времени/слота (предложить ближайший свободный).
     - Вызвать `db.create_booking_atomic(..., pickup_time=chosen_time, pickup_address=address)`.
     - Отправить пользователю сообщение с `booking_code` и инструкциями (адрес, время, отмена).

4) Handlers (поток партнёра)
   - В `handlers/seller/management.py`:
     - Возможность увидеть `pickup_time` и `booking_code` в деталях.
     - Новая команда/кнопка: `Отметить выдано` — ввод/сканирование `code` → проверка и смена статуса `completed/picked_up`.

5) Слоты и capacity (опционально, но рекомендовано)
   - Таблица `pickup_slots(store_id, slot_ts, capacity, reserved)` или вычислять по количеству существующих броней в слоте.
   - При создании брони необходимо атомарно инкрементировать `reserved` и проверить `reserved <= capacity`.

6) Worker: напоминания и expiry
   - Убедиться, что `tasks/booking_expiry_worker.py`:
     - Отправляет напоминания (30/15/5 минут)
     - Отменяет просроченные брони и возвращает quantity в `offers` (atomic)

7) Тесты
   - Unit-tests:
     - `create_booking_atomic` с `pickup_time` → успешно создает бронь и уменьшает запас.
     - Попытка создать бронь при недостатке товара → false.
     - Попытка создать бронь при переполненном слоте → false (если реализован slots).
   - Integration-tests:
     - Полный сценарий: бронь → подтверждение партнёром → оплата/конвертация → выдача по коду.

8) Документация и релиз
   - Обновить `BOOKING_DEBUG.md` и README: UX-поток самовывоза.
   - Подготовить миграции и инструкции deploy (если есть CI/CD).

## Конкретные правки/файлы (короткий чек-лист)
- `database_protocol.py` — метод `create_booking_atomic` signature
- `database.py`, `database_pg.py` — реализация вставки `pickup_time`, `pickup_address`
- `handlers/bookings_create.py` (или место создания брони) — сбор `pickup_time`
- `handlers/bookings_flow.py`, `handlers/bookings_utils.py` — отображение полей `pickup_time` и `pickup_address`
- `handlers/seller/management.py` — добавление проверки `pickup_code` и отметки выдачи
- `tasks/booking_expiry_worker.py` — убедиться, что освобождение товара и напоминания работают с новыми полями
- `tests/*` — добавить тесты выше

## Короткий план по временным оценкам (ориентировочно)
- Миграция + DB API changes: 1–2 часа
- Handlers (UX) + простая валидация слотов: 2–4 часа
- Worker + напоминания: 1–2 часа
- Тесты: 2–3 часа
- Документация и QA: 1 час

## Риски и замечания
- Если в проекте два адаптера БД (SQLite + Postgres), изменения необходимо внести в оба.
- Для точной поддержки слотов желательно иметь таблицу слотов; её проектирование увеличит объём работы.
- Миграции для SQLite ограничены (ALTER ADD COLUMN — OK), но для сложных изменений может потребоваться recreation.

---
Если нужно, могу сделать первый практический шаг: внести минимальные правки в `database_protocol.py` и `database.py` — добавить параметр `pickup_time` в `create_booking_atomic` и сохранить его в `INSERT`. Хотите, чтобы я сделал это сейчас? 
