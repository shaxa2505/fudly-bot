#!/usr/bin/env python3
"""Apply migration 003: Add partner_reminder_sent column"""
import os
import sys
import psycopg2
from dotenv import load_dotenv

load_dotenv()

def main():
    print("🔄 Applying migration 003_add_partner_reminder.sql...")
    
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        print("❌ DATABASE_URL not found in .env")
        return 1
    
    try:
        # Connect to database
        conn = psycopg2.connect(database_url)
        cur = conn.cursor()
        
        # Read migration SQL
        with open("migrations/003_add_partner_reminder.sql", encoding="utf-8") as f:
            migration_sql = f.read()
        
        # Execute migration
        cur.execute(migration_sql)
        conn.commit()
        
        print("✅ Migration applied successfully")
        
        # Verify column exists
        cur.execute("""
            SELECT column_name, data_type, column_default 
            FROM information_schema.columns 
            WHERE table_name='bookings' AND column_name='partner_reminder_sent'
        """)
        result = cur.fetchone()
        
        if result:
            print(f"✅ Column 'partner_reminder_sent' exists:")
            print(f"   Type: {result[1]}")
            print(f"   Default: {result[2]}")
        else:
            print("⚠️ Column 'partner_reminder_sent' not found!")
            return 1
        
        # Check index
        cur.execute("""
            SELECT indexname 
            FROM pg_indexes 
            WHERE tablename='bookings' AND indexname='idx_bookings_partner_reminder'
        """)
        index_result = cur.fetchone()
        
        if index_result:
            print(f"✅ Index 'idx_bookings_partner_reminder' created")
        else:
            print("⚠️ Index not found")
        
        cur.close()
        conn.close()
        
        print("\n✅ Migration 003 completed successfully!")
        return 0
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    sys.exit(main())
