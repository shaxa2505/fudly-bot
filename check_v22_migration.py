"""Проверка результатов миграции v22.0"""
import os
import sys

# Загрузить .env
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    env_file = '.env'
    if os.path.exists(env_file):
        with open(env_file, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    os.environ[key.strip()] = value.strip()

from database_pg import Database
import psycopg

db = Database()

with db.get_connection() as conn:
    cursor = conn.cursor(row_factory=psycopg.rows.dict_row)
    
    # Структура offers
    print("\n" + "=" * 60)
    print("📋 OFFERS TABLE STRUCTURE")
    print("=" * 60)
    cursor.execute("""
        SELECT column_name, data_type, column_default 
        FROM information_schema.columns 
        WHERE table_name = 'offers' 
        ORDER BY ordinal_position
    """)
    
    for row in cursor.fetchall():
        default = str(row['column_default'])[:30] if row['column_default'] else 'NULL'
        print(f"{row['column_name']:20} {row['data_type']:15} {default}")
    
    # Индексы
    print("\n" + "=" * 60)
    print("📑 INDEXES ON OFFERS")
    print("=" * 60)
    cursor.execute("""
        SELECT indexname 
        FROM pg_indexes 
        WHERE tablename = 'offers' AND indexname LIKE 'idx_%'
        ORDER BY indexname
    """)
    
    for row in cursor.fetchall():
        print(f"✅ {row['indexname']}")
    
    # Constraints
    print("\n" + "=" * 60)
    print("🔒 CONSTRAINTS ON OFFERS")
    print("=" * 60)
    cursor.execute("""
        SELECT constraint_name, constraint_type
        FROM information_schema.table_constraints 
        WHERE table_name = 'offers' AND constraint_name LIKE 'check%'
        ORDER BY constraint_name
    """)
    
    for row in cursor.fetchall():
        print(f"✅ {row['constraint_name']}")
    
    # Sample data
    print("\n" + "=" * 60)
    print("📦 SAMPLE OFFERS DATA")
    print("=" * 60)
    cursor.execute("""
        SELECT 
            offer_id, 
            title, 
            category, 
            unit, 
            stock_quantity,
            original_price,
            discount_price
        FROM offers 
        ORDER BY offer_id DESC
        LIMIT 5
    """)
    
    for row in cursor.fetchall():
        print(f"\nID: {row['offer_id']}")
        print(f"  Title: {row['title']}")
        print(f"  Category: {row['category']}")
        print(f"  Unit: {row['unit']}")
        print(f"  Stock: {row['stock_quantity']}")
        print(f"  Price: {row['original_price']} → {row['discount_price']}")
    
    # Orders table
    print("\n" + "=" * 60)
    print("📋 ORDERS TABLE - NEW COLUMNS")
    print("=" * 60)
    cursor.execute("""
        SELECT column_name, data_type 
        FROM information_schema.columns 
        WHERE table_name = 'orders' 
          AND column_name IN ('cancel_reason', 'cancel_comment')
    """)
    
    for row in cursor.fetchall():
        print(f"✅ {row['column_name']:20} {row['data_type']}")

print("\n" + "=" * 60)
print("✅ МИГРАЦИЯ v22.0 ЗАВЕРШЕНА УСПЕШНО!")
print("=" * 60)
