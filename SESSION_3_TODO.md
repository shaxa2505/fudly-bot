# 🚀 SESSION 3 TODO - MVP LAUNCH PREPARATION

**Current Status:** 78% MVP Ready (5 blocking issues remaining)  
**Target:** 95% MVP Ready  
**Estimated Time:** 8-10 hours

---

## 🔴 HIGH PRIORITY (2-3 hours)

### Task 1: Fix Failed Tests (9/26 tests)

**Problem:** Some tests fail due to missing database helper methods

**Required Fixes:**

1. **Add `update_user_profile()` wrapper** (15 min)
   ```python
   # database.py
   def update_user_profile(self, user_id: int, city: str = None, 
                          phone: str = None, full_name: str = None):
       """Update user profile fields atomically."""
       conn = self.get_connection()
       cursor = conn.cursor()
       if city:
           cursor.execute('UPDATE users SET city = ? WHERE user_id = ?', (city, user_id))
       if phone:
           cursor.execute('UPDATE users SET phone = ? WHERE user_id = ?', (phone, user_id))
       if full_name:
           cursor.execute('UPDATE users SET first_name = ? WHERE user_id = ?', (full_name, user_id))
       conn.commit()
       conn.close()
   ```

2. **Fix `get_store()` tuple/dict inconsistency** (30 min)
   - Current: Returns tuple after JOIN
   - Issue: Some tests expect dict
   - Solution: Add `get_store_dict()` or modify tests to use tuple indices

3. **Add `get_stores_by_status()` method** (15 min)
   ```python
   def get_stores_by_status(self, status: str) -> List[Tuple]:
       """Get stores filtered by status (pending/approved/rejected)."""
       conn = self.get_connection()
       cursor = conn.cursor()
       cursor.execute('SELECT * FROM stores WHERE status = ?', (status,))
       return cursor.fetchall()
   ```

4. **Run all tests and verify** (30 min)
   ```powershell
   python -m pytest tests/ -v --tb=short
   ```

**Expected Result:** 26/26 tests passing (100%)

---

## 🟡 MEDIUM PRIORITY (4 hours)

### Task 2: Complete Pydantic Migration

**Current State:**
- ✅ Pydantic models defined (User, Offer, Store, Booking)
- ✅ `get_user_model()` converter ready
- ❌ `get_user_field()` duplicated in 6 files
- ❌ Handlers still use tuple/dict access

**Phase A: Remove Duplication (1 hour)**

Files to update:
1. `handlers/user/profile.py` - Remove local `get_user_field()`, import from `app/core/utils`
2. `handlers/user/favorites.py` - Same
3. `handlers/bookings.py` - Same
4. `handlers/orders.py` - Same
5. `handlers/seller/analytics.py` - Same
6. `handlers/partner.py` - Same

**Phase B: Migrate to Pydantic (3 hours)**

Priority handlers:

1. **handlers/user/profile.py** (1h)
   ```python
   # BEFORE
   user = db.get_user(user_id)
   phone = get_user_field(user, 'phone', 'Не указан')
   if get_user_field(user, 'role') == 'seller':
   
   # AFTER
   user_model = db.get_user_model(user_id)
   phone = user_model.phone or 'Не указан'
   if user_model.is_seller:
   ```

2. **handlers/bookings.py** (1h)
   - Use `Booking.from_db_row()`
   - Access: `booking_model.status`, `booking_model.offer_id`

3. **handlers/offers.py** (1h)
   - Use `Offer.from_db_row()`
   - Access: `offer_model.quantity`, `offer_model.discount_price`

**Benefits:**
- Type safety: IDE autocomplete
- -200 lines of `get_user_field()` calls
- Centralized validation
- Properties: `user_model.is_seller`, `user_model.is_admin`

---

## 🔵 LOW PRIORITY (2-3 hours)

### Task 3: Complete Error Handling

**Current:** 3/30 handlers have error handling  
**Target:** All critical handlers protected

**Locations needing `try/except`:**

1. `handlers/offers.py` - 10 more callbacks
2. `handlers/bookings.py` - 8 more callbacks  
3. `handlers/orders.py` - 12 callbacks
4. `handlers/seller/create_offer.py` - 6 callbacks
5. `handlers/admin/dashboard.py` - 8 callbacks

**Pattern:**
```python
try:
    value = int(callback.data.split("_")[1])
except (ValueError, IndexError) as e:
    logger.error(f"Invalid callback: {callback.data}, error: {e}")
    await callback.answer(get_text(lang, "error"), show_alert=True)
    return
```

