import asyncio
import os
from dotenv import load_dotenv
from aiogram import Bot
import aiohttp

load_dotenv()
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

async def force_reset():
    """ПОЛНОСТЬЮ удаляет webhook и все подключения"""
    bot = Bot(token=TOKEN)
    
    try:
        print("🔧 Проверка текущего webhook...")
        webhook_info = await bot.get_webhook_info()
        print(f"📡 Webhook URL: {webhook_info.url or 'НЕТ'}")
        print(f"📊 Pending updates: {webhook_info.pending_update_count}")
        
        if webhook_info.url:
            print(f"\n⚠️ НАЙДЕН WEBHOOK: {webhook_info.url}")
            print("🔧 Удаляем webhook...")
        
        # Удаляем webhook принудительно
        await bot.delete_webhook(drop_pending_updates=True)
        print("✅ Webhook удалён")
        
        # Ждём 3 секунды
        await asyncio.sleep(3)
        
        # Очищаем все updates
        print("🔧 Очистка всех pending updates...")
        offset = 0
        total_cleared = 0
        while True:
            updates = await bot.get_updates(offset=offset, timeout=1)
            if not updates:
                break
            offset = updates[-1].update_id + 1
            total_cleared += len(updates)
            print(f"⚙️ Очищено {total_cleared} обновлений...")
        
        print(f"✅ Всего очищено: {total_cleared} обновлений")
        
        # Проверяем ещё раз
        print("\n🔍 Финальная проверка...")
        webhook_info = await bot.get_webhook_info()
        print(f"📡 Webhook URL: {webhook_info.url or 'ОЧИЩЕНО ✅'}")
        print(f"📊 Pending updates: {webhook_info.pending_update_count}")
        
        print("\n✅ ГОТОВО!")
        print("\n📋 Следующие шаги:")
        print("1. Подождите 10 секунд")
        print("2. Запустите: python bot.py")
        print("\n💡 Если проблема повторится - у вас webhook на другом сервере!")
        
    except Exception as e:
        print(f"❌ Ошибка: {e}")
    finally:
        await bot.session.close()

if __name__ == "__main__":
    asyncio.run(force_reset())
