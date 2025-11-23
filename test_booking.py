import os
import psycopg2
from psycopg2.extras import RealDictCursor

# Railway database (must be provided via environment variable for safety)
DATABASE_URL = os.getenv('DATABASE_URL')

if not DATABASE_URL:
    print("\n❌ ERROR: Please set the DATABASE_URL environment variable before running this test.")
    print("   Example: export DATABASE_URL=postgresql://user:pass@host:port/dbname\n")
    raise SystemExit(1)

try:
    conn = psycopg2.connect(DATABASE_URL)
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    print("✅ Connected to Railway database\n")
    
    # Check bookings table structure
    print("📋 BOOKINGS TABLE STRUCTURE:")
    cursor.execute("""
        SELECT column_name, data_type, is_nullable, column_default
        FROM information_schema.columns
        WHERE table_name = 'bookings'
        ORDER BY ordinal_position
    """)
    columns = cursor.fetchall()
    for col in columns:
        print(f"   {col['column_name']}: {col['data_type']} (nullable: {col['is_nullable']})")
    
    print("\n" + "="*50)
    
    # Try to create a test booking
    print("\n🧪 Testing booking creation...")
    
    # First, check if we have an active offer
    cursor.execute("""
        SELECT offer_id, title, quantity, discount_price
        FROM offers
        WHERE status = 'active' AND quantity > 0
        LIMIT 1
    """)
    offer = cursor.fetchone()
    
    if offer:
        print(f"   Found offer: {offer['title']} (ID: {offer['offer_id']}, qty: {offer['quantity']})")
        
        # Try to create booking
        booking_code = "TEST01"
        test_user_id = 253445521  # Your user ID
        
        try:
            cursor.execute("""
                INSERT INTO bookings (offer_id, user_id, booking_code, status, quantity)
                VALUES (%s, %s, %s, 'pending', 1)
                RETURNING booking_id
            """, (offer['offer_id'], test_user_id, booking_code))
            
            booking_id = cursor.fetchone()['booking_id']
            conn.commit()
            
            print(f"   ✅ Test booking created! ID: {booking_id}")
            
            # Check if it's in the table
            cursor.execute("SELECT * FROM bookings WHERE booking_id = %s", (booking_id,))
            booking = cursor.fetchone()
            print(f"\n   Booking data: {dict(booking)}")
            
            # Clean up test booking
            cursor.execute("DELETE FROM bookings WHERE booking_id = %s", (booking_id,))
            conn.commit()
            print("\n   🧹 Test booking deleted")
            
        except Exception as e:
            conn.rollback()
            print(f"   ❌ Error creating booking: {e}")
    else:
        print("   ❌ No active offers found")
    
    cursor.close()
    conn.close()
    
except Exception as e:
    print(f"❌ Error: {e}")
