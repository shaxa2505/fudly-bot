"""
Simple script to check database structure
"""
import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import Database

# Create a test database
test_db_path = "test_favorites.db"

# Remove if exists
if os.path.exists(test_db_path):
    os.remove(test_db_path)

# Initialize database
print("Initializing database...")
db = Database(test_db_path)

# Check tables
conn = sqlite3.connect(test_db_path)
cursor = conn.cursor()
cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
tables = cursor.fetchall()

print("\nTables in database:")
for table in tables:
    print(f"  - {table[0]}")

# Check if offer_favorites exists
cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='offer_favorites'")
if cursor.fetchone():
    print("\n✅ Table 'offer_favorites' EXISTS")

    # Show schema
    cursor.execute("PRAGMA table_info(offer_favorites)")
    columns = cursor.fetchall()
    print("\nColumns in offer_favorites:")
    for col in columns:
        print(f"  - {col[1]} ({col[2]})")
else:
    print("\n❌ Table 'offer_favorites' DOES NOT EXIST")

conn.close()

# Cleanup
os.remove(test_db_path)
print("\nTest database removed")
