#!/bin/bash

# Fudly WebApp Deploy Script
# Быстрый деплой на Vercel

echo "🚀 Fudly WebApp Deploy Script"
echo "================================"

# Bump partner panel static version to bust WebView cache
PANEL_INDEX="partner-panel/index.html"
if [ -f "$PANEL_INDEX" ]; then
    VERSION="$(date +%Y%m%d%H%M%S)"
    perl -pi -e "s/\?v=[0-9.]+/\?v=$VERSION/g" "$PANEL_INDEX"
    echo "Updated partner panel asset version to $VERSION"
fi


# Проверка директории
if [ ! -f "package.json" ]; then
    echo "❌ Ошибка: Запустите скрипт из папки webapp/"
    exit 1
fi

# Установка зависимостей
echo "📦 Установка зависимостей..."
npm install

# Сборка
echo "🔨 Сборка production build..."
npm run build

if [ $? -ne 0 ]; then
    echo "❌ Ошибка сборки!"
    exit 1
fi

# Проверка размера
echo "📊 Размер build:"
du -sh dist

# Деплой на Vercel
echo "🚀 Деплой на Vercel..."
vercel deploy --prod

if [ $? -eq 0 ]; then
    echo "✅ Деплой успешен!"
    echo "🎉 Приложение опубликовано!"
else
    echo "❌ Ошибка деплоя!"
    exit 1
fi
