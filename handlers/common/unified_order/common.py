"""Shared utilities and dependencies for unified order handlers."""
from __future__ import annotations

from typing import Any

try:
    from logging_config import logger
except ImportError:  # pragma: no cover - fallback for local runs
    import logging

    logger = logging.getLogger(__name__)


db: Any = None
bot: Any = None


def setup_dependencies(database: Any, bot_instance: Any) -> None:
    """Store shared DB and bot instances for unified order handlers."""
    global db, bot
    db = database
    bot = bot_instance


def _get_db() -> Any:
    """Return configured DB instance (may be None if not initialized)."""
    return db


def _get_store_field(store: Any, field: str, default: Any | None = None) -> Any:
    """Safely read a field from a store model or dict."""
    if isinstance(store, dict):
        return store.get(field, default)
    return getattr(store, field, default) if store is not None else default


def _get_entity_field(entity: Any, field: str, default: Any | None = None) -> Any:
    """Safely read a field from an order/booking model or dict."""
    if isinstance(entity, dict):
        return entity.get(field, default)
    if hasattr(entity, field):
        return getattr(entity, field, default)
    return default
