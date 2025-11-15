"""Database factory selecting PostgreSQL or SQLite backend."""
from __future__ import annotations

from typing import Optional

from .security import logger


def create_database(database_url: Optional[str]):
    """Return proper Database implementation based on env settings."""
    if database_url:
        from database_pg import Database as PostgresDatabase

        logger.info("Using PostgreSQL database")
        print("🐘 Using PostgreSQL database")
        try:
            return PostgresDatabase(database_url=database_url)
        except Exception as exc:
            logger.error(
                "PostgreSQL initialization failed, falling back to SQLite: %s",
                exc,
                exc_info=True,
            )
            print("⚠️ PostgreSQL unavailable, switching to SQLite for local run")

    from database import Database

    logger.info("Using SQLite database (local development)")
    print("📁 Using SQLite database (local development)")
    return Database()
