# 🚀 Fudly WebApp - Быстрые команды

## Development
```bash
npm run dev          # Запуск dev сервера (http://localhost:3000)
```

## Build & Deploy
```bash
npm run build        # Production build
vercel deploy --prod # Деплой на Vercel
```

## Или одной командой:
```powershell
.\deploy.ps1         # Windows
./deploy.sh          # Linux/Mac
```

## Проверка
```bash
npm run build        # Сборка
du -sh dist          # Размер (Linux/Mac)
Get-ChildItem dist   # Размер (Windows)
```

## Git
```bash
git add .
git commit -m "Update webapp"
git push origin main
```

## URL после деплоя
Ваше приложение будет доступно по адресу:
`https://ваш-проект.vercel.app`

## Подключение к боту
В bot.py:
```python
WEBAPP_URL = "https://ваш-проект.vercel.app"
```

---
Всё готово! 🎉
