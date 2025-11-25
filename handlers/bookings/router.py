"""Main bookings router - combines customer and partner handlers."""
from __future__ import annotations

from typing import Any

from aiogram import Router

from . import customer, partner

# Main router that includes all booking sub-routers
router = Router(name="bookings")
router.include_router(customer.router)
router.include_router(partner.router)


def setup_dependencies(
    database: Any,
    bot_instance: Any,
    cache_manager: Any = None,
    metrics: dict[str, int] = None,
) -> None:
    """Setup dependencies for all booking modules.

    Args:
        database: Database protocol instance
        bot_instance: Telegram bot instance
        cache_manager: Optional cache manager
        metrics: Optional metrics dictionary
    """
    # Setup customer module
    customer.setup_dependencies(
        database=database,
        bot_instance=bot_instance,
        cache_manager=cache_manager,
        metrics=metrics,
    )

    # Setup partner module
    partner.setup_dependencies(
        database=database,
        bot_instance=bot_instance,
    )
