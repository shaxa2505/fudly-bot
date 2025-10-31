# 🚀 Деплой на Render.com

Render.com требует чтобы приложение слушало на HTTP порту. Этот файл содержит инструкции для успешного деплоя.

## 📋 Подготовка к деплою

### 1. Файлы для Render
- ✅ `render_app.py` - Основное приложение для Render  
- ✅ `Procfile` - Конфигурация процесса (`web: python render_app.py`)
- ✅ `requirements.txt` - Зависимости с aiohttp и flask
- ✅ `runtime.txt` - Версия Python

### 2. Environment Variables на Render
Добавьте эти переменные в настройках Render:

```env
TELEGRAM_BOT_TOKEN=ваш_токен_бота
ADMIN_ID=ваш_telegram_id
DATABASE_PATH=fudly.db
LOG_LEVEL=INFO
PRODUCTION_FEATURES=true
```

### 3. Webhook URL
Render автоматически предоставляет:
- `RENDER_EXTERNAL_URL` - URL вашего приложения
- `PORT` - порт на котором слушать

## 🛠 Настройка на Render

### Шаг 1: Создание Web Service
1. Зайдите на [render.com](https://render.com)
2. Создайте новый **Web Service**
3. Подключите ваш GitHub репозиторий

### Шаг 2: Настройки сервиса
- **Name**: `fudly-bot`
- **Region**: Выберите ближайший регион
- **Branch**: `main`
- **Runtime**: `Python 3`
- **Build Command**: `pip install -r requirements.txt`
- **Start Command**: `python render_app.py`

### Шаг 3: Environment Variables
В разделе Environment добавьте:
```
TELEGRAM_BOT_TOKEN=7969096859:AAGQCRAKTHCPOVqEcyzbLabl_neyH6QWEzw
ADMIN_ID=253445521
DATABASE_PATH=fudly.db
LOG_LEVEL=INFO
```

### Шаг 4: Деплой
1. Нажмите **Create Web Service**
2. Дождитесь завершения сборки
3. Проверьте логи на наличие ошибок

## 📊 Проверка работы

### Health Check
После деплоя откройте:
```
https://your-app-name.onrender.com/health
```

Должны увидеть:
```json
{
  "status": "ok",
  "service": "fudly-bot",
  "webhook_url": "https://your-app-name.onrender.com/webhook"
}
```

### Логи
В панели Render проверьте логи:
- ✅ "Webhook set to: https://..."
- ✅ "Bot started successfully!"
- ✅ "Starting Fudly Bot on port 10000"

## 🐛 Решение проблем

### Ошибка "Port timeout"
- ✅ Исправлено: используем `render_app.py` вместо `bot.py`
- ✅ Приложение слушает на `0.0.0.0:PORT`

### Ошибка импортов
Если модули не найдены, проверьте `requirements.txt`:
```
aiogram>=3.0.0
python-dotenv>=0.19.0
aiohttp>=3.8.0
```

### Ошибка webhook
Проверьте Environment Variables:
- `TELEGRAM_BOT_TOKEN` должен быть установлен
- URL должен быть HTTPS

### База данных
- SQLite файл создается автоматически
- Данные сохраняются между перезапусками
- Backup происходит автоматически (если включен)

## 🔄 Обновления

При обновлении кода:
1. Push в GitHub
2. Render автоматически пересоберет
3. Бот перезапустится с новым кодом

## 📈 Мониторинг

### Metrics на Render
- CPU usage
- Memory usage  
- Response times
- Error rates

### Логи бота
Все логи доступны в панели Render в реальном времени.

## 🎯 Production Ready

Бот включает:
- ✅ Connection pooling
- ✅ Caching (in-memory)
- ✅ Rate limiting
- ✅ Input validation
- ✅ Background tasks
- ✅ Structured logging
- ✅ Error handling
- ✅ Webhook support
- ✅ Health checks

---

**🚀 Готово к продакшену!** Ваш бот теперь работает на Render.com с полной поддержкой webhook и мониторинга.