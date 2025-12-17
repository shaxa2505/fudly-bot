import psycopg

DB_URL = (
    "postgresql://postgres:AlIcvvweODzccngRJbskNqLIoyzxCtmS@tramway.proxy.rlwy.net:36557/railway"
)

try:
    print("🔌 Connecting to Railway PostgreSQL...")
    conn = psycopg.connect(DB_URL, connect_timeout=10)
    cur = conn.cursor()

    # Check offers table schema
    cur.execute(
        """
        SELECT column_name, data_type, character_maximum_length
        FROM information_schema.columns
        WHERE table_name = 'offers' AND table_schema = 'public'
        ORDER BY ordinal_position
    """
    )

    print("\n📊 offers table schema:")
    print(f"{'Column':<30} {'Type':<20} {'Length':<10}")
    print("=" * 60)
    for row in cur.fetchall():
        col_name, data_type, max_len = row
        length = str(max_len) if max_len else "-"
        print(f"{col_name:<30} {data_type:<20} {length:<10}")

    conn.close()

except Exception as e:
    print(f"\n❌ Error: {e}")
    import traceback

    traceback.print_exc()
