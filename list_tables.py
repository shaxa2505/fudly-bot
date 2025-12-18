"""List all tables in database."""
import os
os.environ['SKIP_DB_INIT'] = '1'

from database_pg import Database

db = Database()

with db.get_connection() as conn:
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT tablename 
        FROM pg_tables 
        WHERE schemaname = 'public' 
        ORDER BY tablename
    """)
    
    print("\n=== EXISTING TABLES ===")
    tables = [row[0] for row in cursor.fetchall()]
    for table in tables:
        print(f"  {table}")
    
    print(f"\nTotal tables: {len(tables)}")
