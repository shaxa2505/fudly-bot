"""Fix payment_settings table structure via DATABASE_URL"""
import os

# Get DATABASE_URL from environment
DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    print("❌ DATABASE_URL environment variable is not set")
    exit(1)

print("Installing psycopg2...")
os.system("pip install psycopg2-binary")

print("\nConnecting to database...")

try:
    import psycopg2
    
    conn = psycopg2.connect(DATABASE_URL)
    cursor = conn.cursor()
    
    print("✅ Connected!")
    print(f"Database: {DATABASE_URL.split('@')[1].split('/')[0]}")  # Show which database we connected to
    
    # Check current data first
    print("\n0. Checking existing data...")
    try:
        cursor.execute("SELECT COUNT(*) FROM payment_settings")
        count = cursor.fetchone()[0]
        print(f"   Current rows in payment_settings: {count}")
        if count > 0:
            cursor.execute("SELECT id, card_number, card_holder FROM payment_settings")
            for row in cursor.fetchall():
                print(f"   - ID: {row[0]}, Card: {row[1]}, Holder: {row[2]}")
    except Exception as e:
        print(f"   Table doesn't exist or error: {e}")
    
    # Drop and recreate table with correct structure
    print("\n1. Dropping old table...")
    cursor.execute("DROP TABLE IF EXISTS payment_settings CASCADE")
    
    print("2. Creating new table with correct structure...")
    cursor.execute("""
        CREATE TABLE payment_settings (
            id SERIAL PRIMARY KEY,
            store_id INTEGER,
            card_number VARCHAR(20) NOT NULL,
            card_holder VARCHAR(100) NOT NULL,
            card_expiry VARCHAR(7),
            payment_instructions TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Insert payment card
    print("3. Inserting payment card...")
    cursor.execute("""
        INSERT INTO payment_settings (card_number, card_holder)
        VALUES ('8600040102359839', 'FUDLY PLATFORM')
    """)
    
    conn.commit()
    
    # Verify
    print("4. Verifying...")
    cursor.execute("SELECT * FROM payment_settings")
    result = cursor.fetchone()
    
    if result:
        print(f"\n✅ SUCCESS! Payment card added:")
        print(f"   ID: {result[0]}")
        print(f"   Card: {result[2]}")
        print(f"   Holder: {result[3]}")
    else:
        print("\n⚠️  No data found")
    
    cursor.close()
    conn.close()
    
    print("\n🚀 Done! Delivery will work now!")
    
except Exception as e:
    print(f"\n❌ Error: {e}")
    print("\nPlease:")
    print("1. Open the script fix_payment_table.py")
    print("2. Replace DATABASE_URL with your full connection string from Railway")
    print("3. Replace PASSWORD with actual password (remove asterisks)")
    print("4. Run: python fix_payment_table.py")
