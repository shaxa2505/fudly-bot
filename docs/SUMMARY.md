Общая оценка

Виден серьёзный эволюционный рефакторинг: переход от «монолита» в bot.py/database.py к модульной архитектуре (core, services, repositories, database_pg_module, unified order service/handlers).
Хорошо продуманы инфраструктурные вещи: PostgreSQL через psycopg_pool, FSM storage в БД, Redis‑кеш, Sentry, health/metrics, webhooks, background workers.
Главный минус сейчас — архитектурный долг по заказам: параллельные модели bookings/orders, несколько точек входа и исторически накопленный код в огромных модулях (bookings.customer, cart.router, offers.browse, и т.п.).
В целом код уровня middle+/senior, но требуются целевые рефакторинги для упрощения, устранения дублирования и выравнивания доменной модели.
Найденные проблемы (с пояснениями)

Фрагментация системы заказов (как уже зафиксировано в ORDER_SYSTEM_AUDIT.md)

Минимум 5 точек создания заказов (bookings, cart, delivery, WebApp, старый OrderService), каждая со своей логикой валидации, резервирования и уведомлений.
UnifiedOrderService и unified_order_handlers уже есть, но подключены только для части сценариев; старые callback‑паттерны и хендлеры (включая fallback_router в bot.py) продолжают жить параллельно.
Результат: высокая когнитивная нагрузка, риск инконсистентности статусов и уведомлений.
Несогласованность моделей bookings и orders

BookingMixin.create_booking_atomic() реализует аккуратную атомарную логику с SELECT ... FOR UPDATE, лимитом активных броней, слотами выдачи и явным временем истечения.
OrderMixin.create_cart_order() просто делает UPDATE offers SET quantity = quantity - %s без проверки остатка и без блокировок, то есть для заказов корзины логика резервирования слабее и может вести к расхождению с bookings.
UnifiedOrderService для pickup‑заказов использует orders через create_cart_order вместо bookings, но старая логика bookings остаётся в ходу через старые хендлеры.
FSM storage: заявлена composite‑key из user_id + chat_id, фактически используется только user_id

В EnhancedPostgreSQLStorage:
В set_state конфликт‑таргет — ON CONFLICT (user_id); chat_id в унике не участвует.
get_state, get_data, get_state_info фильтруют только по user_id, игнорируя chat_id.
Это противоречит комментарию «Composite key (user_id + chat_id)» и означает, что:
Состояния разных чатов одного пользователя перетирают друг друга.
При нескольких чатах (личка + группы, несколько мини‑приложений и т.п.) возможна потеря состояния и странные переходы.
Смешение синхронного I/O и async в горячих путях

Все DB‑операции синхронны (psycopg_pool, get_connection), вызываются напрямую из async‑хендлеров aiogram (в т.ч. FSM‑storage).
Для средней нагрузки это ок, но под высоким RPS или при медленном Postgres будут блокироваться event loop’ы, что ухудшит latency и устойчивость (особенно в webhook‑режиме).
Аналогично FSM‑storage (EnhancedPostgreSQLStorage) внутри async‑методов использует синхронные with self.db.get_connection().
Rate limiting только in‑memory

RateLimiter хранит состояние в памяти процесса; при масштабировании на несколько экземпляров (несколько контейнеров) ограничения перестанут быть глобальными.
Нет механизма очистки/eviction по пользователям, кроме clear_user; при большом количестве уникальных user_id возможен рост памяти.
Фоновые задачи не полностью симметрично управляются

В main() создаются cleanup_task, fsm_cleanup_task, booking_task, rating_task.
В webhook‑ветке в finally отменяются cleanup_task, fsm_cleanup_task, booking_task, но не rating_task.
В polling‑ветке отменяется cleanup_task и booking_task, но не fsm_cleanup_task и не rating_task.
На практике это не критичный баг (при завершении asyncio.run задачи всё равно падут), но shutdown поведение несимметрично и может приводить к логическим гонкам при graceful‑остановке.
Гигантские хендлер‑модули

По PROJECT_MAP.md: bookings/customer.py ~1275 строк, customer/cart/router.py ~1296 строк, customer/offers/browse.py ~1448 строк и т.д.
Даже при наличии services и repositories, значительная часть бизнес‑логики всё ещё живёт прямо в хендлерах, что осложняет тестирование и повторное использование.
Глобальные singletons и нежёсткий DI

UnifiedOrderService реализован как модульный синглтон (_unified_order_service + init_unified_order_service()), handlers.common.unified_order_handlers держит глобальные db, bot.
Это упрощает интеграцию, но вредит тестируемости и делает порядок инициализации критичным (легко получить "db is None" при добавлении новых entrypoints или workers).
Потенциальные баги/уязвимости

