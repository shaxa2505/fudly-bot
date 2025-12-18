#!/usr/bin/env python3
"""
Apply v24 migration: Migrate bookings to orders table
"""
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv()

# Manual .env parsing
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
    """Backup bookings data before migration."""
    print("\n📦 Creating backup...")
    backup_file = f"backup_before_v24_{datetime.now().strftime('%Y%m%d_%H%M%S')}.sql"
    
    try:
        cursor = conn.cursor()
        
        # Count bookings
        cursor.execute("SELECT COUNT(*) FROM bookings")
        bookings_count = cursor.fetchone()[0]
        
        # Get bookings data
        cursor.execute("""
            SELECT booking_id, user_id, offer_id, status, booking_code, 
                   pickup_time, quantity, created_at
            FROM bookings 
            ORDER BY booking_id
        """)
        bookings = cursor.fetchall()
        
        with open(backup_file, 'w', encoding='utf-8') as f:
            f.write("-- Backup before v24 migration (bookings → orders)\n")
            f.write(f"-- Date: {datetime.now()}\n")
            f.write(f"-- Total bookings: {bookings_count}\n\n")
            
            f.write("-- Bookings data:\n")
            for b in bookings:
                f.write(f"-- ID:{b[0]} | User:{b[1]} | Offer:{b[2]} | Status:{b[3]} | Code:{b[4]}\n")
        
        print(f"✅ Backup created: {backup_file}")
        print(f"   Bookings to migrate: {bookings_count}")
        return backup_file, bookings_count
        
    except Exception as e:
        print(f"❌ Backup failed: {e}")
        return None, 0

def apply_migration(conn):
    """Apply v24 migration."""
    print("\n🔄 Applying v24 migration...")
    
    cursor = conn.cursor()
    
    try:
        # Read migration SQL
        with open("migrations/v24_migrate_bookings.sql", "r", encoding="utf-8") as f:
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
    
    try:
        # Check if bookings_archive exists
        cursor.execute("""
            SELECT EXISTS (
                SELECT FROM pg_tables 
                WHERE tablename = 'bookings_archive'
            )
        """)
        archive_exists = cursor.fetchone()[0]
        
        if not archive_exists:
            print("❌ bookings_archive table not found!")
            return False
        
        print("✅ bookings_archive table created")
        
        # Count archived bookings
        cursor.execute("SELECT COUNT(*) FROM bookings_archive")
        archived_count = cursor.fetchone()[0]
        print(f"   Archived bookings: {archived_count}")
        
        # Count pickup orders in orders table
        cursor.execute("SELECT COUNT(*) FROM orders WHERE order_type = 'pickup'")
        pickup_count = cursor.fetchone()[0]
        print(f"   Pickup orders in orders table: {pickup_count}")
        
        # Check order types distribution
        cursor.execute("SELECT order_type, COUNT(*) FROM orders GROUP BY order_type")
        order_types = cursor.fetchall()
        
        print("\n📊 Orders distribution by type:")
        for order_type, count in order_types:
            print(f"   {order_type}: {count}")
        
        # Check indexes
        cursor.execute("""
            SELECT indexname FROM pg_indexes 
            WHERE indexname IN ('idx_orders_pickup_code', 'idx_orders_pickup_time')
        """)
        indexes = cursor.fetchall()
        
        print(f"\n✅ Indexes created: {len(indexes)}/2")
        for (name,) in indexes:
            print(f"   - {name}")
        
        # Check if original bookings table exists
        cursor.execute("""
            SELECT EXISTS (
                SELECT FROM pg_tables 
                WHERE tablename = 'bookings'
            )
        """)
        bookings_exists = cursor.fetchone()[0]
        
        if bookings_exists:
            print("\n⚠️ WARNING: Original 'bookings' table still exists!")
            print("   This should be 'bookings_archive' now.")
            return False
        else:
            print("\n✅ Original 'bookings' table successfully archived")
        
        return True
        
    except Exception as e:
        print(f"❌ Verification failed: {e}")
        return False

def main():
    """Main migration function."""
    print("=" * 60)
    print("🚀 v24 Migration: Consolidate bookings → orders")
    print("=" * 60)
    
    try:
        # Connect to database
        conn = get_db_connection()
        print("✅ Connected to database")
        
        # Create backup
        backup_file, bookings_count = backup_database(conn)
        if not backup_file:
            print("\n⚠️ Backup failed!")
            response = input("Continue anyway? (yes/no): ")
            if response.lower() != 'yes':
                return 1
        
        if bookings_count == 0:
            print("\n⚠️ No bookings found to migrate!")
            response = input("Continue anyway? (yes/no): ")
            if response.lower() != 'yes':
                return 1
        
        # Apply migration
        if not apply_migration(conn):
            print("\n❌ Migration failed!")
            return 1
        
        # Verify
        if not verify_migration(conn):
            print("\n⚠️ Verification warnings found!")
        
        conn.close()
        
        print("\n" + "=" * 60)
        print("✅ v24 Migration completed successfully!")
        print("=" * 60)
        print("\n📝 Summary:")
        print(f"   - Migrated {bookings_count} bookings to orders table")
        print("   - Original table archived as 'bookings_archive'")
        print("   - All pickup orders now in unified 'orders' table")
        print("   - Created pickup-specific indexes")
        print(f"\n💾 Backup: {backup_file}")
        print("\n⚠️ NEXT STEPS:")
        print("   1. Update code to use orders table instead of bookings")
        print("   2. Remove get_store_bookings() methods")
        print("   3. Test all pickup order flows")
        
        return 0
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    sys.exit(main())
