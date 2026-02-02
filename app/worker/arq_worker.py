"""Arq worker for scheduled background tasks."""
from __future__ import annotations

import os
import uuid
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


async def _acquire_lock(ctx: dict[str, Any], key: str, ttl: int) -> str | None:
    redis = ctx.get("redis")
    if not redis:
        return None
    token = str(uuid.uuid4())
    try:
        ok = await redis.set(key, token, ex=ttl, nx=True)
        return token if ok else None
    except Exception:
        return None


async def _release_lock(ctx: dict[str, Any], key: str, token: str) -> None:
    redis = ctx.get("redis")
    if not redis:
        return
    # Release only if token matches
    lua = """
    if redis.call("get", KEYS[1]) == ARGV[1] then
        return redis.call("del", KEYS[1])
    else
        return 0
    end
    """
    try:
        await redis.eval(lua, 1, key, token)
    except Exception:
        try:
            current = await redis.get(key)
            if current == token:
                await redis.delete(key)
        except Exception:
            pass


async def booking_expiry(ctx: dict[str, Any]) -> None:
    ttl = int(os.getenv("ARQ_BOOKING_LOCK_TTL", "360"))
    token = await _acquire_lock(ctx, "locks:booking_expiry", ttl)
    if not token:
        return
    try:
        await run_booking_expiry_cycle(ctx["db"], ctx["bot"])
    finally:
        await _release_lock(ctx, "locks:booking_expiry", token)


async def rating_reminder(ctx: dict[str, Any]) -> None:
    ttl = int(os.getenv("ARQ_RATING_LOCK_TTL", "2100"))
    token = await _acquire_lock(ctx, "locks:rating_reminder", ttl)
    if not token:
        return
    try:
        await run_rating_reminder_cycle(ctx["db"], ctx["bot"])
    finally:
        await _release_lock(ctx, "locks:rating_reminder", token)


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
