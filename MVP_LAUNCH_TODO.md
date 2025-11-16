# 🚀 MVP LAUNCH TODO - Критические задачи

**Цель:** Устранить 8 блокирующих проблем за 2-3 дня  
**Статус:** 0/8 ✅

---

## 🔴 КРИТИЧНО - День 1 (8 часов)

### ✅ Task 1: Fix duplicate `add_rating()` method (5 минут)
**Файл:** `database.py`
**Проблема:** Duplicate definition на строках 1560 и 1631

```python
# Line 1631-1642 - DELETE THIS ENTIRE BLOCK
def add_rating(self, booking_id: int, user_id: int, store_id: int, rating: int, comment: str = None):
    # ... DUPLICATE CODE ...
```

**Приоритет:** 🔴 Критично  
**Время:** 5 минут

---

### ✅ Task 2: Add error handling to handlers (4 часа)

#### 2.1 handlers/offers.py
```python
# BEFORE
async def show_offer(callback: types.CallbackQuery):
    offer_id = int(callback.data.split('_')[1])  # ❌ May crash
    offer = db.get_offer(offer_id)
    await callback.message.edit_text(f"{offer[2]}")  # ❌ May crash

# AFTER
async def show_offer(callback: types.CallbackQuery):
    try:
        offer_id = int(callback.data.split('_')[1])
    except (ValueError, IndexError):
        await callback.answer("Некорректные данные")
        return
    
    offer = db.get_offer(offer_id)
    if not offer:
        await callback.answer("Оффер не найден")
        return
    
    try:
        await callback.message.edit_text(f"{offer[2]}")
    except Exception as e:
        logger.error(f"Error showing offer {offer_id}: {e}")
        await callback.answer("Произошла ошибка")
```

**Файлы для обновления:**
- [ ] `handlers/offers.py` - show_offer, filter_offers
- [ ] `handlers/bookings.py` - create_booking, confirm_booking
- [ ] `handlers/orders.py` - create_order, process_payment
- [ ] `handlers/seller/create_offer.py` - create_offer_handler
- [ ] `handlers/admin/dashboard.py` - approve_store, reject_store

**Приоритет:** 🔴 Критично  
**Время:** 4 часа

---

### ✅ Task 3: Code cleanup (1 час)

#### 3.1 Delete backup files
```powershell
Remove-Item "bot.py.backup*"
```

#### 3.2 Move utilities to scripts/
```powershell
New-Item -ItemType Directory -Path "scripts" -Force
Move-Item "cleanup_bot.py" "scripts/"
Move-Item "check_callbacks.py" "scripts/"
Move-Item "fix_context_managers.py" "scripts/"
Move-Item "migrate_methods.py" "scripts/"
Move-Item "remove_legacy_admin_stats.py" "scripts/"
Move-Item "run_local_test.py" "scripts/"
Move-Item "test_local.py" "scripts/"
```

#### 3.3 Move historical docs to docs/history/
```powershell
New-Item -ItemType Directory -Path "docs/history" -Force
Move-Item "PHASE*.md" "docs/history/"
Move-Item "*_SUMMARY.md" "docs/history/"
Move-Item "*_PROGRESS.md" "docs/history/"
Move-Item "FIXES_SUMMARY.md" "docs/history/"
Move-Item "REFACTORING_*.md" "docs/history/"
Move-Item "ИСПРАВЛЕНИЯ.md" "docs/history/"
Move-Item "ИТОГИ_СЕССИИ.md" "docs/history/"
Move-Item "ЛОКАЛЬНОЕ_ТЕСТИРОВАНИЕ.md" "docs/history/"
Move-Item "ОТЧЁТ_ИСПРАВЛЕНИЙ.md" "docs/history/"
```

#### 3.4 Delete legacy keyboards.py
```powershell
Remove-Item "keyboards.py"
```

**Приоритет:** 🔶 Средний  
**Время:** 1 час

---

## 🔴 КРИТИЧНО - День 2 (8 часов)

### ✅ Task 4: Write critical tests (8 часов)

#### 4.1 Test atomic booking race condition
**Файл:** `tests/test_booking_race_condition.py`

```python
"""Test that atomic booking prevents overbooking."""
import asyncio
import concurrent.futures
import pytest
from database import Database

@pytest.fixture
def db():
    db = Database(':memory:')
    # Setup test data
    db.add_user(1, 'user1')
    store_id = db.add_store(1, 'Test Store', 'Ташкент')
    offer_id = db.add_offer(
        store_id=store_id,
        title='Test Offer',
        description='Test',
        original_price=1000,
        discount_price=500,
        quantity=1,  # Only 1 available!
        available_from='09:00',
        available_until='18:00'
    )
    return db, offer_id

def test_concurrent_bookings_prevent_overbooking(db):
    """Test that 2 concurrent bookings for 1 item only 1 succeeds."""
    database, offer_id = db
    
    # Try 10 concurrent bookings for 1 item
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        futures = [
            executor.submit(database.create_booking_atomic, offer_id, user_id, 1)
            for user_id in range(10, 20)
        ]
        results = [f.result() for f in futures]
    
    # Exactly 1 should succeed
    successful = [r for r in results if r[0] is True]
    assert len(successful) == 1, f"Expected 1 booking, got {len(successful)}"
    
    # Verify offer quantity is 0
    offer = database.get_offer(offer_id)
    assert offer[6] == 0, "Offer quantity should be 0"
```

