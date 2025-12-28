"""
Create bookings_archive table in production database.
Run this via Railway CLI: railway run python create_bookings_archive.py
"""
import os
import psycopg

DATABASE_URL = os.getenv("DATABASE_URL") or os.getenv("DATABASE_PRIVATE_URL")

if not DATABASE_URL:
    print("❌ DATABASE_URL not found!")
    exit(1)

print(f"🔌 Connecting to database...")

try:
    conn = psycopg.connect(DATABASE_URL)
    cursor = conn.cursor()
    
    # Check if table exists
    cursor.execute("""
        SELECT EXISTS (
            SELECT FROM pg_tables 
            WHERE schemaname = 'public' 
            AND tablename = 'bookings_archive'
        )
    """)
    
    exists = cursor.fetchone()[0]
    
    if exists:
        print("✅ bookings_archive table already exists")
        cursor.execute("SELECT COUNT(*) FROM bookings_archive")
        count = cursor.fetchone()[0]
        print(f"   Contains {count} archived bookings")
    else:
        print("📝 Creating bookings_archive table...")
        
        # Create table with same structure as old bookings
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS bookings_archive (
                booking_id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL,
                offer_id INTEGER,
                store_id INTEGER,
                quantity INTEGER DEFAULT 1,
                booking_code VARCHAR(6),
                status VARCHAR(20) DEFAULT 'pending',
                pickup_time TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                total_price INTEGER DEFAULT 0,
                payment_method VARCHAR(20),
                payment_status VARCHAR(20)
            )
        """)
        
        # Create indexes
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_bookings_archive_user_id 
            ON bookings_archive(user_id)
        """)
        
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_bookings_archive_created_at 
            ON bookings_archive(created_at DESC)
        """)
        
        conn.commit()
        print("✅ bookings_archive table created successfully!")
    
    cursor.close()
    conn.close()
    
except Exception as e:
    print(f"❌ Error: {e}")
    exit(1)

print("✅ Done!")
