"""
Customer orders router - delivery orders and history.

Delivery handlers are split into modules:
- delivery.py - Customer flow (qty, address, payment)
- delivery_admin.py - Admin payment confirmation
- delivery_partner.py - Partner order confirmation
- delivery_ui.py - UI builders (cards, keyboards)
"""
from aiogram import Router

from . import delivery, delivery_admin, delivery_partner, history

router = Router(name="customer_orders")
router.include_router(history.router)
router.include_router(delivery.router)
router.include_router(delivery_admin.router)  # Admin payment confirmation
router.include_router(delivery_partner.router)