**Файлы:**
- [ ] `tests/test_booking_race_condition.py` - race conditions
- [ ] `tests/test_offer_validation.py` - offer creation validation
- [ ] `tests/test_admin_actions.py` - approve/reject store
- [ ] `tests/test_payment_flow.py` - order payment

#### 4.2 Integration tests
**Файл:** `tests/test_integration.py`

```python
"""End-to-end integration tests."""
import pytest
from bot import dp, db, bot

@pytest.mark.asyncio
async def test_full_booking_flow():
    """Test: Register → Browse → Book → Confirm."""
    # 1. Register user
    user_id = 12345
    db.add_user(user_id, 'testuser', 'Test User')
    
    # 2. Create store + offer
    store_id = db.add_store(user_id, 'Test Cafe', 'Ташкент')
    db.approve_store(store_id)
    offer_id = db.add_offer(store_id, 'Pizza', 'Desc', 1000, 500, 5, '09:00', '20:00')
    
    # 3. Book offer
    success, booking_id, code = db.create_booking_atomic(offer_id, user_id, 1)
    assert success is True
    assert booking_id is not None
    assert code is not None
    
    # 4. Verify booking
    booking = db.get_booking(booking_id)
    assert booking is not None
    assert booking[3] == 'pending'  # status
    
    # 5. Confirm booking
    db.update_booking_status(booking_id, 'confirmed')
    
    # 6. Complete booking
    db.update_booking_status(booking_id, 'completed')
    
    # Verify final state
    booking = db.get_booking(booking_id)
    assert booking[3] == 'completed'
```

**Приоритет:** 🔴 Критично  
**Время:** 8 часов

---

## 🔶 СРЕДНИЙ ПРИОРИТЕТ - День 3 (4 часа)

### ✅ Task 5: Migrate handlers to Pydantic models (4 часа)

#### 5.1 handlers/user/profile.py
```python
# BEFORE (40 lines of helper functions)
def get_user_field(user, field, default=None):
    # ... 20 lines ...

async def profile(message):
    user = db.get_user(user_id)
    city = get_user_field(user, 'city')
    role = get_user_field(user, 'role')
    is_seller = (role == 'seller')

# AFTER (no helpers needed!)
async def profile(message):
    user = db.get_user_model(user_id)
    city = user.city
    is_seller = user.is_seller
```

**Файлы:**
- [ ] `handlers/user/profile.py` (demo exists in REFACTORING_DEMO_profile.py)
- [ ] `handlers/bookings.py`
- [ ] `handlers/offers.py`

**Приоритет:** 🔶 Средний  
**Время:** 4 часа

---

## 🟢 НИЗКИЙ ПРИОРИТЕТ - Post-MVP

### ✅ Task 6: Fix lint errors (4 часа)
**Файл:** `database_protocol.py` + implementations

Синхронизировать Protocol с Database implementations.

### ✅ Task 7: Load testing (2 часа)
```python
# tests/test_load.py
async def test_100_concurrent_bookings():
    # Simulate 100 users booking at once
    pass
```

### ✅ Task 8: CI/CD setup (2 часа)
```yaml
# .github/workflows/test.yml
name: Tests
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - run: pytest tests/ --cov=. --cov-report=term
      - run: coverage report --fail-under=60
```

---

## 📋 CHECKLIST

### День 1 (8h)
- [ ] Task 1: Delete duplicate add_rating() (5min)
- [ ] Task 2: Add error handling (4h)
- [ ] Task 3: Code cleanup (1h)

### День 2 (8h)
- [ ] Task 4: Write critical tests (8h)
  - [ ] Race condition tests
  - [ ] Integration tests
  - [ ] Validation tests

### День 3 (4h)
- [ ] Task 5: Migrate 3 handlers to models (4h)
- [ ] Manual QA testing (2h)
- [ ] Bug fixes (2h)

### День 4
- [ ] Deploy to Railway staging
- [ ] Smoke tests on staging
- [ ] Performance check

### День 5
- [ ] Final QA
- [ ] Deploy to production
- [ ] 🚀 LAUNCH!

---

## 🎯 SUCCESS CRITERIA

- [ ] All 8 blocking issues fixed
- [ ] Test coverage > 60%
- [ ] No critical bugs found in QA
- [ ] Staging deployment successful
- [ ] Performance acceptable (< 2s response)
- [ ] Railway monitoring active

---

**Время:** 2-3 рабочих дня (~20 часов)  
**Следующий шаг:** Начать с Task 1 (5 минут)

**Файлы для справки:**
- `MVP_PRODUCTION_READINESS_AUDIT.md` - полный аудит
- `REFACTORING_DEMO_profile.py` - пример миграции handler
- `DATABASE_MODELS_INTEGRATION.md` - integration guide
