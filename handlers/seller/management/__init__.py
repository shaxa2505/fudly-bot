"""
Seller management module - modular structure for seller handlers.

This module contains handlers for:
- offers.py: Offer CRUD (create, edit, delete, activate/deactivate)
- orders.py: Seller order management (view, confirm, complete, cancel)
- pickup.py: Pickup code verification
- utils.py: Shared utilities

Usage in bot.py:
    from handlers.seller import management
    management.setup_dependencies(db, bot)
    dp.include_router(management.router)
"""
from __future__ import annotations

from typing import Any

from .router import router
from .utils import setup_dependencies as _setup_utils

__all__ = ["router", "setup_dependencies"]


def setup_dependencies(database: Any, bot_instance: Any) -> None:
    """Setup module dependencies for all sub-modules."""
    _setup_utils(database, bot_instance)