Перепродажа/негативный остаток в create_cart_order

В OrderMixin.create_cart_order():
Нет SELECT ... FOR UPDATE по offers.
UPDATE offers SET quantity = quantity - %s не проверяет, что количество остаётся ≥ 0.
Под параллельной нагрузкой (несколько пользователей бронируют один и тот же оффер) возможны:
Негативные quantity.
Продажа сверх доступного остатка.
В create_booking_atomic() эти кейсы закрыты, поэтому поведение pickup через bookings и через orders может расходиться.
Неправильный расчёт total/delivery для мульти‑стор корзины (по коду UnifiedOrderService)

В UnifiedOrderService.create_order:
total_price = sum(item.price * item.quantity for item in items) — без доставки.
delivery_price = items[0].delivery_price if order_type == "delivery" else 0.
grand_total = total_price + delivery_price.
Если в корзине несколько магазинов с разной стоимостью доставки, delivery_price берётся только от первого item.
При этом на уровне БД total_price в таблице orders считается как discount_price * quantity + delivery_price per‑order.
Если по бизнес‑логике корзина ограничена одним магазином, это безопасно, но сейчас в коде это явно не выражено → потенциальное рассогласование сумм в UI/уведомлениях и реальной суммой в БД.
Смешивание статусов orders между старой и новой моделью

OrderMixin.update_order_status обновляет order_status строкой без нормализации.
UnifiedOrderService.OrderStatus.normalize мапит старый статус 'confirmed' → preparing, но обратной нормализации при чтении из БД не видно.
Старые хендлеры могут писать confirmed/completed/cancelled, новые — preparing/ready/delivering/completed/cancelled.
При отчётах/фильтрации без единого enum‑контракта легко получить «плавающие» статусы.
FSM‑состояния переписываются между чатами одного пользователя

Упомянуто выше: key‑конфликт и выбор по user_id → реальный баг, если один и тот же пользователь взаимодействует с ботом в нескольких чатах.
Условный баг с отменой/откатом заказов

UnifiedOrderService.cancel_order без доп. проверок вызывает update_status(..., CANCELLED):
Нет явной проверки, что заказ ещё не COMPLETED.
_restore_quantities попытается восстановить остаток, даже если параллельно продавец уже завершил выдачу.
Возможно это покрыто на уровне UI (кнопки пропадают), но на уровне домена это не закреплено.
RateLimiter и возможный DoS при большом числе уникальных пользователей

В RateLimiter._user_requests ключами являются user_id, значения — словари action → [timestamps].
Нет глобального лимита на размер структуры, чистится только при clear_user, что для «лёгкого» DoS‑типа атак с большим числом новых user_id может приводить к росту памяти.
Безопасность в целом выглядит аккуратно, но…

В целом используются параметризованные запросы (%s/? placeholders) и InputValidator.
Но при 100k строк кода возможно наличие мест, где:
Формируются SQL‑строки с f‑string’ами от пользовательского ввода (стоит сделать таргетный grep/ревизию).
Используются старые хелперы из security.py (legacy) параллельно с app.core.security.
Архитектурные улучшения

Довести Unified Order Service до единственного источника правды для заказов

Цель: любое создание/изменение заказа/брони проходит через:
UnifiedOrderService.create_order
UnifiedOrderService.update_status (+ шорткаты confirm_order, reject_order, complete_order, и т.д.)
Шаги:
Перенаправить customer.py и router.py/delivery.py на UnifiedOrderService вместо прямых вызовов db.create_*.
В WebApp API (webapp_api.py) вместо ручного выбора между create_booking_atomic/create_order вызывать UnifiedOrderService (через thin adapter).
Везде, где отправляются собственные уведомления продавцам/клиентам — заменить прямые send_message на вызовы методов UnifiedOrderService / NotificationTemplates.
Выбрать целевую доменную модель: всё → orders + order_type или чёткое разделение bookings/orders

Более чистый вариант на будущее: оставить одну доменную сущность Order c полем order_type = pickup|delivery.
Исторические bookings можно:
Либо мигрировать (скрипт: создать новые orders и пометить bookings как архив),
Либо оставить только для read‑only истории и заморозить.
Это сильно упростит код, отчётность и обработчики.
Вынести нотификации в отдельный сервис/модуль

Сейчас шаблоны есть в NotificationTemplates, но вызовы разбросаны по хендлерам и сервисам.
Рекомендация:
Создать app/services/notification_service.py c методами:
notify_seller_new_order(store_id, orders, context)
notify_customer_order_created(order, items, ...)
notify_customer_status_changed(order, new_status, ...)
UnifiedOrderService использует только его, а хендлеры вообще не формируют текст, только вызывают сервис.
Усилить границы между слоями: handlers → services → repositories → DB

