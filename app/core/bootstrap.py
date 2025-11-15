"""Application bootstrap wiring bot, dispatcher, storage, and db."""
from __future__ import annotations

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage

from .cache import CacheManager
from .config import Settings
from .database import create_database
from .security import logger


def build_application(settings: Settings):
    """Create bot runtime components from configuration."""
    bot = Bot(token=settings.bot_token)
    storage = MemoryStorage()
    dispatcher = Dispatcher(storage=storage)
    db = create_database(settings.database_url)
    cache = CacheManager(db)

    if settings.database_url:
        print("💾 Using PostgreSQL database with MemoryStorage")
        print("📝 FSM states saved in database for persistence")
        logger.info("Using PostgreSQL with FSM state persistence in database")
    else:
        print("💾 Using SQLite database with MemoryStorage")
        logger.info("Using SQLite for local development")

    return bot, dispatcher, db, cache
