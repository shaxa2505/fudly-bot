"""
Security module - Backwards compatibility wrapper.

This file re-exports all security components from app.core.security
for backwards compatibility with existing imports.

New code should import from app.core.security directly.
"""
from app.core.security import (
    PRODUCTION_FEATURES,
    InputValidator,
    RateLimiter,
    logger,
    rate_limiter,
    secure_user_input,
    start_background_tasks,
    validate_admin_action,
    validator,
)

__all__ = [
    "InputValidator",
    "RateLimiter",
    "PRODUCTION_FEATURES",
    "logger",
    "rate_limiter",
    "secure_user_input",
    "start_background_tasks",
    "validate_admin_action",
    "validator",
]
