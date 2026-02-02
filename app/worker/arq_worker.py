"""Arq worker for scheduled background tasks."""
from __future__ import annotations

import os
from typing import Any

from arq import cron
from arq.connections import RedisSettings
from aiogram import Bot

from app.core.config import load_settings
from app.core.database import create_database
from tasks.booking_expiry_worker import run_booking_expiry_cycle
from tasks.rating_reminder_worker import run_rating_reminder_cycle


async def startup(ctx: dict[str, Any]) -> None:
    settings = load_settings()
    db = create_database(settings.database_url)
    bot = Bot(settings.bot_token)
    ctx["db"] = db
    ctx["bot"] = bot
    ctx["settings"] = settings


async def shutdown(ctx: dict[str, Any]) -> None:
    bot = ctx.get("bot")
    db = ctx.get("db")
    if bot:
        try:
            await bot.session.close()
        except Exception:
            pass
    if db and hasattr(db, "close"):
        try:
            db.close()
        except Exception:
            pass


async def booking_expiry(ctx: dict[str, Any]) -> None:
    await run_booking_expiry_cycle(ctx["db"], ctx["bot"])


async def rating_reminder(ctx: dict[str, Any]) -> None:
    await run_rating_reminder_cycle(ctx["db"], ctx["bot"])


def _redis_settings() -> RedisSettings:
    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    return RedisSettings.from_dsn(redis_url)


class WorkerSettings:
    redis_settings = _redis_settings()
    functions = [booking_expiry, rating_reminder]
    cron_jobs = [
        cron(booking_expiry, minute="*/5"),
        cron(rating_reminder, minute="*/30"),
    ]
    on_startup = startup
    on_shutdown = shutdown

