"""
Customer orders router - delivery orders and history.
"""
from aiogram import Router

from . import delivery, history

router = Router(name="customer_orders")
router.include_router(history.router)
router.include_router(delivery.router)
