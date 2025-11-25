"""Runner for the booking expiry worker (standalone).

This is a lightweight entrypoint that starts the same worker used inside the bot.
Run:
    python scripts/run_booking_worker.py

Environment variables required:
- `DATABASE_URL` (Postgres) or omit to use local SQLite
- `TELEGRAM_BOT_TOKEN` - bot token used to send reminders/notifications

This file is intended to be run as a separate process (systemd, Docker container, Procfile, etc.).
"""

import asyncio
import logging
import os
import sys

from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize DB
try:
    if os.environ.get("DATABASE_URL"):
        from database_pg import Database as PgDatabase

        db = PgDatabase(os.environ.get("DATABASE_URL"))
    else:
        from database import Database as SqliteDatabase

        # sqlite DB path defaults to project file (database.py handles default)
        db = SqliteDatabase()
except Exception as e:
    logger.error(f"Failed to initialize DB: {e}")
    sys.exit(1)

# Initialize Bot
try:
    from aiogram import Bot

    BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not BOT_TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN env var is missing")
        sys.exit(1)
    bot = Bot(token=BOT_TOKEN)
except Exception as e:
    logger.error(f"Failed to initialize Bot: {e}")
    sys.exit(1)


async def main():
    try:
        from tasks.booking_expiry_worker import start_booking_expiry_worker
    except Exception as e:
        logger.error(f"Could not import worker: {e}")
        return

    try:
        await start_booking_expiry_worker(db, bot)
    finally:
        try:
            await bot.session.close()
        except Exception:
            pass
        try:
            if hasattr(db, "close"):
                db.close()
        except Exception:
            pass


if __name__ == "__main__":
    asyncio.run(main())
