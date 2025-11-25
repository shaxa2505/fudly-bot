"""
Security module - Input validation, rate limiting, and security helpers.

This is the single source of truth for all security-related functionality.
"""
from __future__ import annotations

import asyncio
import functools
import html
import inspect
import logging
import os
import re
import time
from collections.abc import Awaitable, Callable
from typing import Any, TypeVar

# Configure logging
try:
    from logging_config import logger
except ImportError:
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger("fudly")


T = TypeVar("T")


# =============================================================================
# INPUT VALIDATION
# =============================================================================


class InputValidator:
    """Input validation and sanitization for Telegram bot security."""

    # Regex patterns for validation
    PHONE_PATTERN = re.compile(r"^\+?[1-9]\d{1,14}$")
    USERNAME_PATTERN = re.compile(r"^[a-zA-Z0-9_]{3,32}$")
    CITY_PATTERN = re.compile(r"^[a-zA-Zа-яА-Яўғқҳ\s\-\']{1,50}$", re.UNICODE)
    PRICE_PATTERN = re.compile(r"^\d+(\.\d{1,2})?$")

    @staticmethod
    def sanitize_text(text: Any, max_length: int = 1000) -> str:
        """Sanitize text input by escaping HTML and limiting length."""
        if not text or not isinstance(text, str):
            return ""

        # Escape HTML entities to prevent XSS
        sanitized = html.escape(text.strip())

        # Limit length
        if len(sanitized) > max_length:
            sanitized = sanitized[:max_length] + "..."

        return sanitized

    @staticmethod
    def validate_phone(phone: str) -> bool:
        """Validate phone number format (E.164 compatible)."""
        if not phone:
            return False
        # Remove common formatting characters
        cleaned = phone.replace(" ", "").replace("-", "").replace("(", "").replace(")", "")
        return bool(InputValidator.PHONE_PATTERN.match(cleaned))

    @staticmethod
    def validate_username(username: str) -> bool:
        """Validate Telegram username format."""
        if not username:
            return False
        return bool(InputValidator.USERNAME_PATTERN.match(username))

    @staticmethod
    def validate_city(city: Any) -> bool:
        """Validate city name."""
        if not city:
            return False
        city_str = str(city)
        return bool(InputValidator.CITY_PATTERN.match(city_str)) and len(city_str) < 50

    @staticmethod
    def validate_price(price_str: str) -> tuple[bool, float]:
        """Validate and parse price string. Returns (is_valid, parsed_price)."""
        if not price_str:
            return False, 0.0

        if InputValidator.PRICE_PATTERN.match(price_str):
            try:
                price = float(price_str)
                if 0 <= price <= 999999999:  # Reasonable price range (up to ~1M USD)
                    return True, price
            except ValueError:
                pass

        return False, 0.0

    @staticmethod
    def validate_quantity(quantity_str: str) -> tuple[bool, int]:
        """Validate and parse quantity string."""
        if not quantity_str:
            return False, 0

        try:
            quantity = int(quantity_str)
            if 1 <= quantity <= 10000:  # Reasonable quantity range
                return True, quantity
        except ValueError:
            pass

        return False, 0


# =============================================================================
# RATE LIMITING
# =============================================================================


class RateLimiter:
    """
    In-memory rate limiter for user actions.

    Note: For horizontal scaling, consider using Redis-based rate limiting.
    """

    def __init__(self) -> None:
        self._user_requests: dict[int, dict[str, list[float]]] = {}

    def is_allowed(
        self,
        user_id: int,
        action: str,
        max_requests: int = 10,
        window_seconds: int = 60,
    ) -> bool:
        """
        Check if user is allowed to perform action within rate limit.

        Args:
            user_id: Telegram user ID
            action: Action identifier (e.g., 'search', 'booking')
            max_requests: Maximum requests allowed in window
            window_seconds: Time window in seconds

        Returns:
            True if action is allowed, False if rate limited
        """
        current_time = time.time()

        if user_id not in self._user_requests:
            self._user_requests[user_id] = {}

        if action not in self._user_requests[user_id]:
            self._user_requests[user_id][action] = []

        # Clean old timestamps
        requests = self._user_requests[user_id][action]
        self._user_requests[user_id][action] = [
            ts for ts in requests if current_time - ts < window_seconds
        ]

        # Check if under limit
        if len(self._user_requests[user_id][action]) < max_requests:
            self._user_requests[user_id][action].append(current_time)
            return True

        logger.warning(f"Rate limit exceeded: user={user_id}, action={action}")
        return False

    def clear_user(self, user_id: int) -> None:
        """Clear rate limit data for a user."""
        self._user_requests.pop(user_id, None)


# =============================================================================
# DECORATORS
# =============================================================================


def secure_user_input(func: Callable[..., Awaitable[T]]) -> Callable[..., Awaitable[T]]:
    """
    Decorator to add security logging to handlers.

    Logs handler calls and catches exceptions for security monitoring.
    """

    @functools.wraps(func)
    async def wrapper(*args: Any, **kwargs: Any) -> T:
        try:
            logger.debug(f"Handler called: {func.__name__}")

            if inspect.iscoroutinefunction(func):
                return await func(*args, **kwargs)
            else:
                loop = asyncio.get_event_loop()
                return await loop.run_in_executor(None, lambda: func(*args, **kwargs))

        except Exception as e:
            logger.error(f"Handler {func.__name__} failed: {e}")
            raise

    return wrapper


def validate_admin_action(user_id: int, db: Any) -> bool:
    """
    Validate that user is an admin and log the action.

    Args:
        user_id: Telegram user ID
        db: Database instance with is_admin method

    Returns:
        True if user is admin, False otherwise
    """
    try:
        is_admin = db.is_admin(user_id)
        if not is_admin:
            logger.warning(f"Unauthorized admin action attempt: user={user_id}")
        return is_admin
    except Exception as e:
        logger.error(f"Admin validation failed: user={user_id}, error={e}")
        return False


# =============================================================================
# BACKGROUND TASKS
# =============================================================================


def start_background_tasks(db: Any) -> None:
    """Start background maintenance tasks."""
    logger.info("Background tasks initialized")
    # Add any periodic tasks here (e.g., cleanup, stats collection)


# =============================================================================
# GLOBAL INSTANCES
# =============================================================================

validator = InputValidator()
rate_limiter = RateLimiter()

# Production features flag
PRODUCTION_FEATURES: bool = os.getenv("PRODUCTION_FEATURES", "true").lower() in {"true", "1", "yes"}


# =============================================================================
# EXPORTS
# =============================================================================

__all__ = [
    "InputValidator",
    "RateLimiter",
    "validator",
    "rate_limiter",
    "secure_user_input",
    "validate_admin_action",
    "start_background_tasks",
    "logger",
    "PRODUCTION_FEATURES",
]
