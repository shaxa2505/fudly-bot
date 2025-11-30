"""
Sentry Integration for Error Tracking.

This module initializes Sentry for error monitoring in the bot.
All unhandled exceptions will be automatically reported.
"""

import logging
import os

logger = logging.getLogger(__name__)

# Sentry DSN from environment
SENTRY_DSN = os.getenv("SENTRY_DSN", "")
ENVIRONMENT = os.getenv("RAILWAY_ENVIRONMENT", os.getenv("ENVIRONMENT", "development"))


def init_sentry() -> bool:
    """
    Initialize Sentry SDK for error tracking.

    Returns:
        True if Sentry was initialized, False otherwise.
    """
    if not SENTRY_DSN:
        logger.info("Sentry DSN not configured, skipping initialization")
        return False

    try:
        import sentry_sdk
        from sentry_sdk.integrations.aiohttp import AioHttpIntegration
        from sentry_sdk.integrations.logging import LoggingIntegration

        # Configure logging integration
        logging_integration = LoggingIntegration(
            level=logging.INFO,  # Capture info and above as breadcrumbs
            event_level=logging.ERROR,  # Send errors as events
        )

        sentry_sdk.init(
            dsn=SENTRY_DSN,
            environment=ENVIRONMENT,
            traces_sample_rate=0.1,  # 10% of transactions for performance
            profiles_sample_rate=0.1,
            integrations=[
                AioHttpIntegration(),
                logging_integration,
            ],
            # Don't send PII by default
            send_default_pii=False,
            # Release version
            release=os.getenv("RAILWAY_GIT_COMMIT_SHA", "local"),
        )

        logger.info(f"Sentry initialized for environment: {ENVIRONMENT}")
        return True

    except ImportError:
        logger.warning("sentry-sdk not installed, skipping initialization")
        return False
    except Exception as e:
        logger.error(f"Failed to initialize Sentry: {e}")
        return False


def capture_exception(error: Exception, **extra) -> None:
    """Capture an exception and send to Sentry."""
    try:
        import sentry_sdk

        with sentry_sdk.push_scope() as scope:
            for key, value in extra.items():
                scope.set_extra(key, value)
            sentry_sdk.capture_exception(error)
    except Exception:
        pass  # Don't fail if Sentry is not available


def capture_message(message: str, level: str = "info", **extra) -> None:
    """Capture a message and send to Sentry."""
    try:
        import sentry_sdk

        with sentry_sdk.push_scope() as scope:
            for key, value in extra.items():
                scope.set_extra(key, value)
            sentry_sdk.capture_message(message, level=level)
    except Exception:
        pass


def set_user(user_id: int, username: str | None = None) -> None:
    """Set user context for Sentry events."""
    try:
        import sentry_sdk

        sentry_sdk.set_user(
            {
                "id": str(user_id),
                "username": username,
            }
        )
    except Exception:
        pass
