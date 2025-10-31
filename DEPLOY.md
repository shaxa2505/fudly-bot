# 🚀 Инструкция по деплою бота Fudly

## 📋 Требования

- Python 3.11+
- SQLite3 (встроен в Python)
- Токен Telegram бота от @BotFather
- Ваш Telegram User ID (получить у @userinfobot)

## 🛠 Локальный запуск

### 1. Клонируйте репозиторий
```bash
git clone <your-repo-url>
cd проект
```

### 2. Создайте виртуальное окружение
```bash
python -m venv .venv
```

### 3. Активируйте виртуальное окружение

**Windows (PowerShell):**
```powershell
.venv\Scripts\Activate.ps1
```

**Windows (CMD):**
```cmd
.venv\Scripts\activate.bat
```

**Linux/macOS:**
```bash
source .venv/bin/activate
```

### 4. Установите зависимости
```bash
pip install -r requirements.txt
```

### 5. Настройте переменные окружения

Скопируйте `.env.example` в `.env`:
```bash
copy .env.example .env  # Windows
cp .env.example .env    # Linux/macOS
```

Отредактируйте `.env` и укажите:
```env
TELEGRAM_BOT_TOKEN=ваш_токен_от_botfather
ADMIN_ID=ваш_telegram_id
```

### 6. Запустите бота
```bash
python bot.py
```

## ☁️ Деплой на Heroku

### 1. Установите Heroku CLI
Скачайте с https://devcenter.heroku.com/articles/heroku-cli

### 2. Войдите в Heroku
```bash
heroku login
```

### 3. Создайте приложение
```bash
heroku create fudly-bot-uzbekistan
```

### 4. Установите переменные окружения
```bash
heroku config:set TELEGRAM_BOT_TOKEN=ваш_токен
heroku config:set ADMIN_ID=ваш_id
```

### 5. Деплой
```bash
git add .
git commit -m "Deploy Fudly bot"
git push heroku main
```

### 6. Запустите worker
```bash
heroku ps:scale worker=1
```

### 7. Проверьте логи
```bash
heroku logs --tail
```

## 🐳 Деплой на VPS (Docker)

### 1. Создайте Dockerfile
```dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python", "bot.py"]
```

### 2. Создайте docker-compose.yml
```yaml
version: '3.8'

services:
  bot:
    build: .
    restart: unless-stopped
    env_file:
      - .env
    volumes:
      - ./fudly.db:/app/fudly.db
```

### 3. Запустите контейнер
```bash
docker-compose up -d
```

### 4. Просмотр логов
```bash
docker-compose logs -f
```

## 🖥 Деплой на VPS (systemd)

### 1. Скопируйте проект на сервер
```bash
scp -r . user@your-server:/home/user/fudly-bot
```

### 2. Подключитесь к серверу
```bash
ssh user@your-server
cd /home/user/fudly-bot
```

### 3. Установите зависимости
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 4. Создайте .env файл
```bash
nano .env
```

### 5. Создайте systemd service

Создайте файл `/etc/systemd/system/fudly-bot.service`:
```ini
[Unit]
Description=Fudly Telegram Bot
After=network.target

[Service]
Type=simple
User=your-username
WorkingDirectory=/home/user/fudly-bot
Environment="PATH=/home/user/fudly-bot/.venv/bin"
ExecStart=/home/user/fudly-bot/.venv/bin/python bot.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

### 6. Запустите сервис
```bash
sudo systemctl daemon-reload
sudo systemctl enable fudly-bot
sudo systemctl start fudly-bot
```

### 7. Проверьте статус
```bash
sudo systemctl status fudly-bot
```

### 8. Просмотр логов
```bash
sudo journalctl -u fudly-bot -f
```

## 📊 Управление ботом

### Остановка бота
```bash
# Heroku
heroku ps:scale worker=0

# Docker
docker-compose down

# systemd
sudo systemctl stop fudly-bot
```

### Перезапуск бота
```bash
# Heroku
heroku restart

# Docker
docker-compose restart

# systemd
sudo systemctl restart fudly-bot
```

### Обновление кода
```bash
# Heroku
git pull
git push heroku main

# Docker
git pull
docker-compose down
docker-compose up -d --build

# systemd
git pull
source .venv/bin/activate
pip install -r requirements.txt
sudo systemctl restart fudly-bot
```

## 🔒 Безопасность

1. **Никогда не коммитьте .env файл!** Он уже в .gitignore
2. Используйте длинные и сложные токены
3. Регулярно обновляйте зависимости: `pip install --upgrade -r requirements.txt`
4. На production используйте HTTPS для вебхуков (если будете их использовать)
5. Ограничьте доступ к серверу через firewall

## 📝 Проверка перед деплоем

- [ ] Токен бота получен от @BotFather
- [ ] Admin ID указан правильно
- [ ] Все зависимости в requirements.txt
- [ ] .env файл НЕ в git репозитории
- [ ] База данных fudly.db создается автоматически
- [ ] Бот работает локально без ошибок
- [ ] Протестированы основные функции

## 🆘 Проблемы и решения

### Бот не отвечает
1. Проверьте токен: `heroku config` или `cat .env`
2. Проверьте логи: `heroku logs --tail` или `journalctl -u fudly-bot -f`
3. Убедитесь что бот запущен: `heroku ps` или `systemctl status fudly-bot`

### Ошибка "Conflict: terminated by other getUpdates request"
Запустите `python reset_webhook.py` для сброса вебхука

### База данных не создается
Проверьте права на запись в директорию бота

### Ошибки импорта
Переустановите зависимости: `pip install -r requirements.txt --force-reinstall`

## 📞 Поддержка

При возникновении проблем:
1. Проверьте логи бота
2. Убедитесь что все зависимости установлены
3. Проверьте правильность .env файла
4. Перезапустите бота

---

**Готово!** Ваш бот Fudly готов к работе! 🎉
