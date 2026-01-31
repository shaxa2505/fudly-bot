"""Keyboards package - centralized keyboard management.

Usage:
    from app.keyboards import (
        # Common
        language_keyboard,
        cancel_keyboard,
        phone_request_keyboard,
        city_keyboard,

        # User
        main_menu_customer,
        settings_keyboard,
        booking_filters_keyboard,

        # Seller
        main_menu_seller,
        offer_manage_keyboard,

        # Admin
        admin_menu,
        admin_users_keyboard,

        # Offers
        hot_offers_pagination_keyboard,
        offer_details_keyboard,

        # Inline
        offer_keyboard,
        filters_keyboard,
    )
"""

# Common keyboards
# Admin keyboards
from .admin import (
    admin_bookings_keyboard,
    admin_menu,
    admin_offers_keyboard,
    admin_stores_keyboard,
    admin_users_keyboard,
)
from .common import (
    cancel_keyboard,
    category_inline_keyboard,
    category_keyboard,
    city_inline_keyboard,
    city_keyboard,
    discount_keyboard,
    expiry_keyboard,
    language_keyboard,
    phone_request_keyboard,
    photo_keyboard,
    product_categories_keyboard,
    quantity_keyboard,
    unit_type_keyboard,
    units_keyboard,
)

# Inline keyboards (generic)
from .inline import (
    filters_keyboard,
    offer_keyboard,
    rating_filter_keyboard,
)

# Offers keyboards (specific flows)
from .offers import (
    hot_offers_compact_keyboard,
    offer_details_keyboard,
    offer_details_with_back_keyboard,
    offer_quick_keyboard,
    search_results_compact_keyboard,
    store_card_keyboard,
    store_list_keyboard,
    store_offers_compact_keyboard,
    store_offers_keyboard,
    store_reviews_keyboard,
)

# Seller keyboards
from .seller import (
    main_menu_seller,
    moderation_keyboard,
    offer_manage_keyboard,
    store_keyboard,
)

# User keyboards
from .user import (
    booking_filters_keyboard,
    booking_keyboard,
    booking_rating_keyboard,
    business_type_keyboard,
    main_menu_customer,
    offers_category_filter,
    registration_complete_keyboard,
    search_cancel_keyboard,
    settings_keyboard,
    stores_list_keyboard,
)

__all__ = [
    # Common
    "language_keyboard",
    "cancel_keyboard",
    "phone_request_keyboard",
    "city_keyboard",
    "city_inline_keyboard",
    "category_keyboard",
    "category_inline_keyboard",
    "units_keyboard",
    "unit_type_keyboard",
    "product_categories_keyboard",
    # User
    "main_menu_customer",
    "registration_complete_keyboard",
    "search_cancel_keyboard",
    "settings_keyboard",
    "booking_filters_keyboard",
    "booking_keyboard",
    "booking_rating_keyboard",
    "business_type_keyboard",
    "stores_list_keyboard",
    "offers_category_filter",
    # Seller
    "main_menu_seller",
    "offer_manage_keyboard",
    "store_keyboard",
    "moderation_keyboard",
    # Admin
    "admin_menu",
    "admin_users_keyboard",
    "admin_stores_keyboard",
    "admin_offers_keyboard",
    "admin_bookings_keyboard",
    # Offers
    "hot_offers_compact_keyboard",
    "search_results_compact_keyboard",
    "store_card_keyboard",
    "store_list_keyboard",
    "offer_details_keyboard",
    "offer_details_with_back_keyboard",
    "offer_quick_keyboard",
    "store_offers_compact_keyboard",
    "store_offers_keyboard",
    "store_reviews_keyboard",
    # Inline
    "offer_keyboard",
    "filters_keyboard",
    "rating_filter_keyboard",
]
