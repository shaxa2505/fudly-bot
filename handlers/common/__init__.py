"""
Common handlers - shared utilities, registration, commands.

This module provides backward compatibility with the old handlers/common.py
All new code should import from handlers.common.utils and handlers.common.states
"""

# Re-export from utils for backward compatibility
# Export router
from handlers.common.router import router as common_router

# Re-export states for backward compatibility
from handlers.common.states import (
    BookOffer,
    Browse,
    BrowseOffers,
    BulkCreate,
    ChangeCity,
    ConfirmOrder,
    CreateOffer,
    EditOffer,
    OrderDelivery,
    RegisterStore,
    Registration,
    Search,
)
from handlers.common.utils import (
    CITY_UZ_TO_RU,
    UZB_TZ,
    RegistrationCheckMiddleware,
    get_appropriate_menu,
    get_uzb_time,
    has_approved_store,
    normalize_city,
    user_view_mode,
)

__all__ = [
    # Router
    "common_router",
    # States
    "Registration",
    "RegisterStore",
    "CreateOffer",
    "BulkCreate",
    "ChangeCity",
    "EditOffer",
    "ConfirmOrder",
    "BookOffer",
    "BrowseOffers",
    "OrderDelivery",
    "Search",
    "Browse",
    # Utils
    "user_view_mode",
    "normalize_city",
    "get_uzb_time",
    "has_approved_store",
    "get_appropriate_menu",
    "RegistrationCheckMiddleware",
    "UZB_TZ",
    "CITY_UZ_TO_RU",
]
