# 🔧 Audit Fixes Applied

## Overview

This document tracks the fixes applied based on the comprehensive security and code quality audit.

**Audit Date:** June 2025
**Fixes Applied:** June 2025

---

## ✅ Phase 1: Critical Security Fixes

### 1. IDOR Vulnerability (P0)
**File:** `app/api/auth.py`

- Added authorization check to `/api/v1/user/{user_id}/profile` endpoint
- Now validates that authenticated user can only access their own profile
- Returns 403 Forbidden for unauthorized access attempts

### 2. Docker Trust Authentication (P0)
**File:** `docker-compose.yml`, `docker-compose.dev.yml`

- Changed PostgreSQL `POSTGRES_HOST_AUTH_METHOD` from `trust` to `scram-sha-256`
- Removed direct port exposure (5432) from production docker-compose
- Database now only accessible from internal network

### 3. Race Condition in Booking (P0)
**File:** `database_pg_module/mixins/bookings.py`

- Added `FOR UPDATE` to SELECT query in `create_booking_atomic()`
- Prevents double-booking when concurrent requests try to book same offer
- Ensures atomic quantity check and decrement

### 4. SQLite Connection Leak (P1)
**File:** `database.py`

- Added `try/finally` blocks to ensure connections are always closed
- Fixed `get_connection()` context manager usage
- Prevents connection pool exhaustion

### 5. Guest Access Control (P1)
**File:** `app/api/auth.py`

- Implemented guest authentication restrictions
- Guests cannot access user-specific endpoints
- Proper 401/403 responses for unauthorized guest actions

---

## ✅ Phase 2: Scalability Fixes

### 6. user_view_mode Migration to Database (P1)
**Files:**
- `database_pg_module/schema.py` - Added `view_mode` column to users table
- `database_pg_module/mixins/users.py` - Added `get_user_view_mode()` and `set_user_view_mode()` methods
- `database.py` - Added SQLite implementations
- `database_protocol.py` - Added method signatures to protocol
- `handlers/common/utils.py` - New database-backed helper functions
- `handlers/customer/profile.py` - Updated to use database
- `handlers/customer/menu.py` - Updated to use database
- `handlers/seller/registration.py` - Updated to use database
- `handlers/common/commands.py` - Updated to use database

**Problem:** Global `user_view_mode` dict doesn't scale with multiple bot instances
**Solution:** Store view mode in database with new column and accessor methods

---

## ✅ Phase 3: Performance Fixes

### 7. Database Indexes (P1)
**File:** `database_pg_module/schema.py`

Added 20+ new indexes for frequently queried columns:
- `idx_offers_store_id` - Offers by store lookup
- `idx_offers_status` - Active offers filtering
- `idx_offers_city` - Offers by city
- `idx_offers_store_status` - Combined store + status queries
- `idx_offers_city_status` - City + active status queries
- `idx_offers_category_city_status` - Category browsing
- `idx_bookings_user_status` - User booking history
- `idx_bookings_store_status` - Store booking management
- `idx_bookings_code` - Booking code lookup
- `idx_stores_city_status` - Store listings by city
- `idx_stores_owner` - Seller's stores
- `idx_users_phone` - Phone number lookup
- `idx_users_role` - Role-based queries
- `idx_reviews_store` - Store reviews
- `idx_reviews_user` - User's reviews
- And more...

---

## ✅ Phase 4: Rate Limiting Improvements

### 8. Redis-Based Rate Limiting (P1)
**File:** `app/middlewares/rate_limit.py`

- Complete rewrite of rate limiter with Redis support
- In-memory fallback when Redis unavailable
- Configurable limits per endpoint type (default, auth, admin)
- Sliding window algorithm for accurate rate limiting
- Automatic cleanup of expired entries
- Connection pooling for Redis

---

## ✅ Phase 5: Code Quality Fixes

