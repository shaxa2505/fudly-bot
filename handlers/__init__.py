"""
Handlers package - modular bot handlers using aiogram Router

This package contains modular handlers organized by functionality:

NEW STRUCTURE (in progress):
common/             - Common utilities, registration, commands
  ├── __init__.py   - Exports common_router
  ├── router.py     - Main router combining sub-routers
  ├── states.py     - All FSM states (from common_states/)
  ├── utils.py      - Utilities and middleware (from common.py)
  ├── registration.py - Registration handlers
  ├── commands.py   - User commands (/start, language, etc.)
  └── help.py       - Help handler

customer/           - Customer functionality
  ├── offers/       - Browse, search, favorites
  ├── bookings/     - Customer bookings
  ├── orders/       - Delivery orders
  └── menu.py       - Mode switching

seller/             - Seller functionality
  ├── bookings/     - Seller booking confirmation
  ├── management/   - Manage offers
  ├── create_offer  - Create new offers
  ├── analytics     - Sales analytics
  └── bulk_import   - Mass import offers

admin/              - Admin functionality
  ├── dashboard     - Admin dashboard
  └── legacy        - Legacy admin commands

LEGACY STRUCTURE (still in use):
bookings/           - Booking management (modular)
orders              - Delivery order management
partner             - Partner registration
user/               - User profile, favorites
registration        - User registration
user_commands       - Basic commands
common_user         - Common user operations
user_features       - User cart, settings
"""

# Backward compatibility imports from common.py -> common/utils.py
# This allows existing code to continue using `from handlers import common`
# or `from handlers.common import user_view_mode`
