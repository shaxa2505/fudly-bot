# PowerShell версия скрипта установки переменных Railway
# Запуск: .\setup_railway_env.ps1

Write-Host "🔧 Установка переменных окружения в Railway..." -ForegroundColor Cyan

# ВАЖНО: Замените значения на свои!
$TELEGRAM_BOT_TOKEN = "ВАШ_ТОКЕН_ОТ_BOTFATHER"
$ADMIN_ID = "ВАШ_TELEGRAM_ID"

Write-Host "Проверка Railway CLI..." -ForegroundColor Yellow
if (-not (Get-Command railway -ErrorAction SilentlyContinue)) {
    Write-Host "❌ Railway CLI не установлен!" -ForegroundColor Red
    Write-Host "Установите: npm install -g @railway/cli" -ForegroundColor Yellow
    exit 1
}

Write-Host "✅ Railway CLI найден" -ForegroundColor Green

# Проверка текущего проекта
Write-Host "`nТекущий проект:" -ForegroundColor Cyan
railway status

$confirmation = Read-Host "`nПродолжить установку переменных? (y/n)"
if ($confirmation -ne 'y') {
    exit 0
}

# Установка переменных
Write-Host "`n📝 Установка TELEGRAM_BOT_TOKEN..." -ForegroundColor Yellow
railway variables set "TELEGRAM_BOT_TOKEN=$TELEGRAM_BOT_TOKEN"

Write-Host "📝 Установка ADMIN_ID..." -ForegroundColor Yellow
railway variables set "ADMIN_ID=$ADMIN_ID"

Write-Host "📝 Установка DB pool settings..." -ForegroundColor Yellow
railway variables set "DB_MIN_CONN=5"
railway variables set "DB_MAX_CONN=20"

Write-Host "📝 Установка SKIP_DB_INIT..." -ForegroundColor Yellow
railway variables set "SKIP_DB_INIT=1"

Write-Host "📝 Установка LOG_LEVEL..." -ForegroundColor Yellow
railway variables set "LOG_LEVEL=INFO"

Write-Host "`n✅ Переменные установлены!" -ForegroundColor Green
Write-Host "`n🔄 Railway автоматически перезапустит сервисы..." -ForegroundColor Cyan
Write-Host "📊 Проверьте логи через 1-2 минуты: railway logs" -ForegroundColor Yellow
