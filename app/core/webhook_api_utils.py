"""Shared helpers for webhook Mini App API routes."""
from __future__ import annotations

import logging
import os
import urllib.parse
from typing import Callable

from aiohttp import web

logger = logging.getLogger("fudly")


def _origin_from_url(value: str | None) -> str | None:
    if not value:
        return None
    try:
        parsed = urllib.parse.urlsplit(value.strip())
    except Exception:
        return None
    if not parsed.scheme or not parsed.netloc:
        return None
    return f"{parsed.scheme}://{parsed.netloc}"


def _resolve_cors_origin() -> str:
    environment = os.getenv("ENVIRONMENT", "production").lower()
    is_dev = environment in ("development", "dev", "local", "test")
    partner_panel_enabled = os.getenv("PARTNER_PANEL_ENABLED", "0").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }

    # Prefer explicit origins, fall back to WEBAPP_URL
    origin = _origin_from_url(os.getenv("WEBAPP_ORIGIN")) or _origin_from_url(
        os.getenv("WEBAPP_URL")
    )

    if partner_panel_enabled and not origin:
        origin = _origin_from_url(os.getenv("PARTNER_PANEL_ORIGIN")) or _origin_from_url(
            os.getenv("PARTNER_PANEL_URL")
        )

    if origin:
        return origin

    if is_dev:
        return "*"

    logger.warning("⚠️ CORS origin not configured; falling back to '*'")
    return "*"


_CORS_ALLOW_ORIGIN = _resolve_cors_origin()


async def cors_preflight(request: web.Request) -> web.Response:
    """Handle CORS preflight requests."""
    return web.Response(
        status=200,
        headers={
            "Access-Control-Allow-Origin": _CORS_ALLOW_ORIGIN,
            "Access-Control-Allow-Methods": "GET, POST, DELETE, OPTIONS",
            "Access-Control-Allow-Headers": (
                "Content-Type, X-Telegram-Init-Data, Idempotency-Key, X-Idempotency-Key"
            ),
            "Access-Control-Max-Age": "86400",
        },
    )


def add_cors_headers(response: web.Response) -> web.Response:
    """Add CORS headers to response."""
    response.headers["Access-Control-Allow-Origin"] = _CORS_ALLOW_ORIGIN
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, DELETE, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = (
        "Content-Type, X-Telegram-Init-Data, Idempotency-Key, X-Idempotency-Key"
    )
    return response


def build_authenticated_user_id(bot_token: str) -> Callable[[web.Request], int | None]:
    """Factory to validate Telegram initData and return authenticated user_id."""

    def _get_authenticated_user_id(request: web.Request) -> int | None:
        """Validate Telegram initData and return authenticated user_id.

        Mini App must send `X-Telegram-Init-Data` header.
        """
        init_data = request.headers.get("X-Telegram-Init-Data")
        if not init_data:
            return None

        try:
            from app.api.webapp.common import validate_init_data

            validated = validate_init_data(init_data, bot_token)
        except Exception:
            return None

        if not validated:
            return None

        user = validated.get("user")
        if not isinstance(user, dict):
            return None

        try:
            return int(user.get("id"))
        except Exception:
            return None

    return _get_authenticated_user_id
