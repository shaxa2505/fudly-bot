"""Cart system orchestrator for cart-related flows.

This module wires dedicated submodules for cart view, checkout,
delivery, payment, and add-to-cart flows while preserving the
public API (`router`, `setup_dependencies`, `show_cart`).
"""
from __future__ import annotations

from typing import Any

from aiogram import Router

from .common import setup_dependencies as _setup_common_dependencies
from . import view as cart_view
from . import checkout as cart_checkout
from . import delivery as cart_delivery
from . import payment as cart_payment
from . import add as cart_add


router = Router(name="cart")


def setup_dependencies(database: Any, bot_instance: Any) -> None:
    """Initialize shared cart dependencies and register all cart handlers.

    This keeps the original `setup_dependencies` entry point used by
    the bot while delegating to focused submodules.
    """

    # Initialize shared dependencies (DB, bot) in `common`.
    _setup_common_dependencies(database, bot_instance)

    # Register handlers from submodules on the shared `router`.
    cart_view.register(router)
    cart_checkout.register(router)
    cart_delivery.register(router)
    cart_payment.register(router)
    cart_add.register(router)


# Re-export `show_cart` for backward compatibility so existing imports like
# `from handlers.customer.cart.router import show_cart` continue to work.
from .view import show_cart  # noqa: E402,F401
