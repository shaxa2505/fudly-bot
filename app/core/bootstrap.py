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
    db = create_database(settings.database_url)
    
    # Use PostgreSQL storage for production, Memory for local dev
    if settings.database_url and 'postgresql' in settings.database_url:
        try:
            from fsm_storage_pg import PostgreSQLStorage
            storage = PostgreSQLStorage(db)
            print("💾 Using PostgreSQL database with PostgreSQLStorage")
            print("✅ FSM states PERSIST across restarts in database")
            logger.info("Using PostgreSQL with FSM state persistence in database")
        except Exception as e:
            print(f"⚠️ Failed to initialize PostgreSQL storage: {e}")
            print("💾 Falling back to MemoryStorage (states will be lost on restart)")
            storage = MemoryStorage()
            logger.warning("Failed to initialize PostgreSQL storage, using MemoryStorage")
    else:
        storage = MemoryStorage()
        print("💾 Using SQLite database with MemoryStorage")
        print("⚠️ FSM states will be LOST on restart")
        logger.info("Using SQLite for local development with MemoryStorage")
    
    dispatcher = Dispatcher(storage=storage)
    cache = CacheManager(db)

    return bot, dispatcher, db, cache
