import asyncio
from aiogram import Bot
from dotenv import load_dotenv
import os

load_dotenv()
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

async def reset():
    bot = Bot(token=TOKEN)
    await bot.delete_webhook(drop_pending_updates=True)
    print("✅ Webhook удалён, pending updates очищены")
    await bot.session.close()

asyncio.run(reset())
