"""Fix date formats in PostgreSQL database - convert DD.MM.YYYY to YYYY-MM-DD"""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from dotenv import load_dotenv

load_dotenv()

from datetime import datetime

from database_pg import Database


def main():
    db = Database()

    print("🔍 Checking offers with date format issues...")

    with db.get_connection() as conn:
        cursor = conn.cursor()

        # Get all offers with expiry_date
        cursor.execute(
            """
            SELECT offer_id, expiry_date
            FROM offers
            WHERE expiry_date IS NOT NULL
            AND expiry_date LIKE '%.%.%'
        """
        )

        offers = cursor.fetchall()
        print(f"Found {len(offers)} offers with DD.MM.YYYY format")

        fixed_count = 0
        for offer_id, expiry_date in offers:
            try:
                # Parse DD.MM.YYYY
                dt = datetime.strptime(expiry_date, "%d.%m.%Y")
                new_date = dt.strftime("%Y-%m-%d")

                # Update
                cursor.execute(
                    """
                    UPDATE offers
                    SET expiry_date = %s
                    WHERE offer_id = %s
                """,
                    (new_date, offer_id),
                )

                fixed_count += 1
                print(f"✅ Fixed offer {offer_id}: {expiry_date} → {new_date}")

            except Exception as e:
                print(f"❌ Error fixing offer {offer_id}: {e}")

        conn.commit()
        print(f"\n🎉 Fixed {fixed_count} offers!")


if __name__ == "__main__":
    main()
