"""Application bootstrap wiring bot, dispatcher, storage, and db."""
from __future__ import annotations

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.storage.redis import RedisStorage

from .cache import CacheManager
from .config import Settings
from .database import create_database
from .security import logger


def build_application(settings: Settings):
    """Create bot runtime components from configuration."""
    bot = Bot(token=settings.bot_token)
    db = create_database(settings.database_url)

    # Priority 1: Redis (Best for production)
    if settings.redis_url:
        try:
            storage = RedisStorage.from_url(settings.redis_url)
            print("🚀 Using Redis for FSM storage")
            logger.info("Using Redis for FSM storage")
        except Exception as e:
            print(f"⚠️ Failed to initialize Redis storage: {e}")
            storage = MemoryStorage()
            logger.warning("Failed to initialize Redis storage, using MemoryStorage")

    # Priority 2: PostgreSQL (Good fallback)
    elif settings.database_url and "postgresql" in settings.database_url:
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

    # Priority 3: Memory (Local dev)
    else:
        storage = MemoryStorage()
        print("💾 Using SQLite database with MemoryStorage")
        print("⚠️ FSM states will be LOST on restart")
        logger.info("Using SQLite for local development with MemoryStorage")

    dispatcher = Dispatcher(storage=storage)
    cache = CacheManager(db)

    return bot, dispatcher, db, cache
