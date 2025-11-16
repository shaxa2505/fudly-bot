param(
    [string]$Token = $env:TELEGRAM_BOT_TOKEN,
    [string]$AdminId = $env:ADMIN_ID,
    [int]$HealthPort = 8081
)

if (-not $Token) { Write-Error 'Set TELEGRAM_BOT_TOKEN env or pass -Token'; exit 1 }
if (-not $AdminId) { $AdminId = '1' }

$env:USE_WEBHOOK = 'false'
$env:POLLING_HEALTH_PORT = "$HealthPort"
$env:DISABLE_LOCK = '1'
$env:ADMIN_ID = "$AdminId"

Write-Host "Starting Fudly bot in polling mode..."

Get-Process python -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
Start-Sleep -Seconds 1
python bot.py
