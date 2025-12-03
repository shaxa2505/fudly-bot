"""
Customer orders router - delivery orders.
"""
from aiogram import Router

from . import delivery

router = Router(name="customer_orders")
router.include_router(delivery.router)
