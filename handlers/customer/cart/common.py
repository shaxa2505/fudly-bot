"""Common cart dependencies and small helpers.

This module centralizes shared globals (db, bot) and simple helpers
used across cart submodules.
"""
from __future__ import annotations

from typing import Any

import html

# These will be set from `setup_dependencies` in `router.py`.
db: Any = None
bot: Any = None


def setup_dependencies(database: Any, bot_instance: Any) -> None:
    """Initialize shared cart dependencies (database, bot)."""
    global db, bot
    db = database
    bot = bot_instance


def esc(val: Any) -> str:
    """HTML-escape helper used in cart texts."""
    if val is None:
        return ""
    return html.escape(str(val))
