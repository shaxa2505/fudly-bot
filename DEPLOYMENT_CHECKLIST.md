# DEPLOYMENT_CHECKLIST.md

## ✅ Pre-Deployment Checklist

### Выполнено:

#### Безопасность
- [x] TOKEN validation добавлена в bot.py (raise ValueError if missing)
- [x] Phone validation в handlers/registration.py (validator.validate_phone)
- [x] InputValidator класс с валидацией phone, username, city, price, quantity
- [x] RateLimiter класс с is_allowed(user_id, action, max_requests, window)
- [x] SECRET_TOKEN загружается из окружения

#### База данных
- [x] DatabaseProtocol создан для единого интерфейса
- [x] database_types.py с TypedDict (UserDict, StoreDict, OfferDict, BookingDict)
- [x] Все методы в database_pg.py реализованы (get_user_stores, get_active_offers, favorites, etc.)
- [x] Унифицированный возврат dict в database.py (get_user, get_user_stores, get_store, etc.)
- [x] get_active_offers конвертирован в dict с JOIN логикой
- [x] migration_favorites_pg.sql создан для исправления favorites схемы

#### Конфигурация
- [x] runtime.txt обновлён до python-3.13.0
- [x] .env.example создан с DATABASE_URL, DB_MIN_CONN, DB_MAX_CONN
- [x] python-json-logger раскомментирован в requirements.txt
- [x] .gitignore исключает .env и *.db

#### Тестирование
- [x] 20 unit тестов созданы и проходят (test_security.py, test_database.py)
- [x] Нет compile errors в основных файлах

---

## 📋 Railway Deployment Steps

### 1. Подготовка Repository
```bash
# Убедитесь что все изменения закоммичены
git status
git add .
git commit -m "feat: add type safety, security validations, and comprehensive tests"
git push origin main
```

### 2. Railway PostgreSQL Setup
Если PostgreSQL не настроен:
```bash
# См. RAILWAY_POSTGRESQL_SETUP.md для деталей
# После создания БД выполните migration_favorites_pg.sql
```

### 3. Environment Variables в Railway
Установите в Railway Dashboard:
```
TELEGRAM_BOT_TOKEN=ваш_токен_от_BotFather
ADMIN_ID=ваш_telegram_id
DATABASE_URL=postgresql://... (автоматически от Railway)
USE_WEBHOOK=true
WEBHOOK_URL=https://yourapp.railway.app
TELEGRAM_SECRET_TOKEN=random_secure_token
LOG_LEVEL=INFO
DB_MIN_CONN=1
DB_MAX_CONN=10
MAX_REQUESTS_PER_MINUTE=20
RATE_LIMIT_WINDOW=60
```

### 4. Первый Deploy
```bash
# Railway автоматически деплоит из main ветки
# Следите за логами в Railway Dashboard
railway logs
```

### 5. Миграция БД (первый раз)
```bash
# Подключитесь к PostgreSQL и выполните:
railway connect postgres
# Затем вставьте содержимое migration_favorites_pg.sql
```

### 6. Webhook Setup
```bash
# После успешного деплоя установите webhook:
curl -X POST "https://api.telegram.org/bot<YOUR_TOKEN>/setWebhook" \
  -H "Content-Type: application/json" \
  -d '{"url": "https://yourapp.railway.app/webhook", "secret_token": "YOUR_SECRET_TOKEN"}'

# Проверка:
curl "https://api.telegram.org/bot<YOUR_TOKEN>/getWebhookInfo"
```

---

## 🔍 Post-Deployment Verification

### Проверки:
1. ✅ Бот отвечает на /start
2. ✅ Регистрация работает (телефон и город)
3. ✅ Валидация телефона отклоняет некорректные номера
4. ✅ База данных сохраняет данные
5. ✅ Rate limiting работает (попробуйте спамить команды)
6. ✅ Логи JSON форматируются корректно

### Мониторинг:
```bash
# Логи Railway
railway logs --tail

# Проверка webhook
curl "https://api.telegram.org/bot<TOKEN>/getWebhookInfo"

# Метрики БД (если настроены)
railway metrics
```

---

## ⚠️ Known Issues (не критично)

1. **Pylance warnings** для aiogram динамических атрибутов - ожидаемо, см. .pylance-notes.txt
2. **Синхронные БД операции** - работает, но asyncpg рекомендован для production
3. **bot.py монолит** - рефакторинг в handlers/ продолжается

---

## 📚 Документация

- `RAILWAY_POSTGRESQL_SETUP.md` - Настройка PostgreSQL
- `RAILWAY_VOLUME_SETUP.md` - Volume для SQLite (если нужен)
- `DEPLOY_RAILWAY.md` - Общие инструкции по Railway
- `handlers/README.md` - Архитектура handlers
- `REFACTORING_SUMMARY.md` - План рефакторинга

---

## 🎯 Next Steps (после деплоя)

1. Завершить миграцию обработчиков из bot.py в handlers/
2. Создать services/ слой для бизнес-логики
3. Добавить asyncpg для PostgreSQL
4. Централизовать normalize_city/category
5. Разделить requirements.txt и requirements-dev.txt

---

**Дата:** 2025-11-14  
**Статус:** ✅ Ready for deployment  
**Версия:** 1.0.0-stable
