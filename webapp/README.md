# Fudly Mini App

Telegram мини-приложение для сервиса Fudly - покупка продуктов со скидкой.

## Запуск

```bash
# Установка зависимостей
npm install

# Запуск в режиме разработки
npm run dev

# Сборка для продакшна
npm run build

# Предпросмотр сборки
npm run preview
```

## Деплой на Vercel

```bash
# Установить Vercel CLI
npm i -g vercel

# Деплой
vercel --prod
```

## Переменные окружения

Создайте файл `.env`:

```
VITE_API_URL=https://your-api-url.railway.app/api/v1
```

## Технологии

- React 18
- Vite
- Axios
- Telegram WebApp SDK
