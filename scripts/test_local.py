#!/usr/bin/env python3
"""
Скрипт для локального тестирования с Railway PostgreSQL
Запускает бот локально, но с подключением к production БД
"""
import os
import sys
from dotenv import load_dotenv

# Загружаем переменные окружения
load_dotenv()

print("=" * 80)
print("🧪 ЛОКАЛЬНОЕ ТЕСТИРОВАНИЕ С RAILWAY DATABASE")
print("=" * 80)

# Проверяем наличие DATABASE_URL
db_url = os.getenv('DATABASE_URL')
if not db_url:
    print("\n❌ ОШИБКА: DATABASE_URL не найден в .env файле!")
    print("\n📋 Чтобы подключиться к Railway PostgreSQL:")
    print("1. Откройте Railway Dashboard")
    print("2. Скопируйте DATABASE_URL из Variables")
    print("3. Добавьте в .env файл:")
    print("   DATABASE_URL=postgresql://...")
    sys.exit(1)

print(f"\n✅ DATABASE_URL найден")
print(f"📊 БД: {db_url.split('@')[1].split('/')[0] if '@' in db_url else 'unknown'}")

# Отключаем webhook для локального тестирования
os.environ['USE_WEBHOOK'] = 'false'
print("🔧 Webhook отключен (используется polling)")

# Проверяем токен бота
token = os.getenv('TELEGRAM_BOT_TOKEN')
if not token:
    print("\n❌ ОШИБКА: TELEGRAM_BOT_TOKEN не найден!")
    sys.exit(1)

print(f"✅ Bot token найден: ...{token[-10:]}")

admin_id = os.getenv('ADMIN_ID')
if admin_id:
    print(f"👑 Admin ID: {admin_id}")

print("\n" + "=" * 80)
print("🚀 Запускаю бот в режиме локального тестирования...")
print("=" * 80)
print("\n💡 ПОДСКАЗКИ:")
print("   - Все ошибки будут видны в реальном времени")
print("   - Используется PostgreSQL с Railway")
print("   - Для остановки: Ctrl+C")
print("   - Логи сохраняются в консоль\n")
print("=" * 80 + "\n")

if __name__ == "__main__":
    # Импортируем и запускаем бот
    try:
        import bot
    except KeyboardInterrupt:
        print("\n\n👋 Тестирование остановлено пользователем")
        sys.exit(0)
    except Exception as e:
        print(f"\n\n❌ КРИТИЧЕСКАЯ ОШИБКА: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
