from __future__ import annotations

import logging
import os
import secrets
import time
from typing import Any

from app.core.caching import get_cache_service

logger = logging.getLogger("fudly")

_WS_TOKEN_TTL_SECONDS = int(os.getenv("WS_AUTH_TOKEN_TTL_SECONDS", "60"))
_WS_TOKEN_PREFIX = "ws:token:"


def _cache_key(token: str) -> str:
    return f"{_WS_TOKEN_PREFIX}{token}"


async def issue_ws_token(user_id: int, store_id: int | None = None) -> tuple[str, int]:
    token = secrets.token_urlsafe(32)
    payload = {
        "user_id": int(user_id),
        "store_id": int(store_id) if store_id is not None else None,
        "issued_at": int(time.time()),
    }
    cache = get_cache_service(os.getenv("REDIS_URL"))
    try:
        await cache.set(_cache_key(token), payload, ttl=_WS_TOKEN_TTL_SECONDS)
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("Failed to store ws token: %s", exc)
    return token, _WS_TOKEN_TTL_SECONDS


async def consume_ws_token(token: str) -> dict[str, Any] | None:
    if not token:
        return None
    cache = get_cache_service(os.getenv("REDIS_URL"))
    key = _cache_key(token)
    try:
        payload = await cache.get(key)
        if payload is None:
            return None
        await cache.delete(key)
        return payload if isinstance(payload, dict) else None
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("Failed to read ws token: %s", exc)
        return None
