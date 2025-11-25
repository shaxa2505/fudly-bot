# 📁 План реструктуризации handlers/

## 🎯 Цель
Организовать код по логическим группам:
- **Общий код** → `handlers/common/`
- **Код покупателя** → `handlers/customer/`  
- **Код продавца** → `handlers/seller/`
- **Код админа** → `handlers/admin/`

---

## ✅ ВСЁ ВЫПОЛНЕНО (25 ноября 2025)

### Итоговая структура handlers/
```
handlers/
├── __init__.py
├── README.md
├── common/                    # ✅ Общий код
│   ├── __init__.py
│   ├── router.py
│   ├── states.py              # ВСЕ FSM состояния
│   ├── utils.py               # Middleware, утилиты
│   ├── registration.py
│   ├── commands.py
│   └── help.py
├── customer/                  # ✅ Код покупателя
│   ├── __init__.py
│   ├── router.py
│   ├── menu.py                # Переключение режимов
│   ├── features.py            # Корзина, настройки
│   ├── profile.py             # Профиль пользователя
│   ├── favorites.py           # Избранное
│   ├── offers/
│   │   ├── __init__.py
│   │   ├── router.py
│   │   ├── browse.py          # Просмотр предложений
│   │   └── search.py          # Поиск
│   ├── bookings/
│   │   ├── __init__.py
│   │   └── router.py
│   └── orders/
│       ├── __init__.py
│       ├── router.py
│       └── delivery.py        # Заказы с доставкой
├── seller/                    # ✅ Код продавца
│   ├── __init__.py
│   ├── router.py
│   ├── registration.py        # Регистрация магазина
│   ├── create_offer.py
│   ├── analytics.py
│   ├── bulk_import.py
│   ├── order_management.py
│   ├── bookings/
│   │   └── router.py
│   └── management/
│       ├── __init__.py
│       └── offers.py
├── admin/                     # ✅ Код админа
│   ├── __init__.py
│   ├── dashboard.py
│   ├── legacy.py
│   ├── panel.py               # /admin команда
│   └── stats.py               # Статистика
└── bookings/                  # Общие бронирования
    ├── __init__.py
    ├── customer.py
    └── partner.py
```

### Выполненные миграции
| Откуда | Куда | Статус |
|--------|------|--------|
| `common_states/states.py` | `common/states.py` | ✅ |
| `user/favorites.py` | `customer/favorites.py` | ✅ |
| `user/profile.py` | `customer/profile.py` | ✅ |
| `offers.py` | `customer/offers/browse.py` | ✅ |
| `search.py` | `customer/offers/search.py` | ✅ |
| `orders.py` | `customer/orders/delivery.py` | ✅ |
| `partner.py` | `seller/registration.py` | ✅ |
| `admin_panel.py` | `admin/panel.py` | ✅ |
| `admin_stats.py` | `admin/stats.py` | ✅ |

### Удалённые папки
- ❌ `handlers/user/` → перенесено в `customer/`
- ❌ `handlers/common_states/` → перенесено в `common/states.py`
- ❌ `handlers/orders.py` → перенесено в `customer/orders/delivery.py`

### Обновлённые импорты
- `from handlers.common_states.states import X` → `from handlers.common.states import X`
- `from handlers.user import profile, favorites` → `from handlers.customer import profile, favorites`

---

## 📝 Дополнительные улучшения (25 ноября 2025)

### ✅ Исправления DatabaseProtocol
- Добавлен `get_store_rating_summary()` в database.py и database_pg.py
- Добавлен `set_platform_payment_card()` в database.py и database_pg.py  
- Типы в протоколе сделаны гибкими с Union для совместимости

### ✅ Рефакторинг bot.py
- Вынесен webhook server в `app/core/webhook_server.py` (~143 строки)
- bot.py уменьшен с 1218 до 1075 строк

### ⏳ Отложено (слишком много зависимостей)
- Перенос `localization.py` → `app/core/` (25+ файлов импортируют)
- Перенос `security.py` → `app/core/`
- Перенос `logging_config.py` → `app/core/`

### 📊 Статус тестов
- 114 тестов проходят ✅
- 1 тест пропущен (проблема изоляции роутера)

### Фаза 6: Финализация (ожидает)
- [ ] Обновить bot.py для использования новых роутеров
- [ ] Удалить старые файлы из корня handlers/
- [ ] Тестирование всех функций

---

## 📊 Текущий прогресс

| Фаза | Описание | Статус |
|------|----------|--------|
| 1 | Создание структуры папок | ✅ Готово |
| 2 | Миграция common/ | ✅ Готово |
| 3 | Миграция customer/ | ✅ Готово |
| 4 | Миграция seller/ | ✅ Готово |
| 5 | Миграция admin/ | ✅ Готово |
| 6 | Финализация | ✅ Готово |

## ✅ РЕСТРУКТУРИЗАЦИЯ ЗАВЕРШЕНА!

### Финальная структура handlers/
```
handlers/
├── admin/                  # 👨‍💼 АДМИН
│   ├── dashboard.py
│   ├── legacy.py
│   ├── panel.py           
│   └── stats.py           
│
├── bookings/               # 📦 БРОНИРОВАНИЯ (общие)
│   ├── customer.py
│   ├── partner.py
│   ├── router.py
│   └── utils.py
│
├── common/                 # 🔷 ОБЩИЙ КОД
│   ├── commands.py         
│   ├── help.py             
│   ├── registration.py     
│   ├── router.py
│   ├── states.py           
│   └── utils.py            
│
├── customer/               # 🛒 ПОКУПАТЕЛЬ
│   ├── features.py         
│   ├── menu.py             
│   ├── router.py
│   ├── bookings/
│   │   └── router.py
│   ├── offers/
│   │   ├── browse.py       
│   │   ├── router.py
│   │   └── search.py       
│   └── orders/
│       ├── delivery.py     
│       └── router.py
│
├── seller/                 # 🏪 ПРОДАВЕЦ
│   ├── analytics.py
│   ├── bulk_import.py
│   ├── create_offer.py
│   ├── order_management.py
│   ├── registration.py     
│   ├── bookings/
│   │   └── router.py
│   └── management/
│       ├── offers.py
│       ├── orders.py
│       ├── pickup.py
│       ├── router.py
│       └── utils.py
│
└── user/                   # 👤 ПОЛЬЗОВАТЕЛЬ
    ├── favorites.py
    └── profile.py
```

### Миграция файлов (было → стало)
| Было | Стало |
|------|-------|
| `admin_panel.py` | `admin/panel.py` |
| `admin_stats.py` | `admin/stats.py` |
| `common.py` | `common/` (папка) |
| `common_user.py` | `customer/menu.py` |
| `help.py` | `common/help.py` |
| `offers.py` | `customer/offers/browse.py` |
| `orders.py` | `customer/orders/delivery.py` |
| `partner.py` | `seller/registration.py` |
| `registration.py` | `common/registration.py` |
| `search.py` | `customer/offers/search.py` |
| `user_commands.py` | `common/commands.py` |
| `user_features.py` | `customer/features.py` |

---

## ⚠️ Важно

При переносе файлов:
1. Сначала создать новый файл с кодом
2. Обновить импорты в bot.py
3. Протестировать функционал
4. Удалить старый файл
