#!/bin/bash
# Скрипт для установки переменных окружения в Railway
# Запуск: bash setup_railway_env.sh

echo "🔧 Установка переменных окружения в Railway..."

# ВАЖНО: Замените значения на свои!
TELEGRAM_BOT_TOKEN="ВАШ_ТОКЕН_ОТ_BOTFATHER"
ADMIN_ID="ВАШ_TELEGRAM_ID"

echo "Проверка Railway CLI..."
if ! command -v railway &> /dev/null; then
    echo "❌ Railway CLI не установлен!"
    echo "Установите: npm install -g @railway/cli"
    exit 1
fi

echo "✅ Railway CLI найден"

# Убедитесь что вы подключены к правильному проекту
echo "Текущий проект:"
railway status

echo ""
read -p "Продолжить установку переменных? (y/n) " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    exit 1
fi

# Установка переменных
echo "📝 Установка TELEGRAM_BOT_TOKEN..."
railway variables set TELEGRAM_BOT_TOKEN="$TELEGRAM_BOT_TOKEN"

echo "📝 Установка ADMIN_ID..."
railway variables set ADMIN_ID="$ADMIN_ID"

echo "📝 Установка DB pool settings..."
railway variables set DB_MIN_CONN=5
railway variables set DB_MAX_CONN=20

echo "📝 Установка SKIP_DB_INIT..."
railway variables set SKIP_DB_INIT=1

echo "📝 Установка LOG_LEVEL..."
railway variables set LOG_LEVEL=INFO

echo ""
echo "✅ Переменные установлены!"
echo ""
echo "🔄 Railway автоматически перезапустит сервисы..."
echo "📊 Проверьте логи через 1-2 минуты: railway logs"
