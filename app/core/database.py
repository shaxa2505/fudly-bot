"""Database factory - PostgreSQL only."""
from __future__ import annotations

from .security import logger


def create_database(database_url: str | None):
    """Return PostgreSQL Database implementation."""
    if not database_url:
        raise ValueError(
            "❌ DATABASE_URL is required! "
            "SQLite support removed - use PostgreSQL only.\n"
            "For local development, set up PostgreSQL locally or use Docker:\n"
            "  docker run -d -p 5432:5432 -e POSTGRES_PASSWORD=password postgres"
        )

    from database_pg import Database as PostgresDatabase

    logger.info("Using PostgreSQL database")
    print("🐘 Using PostgreSQL database")
    return PostgresDatabase(database_url=database_url)
