"""Check actual database schema."""
import os
os.environ['SKIP_DB_INIT'] = '1'

from database_pg import Database

db = Database()

with db.get_connection() as conn:
    cursor = conn.cursor()
    
    # Check offers columns
    cursor.execute("""
        SELECT column_name, data_type 
        FROM information_schema.columns 
        WHERE table_name = 'offers' 
        ORDER BY ordinal_position
    """)
    
    print("\n=== OFFERS TABLE COLUMNS ===")
    offers_columns = set()
    for row in cursor.fetchall():
        print(f"{row[0]:30} {row[1]}")
        offers_columns.add(row[0])
    
    # Check bookings columns
    cursor.execute("""
        SELECT column_name, data_type 
        FROM information_schema.columns 
        WHERE table_name = 'bookings' 
        ORDER BY ordinal_position
    """)
    
    print("\n=== BOOKINGS TABLE COLUMNS ===")
    bookings_columns = set()
    for row in cursor.fetchall():
        print(f"{row[0]:30} {row[1]}")
        bookings_columns.add(row[0])
    
    # Check what indexes we CAN create
    print("\n=== INDEXES WE CAN CREATE ===")
    
    if 'store_id' in bookings_columns and 'status' in bookings_columns and 'created_at' in bookings_columns:
        print("✅ idx_bookings_store_status_created")
    
    if 'user_id' in bookings_columns and 'created_at' in bookings_columns:
        print("✅ idx_bookings_user_created")
    
    if 'expiry_time' in bookings_columns and 'status' in bookings_columns:
        print("✅ idx_bookings_expiry_active")
    
    if 'store_id' in offers_columns and 'status' in offers_columns:
        print("✅ idx_offers_store_status")
    
    if 'category' in offers_columns and 'status' in offers_columns:
        print("✅ idx_offers_category_status")
    
    # Check existing indexes
    cursor.execute("""
        SELECT indexname 
        FROM pg_indexes 
        WHERE schemaname = 'public' 
        AND tablename IN ('offers', 'bookings', 'favorites', 'notifications')
        ORDER BY indexname
    """)
    
    print("\n=== EXISTING INDEXES ===")
    for row in cursor.fetchall():
        print(f"  {row[0]}")
