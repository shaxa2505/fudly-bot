"""Security helpers with graceful fallbacks for local environments."""
from __future__ import annotations

import logging
import os
from typing import Any, Awaitable, Callable, TypeVar

T = TypeVar("T")

try:
    from security import (  # type: ignore[import]
        rate_limiter,
        secure_user_input,
        validate_admin_action,
        validator,
    )
    from logging_config import logger  # type: ignore[import]

    def start_background_tasks(db: Any) -> None:
        """Background tasks starter (production)."""
        logger.info("Background tasks ready")

    PRODUCTION_FEATURES = True
except ImportError as exc:  # pragma: no cover - fallback for local dev
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger("fudly")
    logger.warning("Production security modules unavailable: %s", exc)

    class FallbackValidator:
        """Fallback validator for local development."""

        @staticmethod
        def sanitize_text(text: Any, max_length: int = 1000) -> str:
            """Sanitize text input."""
            return str(text)[:max_length] if text else ""

        @staticmethod
        def validate_city(city: Any) -> bool:
            """Validate city name."""
            return bool(city and len(str(city)) < 50)

    class FallbackRateLimiter:
        """Fallback rate limiter for local development."""

        def is_allowed(self, *_: Any, **__: Any) -> bool:
            """Always allow in development mode."""
            return True

    def secure_user_input(func: Callable[..., Awaitable[T]]) -> Callable[..., Awaitable[T]]:
        """Security decorator fallback."""
        async def wrapper(*args: Any, **kwargs: Any) -> T:
            return await func(*args, **kwargs)

        return wrapper

    def validate_admin_action(user_id: int, db: Any) -> bool:
        """Validate admin action fallback."""
        return db.is_admin(user_id)

    validator = FallbackValidator()
    rate_limiter = FallbackRateLimiter()

    def start_background_tasks(db: Any) -> None:
        """Background tasks placeholder."""
        logger.info("Background tasks placeholder")

    PRODUCTION_FEATURES: bool = os.getenv("PRODUCTION_FEATURES", "False").lower() == "true"

__all__ = [
    "validator",
    "rate_limiter",
    "secure_user_input",
    "validate_admin_action",
    "logger",
    "start_background_tasks",
    "PRODUCTION_FEATURES",
]
