# Phase 3: Handler Extraction Progress

## Overview
Extracting handlers from monolithic `bot.py` (6,216 lines) into modular structure.

**Goal:** Reduce bot.py to < 1,000 lines by extracting all handlers into organized modules.

## Current Status

### ✅ Extracted Modules (68 handlers, 4,520 lines)

#### 📦 Booking Handlers (`handlers/bookings.py`)
- **Lines:** 386
- **Handlers:** 8
- **Functions:**
  - `book_offer_start` - Start booking flow
  - `book_offer_quantity` - Process quantity and create booking
  - `my_bookings` - Display user's bookings
  - `filter_bookings` - Filter by status
  - `cancel_booking` - Cancel booking
  - `complete_booking` - Mark complete (partner)
  - `rate_booking` - Show rating keyboard
  - `save_booking_rating` - Save rating

#### 🚚 Order Handlers (`handlers/orders.py`)
- **Lines:** 614
- **Handlers:** 10
- **Functions:**
  - `order_delivery_start` - Start delivery order
  - `order_delivery_quantity` - Process quantity
  - `order_delivery_address` - Request delivery address
  - `order_payment_proof` - Handle payment screenshot
  - `order_payment_proof_invalid` - Handle non-photo input
  - `confirm_payment` - Seller confirms payment
  - `reject_payment` - Seller rejects payment
  - `confirm_order` - Seller confirms order
  - `cancel_order` - Seller cancels order
  - `cancel_order_customer` - Customer cancels order

#### 🏪 Partner Handlers (`handlers/partner.py`)
- **Lines:** 348
- **Handlers:** 7
- **Functions:**
  - `become_partner` - Start partner registration
  - `become_partner_cb` - Partner registration from profile
  - `register_store_city` - City selection
  - `register_store_category` - Category selection
  - `register_store_name` - Store name input
  - `register_store_address` - Address input
  - `register_store_description` - Description and store creation

#### 🛍️ Seller Offer Creation (`handlers/seller/create_offer.py`)
- **Lines:** 569
- **Handlers:** 12
- **Functions:**
  - `add_offer_start` - Start offer creation
  - `create_offer_store_selected` - Process store selection
  - `create_offer_title_with_photo` - Handle photo+caption
  - `create_offer_title` - Handle title text
  - `offer_without_photo` - Skip photo from start
  - `skip_photo_goto_step2` - Skip photo after title
  - `create_offer_photo_received` - Process photo upload
  - `select_discount_percent` - Discount % button
  - `create_offer_prices_and_quantity` - Process prices (Step 2)
  - `select_category_simple` - Category selection (Step 3)
  - `select_expiry_simple` - Expiry date and create offer
  - `create_offer_photo_fallback` - Fallback for text

#### ⚙️ Seller Management (`handlers/seller/management.py`)
- **Lines:** 526
- **Handlers:** 15
- **Functions:**
  - `my_offers` - Display seller's offers
  - `quantity_add` - Increase quantity by 1
  - `quantity_subtract` - Decrease quantity by 1
  - `extend_offer` - Extend expiry date
  - `set_expiry` - Set new expiry
  - `cancel_extend` - Cancel extension
  - `deactivate_offer` - Deactivate offer
  - `activate_offer` - Activate offer
  - `delete_offer` - Delete offer
  - `edit_offer` - Show edit menu
  - `edit_time_start` - Start time editing
  - `edit_time_from` - Process start time
  - `edit_time_until` - Process end time
  - `update_offer_message` - Update message helper
  - `duplicate_offer` - Duplicate offer

#### 📊 Seller Analytics (`handlers/seller/analytics.py`)
- **Lines:** 88
- **Handlers:** 2
- **Functions:**
  - `show_analytics` - Show analytics menu
  - `show_store_analytics` - Display detailed analytics

