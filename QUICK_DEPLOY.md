# 🚀 Quick Deploy Guide - Render.com

## Что исправлено:
✅ **Port timeout error** - добавлен `render_app.py` с веб-сервером  
✅ **Webhook support** - автоматическая настройка webhook URL  
✅ **Health checks** - endpoints для мониторинга  
✅ **Environment setup** - правильные переменные окружения  

## Быстрый деплой:

### 1. Commit & Push
```bash
git add .
git commit -m "Fix Render deployment - add web server"
git push origin main
```

### 2. Render Settings
- **Service Type**: Web Service
- **Runtime**: Python 3
- **Build Command**: `pip install -r requirements.txt`  
- **Start Command**: `python render_app.py`

### 3. Environment Variables
```
TELEGRAM_BOT_TOKEN=7969096859:AAGQCRAKTHCPOVqEcyzbLabl_neyH6QWEzw
ADMIN_ID=253445521
LOG_LEVEL=INFO
```

### 4. Проверка
После деплоя откройте: `https://your-app.onrender.com/health`

---
**✅ Готово!** Ошибка "Port timeout" исправлена.