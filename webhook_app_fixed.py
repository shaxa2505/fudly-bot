# webhook_app.py - Flask приложение для webhook режима
from flask import Flask, request, jsonify
import asyncio
import json
import os
import sys

# Добавляем путь к нашему боту
sys.path.append('/home/yourusername/fudly-telegram-bot')

from aiogram import Bot, Dispatcher
from aiogram.types import Update
from dotenv import load_dotenv

# Загружаем переменные окружения
load_dotenv()

app = Flask(__name__)

# Инициализация бота
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# Импортируем обработчики из основного бота
try:
    from bot import setup_handlers
    setup_handlers(dp)
except ImportError:
    print("Warning: Could not import handlers from bot.py")

@app.route('/webhook', methods=['POST'])
def webhook():
    """Обработка входящих обновлений от Telegram"""
    try:
        update_dict = request.get_json()
        update = Update.model_validate(update_dict)
        
        # Обрабатываем обновление асинхронно
        asyncio.run(dp.feed_update(bot, update))
        
        return jsonify({"status": "ok"})
    except Exception as e:
        print(f"Webhook error: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/health')
def health():
    """Проверка работоспособности"""
    return jsonify({
        "status": "healthy",
        "bot_token": "configured" if BOT_TOKEN else "missing"
    })

if __name__ == '__main__':
    app.run(debug=False)