#### 👤 User Profile (`handlers/user/profile.py`)
- **Lines:** 315
- **Handlers:** 9
- **Functions:**
  - `profile` - Display profile with statistics
  - `profile_change_city` - Start city change
  - `switch_to_customer_cb` - Switch to customer mode
  - `change_language` - Start language change
  - `toggle_notifications_callback` - Toggle notifications
  - `delete_account_prompt` - Prompt deletion
  - `confirm_delete_yes` - Confirm deletion
  - `confirm_delete_no` - Cancel deletion
  - `switch_to_customer` - Switch mode from menu

#### ❤️ User Favorites (`handlers/user/favorites.py`)
- **Lines:** 139
- **Handlers:** 5
- **Functions:**
  - `show_my_city` - Display current city
  - `change_city_process` - Process city change
  - `show_favorites` - Show favorite stores
  - `toggle_favorite` - Add to favorites
  - `remove_favorite` - Remove from favorites

### 📊 Statistics

**Extracted:**
- **Total Handlers:** 68 (46% of ~148)
- **Total Lines:** 4,520 lines of modular code
- **Modules Created:** 8 handler files

**Remaining in bot.py:**
- **Current Size:** 5,966 lines (code duplicated, not yet removed)
- **Handlers Remaining:** ~80 (54%)
- **Categories:** Admin, catalog browsing, ratings, bulk operations, misc

## Module Organization

```
handlers/
├── __init__.py (aggregates all routers)
├── bookings.py (8 handlers)
├── orders.py (10 handlers)
├── partner.py (7 handlers)
├── seller/
│   ├── __init__.py
│   ├── create_offer.py (12 handlers)
│   ├── management.py (15 handlers)
│   └── analytics.py (2 handlers)
└── user/
    ├── __init__.py
    ├── profile.py (9 handlers)
    └── favorites.py (5 handlers)
```

## Dependency Injection Pattern

All modules use consistent dependency injection:

```python
# Module-level dependencies
db: DatabaseProtocol | None = None
bot: Any | None = None
user_view_mode: dict[int, str] | None = None

def setup_dependencies(
    database: DatabaseProtocol, 
    bot_instance: Any, 
    view_mode_dict: dict[int, str]
) -> None:
    global db, bot, user_view_mode
    db = database
    bot = bot_instance
    user_view_mode = view_mode_dict
```

## Next Steps

### Remaining Handler Categories

1. **Admin Handlers (~25 handlers)**
   - Moderation (approve/reject stores)
   - Statistics and dashboards
   - User/store management
   - Broadcast messages

2. **Catalog Browsing (~15 handlers)**
   - Browse by category
   - Browse by city
   - Offer details
   - Search functionality

3. **Rating System (~5 handlers)**
   - Store ratings
   - Booking ratings
   - Rating display

4. **Bulk Operations (~5 handlers)**
   - Bulk offer creation
   - Cleanup operations

5. **Miscellaneous (~30 handlers)**
   - Error handlers
   - Callback handlers
   - Helper functions
   - Startup/shutdown

### Integration Steps

1. **Remove Extracted Code from bot.py**
   - Delete extracted handler definitions
   - Clean up duplicate code
   - Target: Reduce to < 3,000 lines

2. **Update bot.py Imports**
   ```python
   from handlers import router as handlers_router
   dp.include_router(handlers_router)
   ```

3. **Setup Dependencies**
   ```python
   handlers.bookings.setup_dependencies(db, bot, user_view_mode)
   handlers.orders.setup_dependencies(db, bot, user_view_mode)
   # ... etc
   ```

4. **Testing**
   - Verify all extracted handlers work
   - Test dependency injection
   - Ensure router order correct

## Benefits Achieved

✅ **Code Organization:** Handlers grouped by functionality
✅ **Maintainability:** Easier to find and modify specific features
✅ **Type Safety:** Consistent type annotations
✅ **Testability:** Each module independently testable
✅ **Scalability:** Easy to add new handlers per category
✅ **Pattern Consistency:** All modules follow same structure

## Timeline

- **Start:** Phase 3 initiated
- **Current:** 46% extraction complete
- **Target:** 100% extraction, bot.py < 1,000 lines
- **ETA:** 2-3 more sessions for full migration

---

**Status:** 🟡 In Progress (46% Complete)
**Last Updated:** Phase 3 Handler Extraction Session
