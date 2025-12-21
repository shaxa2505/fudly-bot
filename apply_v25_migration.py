"""Apply v25 migration: Add message tracking fields for live updates.

This migration adds customer_message_id and seller_message_id columns
to orders and bookings tables to enable live message editing.
"""
import os
import sys

import psycopg

from logging_config import logger


def apply_v25_migration():
    """Apply v25 migration to add message tracking fields."""
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        logger.error("DATABASE_URL environment variable not set")
        return False

    try:
        with psycopg.connect(database_url) as conn:
            with conn.cursor() as cursor:
                logger.info("Starting v25 migration: Add message tracking fields")

                # Read migration file
                migration_file = "migrations/v25_add_message_tracking.sql"
                with open(migration_file, "r", encoding="utf-8") as f:
                    migration_sql = f.read()

                # Execute migration
                cursor.execute(migration_sql)
                conn.commit()

                logger.info("✅ v25 migration completed successfully")

                # Verify
                cursor.execute("""
                    SELECT 
                        COUNT(*) as total_orders,
                        COUNT(customer_message_id) as with_customer_msg,
                        COUNT(seller_message_id) as with_seller_msg
                    FROM orders
                """)
                result = cursor.fetchone()
                if result:
                    logger.info(
                        f"Verification: {result[0]} total orders, "
                        f"{result[1]} with customer_msg, {result[2]} with seller_msg"
                    )

                return True

    except Exception as e:
        logger.error(f"❌ Migration failed: {e}")
        return False


if __name__ == "__main__":
    success = apply_v25_migration()
    sys.exit(0 if success else 1)
