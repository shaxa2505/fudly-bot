#!/usr/bin/env python3
"""
Apply v23 migration: Unify order statuses (confirmed → preparing, new → pending)
"""
import os
import sys
from datetime import datetime

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv()

# Manual .env parsing if dotenv fails
if not os.getenv("DATABASE_URL"):
    try:
        with open(".env", "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, value = line.split("=", 1)
                    os.environ[key.strip()] = value.strip().strip('"').strip("'")
    except Exception as e:
        print(f"⚠️ Warning: Could not load .env file: {e}")

import psycopg2

def get_db_connection():
    """Get database connection."""
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise ValueError("DATABASE_URL not found in environment")
    return psycopg2.connect(database_url)

def backup_database(conn):
    """Backup critical data before migration."""
    print("\n📦 Creating backup...")
    backup_file = f"backup_before_v23_{datetime.now().strftime('%Y%m%d_%H%M%S')}.sql"
    
    try:
        cursor = conn.cursor()
        
        # Get current status distribution
        cursor.execute("SELECT order_status, COUNT(*) FROM orders GROUP BY order_status")
        orders_stats = cursor.fetchall()
        
        cursor.execute("SELECT status, COUNT(*) FROM bookings GROUP BY status")
        bookings_stats = cursor.fetchall()
        
        with open(backup_file, 'w', encoding='utf-8') as f:
            f.write("-- Backup before v23 migration\n")
            f.write(f"-- Date: {datetime.now()}\n\n")
            
            f.write("-- Orders status distribution BEFORE:\n")
            for status, count in orders_stats:
                f.write(f"-- {status}: {count}\n")
            
            f.write("\n-- Bookings status distribution BEFORE:\n")
            for status, count in bookings_stats:
                f.write(f"-- {status}: {count}\n")
            
            f.write("\n-- Full backup of affected records:\n")
            
            # Backup orders with old statuses
            cursor.execute("""
                SELECT order_id, user_id, store_id, offer_id, order_status, created_at
                FROM orders 
                WHERE order_status IN ('confirmed', 'new')
                ORDER BY order_id
            """)
            
            f.write("\n-- Orders with old statuses:\n")
            for row in cursor.fetchall():
                f.write(f"-- ID:{row[0]} | Status:{row[4]} | Created:{row[5]}\n")
            
            # Backup bookings with old statuses  
            cursor.execute("""
                SELECT booking_id, user_id, offer_id, status, created_at
                FROM bookings 
                WHERE status IN ('confirmed', 'new')
                ORDER BY booking_id
            """)
            
            f.write("\n-- Bookings with old statuses:\n")
            for row in cursor.fetchall():
                f.write(f"-- ID:{row[0]} | Status:{row[3]} | Created:{row[4]}\n")
        
        print(f"✅ Backup created: {backup_file}")
        return backup_file
        
    except Exception as e:
        print(f"❌ Backup failed: {e}")
        return None

def apply_migration(conn):
    """Apply v23 migration."""
    print("\n🔄 Applying v23 migration...")
    
    cursor = conn.cursor()
    
    try:
        # Read migration SQL
        with open("migrations/v23_unify_statuses.sql", "r", encoding="utf-8") as f:
            migration_sql = f.read()
        
        # Execute migration
        cursor.execute(migration_sql)
        conn.commit()
        
        print("✅ Migration applied successfully!")
        return True
        
    except Exception as e:
        print(f"❌ Migration failed: {e}")
        conn.rollback()
        return False

def verify_migration(conn):
    """Verify migration results."""
    print("\n🔍 Verifying migration...")
    
    cursor = conn.cursor()
    
    # Check orders statuses
    cursor.execute("SELECT order_status, COUNT(*) FROM orders GROUP BY order_status ORDER BY order_status")
    orders_stats = cursor.fetchall()
    
    print("\n📊 Orders status distribution:")
    for status, count in orders_stats:
        print(f"   {status}: {count}")
    
    # Check bookings statuses
    cursor.execute("SELECT status, COUNT(*) FROM bookings GROUP BY status ORDER BY status")
    bookings_stats = cursor.fetchall()
    
    print("\n📊 Bookings status distribution:")
    for status, count in bookings_stats:
        print(f"   {status}: {count}")
    
    # Verify no old statuses remain
    cursor.execute("SELECT COUNT(*) FROM orders WHERE order_status IN ('confirmed', 'new')")
    old_orders = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM bookings WHERE status IN ('confirmed', 'new')")
    old_bookings = cursor.fetchone()[0]
    
    if old_orders > 0 or old_bookings > 0:
        print(f"\n⚠️ WARNING: Found {old_orders} orders and {old_bookings} bookings with old statuses!")
        return False
    
    print("\n✅ No old statuses found - migration successful!")
    
    # Check constraints
    cursor.execute("""
        SELECT conname FROM pg_constraint 
        WHERE conname IN ('check_order_status', 'check_booking_status')
    """)
    constraints = cursor.fetchall()
    
    print(f"\n✅ Constraints created: {len(constraints)}/2")
    for (name,) in constraints:
        print(f"   - {name}")
    
    # Check indexes
    cursor.execute("""
        SELECT indexname FROM pg_indexes 
        WHERE indexname IN ('idx_orders_status_created', 'idx_bookings_status_created')
    """)
    indexes = cursor.fetchall()
    
    print(f"\n✅ Indexes created: {len(indexes)}/2")
    for (name,) in indexes:
        print(f"   - {name}")
    
    return True

def main():
    """Main migration function."""
    print("=" * 60)
    print("🚀 v23 Migration: Unify Order Statuses")
    print("=" * 60)
    
    try:
        # Connect to database
        conn = get_db_connection()
        print("✅ Connected to database")
        
        # Create backup
        backup_file = backup_database(conn)
        if not backup_file:
            print("\n⚠️ Backup failed, but continuing...")
        
        # Apply migration
        if not apply_migration(conn):
            print("\n❌ Migration failed!")
            return 1
        
        # Verify
        if not verify_migration(conn):
            print("\n⚠️ Verification failed!")
            return 1
        
        conn.close()
        
        print("\n" + "=" * 60)
        print("✅ v23 Migration completed successfully!")
        print("=" * 60)
        print("\n📝 Summary:")
        print("   - Replaced 'confirmed' → 'preparing'")
        print("   - Replaced 'new' → 'pending'")
        print("   - Added status constraints")
        print("   - Created performance indexes")
        print(f"\n💾 Backup: {backup_file}")
        
        return 0
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    sys.exit(main())
