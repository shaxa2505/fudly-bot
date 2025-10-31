#!/usr/bin/env python3
"""
Тест Render приложения локально
Запустите этот файл чтобы проверить работу перед деплоем
"""

import os
import sys
import requests
import time
import asyncio
from render_app import create_app
from aiohttp import web
import threading

def test_local():
    """Тест локального запуска"""
    print("🧪 Тестирование Render приложения...")
    
    # Устанавливаем тестовые переменные
    os.environ['PORT'] = '8000'
    os.environ['RENDER_EXTERNAL_URL'] = 'http://localhost:8000'
    
    print("📋 Environment variables:")
    print(f"  PORT: {os.environ.get('PORT')}")
    print(f"  RENDER_EXTERNAL_URL: {os.environ.get('RENDER_EXTERNAL_URL')}")
    print(f"  TELEGRAM_BOT_TOKEN: {'✅ Set' if os.environ.get('TELEGRAM_BOT_TOKEN') else '❌ Missing'}")
    
    # Создаем приложение
    try:
        app = create_app()
        print("✅ App created successfully")
    except Exception as e:
        print(f"❌ Failed to create app: {e}")
        return False
    
    # Запускаем сервер в отдельном потоке
    def run_server():
        try:
            web.run_app(
                app,
                host="localhost",
                port=8000,
                print=None  # Отключаем вывод aiohttp
            )
        except Exception as e:
            print(f"❌ Server error: {e}")
    
    server_thread = threading.Thread(target=run_server, daemon=True)
    server_thread.start()
    
    # Ждем запуска сервера
    print("⏳ Waiting for server to start...")
    time.sleep(3)
    
    # Тестируем endpoints
    test_endpoints = [
        ('Health check', 'http://localhost:8000/health'),
        ('Root endpoint', 'http://localhost:8000/'),
    ]
    
    all_passed = True
    
    for name, url in test_endpoints:
        try:
            response = requests.get(url, timeout=5)
            if response.status_code == 200:
                data = response.json()
                print(f"✅ {name}: {data.get('status', 'unknown')}")
            else:
                print(f"❌ {name}: HTTP {response.status_code}")
                all_passed = False
        except Exception as e:
            print(f"❌ {name}: {e}")
            all_passed = False
    
    if all_passed:
        print("🎉 Все тесты прошли! Готово к деплою на Render.")
    else:
        print("⚠️ Есть ошибки. Проверьте конфигурацию.")
    
    return all_passed

if __name__ == "__main__":
    # Загружаем .env файл
    try:
        from dotenv import load_dotenv
        load_dotenv()
        print("✅ Environment variables loaded from .env")
    except:
        print("⚠️ Could not load .env file")
    
    success = test_local()
    
    if success:
        print("\n🚀 Готово к деплою:")
        print("1. Commit and push to GitHub")
        print("2. Create Web Service on Render")
        print("3. Set environment variables")
        print("4. Deploy!")
    else:
        print("\n🔧 Исправьте ошибки перед деплоем")
    
    sys.exit(0 if success else 1)