**Migrations Runbook**

- **Purpose**: apply SQL migration files in `migrations/` to local SQLite DB or a Postgres database.

- **Quick usage (SQLite)**:

```powershell
# Activate venv if needed
& .\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python .\scripts\apply_migrations.py --sqlite-db .\fudly.db
```

- **Quick usage (Postgres)**:

```powershell
# Ensure env var PG_DSN or pass DSN explicitly
python .\scripts\apply_migrations.py --pg-dsn "postgresql://user:password@host:5432/dbname"
```

- **Notes & tips**:
  - The migration SQL files use markers `-- SQLite` and `-- Postgres`; the helper script will apply the correct section for the chosen DB.
  - If you prefer manual control, open each `migrations/*.sql` and run the DB-specific block using `sqlite3` or `psql`.
  - For production, take a DB backup before applying migrations.

**Example: manual SQLite via sqlite3 CLI**

```powershell
sqlite3 .\fudly.db < migrations\001_add_pickup_fields.sql
```

This will only work if the file contains pure SQLite SQL; prefer the helper script when files contain both variants.

**Rollback / safety**

- The migrations provided are additive (ADD COLUMN, CREATE TABLE). If you need to revert, you must restore from backup.
