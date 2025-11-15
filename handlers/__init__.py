"""
Handlers package - modular bot handlers using aiogram Router

This package contains modular handlers organized by functionality:
- bookings: Booking management (create, view, cancel, rate)
- orders: Delivery order management (payment, confirmation)
- partner: Partner registration and store management
- seller: Seller functionality (create offers, management, analytics)
- user: User functionality (profile, favorites, city management)
- registration: User registration (phone, city)
- user_commands: Basic commands (/start, language, city selection, cancel)
- admin: Admin panel and commands
- admin_stats: Admin statistics and dashboards
- offers: Offer browsing and display
- common: Shared states and utilities

Routers are registered directly in bot.py, not through this package.
"""

# No automatic router registration - each module is imported and registered separately in bot.py
