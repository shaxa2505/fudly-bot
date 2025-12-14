# Partner Panel - Telegram Mini App

Веб-панель для партнёров Fudly Bot с удобным управлением товарами, заказами и статистикой.

## 🌟 Возможности

- **📦 Управление товарами**: Добавление, редактирование, удаление товаров через удобную форму
- **📊 CSV импорт**: Массовая загрузка товаров из CSV файла (drag-and-drop)
- **🧾 Заказы**: Просмотр и управление заказами (подтверждение/отмена)
- **📈 Статистика**: Детальная аналитика продаж (сегодня/неделя/месяц/все время)
- **⚙️ Настройки**: Редактирование информации о магазине

## 🛠 Технологии

- **Frontend**: Vanilla JS, HTML5, CSS3
- **UI**: Telegram Mini App Design (CSS Variables)
- **Backend API**: FastAPI (Python)
- **Auth**: Telegram WebApp initData signature validation
- **Deploy**: Vercel (static hosting)

## 📁 Структура файлов

```
webapp/partner-panel/
├── index.html       # HTML структура (4 view: products, orders, stats, settings)
├── styles.css       # Telegram-themed CSS с CSS variables
└── app.js          # JavaScript логика (CRUD, CSV, API calls)
```

## 🚀 Деплой на Vercel

### Шаг 1: Подготовка

```bash
# Убедитесь что файлы в webapp/partner-panel/
cd webapp/partner-panel/
ls  # index.html, styles.css, app.js
```

### Шаг 2: Установка Vercel CLI

```bash
npm install -g vercel
```

### Шаг 3: Деплой

```bash
# Из корня проекта
vercel --prod

# Выберите:
# - Scope: ваш аккаунт
# - Project name: fudly-partner-panel
# - Root directory: webapp/partner-panel
```

### Шаг 4: Настройка переменных окружения

В Vercel Dashboard:
- Settings → Environment Variables
- Добавить: `API_URL` = `https://fudly-bot-production.up.railway.app`

### Шаг 5: Обновить URL в боте

```bash
# В Railway (или .env локально)
PARTNER_PANEL_URL=https://fudly-partner-panel.vercel.app
```

## 🔌 Интеграция с ботом

### Backend API

API endpoints находятся в `app/api/partner_panel.py`:

```python
# Endpoints:
GET  /api/partner/profile      # Профиль партнёра
GET  /api/partner/products     # Список товаров
POST /api/partner/products     # Создать товар
PUT  /api/partner/products/:id # Обновить товар
DELETE /api/partner/products/:id # Удалить товар
POST /api/partner/products/import # Импорт CSV
GET  /api/partner/orders       # Список заказов
POST /api/partner/orders/:id/confirm # Подтвердить заказ
POST /api/partner/orders/:id/cancel  # Отменить заказ
GET  /api/partner/stats        # Статистика
PUT  /api/partner/store        # Настройки магазина
```

### Bot Button

Кнопка "🖥 Веб-панель" добавлена в `app/keyboards/seller.py`:

```python
from aiogram.types import WebAppInfo

def main_menu_seller(lang: str = "ru", webapp_url: str = None):
    builder = ReplyKeyboardBuilder()
    # ... другие кнопки
    if webapp_url:
        builder.button(
            text="🖥 Веб-панель",
            web_app=WebAppInfo(url=webapp_url)
        )
    # ...
```

## 📊 CSV формат импорта

CSV файл должен содержать заголовки:

```csv
title,category,original_price,discount_price,quantity,unit,expiry_date,description
Яблоки Фуджи,fruits,15000,12000,50,кг,2024-12-31,Свежие импортные яблоки
Молоко 3.2%,dairy,8000,7500,100,л,,Фермерское молоко
```

Поля:
- `title` (обязательно) - Название товара
- `category` - Категория (fruits, vegetables, dairy, meat, bakery, other)
- `original_price` - Цена без скидки (опционально)
- `discount_price` (обязательно) - Цена со скидкой
- `quantity` (обязательно) - Количество
- `unit` - Единица измерения (кг, л, шт)
- `expiry_date` - Срок годности (YYYY-MM-DD, опционально)
- `description` - Описание (опционально)

## 🔒 Безопасность

### Telegram WebApp Authentication

Каждый API запрос проверяет `initData` из Telegram:

```javascript
// Frontend (app.js)
const initData = tg.initData;
fetch(url, {
    headers: {
        'Authorization': `tma ${initData}`
    }
});
```

```python
# Backend (partner_panel.py)
def verify_telegram_webapp_data(init_data: str, bot_token: str):
    # HMAC SHA256 signature verification
    # Returns user data if valid
    # Raises HTTPException if invalid
```

### Проверки безопасности:
- ✅ HMAC signature validation
- ✅ User role verification (только sellers)
- ✅ Ownership checks (только свои товары/заказы)
- ✅ CORS настройки (только Telegram домены)

## 🎨 UI/UX Features

### Telegram Theme Integration
Mini App автоматически использует тему Telegram:

```css
:root {
    --tg-theme-bg-color: var(--tg-theme-bg-color, #ffffff);
    --tg-theme-text-color: var(--tg-theme-text-color, #000000);
    --tg-theme-button-color: var(--tg-theme-button-color, #3390ec);
    /* ... */
}
```

### Responsive Design
- Desktop: 280px карточки товаров, 3 колонки
- Mobile: 160px карточки, 2 колонки
- Touch-friendly кнопки (44px height)

### UX Patterns
- **Loading states**: Loader при загрузке данных
- **Empty states**: Friendly сообщения при пустых списках
- **Confirmation**: Confirm перед удалением
- **Feedback**: Telegram alerts для успеха/ошибок

## 🧪 Локальная разработка

### 1. Запуск с Live Server

```bash
# VS Code extension: Live Server
# Правый клик на index.html → Open with Live Server
# http://localhost:5500
```

### 2. Туннель через ngrok (для Telegram)

```bash
ngrok http 5500
# Используйте https URL в Telegram для тестирования
```

### 3. Тестирование API

```bash
# Запустить бота локально
python bot.py

# API доступно на http://localhost:8000
# Swagger docs: http://localhost:8000/api/docs
```

## 📝 Дальнейшее развитие

### Запланированные фичи:
- [ ] Фото товаров (upload через Telegram)
- [ ] Графики статистики (Chart.js)
- [ ] Фильтры по категориям
- [ ] Поиск по товарам
- [ ] Экспорт статистики в Excel
- [ ] Push-уведомления о новых заказах
- [ ] Bulk edit товаров
- [ ] Дублирование товаров

### Оптимизации:
- [ ] Pagination для больших списков
- [ ] Debounce для поиска
- [ ] Cache API responses
- [ ] Service Worker для offline

## 🐛 Отладка

### Проверка API:
```bash
# Проверить что API включён в bot.py
grep "partner_panel" app/api/api_server.py

# Проверить CORS настройки
curl -H "Origin: https://web.telegram.org" \
     -H "Authorization: tma FAKE_DATA" \
     -I https://your-api.railway.app/api/partner/profile
```

### Проверка деплоя:
```bash
# Vercel deployment status
vercel list

# Проверить URL
curl https://fudly-partner-panel.vercel.app
```

## 📞 Поддержка

Issues: GitHub repository
Docs: `docs/MINI_APP_ORDER_SYSTEM.md`
Telegram: @fudly_support
