"""Business services orchestrating domain logic.

Compatibility layer: re-export unified order service under legacy names so
any stray imports still go through the canonical implementation.
"""

from .unified_order_service import (
    OrderItem,
    OrderResult,
    UnifiedOrderService as OrderService,
    get_unified_order_service as get_order_service,
    init_unified_order_service as init_order_service,
)

__all__ = ["OrderItem", "OrderResult", "OrderService", "get_order_service", "init_order_service"]
