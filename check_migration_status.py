"""
Проверка состояния миграции и базы данных после деплоя.
Запускать: railway run python check_migration_status.py
"""
import os
import sys

import psycopg

# Get DATABASE_URL from environment
DB_URL = os.environ.get("DATABASE_URL")

if not DB_URL:
    print("❌ DATABASE_URL не установлен!")
    sys.exit(1)

print("=" * 80)
print("🔍 ПРОВЕРКА СОСТОЯНИЯ МИГРАЦИИ")
print("=" * 80)

try:
    conn = psycopg.connect(DB_URL, connect_timeout=10)
    cursor = conn.cursor()

    # 1. Проверка текущей версии Alembic
    print("\n📋 1. Текущая версия миграции:")
    try:
        cursor.execute("SELECT version_num FROM alembic_version")
        version = cursor.fetchone()
        if version:
            print(f"   ✅ Версия: {version[0]}")
        else:
            print("   ⚠️  Версия не найдена (возможно, миграции не применены)")
    except Exception as e:
        print(f"   ❌ Ошибка: {e}")

    # 2. Проверка типов данных в таблице offers
    print("\n📊 2. Типы данных в таблице offers:")
    cursor.execute(
        """
        SELECT column_name, data_type, character_maximum_length
        FROM information_schema.columns
        WHERE table_name = 'offers'
        AND column_name IN ('available_from', 'available_until', 'expiry_date', 'original_price', 'discount_price')
        ORDER BY column_name
    """
    )

    columns = cursor.fetchall()
    expected_types = {
        "available_from": "time without time zone",
        "available_until": "time without time zone",
        "expiry_date": "date",
        "original_price": "integer",
        "discount_price": "integer",
    }

    all_correct = True
    for col in columns:
        col_name = col[0]
        data_type = col[1]
        expected = expected_types.get(col_name, "unknown")

        if data_type == expected:
            print(f"   ✅ {col_name}: {data_type}")
        else:
            print(f"   ❌ {col_name}: {data_type} (ожидалось: {expected})")
            all_correct = False

    # 3. Проверка данных в offers
    print("\n📦 3. Примеры данных из offers:")
    cursor.execute(
        """
        SELECT offer_id, available_from, available_until, expiry_date,
               original_price, discount_price
        FROM offers
        LIMIT 3
    """
    )
    offers = cursor.fetchall()
    if offers:
        for offer in offers:
            print(f"   Offer #{offer[0]}:")
            print(f"     available_from: {offer[1]} (type: {type(offer[1]).__name__})")
            print(f"     available_until: {offer[2]} (type: {type(offer[2]).__name__})")
            print(f"     expiry_date: {offer[3]} (type: {type(offer[3]).__name__})")
            print(f"     original_price: {offer[4]} (type: {type(offer[4]).__name__})")
            print(f"     discount_price: {offer[5]} (type: {type(offer[5]).__name__})")
    else:
        print("   ⚠️  Нет данных в таблице offers")

    # 4. Проверка количества соединений
    print("\n🔌 4. Активные соединения PostgreSQL:")
    cursor.execute(
        """
        SELECT count(*), state
        FROM pg_stat_activity
        WHERE datname = current_database()
        GROUP BY state
        ORDER BY count(*) DESC
    """
    )
    connections = cursor.fetchall()
    total_conns = 0
    for conn_info in connections:
        print(f"   {conn_info[1] or 'unknown'}: {conn_info[0]}")
        total_conns += conn_info[0]
    print(f"   Всего соединений: {total_conns}")

    # 5. Проверка индексов
    print("\n🔍 5. Индексы на таблице offers:")
    cursor.execute(
        """
        SELECT indexname, indexdef
        FROM pg_indexes
        WHERE tablename = 'offers'
        ORDER BY indexname
    """
    )
    indexes = cursor.fetchall()
    for idx in indexes:
        print(f"   ✅ {idx[0]}")

    print("\n" + "=" * 80)
    if all_correct:
        print("✅ ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ!")
        print("=" * 80)
        sys.exit(0)
    else:
        print("⚠️  ОБНАРУЖЕНЫ ПРОБЛЕМЫ - НУЖНО ЗАПУСТИТЬ МИГРАЦИЮ!")
        print("💡 Выполните: railway run alembic upgrade head")
        print("=" * 80)
        sys.exit(1)

except Exception as e:
    print(f"\n❌ ОШИБКА ПОДКЛЮЧЕНИЯ К БД: {e}")
    sys.exit(1)
finally:
    if "conn" in locals():
        conn.close()
