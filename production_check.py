#!/usr/bin/env python3
"""
Production readiness checker for Fudly Bot.
Validates security, performance, reliability and monitoring.
"""
import os
import sys
import sqlite3
import tempfile
from pathlib import Path

def check_security():
    """Check security configurations."""
    print("🔒 ПРОВЕРКА БЕЗОПАСНОСТИ")
    print("-" * 50)
    
    # Check for hardcoded secrets
    secrets_found = []
    python_files = list(Path('.').glob('**/*.py'))
    
    dangerous_patterns = ['token=', 'password=', 'secret=', 'key=']
    
    for file_path in python_files:
        if any(folder in str(file_path) for folder in ['.venv', 'backup_', '__pycache__', '.git']):
            continue
            
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read().lower()
                for pattern in dangerous_patterns:
                    if pattern in content and 'os.getenv' not in content:
                        secrets_found.append(f"{file_path}: {pattern}")
        except:
            continue
    
    if secrets_found:
        print("❌ Найдены потенциальные хардкоденные секреты:")
        for secret in secrets_found:
            print(f"   {secret}")
        return False
    else:
        print("✅ Хардкоденные секреты не найдены")
    
    # Check .gitignore
    if os.path.exists('.gitignore'):
        try:
            with open('.gitignore', 'r', encoding='utf-8') as f:
                gitignore_content = f.read()
                if '.env' in gitignore_content and '*.db' in gitignore_content:
                    print("✅ .gitignore корректно настроен")
                else:
                    print("⚠️ .gitignore может быть неполным")
        except Exception as e:
            print(f"⚠️ Ошибка чтения .gitignore: {e}")
    else:
        print("❌ .gitignore не найден")
        return False
    
    # Check environment variables
    required_vars = ['TELEGRAM_BOT_TOKEN', 'ADMIN_ID']
    missing = []
    
    for var in required_vars:
        if not os.getenv(var):
            missing.append(var)
    
    if missing:
        print(f"⚠️ Отсутствуют переменные окружения: {', '.join(missing)}")
        print("   (Это нормально для проверки, но нужно для работы)")
    else:
        print("✅ Все необходимые переменные окружения настроены")
    
    return True


def check_performance():
    """Check performance optimizations."""
    print("\n⚡ ПРОВЕРКА ПРОИЗВОДИТЕЛЬНОСТИ")
    print("-" * 50)
    
    # Check database indexes
    try:
        from database import Database
        db = Database()
        conn = db.get_connection()
        cursor = conn.cursor()
        
        cursor.execute("SELECT name FROM sqlite_master WHERE type='index' AND name NOT LIKE 'sqlite_%'")
        indexes = cursor.fetchall()
        
        print(f"✅ Индексы в БД: {len(indexes)}")
        expected_indexes = ['idx_stores_city_status', 'idx_offers_store_status', 'idx_bookings_user']
        
        found_indexes = [idx[0] for idx in indexes]
        for expected in expected_indexes:
            if expected in found_indexes:
                print(f"   ✅ {expected}")
            else:
                print(f"   ❌ Отсутствует: {expected}")
        
        conn.close()
        
    except Exception as e:
        print(f"❌ Ошибка проверки БД: {e}")
        return False
    
    # Check caching
    try:
        from cache import cache
        cache.set('test_key', 'test_value', ex=1)
        result = cache.get('test_key')
        if result == 'test_value':
            print("✅ Кэширование работает")
        else:
            print("⚠️ Проблемы с кэшированием")
    except Exception as e:
        print(f"⚠️ Кэширование недоступно: {e}")
    
    # Check connection pooling
    try:
        from db_pool import SQLitePool
        pool = SQLitePool('test.db', maxsize=2)
        conn1 = pool.getconn()
        conn2 = pool.getconn()
        conn1.close()
        conn2.close()
        print("✅ Пулинг соединений работает")
        # Cleanup
        try:
            os.unlink('test.db')
        except:
            pass
    except Exception as e:
        print(f"❌ Проблемы с пулингом: {e}")
        return False
    
    return True


