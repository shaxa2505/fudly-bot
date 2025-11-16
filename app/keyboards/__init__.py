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
from .common import (
    language_keyboard,
    cancel_keyboard,
    phone_request_keyboard,
    city_keyboard,
    city_inline_keyboard,
    category_keyboard,
    category_inline_keyboard,
    units_keyboard,
    product_categories_keyboard,
)

# User keyboards
from .user import (
    main_menu_customer,
    settings_keyboard,
    booking_filters_keyboard,
    booking_keyboard,
    booking_rating_keyboard,
    business_type_keyboard,
    stores_list_keyboard,
    offers_category_filter,
)

# Seller keyboards
from .seller import (
    main_menu_seller,
    offer_manage_keyboard,
    store_keyboard,
    moderation_keyboard,
)

# Admin keyboards
from .admin import (
    admin_menu,
    admin_users_keyboard,
    admin_stores_keyboard,
    admin_offers_keyboard,
    admin_bookings_keyboard,
)

# Offers keyboards (specific flows)
from .offers import (
    hot_offers_pagination_keyboard,
    store_card_keyboard,
    offer_details_keyboard,
    offer_quick_keyboard,
    store_offers_keyboard,
    store_reviews_keyboard,
    back_to_hot_keyboard,
)

# Inline keyboards (generic)
from .inline import (
    offer_keyboard,
    filters_keyboard,
    rating_filter_keyboard,
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
    "product_categories_keyboard",
    # User
    "main_menu_customer",
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
    "hot_offers_pagination_keyboard",
    "store_card_keyboard",
    "offer_details_keyboard",
    "offer_quick_keyboard",
    "store_offers_keyboard",
    "store_reviews_keyboard",
    "back_to_hot_keyboard",
    # Inline
    "offer_keyboard",
    "filters_keyboard",
    "rating_filter_keyboard",
]
