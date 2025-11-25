"""
Handlers package - modular bot handlers using aiogram Router

This package contains modular handlers organized by functionality:

bookings/           - Booking management (modular structure)
  ├── __init__.py   - Exports router and setup_dependencies
  ├── router.py     - Main router combining sub-routers
  ├── customer.py   - Customer actions (create, view, cancel booking)
  ├── partner.py    - Partner actions (confirm, reject, complete)
  └── utils.py      - Shared utilities

orders              - Delivery order management (payment, confirmation)
partner             - Partner registration and store management

seller/             - Seller functionality
  ├── create_offer  - Create new offers
  ├── management    - Manage existing offers
  ├── analytics     - Sales analytics
  └── bulk_import   - Mass import offers

user/               - User functionality
  ├── profile       - User profile management
  └── favorites     - Favorite stores

admin/              - Admin functionality
  ├── dashboard     - Admin dashboard
  └── legacy        - Legacy admin commands

registration        - User registration (phone, city)
user_commands       - Basic commands (/start, language, city selection)
common_user         - Common user operations
user_features       - User cart, settings

Routers are registered directly in bot.py, not through this package.
"""

# No automatic router registration - each module is imported and registered separately in bot.py
