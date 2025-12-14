# Partner Panel - Production Ready Checklist

## ✅ Готово к продакшену

### Бэкенд (Bot)
- ✅ **Partner Panel API** (`app/api/partner_panel_simple.py`)
  - Все endpoints работают (products, orders, stats, store)
  - Авторизация через Telegram initData
  - CORS настроен для Mini App
  - Статистика с Period dataclass (исправлена)

- ✅ **Bot Integration**
  - Кнопка веб-панели в меню продавца (`app/keyboards/seller.py`)
  - WebApp URL из переменной окружения (`handlers/common/webapp.py`)
  - Интеграция в 4 местах меню (`handlers/common/commands.py`)

- ✅ **Database**
  - PostgreSQL ready
  - Все таблицы созданы
  - Миграции через Alembic

### Фронтенд (Mini App)
- ✅ **UI/UX Design**
  - Современный компактный дизайн
  - Responsive layout
  - Telegram-native стиль
  - Все иконки и статы

- ✅ **Functionality**
  - Управление товарами (CRUD)
  - Просмотр заказов
  - Статистика (сегодня/вчера/неделя/месяц)
  - Настройки магазина
  - Загрузка CSV

- ✅ **Technical**
  - Vanilla JS (без зависимостей)
  - Auto-detect API URL (localhost/production)
  - Dev mode для локального тестирования
  - Error handling

### Deployment
- ✅ **Docker**
  - Multi-stage Dockerfile
  - Python 3.11-slim
  - Оптимизирован для Railway

- ✅ **Railway**
  - railway.toml настроен
  - Health check endpoint
  - Restart policy
  - Environment variables ready

---

## 📋 Что нужно сделать для деплоя

### 1. Задеплоить Mini App (Веб-панель)

**Вариант A: Vercel (Рекомендуется)** ⭐
```bash
# Установить Vercel CLI
npm install -g vercel

# Деплой
cd webapp/partner-panel
vercel --prod

# Скопировать URL из вывода
# Например: https://fudly-partner-abc123.vercel.app
```

**Вариант B: Netlify**
```bash
# Установить Netlify CLI
npm install -g netlify-cli

# Деплой
cd webapp/partner-panel
netlify deploy --prod --dir=.

# Скопировать URL
```

**Вариант C: GitHub Pages**
1. Создать репозиторий для фронтенда
2. Залить папку `webapp/partner-panel`
3. Settings → Pages → Deploy from main
4. URL: `https://username.github.io/repo-name`

---

### 2. Настроить Environment Variables

После деплоя Mini App, добавить в Railway:

```env
# Railway → Settings → Variables

# URL задеплоенного Mini App (из шага 1)
PARTNER_PANEL_URL=https://your-panel.vercel.app

# Telegram Bot Token (уже должен быть)
TELEGRAM_BOT_TOKEN=ваш_токен

# Database URL (Railway автоматически создаст)
DATABASE_URL=${{Postgres.DATABASE_URL}}

# Webhook для Railway (после первого деплоя)
WEBHOOK_URL=https://your-bot.up.railway.app
PORT=8000
```

---

### 3. Обновить API URL в Mini App

В файле `webapp/partner-panel/app.js` (строка 17):

```javascript
// Заменить на ваш Railway URL
return 'https://ваш-бот.up.railway.app/api';
```

**Или** использовать переменную окружения Vercel:
```bash
# В настройках Vercel добавить:
PARTNER_API_URL=https://ваш-бот.up.railway.app/api
```

---

### 4. Задеплоить бота на Railway

```bash
# Убедиться что все изменения закоммичены
git add .
git commit -m "feat: partner panel production ready"
git push origin main

# Railway автоматически задеплоит
```

Или через Railway CLI:
```bash
railway up
```

---

### 5. Проверить работу

#### A. Проверить Bot API
```bash
# Health check
curl https://ваш-бот.up.railway.app/health

# Partner API (нужен токен)
curl https://ваш-бот.up.railway.app/api/partner/profile \
  -H "Authorization: dev_123456"
```

#### B. Проверить Mini App
1. Открыть бота в Telegram
2. Переключиться в режим продавца
3. Должна появиться кнопка "🖥 Веб-панель"
4. Нажать на кнопку
5. Должна открыться веб-панель

#### C. Проверить функции
- ✅ Загрузка товаров
- ✅ Добавление товара
- ✅ Редактирование товара
- ✅ Удаление товара
- ✅ Просмотр заказов
- ✅ Статистика
- ✅ Настройки магазина

---

## 🚨 Troubleshooting

### Кнопка не появляется
1. Проверить `PARTNER_PANEL_URL` в Railway variables
2. Перезапустить бота на Railway
3. Убедиться что вы в режиме продавца (не покупателя)
4. Проверить логи: `railway logs`

### Mini App не открывается
1. Проверить HTTPS (обязательно для Telegram)
2. Проверить CORS в `api_server.py`
3. Проверить URL в Vercel deployment
4. Открыть DevTools → Console → проверить ошибки

### API не отвечает
1. Проверить Railway deployment: `railway status`
2. Проверить логи: `railway logs`
3. Проверить DATABASE_URL
4. Проверить CORS origin в `api_server.py`

### 401 Unauthorized
1. Telegram initData работает только в Mini App
2. Для теста использовать dev mode (localhost)
3. Проверить что токен бота правильный
4. Проверить что пользователь зарегистрирован как продавец

---

## 📊 Checklist перед продакшеном

### Безопасность
- ✅ HTTPS везде (Vercel и Railway автоматически)
- ✅ Telegram initData validation
- ✅ CORS только для доверенных доменов
- ⚠️ Rate limiting (TODO: добавить в будущем)
- ⚠️ Input validation (TODO: улучшить)

### Performance
- ✅ Minimal dependencies (Vanilla JS)
- ✅ CDN для статики (Vercel)
- ✅ Docker multi-stage build
- ⚠️ Database indexes (TODO: проверить)
- ⚠️ Caching (TODO: Redis)

### Monitoring
- ⚠️ Sentry для ошибок (OPTIONAL)
- ⚠️ Railway metrics (встроенные)
- ⚠️ Vercel analytics (встроенные)
- ⚠️ Custom logging (уже есть в боте)

### UX
- ✅ Loading states
- ✅ Error messages
- ✅ Responsive design
- ✅ Telegram theme integration
- ✅ Empty states

---

## 🎯 Quick Start Commands

```bash
# 1. Деплой Mini App
cd webapp/partner-panel
vercel --prod
# Копируем URL: https://fudly-partner-xyz.vercel.app

# 2. Обновить API URL в app.js
# Редактируем строку 17:
# return 'https://ваш-бот.up.railway.app/api';

# 3. Добавить в Railway переменные
railway variables set PARTNER_PANEL_URL=https://fudly-partner-xyz.vercel.app

# 4. Деплой бота
git add .
git commit -m "Production ready"
git push origin main

# 5. Проверить
railway logs --tail
```

Готово! 🚀

---

## 🔮 Future Improvements

### Priority 1 (Near Future)
- [ ] Offline mode (Service Worker)
- [ ] Push notifications через бота
- [ ] Bulk operations для товаров
- [ ] Analytics dashboard

### Priority 2 (Later)
- [ ] Multi-language support
- [ ] Image optimization
- [ ] Dark/Light theme toggle
- [ ] Export reports (PDF/Excel)

### Priority 3 (Nice to Have)
- [ ] PWA (installable app)
- [ ] Real-time order updates (WebSocket)
- [ ] Chat с покупателем
- [ ] AI-powered insights
