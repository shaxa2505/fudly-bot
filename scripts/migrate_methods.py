"""
Script to port missing methods from database.py to database_pg.py
Converts SQLite syntax to PostgreSQL syntax.

Notes:
- This helper is purely textual; it does NOT execute SQL.
- Added type hints to satisfy static analysis.
"""
import re

# SQL syntax conversions (pattern -> replacement)
conversions: list[tuple[str, str]] = [
    # SQLite placeholders to PostgreSQL
    (r"\?", "%s"),
    # Date functions
    (r"date\('now'\)", "CURRENT_DATE"),
    (r"datetime\('now'\)", "CURRENT_TIMESTAMP"),
    (r"CURRENT_TIMESTAMP", "CURRENT_TIMESTAMP"),
    # LIKE patterns
    (r"LIKE \?", "ILIKE %s"),
    # Last insert ID
    (r"cursor\.lastrowid", "cursor.fetchone()[0]"),
    (r"INSERT INTO", "INSERT INTO"),  # May need RETURNING clause
    # Connection handling
    (r"conn = self\.get_connection\(\)", "with self.get_connection() as conn:"),
    (r"conn\.close\(\)", "# Auto-closed by context manager"),
    (r"try:\s+conn\.close\(\)\s+except.*?pass", ""),
]


def convert_method(sqlite_code: str) -> str:
    """Convert a snippet of SQLite-oriented code to PostgreSQL-oriented code.

    This performs best-effort regex substitutions defined in `conversions`.
    It is intentionally conservative; manual review is still required.
    """
    pg_code: str = sqlite_code

    for pattern, replacement in conversions:
        pg_code = re.sub(pattern, replacement, pg_code)

    return pg_code


# Missing critical methods to port
missing_methods = [
    "get_all_users",
    "get_stores_by_city",
    "get_offers_by_city_and_category",
    "get_platform_payment_card",
    "get_store_owner",
    "delete_user",
    "delete_store",
    "get_all_admins",
    "toggle_notifications",
    "update_user_role",
    "activate_offer",
    "deactivate_offer",
    "get_booking_history",
    "add_to_favorites",
    "remove_from_favorites",
    "get_favorites",
]

print("=" * 60)
print("CRITICAL MISSING METHODS")
print("=" * 60)
for method in missing_methods:
    print(f"- {method}")

print("\n⚠️  Эти методы нужно портировать вручную из database.py")
print("⚠️  Используйте RealDictCursor и PostgreSQL синтаксис (%s вместо ?)")
