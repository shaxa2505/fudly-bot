"""Cart module for customer orders.

Provides cart functionality:
- Add items to cart
- Update quantities
- Remove items
- View cart
- Checkout flow
"""
from .router import router, setup_dependencies
from .storage import CartStorage

__all__ = ["router", "setup_dependencies", "CartStorage"]
