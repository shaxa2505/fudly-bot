# Спецификация статистики (Партнёр и Админ)

Дата: 2025-12-13
Версия: 1.0

## Общие принципы
- Все агрегаты считаются по временному интервалу (периоды: Сегодня, Вчера, Неделя, Месяц, Кастомный диапазон).
- Временные вычисления выполняются с учётом таймзоны пользователя (партнёр) или глобальной таймзоны системы (админ).
- Источники данных: таблицы заказов, позиций заказов, товаров, пользователей, платежей. Реализация через `app/repositories/*` и `database_pg_module/`.
- Статусы заказов для выручки: включать `paid`, `completed`; исключать `cancelled`, `unpaid`, `refunded` (возвраты учитывать отдельно).

## Партнёрская статистика
Покрывает данные по текущему партнёру (`partner_id`), привязывает агрегаты к его товарам и заказам.

Метрики:
- Выручка: сумма оплаченных заказов за выбранный период.
- Заказов: количество уникальных заказов со статусами `paid`/`completed`.
- Товаров продано: сумма количеств позиций заказов (по товарам партнёра).
- Активных товаров: количество активных товаров партнёра (`status='active'`, опционально `stock > 0`).
- Средний чек: `revenue / orders_count` при `orders_count > 0`.
- Возвраты (опционально): сумма и количество возвратов за период.

Фильтры и связи:
- `order_item.seller_id = partner_id` или `order.seller_id = partner_id` (в зависимости от модели данных).
- Период: `[start, end)` в TZ партнёра.
- Магазин/витрина (если есть): фильтр `store_id`.

UX:
- Карточка "Статистика" с переключателями периода: Сегодня/Вчера/Неделя/Месяц.
- Кнопка "Обновить" (респект антифлуду, кэш 30–60 сек).
- Опционально: "Экспорт CSV".

Контракт сервиса:
```
get_partner_stats(partner_id: int, period: Period, tz: str, store_id: Optional[int]) -> PartnerStats
```
`PartnerStats`:
```
{
  period: { start: datetime, end: datetime, tz: str },
  totals: {
    revenue: Decimal,
    orders: int,
    items_sold: int,
    active_products: int,
    avg_ticket: Decimal | null,
    refunds_amount: Decimal,
    refunds_count: int
  }
}
```

## Админская статистика (полная)
Охватывает все данные системы, с возможностью фильтрации по магазину, городу, категории, продавцу.

Метрики (агрегаты по системе):
- Общая выручка: сумма оплаченных/завершённых заказов за период.
- Заказов: количество уникальных заказов (`paid`/`completed`).
- Покупателей: число уникальных пользователей, оформивших заказ.
- Продавцов активных: число продавцов с хотя бы одним активным товаром или заказом.
- Товаров продано: суммарно по всем продавцам.
- Средний чек: `revenue / orders_count`.
- Возвраты: сумма и количество.
- Каналы продаж (опционально): распределение по источникам (бот, мини-апп, веб).
- Топ-товары/продавцы: топ-N по выручке/продажам.

Фильтры:
- Диапазон времени (TZ системы).
- `store_id`, `city`, `category_id`, `seller_id`.
- Статусы: включать `paid`, `completed`; учитывать `refunded` отдельно.

Контракт сервиса:
```
get_admin_stats(filters: AdminStatsFilters) -> AdminStats
```
`AdminStatsFilters`:
```
{
  period: { start: datetime, end: datetime, tz: str },
  store_id?: int,
  city?: str,
  category_id?: int,
  seller_id?: int
}
```
`AdminStats`:
```
{
  period: { start: datetime, end: datetime, tz: str },
  totals: {
    revenue: Decimal,
    orders: int,
    buyers: int,
    active_sellers: int,
    items_sold: int,
    avg_ticket: Decimal | null,
    refunds_amount: Decimal,
    refunds_count: int
  },
  breakdowns: {
    by_channel?: Array<{ channel: str, revenue: Decimal, orders: int }>,
    top_products?: Array<{ product_id: int, name: str, revenue: Decimal, qty: int }>,
    top_sellers?: Array<{ seller_id: int, name: str, revenue: Decimal, orders: int }>
  }
}
```

## Технические заметки
- Кэшировать результаты агрегации на короткий срок (30–60 сек) для популярных периодов.
- Все строки интерфейса — из `locales/` через `localization.py`.
- Учитывать часовые пояса (TZ) строго на уровне запросов/агрегаций.
- Логировать ошибки и аномально высокую нагрузку.

## Следующие шаги
- Реализовать `app/services/stats.py` с указанными контрактами.
- Подключить хендлеры в `handlers/seller/` и `handlers/admin/`.
- Добавить интеграционные тесты для агрегатов.
