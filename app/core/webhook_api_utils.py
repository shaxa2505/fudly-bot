"""Shared helpers for webhook Mini App API routes."""
from __future__ import annotations

from typing import Callable

from aiohttp import web


async def cors_preflight(request: web.Request) -> web.Response:
    """Handle CORS preflight requests."""
    return web.Response(
        status=200,
        headers={
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET, POST, DELETE, OPTIONS",
            "Access-Control-Allow-Headers": (
                "Content-Type, X-Telegram-Init-Data, Idempotency-Key, X-Idempotency-Key"
            ),
            "Access-Control-Max-Age": "86400",
        },
    )


def add_cors_headers(response: web.Response) -> web.Response:
    """Add CORS headers to response."""
    response.headers["Access-Control-Allow-Origin"] = "*"
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
