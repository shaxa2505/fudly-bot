# 🚀 Partner Panel - Vercel Deployment Fix

## Проблема
Партнер панель на Vercel (`https://partner-panel-shaxbozs-projects-d385e345.vercel.app`) не работает, потому что пытается отправлять API запросы на свой собственный домен вместо Railway backend API.

## Решение

### 1. ✅ Исправлены файлы (уже сделано):
- **config.js** - добавлен fallback URL к Railway API
- **index.html** - обновлен meta-тег с Railway API URL
- **build.sh** - создан скрипт для генерации config.js при деплое
- **package.json** - добавлена build команда
- **vercel.json** - настроен buildCommand

### 2. 🔧 Настройка Vercel (ОБЯЗАТЕЛЬНО):

#### Шаг 1: Добавить переменную окружения в Vercel
1. Зайдите в проект на Vercel: https://vercel.com/shaxbozs-projects-d385e345/fudly-partner-panel
2. Settings → Environment Variables
3. Добавьте новую переменную:
   - **Name**: `PARTNER_API_BASE`
   - **Value**: `https://fudly-bot-production.up.railway.app`
   - **Environments**: Production, Preview, Development (выбрать все)

#### Шаг 2: Redeploy
1. Перейдите в Deployments
2. Нажмите на последний деплоймент
3. Нажмите три точки (...) → Redeploy
4. Выберите "Use existing Build Cache" → Redeploy

### 3. 📋 Проверка после деплоя:

Откройте консоль браузера (F12) и проверьте:
```javascript
window.PARTNER_API_BASE
// Должно быть: "https://fudly-bot-production.up.railway.app"
```

Проверьте Network tab - все запросы должны идти на:
```
https://fudly-bot-production.up.railway.app/api/partner/...
```

### 4. 🔍 Альтернативное решение (если не помогло):

Если Vercel build не работает, можно использовать Railway для хостинга партнер панели:

1. В файле `.env` добавьте:
   ```
   PARTNER_PANEL_URL=https://fudly-bot-production.up.railway.app/partner-panel
   ```

2. Railway автоматически будет сервировать партнер панель на `/partner-panel` endpoint

### 5. ✅ Что было исправлено:

#### config.js
```javascript
// ДО:
window.PARTNER_API_BASE = window.PARTNER_API_BASE || '';

// ПОСЛЕ:
window.PARTNER_API_BASE = window.PARTNER_API_BASE || 'https://fudly-bot-production.up.railway.app';
```

#### index.html meta-тег
```html
<!-- ДО: -->
<meta name="api-base" content="">

<!-- ПОСЛЕ: -->
<meta name="api-base" content="https://fudly-bot-production.up.railway.app">
```

## 🎯 Как работает цепочка fallback:

```javascript
const API_BASE =
    window.PARTNER_API_BASE ||                              // 1. Из config.js (генерируется при билде)
    document.querySelector('meta[name="api-base"]')?.getAttribute('content') ||  // 2. Из meta-тега
    window.location.origin;                                 // 3. Fallback (проблемный вариант)
```

Теперь даже если переменная окружения не установлена на Vercel, партнер панель будет работать с hardcoded URL.

## 📝 Примечание:

После деплоя партнер панель должна работать правильно. Убедитесь, что в Railway bot переменная `PARTNER_PANEL_URL` указывает на правильный URL Vercel deployment:

```bash
PARTNER_PANEL_URL=https://partner-panel-shaxbozs-projects-d385e345.vercel.app
```
