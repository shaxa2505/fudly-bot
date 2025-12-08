"""Test script to verify profile switching logic."""
import sys


# Mock database protocol
class MockDB:
    def __init__(self):
        self.users = {
            123: {"role": "seller", "lang": "ru"},
            456: {"role": "customer", "lang": "ru"},
        }
        self.stores = {
            123: [{"status": "active", "store_id": 1}],
            456: [],
        }

    def get_user_language(self, user_id: int) -> str:
        return self.users.get(user_id, {}).get("lang", "ru")

    def get_user_model(self, user_id: int):
        class User:
            def __init__(self, data):
                self.role = data.get("role", "customer")
                self.lang = data.get("lang", "ru")

        user_data = self.users.get(user_id)
        return User(user_data) if user_data else None

    def get_user_accessible_stores(self, user_id: int):
        return self.stores.get(user_id, [])


def has_approved_store(user_id: int, db: MockDB) -> bool:
    """Check if user has an approved store (owned or admin access)."""
    stores = db.get_user_accessible_stores(user_id)
    return any(store.get("status") == "active" for store in stores)


def test_seller_with_store():
    """Test seller with approved store."""
    print("Test 1: Seller with approved store")
    db = MockDB()
    user_id = 123

    user = db.get_user_model(user_id)
    user_role = getattr(user, "role", "customer")
    has_store = has_approved_store(user_id, db)
    is_seller = user_role == "seller" and has_store

    print(f"  User ID: {user_id}")
    print(f"  Role: {user_role}")
    print(f"  Has approved store: {has_store}")
    print(f"  Can switch to seller mode: {is_seller}")
    print("  ✅ PASS" if is_seller else "  ❌ FAIL")
    print()


def test_customer_without_store():
    """Test customer without store."""
    print("Test 2: Customer without store")
    db = MockDB()
    user_id = 456

    user = db.get_user_model(user_id)
    user_role = getattr(user, "role", "customer")
    has_store = has_approved_store(user_id, db)
    is_seller = user_role == "seller" and has_store

    print(f"  User ID: {user_id}")
    print(f"  Role: {user_role}")
    print(f"  Has approved store: {has_store}")
    print(f"  Can switch to seller mode: {is_seller}")
    print("  ✅ PASS" if not is_seller else "  ❌ FAIL")
    print()


def test_seller_without_store():
    """Test seller without approved store."""
    print("Test 3: Seller without approved store")
    db = MockDB()
    user_id = 789
    db.users[789] = {"role": "seller", "lang": "ru"}
    db.stores[789] = []

    user = db.get_user_model(user_id)
    user_role = getattr(user, "role", "customer")
    has_store = has_approved_store(user_id, db)
    is_seller = user_role == "seller" and has_store

    print(f"  User ID: {user_id}")
    print(f"  Role: {user_role}")
    print(f"  Has approved store: {has_store}")
    print(f"  Can switch to seller mode: {is_seller}")
    print("  ✅ PASS" if not is_seller else "  ❌ FAIL")
    print()


if __name__ == "__main__":
    print("=" * 60)
    print("Profile Switching Logic Tests")
    print("=" * 60)
    print()

    test_seller_with_store()
    test_customer_without_store()
    test_seller_without_store()

    print("=" * 60)
    print("All tests completed!")
    print("=" * 60)
