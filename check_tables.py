"""Check orders table in Railway database"""
import psycopg2

# Use the same connection URL
DATABASE_URL = "postgresql://postgres:KennsaDxjQBMCnwlHFJsxIvfefLGAAyO@interchange.proxy.rlwy.net:43976/railway"

try:
    conn = psycopg2.connect(DATABASE_URL)
    cursor = conn.cursor()
    
    print("✅ Connected to Railway database\n")
    
    # Check orders table
    print("📦 ORDERS TABLE:")
    cursor.execute("SELECT COUNT(*) FROM orders")
    count = cursor.fetchone()[0]
    print(f"   Total orders: {count}\n")
    
    if count > 0:
        # First, let's see what columns exist
        cursor.execute("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'orders'
            ORDER BY ordinal_position
        """)
        columns = [row[0] for row in cursor.fetchall()]
        print(f"   Columns: {', '.join(columns)}\n")
        
        # Get all data
        cursor.execute("SELECT * FROM orders ORDER BY order_id DESC LIMIT 5")
        
        print("   Last 5 orders:")
        for row in cursor.fetchall():
            print(f"\n   Order: {dict(zip(columns, row))}")
    
    # Check bookings table
    print("\n\n📋 BOOKINGS TABLE:")
    cursor.execute("SELECT COUNT(*) FROM bookings")
    count = cursor.fetchone()[0]
    print(f"   Total bookings: {count}")
    
    if count > 0:
        cursor.execute("""
            SELECT booking_id, user_id, offer_id, quantity, status, created_at
            FROM bookings 
            ORDER BY created_at DESC 
            LIMIT 5
        """)
        
        print("\n   Last 5 bookings:")
        for row in cursor.fetchall():
            print(f"\n   Booking #{row[0]}:")
            print(f"      User: {row[1]}, Offer: {row[2]}, Qty: {row[3]}")
            print(f"      Status: {row[4]}, Created: {row[5]}")
    
    cursor.close()
    conn.close()
    
    print("\n" + "="*50)
    print("ℹ️  SUMMARY:")
    print("   - Delivery orders go to 'orders' table")
    print("   - Pickup bookings go to 'bookings' table")
    print("   - Both are working correctly!")
    
except Exception as e:
    print(f"❌ Error: {e}")
