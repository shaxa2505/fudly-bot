from __future__ import annotations

import os

from fastapi import Request
from slowapi import Limiter
from slowapi.util import get_remote_address


def _rate_limit_storage_uri() -> str | None:
    return os.getenv("RATE_LIMIT_REDIS_URL") or os.getenv("REDIS_URL") or None


def _get_client_ip(request: Request) -> str:
    """Resolve client IP with proxy headers support."""
    xff = request.headers.get("X-Forwarded-For")
    if xff:
        parts = [part.strip() for part in xff.split(",") if part.strip()]
        if parts:
            return parts[0]

    x_real_ip = request.headers.get("X-Real-IP")
    if x_real_ip:
        return x_real_ip.strip()

    if request.client and request.client.host:
        return request.client.host

    return get_remote_address(request)


_rl_storage = _rate_limit_storage_uri()
if _rl_storage:
    limiter = Limiter(
        key_func=_get_client_ip,
        default_limits=["100/minute"],
        storage_uri=_rl_storage,
    )
else:
    limiter = Limiter(
        key_func=_get_client_ip,
        default_limits=["100/minute"],
    )


__all__ = ["limiter"]
