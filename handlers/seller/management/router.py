"""Main router combining all seller management sub-routers."""
from __future__ import annotations

from aiogram import Router

from . import offers, orders, pickup

# Create main router
router = Router(name="seller_management")

# Include sub-routers
router.include_router(pickup.router)
router.include_router(offers.router)
router.include_router(orders.router)
