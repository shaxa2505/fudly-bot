"""Migration Guide: From dict/tuple to Pydantic Models

This file shows step-by-step how to migrate handlers to use typed models.
"""

# ============================================================================
# STEP 1: OLD CODE (Before Migration)
# ============================================================================

def old_handler_example(message, db):
    """Old way: working with dict/tuple."""
    user_id = message.from_user.id
    
    # Get user as dict
    user = db.get_user(user_id)
    if not user:
        return
    
    # Access fields - need to remember structure
    if isinstance(user, dict):
        city = user.get('city', 'Ташкент')
        lang = user.get('language', 'ru')
        role = user.get('role', 'customer')
    else:
        # tuple - need to remember indexes!
        city = user[4] if len(user) > 4 else 'Ташкент'
        lang = user[5] if len(user) > 5 else 'ru'
        role = user[6] if len(user) > 6 else 'customer'
    
    # Check if seller
    is_seller = (role == 'seller')
    
    # Use data
    if is_seller:
        print(f"Seller {city}")
    else:
        print(f"Customer {city}")


# ============================================================================
# STEP 2: NEW CODE (After Migration)
# ============================================================================

def new_handler_example(message, db):
    """New way: using Pydantic model."""
    user_id = message.from_user.id
    
    # Get user as typed model
    user = db.get_user_model(user_id)
    if not user:
        return
    
    # Type-safe access with autocomplete!
    city = user.city  # IDE knows it's a string
    lang = user.language  # IDE knows it's Language enum
    
    # Use properties instead of comparisons
    if user.is_seller:
        print(f"Seller {city}")
    else:
        print(f"Customer {city}")
    
    # Properties are much more readable!
    # user.is_seller instead of user.role == 'seller'
    # user.is_admin instead of user.role == 'admin'
    # user.display_name instead of f"@{user.username}" or user.first_name


# ============================================================================
# STEP 3: MIGRATION STRATEGY
# ============================================================================

"""
Strategy for gradual migration:

1. ✅ Add get_user_model() method to database (DONE)
2. 🔲 Create wrapper in handlers for backward compatibility
3. 🔲 Migrate handlers one by one
4. 🔲 Eventually deprecate old get_user() method

Example backward-compatible wrapper:
"""

def get_user_safe(db, user_id):
    """Backward compatible: returns model if available, falls back to dict."""
    try:
        user = db.get_user_model(user_id)
        if user:
            return user
    except Exception:
        pass
    
    # Fallback to old method
    return db.get_user(user_id)


# ============================================================================
# STEP 4: REAL WORLD EXAMPLE
# ============================================================================

# Before: handlers/user/favorites.py
def show_my_city_OLD(message, state, db):
    """Old implementation."""
    user_id = message.from_user.id
    lang = db.get_user_language(user_id)
    user = db.get_user(user_id)
    
    # Ugly field extraction
    if isinstance(user, dict):
        current_city = user.get("city", "Не выбран")
    else:
        current_city = user[4] if user and len(user) > 4 else "Не выбран"
    
    text = f"🌆 Ваш город: {current_city}"
    # ...


# After: handlers/user/favorites.py
def show_my_city_NEW(message, state, db):
    """New implementation with model."""
    user_id = message.from_user.id
    user = db.get_user_model(user_id)
    
    if not user:
        return
    
    # Clean, type-safe access
    current_city = user.city
    lang = user.language
    
    text = f"🌆 Ваш город: {current_city}"
    # ...


# ============================================================================
# STEP 5: BENEFITS SUMMARY
# ============================================================================

"""
OLD WAY:
- user['city'] or user[4]  ❌ Error-prone
- No autocomplete          ❌ Slow development
- No type checking         ❌ Runtime errors
- if role == 'seller'      ❌ Magic strings

NEW WAY:
- user.city                ✅ Type-safe
- Full autocomplete        ✅ Fast development  
- Type checking            ✅ Catch errors early
- user.is_seller           ✅ Readable properties
- user.display_name        ✅ Business logic in model
"""


# ============================================================================
# STEP 6: QUICK REFERENCE
# ============================================================================

"""
# User Model Quick Reference

## Properties:
user.user_id          # int - Telegram ID
user.username         # str | None - @username
user.first_name       # str - First name
user.phone            # str | None - Phone number
user.city             # str - City name
user.language         # Language - ru or uz
user.role             # UserRole - customer, seller, admin

## Computed Properties:
user.is_seller        # bool - Check if seller
user.is_admin         # bool - Check if admin
user.display_name     # str - @username or first_name

## Methods:
user.to_dict()        # dict - Convert to dict for DB
User.from_db_row(row) # User - Create from DB row

## Validation:
- Phone format validated automatically
- Required fields enforced
- Type checking built-in
"""


if __name__ == "__main__":
    print(__doc__)
    print("\n✅ This is a guide file, not executable code.")
    print("📖 Read the examples above to learn migration strategy.")
