"""Standalone booking expiry worker.
This script can be run separately from the bot process to perform reminders and auto-cancels.
Usage:
    python scripts/booking_expiry_worker.py

Environment variables required:
- DATABASE_URL (Postgres) or leave empty to use local SQLite
- TELEGRAM_BOT_TOKEN for sending messages

This script will import the project's `Database` implementation and start the same worker
logic implemented in `tasks/booking_expiry_worker.py`.
"""
import asyncio
import logging
import os
import sys

from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create DB instance (postgres if DATABASE_URL set, otherwise fallback to sqlite database.py)
try:
    if os.environ.get("DATABASE_URL"):
        from database_pg import Database as PgDatabase

        db = PgDatabase(os.environ.get("DATABASE_URL"))
    else:
        from database import Database as SqliteDatabase

        db = SqliteDatabase()
except Exception as e:
    logger.error(f"Failed to initialize database: {e}")
    sys.exit(1)

# Create bot
try:
    from aiogram import Bot

    BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not BOT_TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN is required to send reminders")
        sys.exit(1)
    bot = Bot(token=BOT_TOKEN)
except Exception as e:
    logger.error(f"Failed to create bot: {e}")
    sys.exit(1)


# Start worker
async def main():
    try:
        from tasks.booking_expiry_worker import start_booking_expiry_worker
    except Exception as e:
        logger.error(f"Worker import failed: {e}")
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
