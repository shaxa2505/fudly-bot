# 🚀 Инструкция по деплою Partner Panel

## Вариант 1: Vercel (Рекомендуется)

### Шаг 1: Подготовка
```bash
# Установить Vercel CLI (если еще не установлен)
npm install -g vercel
```

### Шаг 2: Деплой
```bash
cd webapp/partner-panel
vercel --prod
```

### Шаг 3: Настройка
После деплоя получите URL (например: `https://fudly-partner.vercel.app`)

Добавьте в `.env` бота:
```env
PARTNER_PANEL_URL=https://fudly-partner.vercel.app
```

---

## Вариант 2: Netlify

### Через Web UI:
1. Зайти на [netlify.com](https://netlify.com)
2. New Site → Deploy manually
3. Перетащить папку `webapp/partner-panel`
4. Скопировать URL
5. Добавить в `.env`: `PARTNER_PANEL_URL=https://your-site.netlify.app`

### Через CLI:
```bash
npm install -g netlify-cli
cd webapp/partner-panel
netlify deploy --prod --dir=.
```

---

## Вариант 3: GitHub Pages

### Настройка:
1. Создать репозиторий на GitHub
2. Залить папку `webapp/partner-panel`
3. Settings → Pages → Deploy from branch `main`
4. URL будет: `https://username.github.io/repo-name`

---

## Вариант 4: Railway (вместе с ботом)

### Настройка nginx для статики:
Добавить в Dockerfile:
```dockerfile
# Копировать статику
COPY webapp/partner-panel /app/static/partner-panel

# В bot.py добавить статик сервер
from fastapi.staticfiles import StaticFiles
app.mount("/partner-panel", StaticFiles(directory="static/partner-panel", html=True), name="partner-panel")
```

Тогда URL будет: `https://your-bot.railway.app/partner-panel`

---

## После деплоя

### 1. Обновить .env
```env
PARTNER_PANEL_URL=https://ваш-url.vercel.app
```

### 2. Обновить app.js
В файле `webapp/partner-panel/app.js` найти:
```javascript
const API_BASE = 'https://your-bot-url.railway.app/api/partner';
```

Заменить на ваш URL Railway бота.

### 3. Перезапустить бота
```bash
# Локально
python bot.py

# На Railway
git push origin main
```

### 4. Проверить кнопку
Открыть бота → Меню продавца → Должна появиться кнопка "🖥 Веб-панель"

---

## Troubleshooting

### Кнопка не появляется:
- Проверить `PARTNER_PANEL_URL` в `.env`
- Убедиться что бот перезапущен
- Проверить что вы в режиме продавца (не покупателя)

### Веб-панель не открывается:
- Проверить CORS в боте (см. `partner_panel_simple.py`)
- Проверить что API_BASE в `app.js` указывает на Railway бот
- Открыть DevTools → Network → проверить запросы

### 401 Unauthorized:
- Telegram не передает initData в локальном браузере
- Открывать только через кнопку в боте
- Для локального теста использовать ngrok

---

## Рекомендации для продакшена

1. **Vercel** - лучший выбор для статики (бесплатно, CDN, автодеплой)
2. **API URL** - использовать переменные окружения в `app.js`
3. **HTTPS** - обязательно для Telegram Mini Apps
4. **CSP** - Content Security Policy для безопасности
5. **Мониторинг** - Vercel Analytics или Sentry

---

## Быстрый старт (Vercel)

```bash
# 1. Войти в Vercel
vercel login

# 2. Деплой
cd webapp/partner-panel
vercel --prod

# 3. Скопировать URL из вывода
# Production: https://fudly-partner-xxxxx.vercel.app

# 4. Добавить в .env бота
echo "PARTNER_PANEL_URL=https://fudly-partner-xxxxx.vercel.app" >> ../../.env

# 5. Перезапустить бота
cd ../..
python bot.py
```

Готово! 🎉
