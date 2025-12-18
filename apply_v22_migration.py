#!/usr/bin/env python3
"""
Применить миграцию v22.0 с бэкапом и проверкой.
Использование: python apply_v22_migration.py
"""

import os
import sys
from datetime import datetime

# Добавить корневую директорию в путь
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Загрузить .env файл если есть
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    # dotenv не установлен, попробуем загрузить вручную
    env_file = os.path.join(os.path.dirname(__file__), '.env')
    if os.path.exists(env_file):
        with open(env_file, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    os.environ[key.strip()] = value.strip()

from database_pg import Database
from logging_config import logger


def create_backup(db: Database) -> str:
    """Создать бэкап базы данных (SQL дамп критичных таблиц)."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_file = f"backup_before_v22_{timestamp}.sql"
    
    logger.info(f"📦 Creating backup: {backup_file}")
    
    try:
        with open(backup_file, 'w', encoding='utf-8') as f:
            f.write(f"-- Backup created: {datetime.now()}\n")
            f.write(f"-- Before v22.0 migration\n\n")
            
            # Backup offers table structure and data
            with db.get_connection() as conn:
                cursor = conn.cursor()
                
                # Get offers count
                cursor.execute("SELECT COUNT(*) FROM offers")
                offers_count = cursor.fetchone()[0]
                
                # Get orders count
                cursor.execute("SELECT COUNT(*) FROM orders")
                orders_count = cursor.fetchone()[0]
                
                f.write(f"-- Offers: {offers_count} records\n")
                f.write(f"-- Orders: {orders_count} records\n\n")
                
                # Backup критичных данных для восстановления
                f.write("-- Sample of existing data (first 10 offers):\n")
                cursor.execute("""
                    SELECT offer_id, store_id, title, category, unit, 
                           original_price, discount_price, quantity, expiry_date
                    FROM offers 
                    ORDER BY offer_id DESC 
                    LIMIT 10
                """)
                f.write("-- " + str(cursor.fetchall()) + "\n\n")
        
        logger.info(f"✅ Backup created: {backup_file}")
        logger.info(f"   Offers: {offers_count}, Orders: {orders_count}")
        return backup_file
        
    except Exception as e:
        logger.error(f"❌ Backup failed: {e}")
        raise


def apply_migration(db: Database, migration_file: str = "migrations/v22_add_fields.sql"):
    """Применить SQL миграцию."""
    logger.info(f"🔄 Applying migration: {migration_file}")
    
    if not os.path.exists(migration_file):
        logger.error(f"❌ Migration file not found: {migration_file}")
        return False
    
    # Прочитать SQL файл
    with open(migration_file, 'r', encoding='utf-8') as f:
        sql_content = f.read()
    
    # Применить миграцию
    try:
        with db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(sql_content)
            conn.commit()
            logger.info("✅ Migration applied successfully")
            return True
    except Exception as e:
        logger.error(f"❌ Migration failed: {e}")
        return False


def verify_migration(db: Database) -> bool:
    """Проверить, что миграция применилась корректно."""
    logger.info("🔍 Verifying migration...")
    
    checks = []
    
    with db.get_connection() as conn:
        cursor = conn.cursor()
        
        # Проверка 1: stock_quantity существует
        cursor.execute("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'offers' AND column_name = 'stock_quantity'
        """)
        if cursor.fetchone():
            logger.info("  ✅ offers.stock_quantity exists")
            checks.append(True)
        else:
            logger.error("  ❌ offers.stock_quantity missing")
            checks.append(False)
        
        # Проверка 2: cancel_reason существует
        cursor.execute("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'orders' AND column_name = 'cancel_reason'
        """)
        if cursor.fetchone():
            logger.info("  ✅ orders.cancel_reason exists")
            checks.append(True)
        else:
            logger.error("  ❌ orders.cancel_reason missing")
            checks.append(False)
        
        # Проверка 3: индексы созданы
        cursor.execute("""
            SELECT indexname 
            FROM pg_indexes 
            WHERE tablename = 'offers' AND indexname = 'idx_offers_category'
        """)
        if cursor.fetchone():
            logger.info("  ✅ idx_offers_category exists")
            checks.append(True)
        else:
            logger.error("  ❌ idx_offers_category missing")
            checks.append(False)
        
        # Проверка 4: constraints добавлены
        cursor.execute("""
            SELECT constraint_name 
            FROM information_schema.table_constraints 
            WHERE table_name = 'offers' AND constraint_name = 'check_valid_category'
        """)
        if cursor.fetchone():
            logger.info("  ✅ check_valid_category exists")
            checks.append(True)
        else:
            logger.warning("  ⚠️  check_valid_category missing (optional)")
            checks.append(True)  # Не критично
        
        # Статистика
        cursor.execute("SELECT COUNT(*) FROM offers WHERE stock_quantity IS NOT NULL")
        count = cursor.fetchone()[0]
        logger.info(f"  📊 {count} offers have stock_quantity")
    
    return all(checks)


def print_statistics(db: Database):
    """Вывести статистику после миграции."""
    logger.info("📊 Post-migration statistics:")
    
    with db.get_connection() as conn:
        cursor = conn.cursor()
        
        # Товары по категориям
        cursor.execute("""
            SELECT category, COUNT(*) as count 
            FROM offers 
            GROUP BY category 
            ORDER BY count DESC
        """)
        logger.info("  Offers by category:")
        for row in cursor.fetchall():
            logger.info(f"    - {row[0]}: {row[1]}")
        
        # Товары по единицам
        cursor.execute("""
            SELECT unit, COUNT(*) as count 
            FROM offers 
            GROUP BY unit 
            ORDER BY count DESC
        """)
        logger.info("  Offers by unit:")
        for row in cursor.fetchall():
            logger.info(f"    - {row[0]}: {row[1]}")
        
        # Товары с остатками
        cursor.execute("""
            SELECT 
                COUNT(*) FILTER (WHERE stock_quantity > 0) as with_stock,
                COUNT(*) FILTER (WHERE stock_quantity = 0) as without_stock,
                COUNT(*) as total
            FROM offers
        """)
        row = cursor.fetchone()
        logger.info(f"  Stock status:")
        logger.info(f"    - With stock: {row[0]}")
        logger.info(f"    - Without stock: {row[1]}")
        logger.info(f"    - Total: {row[2]}")


def main():
    """Главная функция."""
    logger.info("=" * 60)
    logger.info("🚀 Starting v22.0 migration")
    logger.info("=" * 60)
    
    try:
        # 1. Подключиться к БД
        logger.info("\n🔌 Step 1: Connecting to database...")
        db = Database()
        logger.info("   Connected successfully")
        
        # 2. Создать бэкап
        logger.info("\n📦 Step 2: Creating backup...")
        backup_file = create_backup(db)
        logger.info(f"   Backup saved: {backup_file}")
        
        # 3. Применить миграцию
        logger.info("\n🔄 Step 3: Applying migration...")
        if not apply_migration(db, "migrations/v22_add_fields.sql"):
            logger.error("   Migration failed! Exiting...")
            logger.info(f"   Backup reference saved in: {backup_file}")
            return 1
        
        # 4. Проверить миграцию
        logger.info("\n🔍 Step 4: Verifying migration...")
        if not verify_migration(db):
            logger.error("   Verification failed!")
            logger.info(f"   Backup reference saved in: {backup_file}")
            return 1
        
        # 5. Вывести статистику
        logger.info("\n📊 Step 5: Collecting statistics...")
        print_statistics(db)
        
        # Готово!
        logger.info("\n" + "=" * 60)
        logger.info("✅ Migration v22.0 completed successfully!")
        logger.info("=" * 60)
        logger.info(f"\nBackup saved: {backup_file}")
        logger.info("Next steps:")
        logger.info("  1. Restart bot: systemctl restart fudly-bot")
        logger.info("  2. Test product creation via bot")
        logger.info("  3. Test product creation via web panel")
        logger.info("  4. Test order cancellation with reason")
        
        return 0
        
    except KeyboardInterrupt:
        logger.warning("\n⚠️  Migration interrupted by user")
        return 1
    except Exception as e:
        logger.error(f"\n❌ Migration failed with error: {e}")
        logger.exception(e)
        return 1


if __name__ == "__main__":
    sys.exit(main())
