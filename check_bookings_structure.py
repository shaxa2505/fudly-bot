import os
import sys
from dotenv import load_dotenv
load_dotenv()

import psycopg2

conn = psycopg2.connect(os.getenv("DATABASE_URL"))
cur = conn.cursor()

# Check bookings table structure
cur.execute("""
    SELECT column_name, data_type, character_maximum_length
    FROM information_schema.columns 
    WHERE table_name='bookings'
    ORDER BY ordinal_position
""")

print("\n📋 Bookings table structure:")
for row in cur.fetchall():
    print(f"  {row[0]}: {row[1]}" + (f"({row[2]})" if row[2] else ""))

# Check a sample booking
cur.execute("SELECT * FROM bookings LIMIT 1")
if cur.description:
    cols = [desc[0] for desc in cur.description]
    print(f"\n📊 Columns: {cols}")
    row = cur.fetchone()
    if row:
        print("\n📦 Sample booking:")
        for i, val in enumerate(row):
            print(f"  {cols[i]}: {val} ({type(val).__name__})")

conn.close()
