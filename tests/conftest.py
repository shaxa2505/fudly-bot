"""Shared pytest fixtures for database-backed tests."""
from __future__ import annotations

import os
from urllib.parse import urlparse

import pytest
from psycopg import sql

from database_pg import Database


def _get_test_db_url() -> str | None:
    return os.getenv("TEST_DATABASE_URL") or os.getenv("DATABASE_URL")


def _is_safe_db_url(db_url: str) -> bool:
    """Allow only local/test hosts unless explicitly overridden."""
    parsed = urlparse(db_url)
    host = (parsed.hostname or "").lower()
    return host in {"localhost", "127.0.0.1", "postgres", "db"}


def _truncate_all_tables(db: Database) -> None:
    """Remove all rows from public tables to keep tests isolated."""
    with db.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
        rows = cursor.fetchall()
        tables = [row[0] for row in rows]
        if not tables:
            return
        table_list = sql.SQL(", ").join(sql.Identifier(name) for name in tables)
        cursor.execute(sql.SQL("TRUNCATE TABLE {} RESTART IDENTITY CASCADE").format(table_list))


@pytest.fixture(scope="session")
def postgres_db() -> Database:
    """Session-scoped PostgreSQL database handle for tests."""
    db_url = _get_test_db_url()
    if not db_url:
        pytest.skip("TEST_DATABASE_URL (or DATABASE_URL) is required for DB tests")
    if not _is_safe_db_url(db_url) and os.getenv("ALLOW_TEST_DB_RESET") != "1":
        pytest.skip(
            "Refusing to run DB tests against non-local database. "
            "Set ALLOW_TEST_DB_RESET=1 to override."
        )

    # Ensure schema is initialized for tests
    os.environ["RUN_DB_MIGRATIONS"] = "1"

    db = Database(db_url)
    try:
        yield db
    finally:
        try:
            db.close()
        except Exception:
            pass


@pytest.fixture()
def db(postgres_db: Database) -> Database:
    """Function-scoped database fixture with clean tables."""
    _truncate_all_tables(postgres_db)
    return postgres_db
