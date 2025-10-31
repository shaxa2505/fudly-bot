import asyncio
import os
from dotenv import load_dotenv
from aiogram import Bot

load_dotenv()
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

async def fix_conflict():
    """Удаляет webhook и очищает все pending updates принудительно"""
    bot = Bot(token=TOKEN)
    
    try:
        print("🔧 Удаление webhook...")
        await bot.delete_webhook(drop_pending_updates=True)
        print("✅ Webhook удалён")
        
        print("🔧 Очистка pending updates...")
        # Получаем и пропускаем все pending updates
        offset = 0
        while True:
            updates = await bot.get_updates(offset=offset, timeout=1)
            if not updates:
                break
            offset = updates[-1].update_id + 1
            print(f"⚙️ Очищено {len(updates)} обновлений...")
        
        print("✅ Все обновления очищены!")
        print("\n💡 Теперь:")
        print("1. Закройте Telegram на ВСЕХ устройствах (телефон, веб)")
        print("2. Подождите 10 секунд")
        print("3. Запустите: python bot.py")
        
    except Exception as e:
        print(f"❌ Ошибка: {e}")
    finally:
        await bot.session.close()

if __name__ == "__main__":
    asyncio.run(fix_conflict())
