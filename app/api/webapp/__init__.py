from __future__ import annotations

from fastapi import APIRouter

from . import (
    routes_cart,
    routes_favorites,
    routes_offers,
    routes_orders,
    routes_photo,
    routes_search_stats,
    routes_stores,
)
from .common import set_db_instance

router = APIRouter(prefix="/api/v1", tags=["webapp"])

router.include_router(routes_offers.router)
router.include_router(routes_stores.router)
router.include_router(routes_orders.router)
router.include_router(routes_favorites.router)
router.include_router(routes_cart.router)
router.include_router(routes_photo.router)
router.include_router(routes_search_stats.router)

__all__ = ["router", "set_db_instance"]