### 9. Helper Function Consolidation (P2)
**Files:**
- `app/core/utils.py` - Centralized `get_field()` function
- `handlers/customer/profile.py` - Now imports from utils
- `handlers/customer/menu.py` - Now imports from utils
- `handlers/seller/order_management.py` - Now imports from utils
- `handlers/customer/features.py` - Now imports from utils

**Problem:** 6 duplicate implementations of `get_field()` helper
**Solution:** Consolidated to single implementation in `app/core/utils.py`

### 10. Test Fixes
**File:** `tests/test_handlers_common.py`

- Fixed `has_approved_store` tests to mock correct method name
- Tests now use `get_user_accessible_stores` instead of `get_user_stores`

### 11. has_approved_store Consolidation (P2)
**Files:**
- `handlers/common/utils.py` - Canonical implementation
- `handlers/seller/registration.py` - Now imports from utils.py
- `bot.py` - Thin wrapper that delegates to utils.py

**Problem:** 3 duplicate implementations of `has_approved_store()`
**Solution:** Consolidated to single implementation in `handlers/common/utils.py`

### 12. normalize_city Consolidation (P2)
**Files:**
- `handlers/common/utils.py` - Canonical implementation with complete city mapping
- `handlers/seller/registration.py` - Now imports from utils.py

**Problem:** 3 duplicate implementations with incomplete city mappings
**Solution:** Consolidated to single implementation with all cities (added Qo'qon/Коканд)

### 13. normalize_category → normalize_business_type Rename (P2)
**File:** `handlers/seller/registration.py`

**Problem:** Function named `normalize_category` but actually normalizes business types (Restaurant, Cafe, etc.)
**Solution:** Renamed to `normalize_business_type` for clarity

### 14. TODO Comments Cleanup (P3)
**Files:**
- `handlers/customer/orders/delivery.py` - Updated comment to reference middleware rate limiting
- `handlers/bookings/utils.py` - Updated comment to reference middleware rate limiting

**Problem:** Outdated TODO comments about rate limiting
**Solution:** Updated docstrings to indicate rate limiting is now handled by middleware

---

## 🔄 Remaining Tasks

### Low Priority (P3)

1. **Duplicate Mini App API** - `webhook_server.py` has ~500 lines of API endpoints that duplicate `webapp_api.py`
   - **Status:** Documented but not changed (breaking change risk)
   - **Recommendation:** Migrate to FastAPI when refactoring webhook handling

2. **Type Annotations** - Some functions use `Any` return types
   - **Status:** Not critical, IDE warnings only
   - **Recommendation:** Gradually improve type hints

3. **Global Caches** - Some in-memory caches exist:
   - `_photo_url_cache` in webhook_server.py (OK for single instance)
   - `onec_configs/onec_instances` in import_products.py (1C integration per user)
   - `_user_languages` in i18n.py (language cache)
   - **Recommendation:** Consider Redis for multi-instance deployments

---

## ✅ Security Verification

### Checked and Verified:
- ✅ No hardcoded credentials (only examples in docs)
- ✅ No `eval()` or `exec()` code execution
- ✅ SQL injection protection via parameterized queries
- ✅ `.env` properly in `.gitignore`
- ✅ Secrets use environment variables
- ✅ Input validation with regex patterns in `app/core/security.py`

---

## Test Results

```
tests/test_handlers_common.py - 35 passed ✅
```

All affected tests pass after fixes.

---

## Migration Notes

### For Database (PostgreSQL)

Run this SQL to add the view_mode column if migrating existing database:

```sql
ALTER TABLE users ADD COLUMN IF NOT EXISTS view_mode VARCHAR(20) DEFAULT 'customer';
```

### For Existing Deployments

1. Update environment variables for Redis rate limiting:
   ```
   REDIS_URL=redis://localhost:6379/0
   ```

2. Run database migrations for new indexes:
   ```bash
   alembic upgrade head
   ```

3. Restart all bot instances to pick up new code

---

**Document Version:** 1.0
**Last Updated:** June 2025
