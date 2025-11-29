# 🚀 Инструкция по деплою Fudly WebApp

## Предварительная подготовка

### 1. Убедитесь что всё работает локально
```bash
cd webapp
npm install
npm run dev
```
Откройте http://localhost:3000 и проверьте все страницы.

### 2. Соберите production build
```bash
npm run build
```
Проверьте папку `dist/` - там должны быть минифицированные файлы.

## Деплой на Vercel (Рекомендуется) ⭐

### Автоматический деплой

1. Установите Vercel CLI:
```bash
npm install -g vercel
```

2. Войдите в аккаунт:
```bash
vercel login
```

3. Деплой:
```bash
cd webapp
vercel deploy --prod
```

### Через GitHub

1. Запушьте код в GitHub:
```bash
git add .
git commit -m "Ready for deploy"
git push origin main
```

2. Зайдите на [vercel.com](https://vercel.com)
3. Нажмите "Import Project"
4. Выберите ваш репозиторий
5. Настройки:
   - **Framework Preset:** Vite
   - **Root Directory:** `webapp`
   - **Build Command:** `npm run build`
   - **Output Directory:** `dist`

6. Нажмите "Deploy"

### Конфигурация Vercel

Создайте `vercel.json` в корне `webapp/`:
```json
{
  "buildCommand": "npm run build",
  "outputDirectory": "dist",
  "framework": "vite",
  "rewrites": [
    { "source": "/(.*)", "destination": "/index.html" }
  ],
  "headers": [
    {
      "source": "/assets/(.*)",
      "headers": [
        {
          "key": "Cache-Control",
          "value": "public, max-age=31536000, immutable"
        }
      ]
    }
  ]
}
```

## Деплой на Railway 🚂

### 1. Установите Railway CLI
```bash
npm install -g @railway/cli
```

### 2. Войдите в аккаунт
```bash
railway login
```

### 3. Инициализируйте проект
```bash
cd webapp
railway init
```

### 4. Создайте `railway.toml`
```toml
[build]
builder = "nixpacks"
buildCommand = "npm install && npm run build"

[deploy]
startCommand = "npx serve dist -s -l $PORT"
healthcheckPath = "/"
restartPolicyType = "on-failure"
```

### 5. Добавьте в `package.json`
```json
{
  "scripts": {
    "start": "serve dist -s -l 3000"
  },
  "dependencies": {
    "serve": "^14.2.0"
  }
}
```

### 6. Деплой
```bash
railway up
```

## Деплой на Netlify 🌐

### 1. Установите Netlify CLI
```bash
npm install -g netlify-cli
```

### 2. Войдите
```bash
netlify login
```

### 3. Создайте `netlify.toml`
```toml
[build]
  command = "npm run build"
  publish = "dist"

[[redirects]]
  from = "/*"
  to = "/index.html"
  status = 200

[[headers]]
  for = "/assets/*"
  [headers.values]
    Cache-Control = "public, max-age=31536000, immutable"
```

### 4. Деплой
```bash
cd webapp
netlify deploy --prod
```

## Деплой на GitHub Pages 📄

### 1. Установите gh-pages
```bash
npm install --save-dev gh-pages
```

### 2. Добавьте в `package.json`
```json
{
  "homepage": "https://username.github.io/fudly-bot",
  "scripts": {
    "predeploy": "npm run build",
    "deploy": "gh-pages -d dist"
  }
}
```

### 3. Обновите `vite.config.js`
```javascript
export default defineConfig({
  base: '/fudly-bot/',
  // ... остальное
})
```

### 4. Деплой
```bash
npm run deploy
```

## Подключение к Telegram боту

После деплоя обновите URL в вашем боте:

### 1. Откройте `bot.py`
```python
WEBAPP_URL = "https://your-domain.vercel.app"
```

### 2. Создайте кнопку WebApp
```python
from aiogram.types import WebAppInfo, InlineKeyboardButton, InlineKeyboardMarkup

webapp_button = InlineKeyboardButton(
    text="🛒 Ochish", 
    web_app=WebAppInfo(url=WEBAPP_URL)
)
keyboard = InlineKeyboardMarkup(inline_keyboard=[[webapp_button]])

await message.answer("Do'kondan buyurtma bering:", reply_markup=keyboard)
```

### 3. Перезапустите бота
```bash
python bot.py
```

## Переменные окружения

### Vercel
```bash
vercel env add VITE_API_URL
vercel env add VITE_BOT_TOKEN
```

### Railway
```bash
railway variables set VITE_API_URL=https://api.example.com
railway variables set VITE_BOT_TOKEN=your_token
```

### Netlify
В панели управления: Site settings → Environment variables

## Проверка после деплоя ✅

1. Откройте URL в браузере
2. Проверьте все страницы:
   - ✅ Главная
   - ✅ Do'konlar
   - ✅ Детали товара
   - ✅ Корзина
   - ✅ Профиль
3. Проверьте в Telegram:
   - Откройте бота
   - Нажмите кнопку WebApp
   - Проверьте все функции

## Мониторинг

### Vercel
- Dashboard: https://vercel.com/dashboard
- Логи деплоя
- Аналитика посещений

### Railway
- Dashboard: https://railway.app/dashboard
- Логи в реальном времени
- Метрики CPU/Memory

## Обновление после изменений

```bash
# 1. Внесите изменения в код
# 2. Закоммитьте
git add .
git commit -m "Update features"
git push

# 3. Деплой произойдет автоматически (если настроен CI/CD)
# Или вручную:
vercel deploy --prod
# или
railway up
# или
netlify deploy --prod
```

## Troubleshooting 🔧

### Ошибка 404 на страницах
Добавьте redirects/rewrites (см. конфиги выше)

### Не работает в Telegram
1. Проверьте HTTPS (обязательно!)
2. Проверьте CSP headers
3. Убедитесь что Telegram WebApp SDK подключен

### Медленная загрузка
1. Проверьте размер bundle: `npm run build -- --report`
2. Оптимизируйте изображения
3. Включите кэширование

### Ошибки CORS
Настройте backend для разрешения вашего домена:
```python
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://your-domain.vercel.app"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

## Полезные ссылки 🔗

- Vercel Docs: https://vercel.com/docs
- Railway Docs: https://docs.railway.app
- Netlify Docs: https://docs.netlify.com
- Telegram WebApp: https://core.telegram.org/bots/webapps
- Vite Docs: https://vitejs.dev

---

**Готово! Ваше приложение в продакшне! 🎉**
