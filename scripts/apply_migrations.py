#!/usr/bin/env python3
"""Apply SQL migration files in `migrations/` to SQLite and/or Postgres.

Usage:
  python scripts/apply_migrations.py --sqlite-db path/to/db.sqlite [--migrations migrations/]
  python scripts/apply_migrations.py --pg-dsn "postgresql://user:pass@host/db" [--migrations migrations/]

The script looks for SQL files in the `migrations/` directory and applies the
section marked `-- SQLite` for SQLite, or `-- Postgres` for Postgres. Files
must include those markers (our project migration files follow this convention).
"""
from __future__ import annotations

import argparse
import os
import sqlite3
from glob import glob
from typing import List


def load_migration_sections(path: str) -> dict:
    """Return dict with 'sqlite' and 'postgres' keys containing SQL snippets."""
    with open(path, 'r', encoding='utf-8') as f:
        content = f.read()

    # Simple split by markers
    sections = {'sqlite': '', 'postgres': '', 'all': ''}
    lines = content.splitlines()
    mode = 'all'
    buf: List[str] = []
    for ln in lines:
        stripped = ln.strip()
        if stripped.lower().startswith('-- sqlite'):
            # flush previous
            if buf:
                sections[mode] += '\n'.join(buf) + '\n'
            mode = 'sqlite'
            buf = []
            continue
        if stripped.lower().startswith('-- postgres'):
            if buf:
                sections[mode] += '\n'.join(buf) + '\n'
            mode = 'postgres'
            buf = []
            continue
        buf.append(ln)

    if buf:
        sections[mode] += '\n'.join(buf) + '\n'

    # If sections are empty, fall back to entire content
    if not sections['sqlite'].strip():
        sections['sqlite'] = sections['all'] or content
    if not sections['postgres'].strip():
        sections['postgres'] = sections['all'] or content

    return sections


def apply_sqlite(sql: str, db_path: str) -> None:
    conn = sqlite3.connect(db_path)
    try:
        cur = conn.cursor()
        # Execute statements one-by-one to allow ignoring benign errors (e.g. duplicate column)
        statements = [s.strip() for s in sql.split(';') if s.strip()]
        for stmt in statements:
            try:
                cur.execute(stmt)
            except sqlite3.OperationalError as e:
                msg = str(e).lower()
                # Ignore duplicate column / table already exists errors for idempotency
                if 'duplicate column' in msg or 'already exists' in msg or 'duplicate' in msg:
                    print(f"Ignored sqlite warning: {e}")
                    continue
                raise
        conn.commit()
        print(f"Applied SQLite migration to {db_path}")
    finally:
        conn.close()


def apply_postgres(sql: str, dsn: str) -> None:
    try:
        import psycopg
    except Exception as e:
        print("psycopg not available; install requirements to apply Postgres migrations: pip install -r requirements.txt")
        raise

    with psycopg.connect(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(sql)
        conn.commit()
    print("Applied Postgres migration")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument('--migrations', default='migrations', help='Migrations directory')
    p.add_argument('--sqlite-db', help='Path to SQLite DB file')
    p.add_argument('--pg-dsn', help='Postgres DSN (e.g. postgresql://user:pass@host/db)')
    args = p.parse_args()

    if not os.path.isdir(args.migrations):
        raise SystemExit(f'migrations dir not found: {args.migrations}')

    files = sorted(glob(os.path.join(args.migrations, '*.sql')))
    if not files:
        print('No migration files found')
        return

    for f in files:
        print('Processing', f)
        sections = load_migration_sections(f)
        if args.sqlite_db:
            sql = sections.get('sqlite') or sections.get('all')
            try:
                apply_sqlite(sql, args.sqlite_db)
            except Exception as e:
                print(f'Error applying {f} to sqlite: {e}')
                raise

        if args.pg_dsn:
            sql = sections.get('postgres') or sections.get('all')
            try:
                apply_postgres(sql, args.pg_dsn)
            except Exception as e:
                print(f'Error applying {f} to postgres: {e}')
                raise


if __name__ == '__main__':
    main()
