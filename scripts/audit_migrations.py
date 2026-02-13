#!/usr/bin/env python3
"""Audit Alembic migration status against a target database.

Usage:
  python scripts/audit_migrations.py
  python scripts/audit_migrations.py --strict
  python scripts/audit_migrations.py --database-url postgresql://...
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path

from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from dotenv import load_dotenv
from sqlalchemy import create_engine


PROJECT_ROOT = Path(__file__).resolve().parent.parent


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Audit DB migration status (current vs head).")
    parser.add_argument(
        "--database-url",
        default="",
        help="Database URL. If omitted, uses DATABASE_URL from environment.",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit with code 1 when DB is not on head revision.",
    )
    return parser.parse_args()


def normalize_database_url(database_url: str) -> str:
    if database_url.startswith("postgres://"):
        return database_url.replace("postgres://", "postgresql://", 1)
    return database_url


def collect_pending_revisions(
    script: ScriptDirectory, current_heads: set[str], head_revisions: list[str]
) -> list[str]:
    """Best-effort list of revisions above current heads."""
    if not current_heads:
        pending: set[str] = set()
        for head in head_revisions:
            for rev in script.iterate_revisions(head, "base"):
                pending.add(rev.revision)
        return sorted(pending)

    pending_set: set[str] = set()
    for head in head_revisions:
        for rev in script.iterate_revisions(head, "base"):
            if rev.revision in current_heads:
                break
            pending_set.add(rev.revision)
    return sorted(pending_set)


def main() -> int:
    load_dotenv()
    args = parse_args()

    database_url = args.database_url or os.getenv("DATABASE_URL", "")
    database_url = normalize_database_url(database_url.strip())
    if not database_url:
        print("DATABASE_URL is not set. Provide --database-url or export DATABASE_URL.")
        return 2

    config = Config(str(PROJECT_ROOT / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", database_url)
    script = ScriptDirectory.from_config(config)
    head_revisions = list(script.get_heads())

    engine = create_engine(database_url)
    with engine.connect() as conn:
        context = MigrationContext.configure(conn)
        current_heads = set(context.get_current_heads())

    print(f"Current DB heads: {sorted(current_heads) if current_heads else ['<none>']}")
    print(f"Alembic heads: {sorted(head_revisions)}")

    if set(head_revisions) == current_heads:
        print("Migration status: up-to-date")
        return 0

    pending = collect_pending_revisions(script, current_heads, head_revisions)
    print("Migration status: OUTDATED")
    if pending:
        print("Pending revisions:")
        for rev in pending:
            print(f"  - {rev}")
    else:
        print("Pending revisions could not be resolved exactly (branch mismatch).")
    print("Run: python -m alembic upgrade head")

    if args.strict:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
