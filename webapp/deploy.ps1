# Fudly WebApp Deploy Script (PowerShell)
# Быстрый деплой на Vercel

Write-Host "🚀 Fudly WebApp Deploy Script" -ForegroundColor Green
Write-Host "================================" -ForegroundColor Green

# Bump partner panel static version to bust WebView cache
$panelIndex = "partner-panel/index.html"
if (Test-Path $panelIndex) {
    $version = Get-Date -Format "yyyyMMddHHmmss"
    $content = Get-Content $panelIndex -Raw
    $content = $content -replace "\?v=[0-9.]+", "?v=$version"
    Set-Content -Path $panelIndex -Value $content
    Write-Host "Updated partner panel asset version to $version" -ForegroundColor Cyan
}


# Проверка директории
if (-not (Test-Path "package.json")) {
    Write-Host "❌ Ошибка: Запустите скрипт из папки webapp/" -ForegroundColor Red
    exit 1
}

# Установка зависимостей
Write-Host "`n📦 Установка зависимостей..." -ForegroundColor Cyan
npm install

# Сборка
Write-Host "`n🔨 Сборка production build..." -ForegroundColor Cyan
npm run build

if ($LASTEXITCODE -ne 0) {
    Write-Host "❌ Ошибка сборки!" -ForegroundColor Red
    exit 1
}

# Проверка размера
Write-Host "`n📊 Размер build:" -ForegroundColor Cyan
$size = (Get-ChildItem dist -Recurse | Measure-Object -Property Length -Sum).Sum / 1MB
Write-Host "$([math]::Round($size, 2)) MB"

# Деплой на Vercel
Write-Host "`n🚀 Деплой на Vercel..." -ForegroundColor Cyan
vercel deploy --prod

if ($LASTEXITCODE -eq 0) {
    Write-Host "`n✅ Деплой успешен!" -ForegroundColor Green
    Write-Host "🎉 Приложение опубликовано!" -ForegroundColor Green
} else {
    Write-Host "`n❌ Ошибка деплоя!" -ForegroundColor Red
    exit 1
}