### Task 4: Type Annotation Fixes

**Current:** 2044 lint errors  
**Target:** <500 errors

Focus on:
1. Function signatures (add return types)
2. Variable type hints
3. Optional types (`Optional[str]`, `Optional[int]`)

---

## 📊 SUCCESS METRICS

| Metric | Current | Target |
|--------|---------|--------|
| Test Coverage | 65% (17/26) | 100% (26/26) |
| Error Handling | 10% (3/30) | 80% (24/30) |
| Code Duplication | 6 files | 0 files |
| Lint Errors | 2044 | <500 |
| MVP Readiness | 78% | 95% |

---

## 🎯 BLOCKERS REMAINING

1. ❌ **9 Failed Tests** → Task 1 (2-3h)
2. ❌ **Handler Duplication** → Task 2 Phase A (1h)
3. ❌ **No Type Safety** → Task 2 Phase B (3h)
4. ⚠️ **Partial Error Handling** → Task 3 (2h)
5. ⚠️ **Many Lint Errors** → Task 4 (1h)

**Total:** 9-10 hours to 95% MVP ready

---

## 📁 FILES TO EDIT (Session 3)

**High Priority:**
- `database.py` (add 3 methods)
- `tests/test_integration.py` (fix tuple indices)
- `tests/test_validation.py` (fix tuple indices)

**Medium Priority:**
- `handlers/user/profile.py` (Pydantic migration)
- `handlers/bookings.py` (Pydantic migration)
- `handlers/offers.py` (Pydantic migration)

**Low Priority:**
- All remaining handlers (error handling)

---

## 🧪 TEST RESULTS (Session 2)

### ✅ Passing Tests (17/26)

**test_booking_race_condition.py (5/6)**
- ✅ test_single_booking_succeeds
- ✅ test_concurrent_bookings_no_overbooking (10 threads!)
- ✅ test_concurrent_large_quantity_bookings
- ✅ test_booking_more_than_available_fails
- ✅ test_unique_booking_codes
- ⚠️ test_booking_inactive_offer (Windows file lock)

**test_integration.py (4/8)**
- ✅ test_favorites_flow
- ✅ test_get_nonexistent_user
- ✅ test_get_nonexistent_store
- ✅ test_duplicate_favorite_ignored
- ❌ test_complete_buyer_flow (missing `update_user_profile`)
- ❌ test_complete_seller_flow (tuple/dict issue)
- ❌ test_admin_store_approval_workflow (missing `get_stores_by_status`)
- ❌ Others (similar issues)

**test_validation.py (8/12)**
- ✅ test_offer_price_positive
- ✅ test_offer_discounted_price_less_than_original
- ✅ test_offer_quantity_positive
- ✅ test_store_requires_valid_owner
- ✅ test_rating_range_validation
- ✅ test_rating_comment_optional
- ✅ test_seller_cannot_book_own_offer
- ✅ test_store_status_workflow
- ❌ 4 tests with tuple index errors

---

## 💡 QUICK WINS (15-30 min each)

1. Add `update_user_profile()` → fixes 2 tests ✅
2. Add `get_stores_by_status()` → fixes 1 test ✅
3. Fix tuple indices in test_integration.py → fixes 3 tests ✅
4. Fix tuple indices in test_validation.py → fixes 3 tests ✅

**Result:** 26/26 tests passing in ~2 hours!

---

## 🚀 DEPLOYMENT READINESS

After Session 3 completion:

- ✅ 100% test coverage (26/26)
- ✅ Race condition protection verified
- ✅ Error handling in critical paths
- ✅ Type-safe Pydantic models
- ✅ No code duplication
- ✅ Clean architecture
- ✅ Production-ready database

**Ready for:**
1. Railway staging deploy
2. QA testing with real users
3. Production launch (soft launch)

---

## 📝 NOTES FROM SESSION 2

**Key Achievements:**
- ✅ Race condition test: 10 concurrent threads → 5 bookings (exact!)
- ✅ Atomic `create_booking_atomic()` works correctly
- ✅ Test infrastructure established (1030 lines)
- ✅ Error handling pattern defined

**Deferred Items:**
- Full Pydantic migration (analyzed, ready to execute)
- Complete error handling (pattern proven, needs rollout)
- Lint fixes (low priority, doesn't block launch)

**Recommendation:**
Start Session 3 with Task 1 (fix failed tests) for quick wins and confidence boost. Then proceed to Pydantic migration for long-term code quality.