Сейчас уже есть services и repositories, но значительная часть логики (особенно в bookings/cart/offers) осталась в хендлерах.
План:
Для каждого крупного флоу (bookings, cart, delivery) сделать доменный сервис в app/services/*.
Хендлеры должны делать только:
парсинг callback/data/state,
обращение к сервису,
преобразование результата в сообщения/клавиатуры.
Убрать/минимизировать глобальные singletons

Вместо _unified_order_service + get_unified_order_service() использовать DI:
В build_application создать сервисы и передать их в нужные модули/routers через setup_dependencies (как уже делается для bookings, cart, orders_delivery и т.п.).
Для workers/веб‑сервера также передавать зависимости явно, чтобы избежать «магии» глобальных переменных.
Оптимизации производительности

Сделать операции с БД менее блокирующими для event loop’а

Варианты (по нарастающей сложности):
Обернуть тяжёлые DB‑операции (массовые выборки, создание заказов, отчёты) в asyncio.to_thread/loop.run_in_executor, чтобы не блокировать event loop.
Долгосрочно — перейти на async‑драйвер (например, asyncpg) и async‑ORM/QueryBuilder (но это уже крупная миграция).
Укрепить атомарность и конкуррентную безопасность для заказов корзины

Переписать OrderMixin.create_cart_order():
Использовать SELECT quantity, status, ... FOR UPDATE по офферам (как в create_booking_atomic).
Внутри одной транзакции:
проверить остатки по всем item’ам,
только после успешной проверки создать все заказы и обновить quantity.
В случае любой ошибки откатывать всю корзину (а не частично).
Использовать Redis для rate limiting и, возможно, для очередей

Реализовать Redis‑базированный RateLimiter (ключи user:{id}:action) с TTL.
Для интенсивных уведомлений (e.g. рассылки, тяжёлые отчёты) можно вынести отправку сообщений в фоновые воркеры (постановка в Redis/кью, обработка воркерами).
Таргетное кеширование тяжёлых запросов

Уже есть CacheManager с Redis‑поддержкой; можно:
Расширить кеширование для популярных выборок (history, top offers, store stats), если профиль нагрузки это подтверждает.
Добавить «soft» инвалидацию через события (после изменений в офферах/заказах вызывать invalidate_*).
Улучшения структуры кодовой базы

Декомпозиция гигантских хендлер‑модулей

Например, customer/cart/router.py:
Разбить на подпакеты: cart/browse.py, cart/edit.py, cart/checkout.py, cart/admin.py и т.д.
Общие UI‑билдеры и хелперы оставить в cart_ui.py и cart/services.py.
Аналогично для bookings/customer.py, offers/browse.py, seller/store_settings.py, admin/dashboard.py.
Чёткое разделение legacy / new

Явно пометить legacy‑директории/файлы (у вас уже есть legacy.py в admin):
Сложить устаревшие обработчики в handlers/legacy/.
Убрать их из регистрации в bot.py, как только UnifiedOrderService покроет все кейсы.
Выравнивание контрактов репозиториев

app.repositories уже есть, но часть кода ходит напрямую в db.*.
Желательно:
Для всех основных доменов (users, stores, offers, orders, bookings, ratings) иметь явные репозитории.
Любой доступ к БД из сервисов/хендлеров — только через них (чтобы можно было легко менять реализацию, добавлять кеширование, аудит и т.п.).
Улучшения для читаемости и чистоты

Сократить дублирование текстов RU/UZ

В NotificationTemplates и хендлерах многократно повторяется структура сообщений на двух языках.
Можно:
Вынести общие куски в шаблоны/форматтеры (например, через маленький DSL или Jinja2‑шаблоны).
Использовать единый i18n‑слой (get_text), где это уместно.
Упростить callback‑паттерны

Сейчас поддерживается много комбинаций: order_confirm_, booking_confirm_, partner_confirm_, partner_confirm_order_, confirm_order_, и т.д.
После миграции на UnifiedOrderService можно оставить:
order:{id}:confirm, order:{id}:reject, order:{id}:ready, order:{id}:complete и т.п.
В обработчике разбирать тип/действие по простому split, не по regex.
Единый стиль логирования

Логи mostly ок, но:
Есть и print, и logger.info, и русско‑/узбекоязычные message’и вперемешку.
Рекомендация: оставить только logger.*, с понятными machine‑parsable ключами (e.g. event="order_created" user_id=...), а локализованный текст выводить в Telegram, а не в логи.
Рекомендации по рефакторингу

Краткий план по шагам (без «переписать всё»):

Order System v1.5 (быстрый выигрыш)

Исправить EnhancedPostgreSQLStorage:
Добавить уникальный индекс (user_id, chat_id).
Изменить ON CONFLICT (user_id) на ON CONFLICT (user_id, chat_id).
Фильтрацию в get_state, get_data, get_state_info делать по обоим полям.
Усилить OrderMixin.create_cart_order:
Добавить проверки количества и защиту от quantity < 0 (минимум — через условие в UPDATE + проверку rowcount).
Нормализовать статусы orders/bookings (ввести единый enum и адаптеры для legacy).
Order System v2 (унификация)

Перенаправить все новые/активные флоу на UnifiedOrderService/unified_order_handlers.
Временно пометить старые хендлеры как legacy и прикрыть их дополнительными логами/метриками, чтобы понимать, сколько трафика ещё идёт через них.
Декомпозиция крупных модулей

Начать с самых больших (cart, bookings, offers), соблюдая один и тот же паттерн:
Вынос бизнес‑логики в сервисы.
Разбиение модулей по use‑case’ам.
Добавление unit‑тестов на вынесенные сервисы.
Укрепление DI и отказ от глобальных singletons

Постепенно заменить get_unified_order_service и глобальные db/bot в модулях на явную передачу зависимостей через setup_dependencies/конструкторы.
Предложения по тестированию

Юнит‑ и интеграционные тесты для UnifiedOrderService

Тесты для:
create_order (pickup/delivery, success/ошибка, мульти‑items).
update_status с REJECTED/CANCELLED и проверкой восстановления quantity.
Поведение customer/seller уведомлений (можно мокать bot.send_message).
Проверить, что:
Статусы корректно записываются в БД.
Сообщения корректно формируются на RU/UZ.
Тесты конкурентности для бронирований/заказов

Сымитировать несколько конкурентных create_cart_order с общим offer_id:
Убедиться, что количество не уходит в минус, заказы не превышают остаток.
Аналогично для create_booking_atomic (здесь уже лучше, но полезно зафиксировать поведение тестами).
Тесты FSM‑хранилища

EnhancedPostgreSQLStorage:
set_state/get_state для нескольких чатов одного пользователя.
TTL и cleanup_expired.
Совместимость с legacy‑данными (если есть).
Контрактные тесты для AdminService и репозиториев

Проверка, что запросы статистики не ломаются при изменении схемы (миграциях).
Предложения по масштабированию

Поддержка нескольких инстансов бота

Перевести rate‑limitинг на Redis или иной распределённый стор.
Убедиться, что все состояния (FSM, корзина, заказы) либо:
Внешние (Postgres/Redis), либо
Явно не зависят от конкретного процесса.
Разделение ролей по процессам

Вынести тяжёлые фоновые задачи в отдельные workers (вы уже идёте в эту сторону — booking_expiry_worker, rating_reminder_worker):
Один процесс только telegram‑updates (webhook/polling).
Несколько воркеров для обработки очередей заказов, нотификаций, отчётов.
Метрики и алерты вокруг узких мест

Уже есть Prometheus‑style /metrics:
Добавить метрики по:
Времени ответа БД.
Количеству активных состояний FSM.
Количеству неуспешных заказов/броней по причинам.
Настроить алерты на рост ошибок, увеличение latency, падение пула соединений.
Список вопросов для уточнения

Корзина ограничена одним магазином или может содержать товары из разных?

От ответа зависит, является ли проблема с delivery_price/grand_total в UnifiedOrderService.create_order логической ошибкой или допустимым упрощением.
Планируете ли вы полностью отказаться от таблицы bookings в пользу orders?

Если да, имеет смысл сразу проектировать миграцию и постепенно выводить bookings в архив.
Есть ли текущие метрики по нагрузке (RPS, количество одновременных пользователей, среднее время ответа)?

От этого зависит приоритет миграции на async‑драйверы и усиления конкурентной безопасности.
Насколько активно используется WebApp (Mini App) по сравнению с «чистым» ботом?

Это влияет на приоритет унификации точек входа и форматов уведомлений.
Есть ли требования к строгой идемпотентности заказов (повторные callback’и, повторные запросы от WebApp)?

Если да, имеет смысл ввести idempotency‑ключи (например, по user_id + cart_hash) и хранить их в отдельной таблице/Redis.
Какая часть кода считается устаревшей и может быть реально удалена после миграции?

Например, топ‑уровневый database.py/security.py/fsm_storage_pg.py и часть legacy‑хендлеров — это важно знать для планирования чистки.
Если хочешь, я могу дальше:

точечно разобрать конкретный модуль (например, customer.py или конкретный сценарий из unified_order_service) и предложить детализированный план его пошагового рефакторинга, либо
помочь начать миграцию всех потоков заказов на UnifiedOrderService с минимальным риском.
