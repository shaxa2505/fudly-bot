import os
import psycopg

DB_URL = os.getenv("DATABASE_URL")
if not DB_URL:
    raise SystemExit("DATABASE_URL env var is required (e.g. Railway DATABASE_URL).")

try:
    print("рџ”Њ Connecting to Railway PostgreSQL...")
    conn = psycopg.connect(DB_URL, connect_timeout=10)
    cur = conn.cursor()

    # Check existing tables
    cur.execute("SELECT tablename FROM pg_tables WHERE schemaname='public'")
    tables = [row[0] for row in cur.fetchall()]

    print("\nвњ… Connected successfully!")
    print(f"\nрџ“‹ Existing tables ({len(tables)}):")
    for table in sorted(tables):
        print(f"  - {table}")

    # Check if main tables exist (offers, not products!)
    required_tables = ["users", "stores", "offers", "orders"]
    missing_tables = [t for t in required_tables if t not in tables]

    if missing_tables:
        print(f"\nвљ пёЏ  Missing required tables: {', '.join(missing_tables)}")
    else:
        print("\nвњ… All required tables exist!")

        # Check row counts
        print("\nрџ“Љ Table sizes:")
        for table in required_tables:
            cur.execute(f"SELECT COUNT(*) FROM {table}")
            count = cur.fetchone()[0]
            print(f"  - {table}: {count} rows")

    conn.close()
    print("\nвњ… Connection closed")

except Exception as e:
    print(f"\nвќЊ Error: {e}")
    import traceback

    traceback.print_exc()

