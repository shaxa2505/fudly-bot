#!/usr/bin/env python3
"""
Database migration management script.

Usage:
    python scripts/migrate.py upgrade      # Apply all pending migrations
    python scripts/migrate.py downgrade    # Rollback last migration
    python scripts/migrate.py current      # Show current revision
    python scripts/migrate.py history      # Show migration history
    python scripts/migrate.py new "message" # Create new migration
    python scripts/migrate.py stamp head   # Mark DB as up-to-date (for existing DBs)
"""
import os
import sys

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv

load_dotenv()

from alembic import command
from alembic.config import Config


def get_alembic_config():
    """Get Alembic config with correct paths."""
    config = Config("alembic.ini")

    # Override database URL from environment
    db_url = os.environ.get("DATABASE_URL")
    if db_url:
        # Handle Railway's postgres:// vs postgresql://
        if db_url.startswith("postgres://"):
            db_url = db_url.replace("postgres://", "postgresql://", 1)
        config.set_main_option("sqlalchemy.url", db_url)

    return config


def upgrade(revision="head"):
    """Apply migrations up to revision."""
    config = get_alembic_config()
    command.upgrade(config, revision)
    print(f"OK Upgraded to: {revision}")


def downgrade(revision="-1"):
    """Rollback migrations."""
    config = get_alembic_config()
    command.downgrade(config, revision)
    print(f"OK Downgraded by: {revision}")


def current():
    """Show current revision."""
    config = get_alembic_config()
    command.current(config, verbose=True)


def history():
    """Show migration history."""
    config = get_alembic_config()
    command.history(config, verbose=True)


def revision(message: str, autogenerate: bool = False):
    """Create new migration."""
    config = get_alembic_config()
    command.revision(config, message=message, autogenerate=autogenerate)
    print(f"OK Created new migration: {message}")


def stamp(revision: str = "head"):
    """Stamp database with revision without running migrations.

    Useful for marking existing databases as up-to-date.
    """
    config = get_alembic_config()
    command.stamp(config, revision)
    print(f"OK Stamped database at: {revision}")


def heads():
    """Show current heads."""
    config = get_alembic_config()
    command.heads(config, verbose=True)


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    cmd = sys.argv[1].lower()

    if cmd == "upgrade":
        rev = sys.argv[2] if len(sys.argv) > 2 else "head"
        upgrade(rev)

    elif cmd == "downgrade":
        rev = sys.argv[2] if len(sys.argv) > 2 else "-1"
        downgrade(rev)

    elif cmd == "current":
        current()

    elif cmd == "history":
        history()

    elif cmd == "new":
        if len(sys.argv) < 3:
            print("Usage: python scripts/migrate.py new 'migration message'")
            sys.exit(1)
        message = sys.argv[2]
        autogen = "--autogenerate" in sys.argv or "-a" in sys.argv
        revision(message, autogenerate=autogen)

    elif cmd == "stamp":
        rev = sys.argv[2] if len(sys.argv) > 2 else "head"
        stamp(rev)

    elif cmd == "heads":
        heads()

    else:
        print(f"Unknown command: {cmd}")
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
