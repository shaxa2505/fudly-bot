"""Legacy cart checkout module (deprecated).

The real cart checkout logic now lives in
`handlers.customer.cart.router` and uses UnifiedOrderService.

This file is kept only so that old imports like
`handlers.customer.cart.cart_checkout` do not fail at import time.
It does **not** register any handlers and must not be used in new code.
"""

from __future__ import annotations

import logging

from aiogram import Router


logger = logging.getLogger(__name__)

# Dummy router placeholder (not wired anywhere)
router = Router(name="cart_checkout_legacy")

__all__ = ["router"]
