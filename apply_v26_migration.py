"""Apply v26 migration: Add region/district fields for stores."""
import os
import sys

import psycopg

from logging_config import logger


def apply_v26_migration():
    """Apply v26 migration to add region/district columns and indexes."""
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        logger.error("DATABASE_URL environment variable not set")
        return False

    try:
        with psycopg.connect(database_url) as conn:
            with conn.cursor() as cursor:
                logger.info("Starting v26 migration: Add store region/district")

                migration_file = "migrations/v26_add_store_location.sql"
                with open(migration_file, "r", encoding="utf-8") as f:
                    migration_sql = f.read()

                cursor.execute(migration_sql)
                conn.commit()

                logger.info("v26 migration completed successfully")

                cursor.execute(
                    """
                    SELECT column_name
                    FROM information_schema.columns
                    WHERE table_name = 'stores'
                      AND column_name IN ('region', 'district')
                    """
                )
                columns = {row[0] for row in cursor.fetchall()}
                logger.info("Verification: stores columns present: %s", ", ".join(sorted(columns)))

                return True

    except Exception as exc:
        logger.error("Migration failed: %s", exc)
        return False


if __name__ == "__main__":
    success = apply_v26_migration()
    sys.exit(0 if success else 1)
