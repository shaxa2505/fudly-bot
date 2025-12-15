import psycopg

DB_URL = (
    "postgresql://postgres:joXsidsEFuGPOyxZEVTcUMZcNuZtdknG@shuttle.proxy.rlwy.net:42576/railway"
)

try:
    print("🔌 Connecting to Railway PostgreSQL...")
    conn = psycopg.connect(DB_URL, connect_timeout=10)
    cur = conn.cursor()

    # Check existing tables
    cur.execute("SELECT tablename FROM pg_tables WHERE schemaname='public'")
    tables = [row[0] for row in cur.fetchall()]

    print("\n✅ Connected successfully!")
    print(f"\n📋 Existing tables ({len(tables)}):")
    for table in sorted(tables):
        print(f"  - {table}")

    # Check if main tables exist (offers, not products!)
    required_tables = ["users", "stores", "offers", "orders"]
    missing_tables = [t for t in required_tables if t not in tables]

    if missing_tables:
        print(f"\n⚠️  Missing required tables: {', '.join(missing_tables)}")
    else:
        print("\n✅ All required tables exist!")

        # Check row counts
        print("\n📊 Table sizes:")
        for table in required_tables:
            cur.execute(f"SELECT COUNT(*) FROM {table}")
            count = cur.fetchone()[0]
            print(f"  - {table}: {count} rows")

    conn.close()
    print("\n✅ Connection closed")

except Exception as e:
    print(f"\n❌ Error: {e}")
    import traceback

    traceback.print_exc()
