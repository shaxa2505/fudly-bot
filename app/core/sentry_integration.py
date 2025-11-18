"""Sentry integration for error tracking and monitoring."""
from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

# Try to import Sentry SDK
try:
    import sentry_sdk
    from sentry_sdk.integrations.logging import LoggingIntegration
    SENTRY_AVAILABLE = True
except ImportError:
    SENTRY_AVAILABLE = False
    logger.info("Sentry SDK not installed - error tracking disabled")


def init_sentry(
    environment: str = "production",
    enable_logging: bool = True,
    sample_rate: float = 1.0,
    traces_sample_rate: float = 0.1
) -> bool:
    """Initialize Sentry error tracking.
    
    Args:
        environment: Environment name (production, staging, development)
        enable_logging: Enable automatic logging integration
        sample_rate: Error sampling rate (1.0 = 100%)
        traces_sample_rate: Performance tracing rate (0.1 = 10%)
        
    Returns:
        True if Sentry was initialized successfully
    """
    if not SENTRY_AVAILABLE:
        logger.warning("Sentry SDK not available - skipping initialization")
        return False
    
    sentry_dsn = os.getenv("SENTRY_DSN")
    if not sentry_dsn:
        logger.info("SENTRY_DSN not set - error tracking disabled")
        return False
    
    try:
        # Configure Sentry
        integrations = []
        
        if enable_logging:
            # Capture ERROR and above automatically
            integrations.append(
                LoggingIntegration(
                    level=logging.INFO,       # Breadcrumbs from INFO
                    event_level=logging.ERROR # Events from ERROR
                )
            )
        
        sentry_sdk.init(
            dsn=sentry_dsn,
            environment=environment,
            integrations=integrations,
            sample_rate=sample_rate,
            traces_sample_rate=traces_sample_rate,
            # Send PII (Personally Identifiable Information) - be careful!
            send_default_pii=False,
            # Release tracking
            release=os.getenv("RAILWAY_GIT_COMMIT_SHA", "unknown"),
        )
        
        logger.info(f"✅ Sentry initialized for {environment} environment")
        return True
        
    except Exception as e:
        logger.error(f"Failed to initialize Sentry: {e}")
        return False


def capture_exception(error: Exception, **extra: Any) -> None:
    """Capture exception and send to Sentry with additional context.
    
    Args:
        error: Exception to capture
        **extra: Additional context data
    """
    if not SENTRY_AVAILABLE:
        return
    
    try:
        with sentry_sdk.push_scope() as scope:
            # Add extra context
            for key, value in extra.items():
                scope.set_context(key, value)
            
            sentry_sdk.capture_exception(error)
    except Exception as e:
        logger.error(f"Failed to capture exception in Sentry: {e}")


def capture_message(message: str, level: str = "info", **extra: Any) -> None:
    """Capture message and send to Sentry.
    
    Args:
        message: Message to send
        level: Severity level (debug, info, warning, error, fatal)
        **extra: Additional context data
    """
    if not SENTRY_AVAILABLE:
        return
    
    try:
        with sentry_sdk.push_scope() as scope:
            for key, value in extra.items():
                scope.set_context(key, value)
            
            sentry_sdk.capture_message(message, level=level)
    except Exception as e:
        logger.error(f"Failed to capture message in Sentry: {e}")


def set_user_context(user_id: int, **extra: Any) -> None:
    """Set user context for Sentry events.
    
    Args:
        user_id: Telegram user ID
        **extra: Additional user data (username, language, etc.)
    """
    if not SENTRY_AVAILABLE:
        return
    
    try:
        sentry_sdk.set_user({
            "id": str(user_id),
            **extra
        })
    except Exception as e:
        logger.error(f"Failed to set user context in Sentry: {e}")


def add_breadcrumb(message: str, category: str = "default", level: str = "info", **data: Any) -> None:
    """Add breadcrumb for debugging context.
    
    Args:
        message: Breadcrumb message
        category: Category (auth, db, ui, etc.)
        level: Severity level
        **data: Additional data
    """
    if not SENTRY_AVAILABLE:
        return
    
    try:
        sentry_sdk.add_breadcrumb(
            message=message,
            category=category,
            level=level,
            data=data
        )
    except Exception as e:
        logger.error(f"Failed to add breadcrumb in Sentry: {e}")