def check_reliability():
    """Check reliability features."""
    print("\n🛡️ ПРОВЕРКА НАДЕЖНОСТИ")
    print("-" * 50)
    
    # Check exception handling in main files
    try:
        with open('bot.py', 'r', encoding='utf-8') as f:
            bot_content = f.read()
            
        try_except_count = bot_content.count('try:')
        logger_count = bot_content.count('logger.')
        
        print(f"✅ Блоков try/except: {try_except_count}")
        print(f"✅ Вызовов логгера: {logger_count}")
        
        if try_except_count > 5 and logger_count > 5:
            print("✅ Обработка ошибок выглядит достаточной")
        else:
            print("⚠️ Может потребоваться больше обработки ошибок")
            
    except Exception as e:
        print(f"❌ Ошибка анализа кода: {e}")
        return False
    
    # Check production utils
    if os.path.exists('production_utils.py'):
        print("✅ Утилиты для продакшена найдены")
    else:
        print("❌ Утилиты для продакшена отсутствуют")
        return False
    
    return True


def check_monitoring():
    """Check monitoring capabilities."""
    print("\n📊 ПРОВЕРКА МОНИТОРИНГА")
    print("-" * 50)
    
    # Check logging configuration
    try:
        from logging_config import logger
        logger.info("Test log message")
        print("✅ Логирование настроено")
    except Exception as e:
        print(f"⚠️ Проблемы с логированием: {e}")
    
    # Check background tasks
    try:
        from background import start_background_tasks
        print("✅ Фоновые задачи доступны")
    except Exception as e:
        print(f"❌ Фоновые задачи недоступны: {e}")
        return False
    
    # Check security monitoring
    try:
        from security import rate_limiter, validator
        print("✅ Мониторинг безопасности доступен")
    except Exception as e:
        print(f"❌ Мониторинг безопасности недоступен: {e}")
    
    return True


def check_deployment_readiness():
    """Check deployment readiness."""
    print("\n🚀 ГОТОВНОСТЬ К ДЕПЛОЮ")
    print("-" * 50)
    
    # Check required files
    required_files = [
        'bot.py', 'database.py', 'requirements.txt', 
        '.env.example', '.gitignore', 'PRODUCTION.md'
    ]
    
    missing_files = []
    for file in required_files:
        if os.path.exists(file):
            print(f"✅ {file}")
        else:
            print(f"❌ Отсутствует: {file}")
            missing_files.append(file)
    
    if missing_files:
        print(f"\n❌ Отсутствуют файлы: {', '.join(missing_files)}")
        return False
    
    # Check requirements.txt
    try:
        with open('requirements.txt', 'r') as f:
            requirements = f.read()
            
        essential_packages = ['aiogram', 'python-dotenv']
        for package in essential_packages:
            if package in requirements:
                print(f"✅ Зависимость: {package}")
            else:
                print(f"⚠️ Возможно отсутствует: {package}")
                
    except Exception as e:
        print(f"❌ Ошибка проверки requirements.txt: {e}")
        return False
    
    return True


def main():
    """Run all production readiness checks."""
    print("🔍 ПРОВЕРКА ГОТОВНОСТИ К ПРОДАКШЕНУ")
    print("=" * 60)
    
    checks = [
        ("Безопасность", check_security),
        ("Производительность", check_performance), 
        ("Надежность", check_reliability),
        ("Мониторинг", check_monitoring),
        ("Готовность к деплою", check_deployment_readiness)
    ]
    
    results = {}
    
    for check_name, check_func in checks:
        try:
            results[check_name] = check_func()
        except Exception as e:
            print(f"❌ Ошибка в проверке {check_name}: {e}")
            results[check_name] = False
    
    # Summary
    print("\n" + "=" * 60)
    print("📋 СВОДКА РЕЗУЛЬТАТОВ")
    print("=" * 60)
    
    passed = 0
    total = len(results)
    
    for check, result in results.items():
        status = "✅ ПРОШЛА" if result else "❌ НЕ ПРОШЛА"
        print(f"{check:<20} {status}")
        if result:
            passed += 1
    
    print("-" * 60)
    print(f"Пройдено проверок: {passed}/{total}")
    
    if passed == total:
        print("\n🎉 БОТ ГОТОВ К ПРОДАКШЕНУ!")
        print("Можно загружать в GitHub и деплоить в PythonAnywhere")
        return True
    else:
        print(f"\n⚠️ НЕОБХОДИМО ИСПРАВИТЬ {total - passed} ПРОБЛЕМ(Ы)")
        return False


if __name__ == '__main__':
    success = main()
    sys.exit(0 if success else 1)