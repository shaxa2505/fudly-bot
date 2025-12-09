"""Unified Order Handlers orchestrator.

This module keeps the public API (`router`, `setup_dependencies`)
but delegates all concrete handlers to dedicated submodules under
`handlers.common.unified_order`.
"""
from __future__ import annotations

from typing import Any

from aiogram import Router

from .unified_order import common as unified_common
from .unified_order import seller as unified_seller
from .unified_order import customer as unified_customer


router = Router(name="unified_order_handlers")


def setup_dependencies(database: Any, bot_instance: Any) -> None:
    """Initialize shared deps and register unified order handlers.

    This preserves the original entry point used in `bot.py` while
    moving heavy handler implementations into smaller focused modules.
    """

    unified_common.setup_dependencies(database, bot_instance)
    unified_seller.register(router)
    unified_customer.register(router)
