from __future__ import annotations

from fastapi import APIRouter

from .common import set_db_instance

_router: APIRouter | None = None


def get_router() -> APIRouter:
    """Build webapp router lazily to avoid circular imports."""
    global _router
    if _router is not None:
        return _router

    from . import (
        routes_cart,
        routes_favorites,
        routes_location,
        routes_offers,
        routes_orders,
        routes_photo,
        routes_search,
        routes_search_stats,
        routes_stores,
    )

    router = APIRouter(prefix="/api/v1", tags=["webapp"])
    router.include_router(routes_offers.router)
    router.include_router(routes_stores.router)
    router.include_router(routes_orders.router)
    router.include_router(routes_favorites.router)
    router.include_router(routes_cart.router)
    router.include_router(routes_photo.router)
    router.include_router(routes_search.router)
    router.include_router(routes_search_stats.router)
    router.include_router(routes_location.router)

    _router = router
    return _router


def __getattr__(name: str):
    if name == "router":
        return get_router()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = ["router", "get_router", "set_db_instance"]
