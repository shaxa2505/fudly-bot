"""Add platform payment card to database."""
import os
from database_pg import Database

# Get DATABASE_URL from environment
database_url = os.getenv('DATABASE_URL')
if not database_url:
    print("❌ DATABASE_URL not found in environment variables")
    print("Please set it in Railway or .env file")
    exit(1)

# Initialize database
db = Database(database_url)

# Add payment card
try:
    with db.get_connection() as conn:
        cursor = conn.cursor()
        
        # Check if payment_settings table exists
        cursor.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_name = 'payment_settings'
            )
        """)
        table_exists = cursor.fetchone()[0]
        
        if not table_exists:
            print("⚠️  Creating payment_settings table...")
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS payment_settings (
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
            print("✅ Table created")
        
        # Check if card already exists
        cursor.execute("SELECT COUNT(*) FROM payment_settings")
        count = cursor.fetchone()[0]
        
        if count > 0:
            print(f"ℹ️  Found {count} payment card(s) in database")
            cursor.execute("SELECT card_number, card_holder FROM payment_settings LIMIT 1")
            card = cursor.fetchone()
            print(f"   Card: {card[0]} ({card[1]})")
            
            update = input("\nUpdate existing card? (y/n): ")
            if update.lower() != 'y':
                print("Cancelled")
                exit(0)
        
        # Get card details
        print("\n📝 Enter payment card details:")
        card_number = input("Card number (16 digits): ").strip()
        card_holder = input("Card holder name: ").strip()
        
        if not card_number or not card_holder:
            print("❌ Card number and holder name are required")
            exit(1)
        
        # Insert or update
        if count > 0:
            cursor.execute("""
                UPDATE payment_settings 
                SET card_number = %s, card_holder = %s, updated_at = CURRENT_TIMESTAMP
                WHERE id = (SELECT id FROM payment_settings LIMIT 1)
            """, (card_number, card_holder))
            print(f"\n✅ Updated payment card: {card_number} ({card_holder})")
        else:
            cursor.execute("""
                INSERT INTO payment_settings (card_number, card_holder)
                VALUES (%s, %s)
            """, (card_number, card_holder))
            print(f"\n✅ Added payment card: {card_number} ({card_holder})")
        
        conn.commit()
        
except Exception as e:
    print(f"\n❌ Error: {e}")
    import traceback
    traceback.print_exc()
