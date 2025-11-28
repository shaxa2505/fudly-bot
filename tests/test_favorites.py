"""
Test script to verify database improvements.
Проверка работы новых методов для избранного.
"""
import os
import sys

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import Database


def test_favorites():
    """Test favorite offers functionality."""
    print("=" * 50)
    print("Testing Favorite Offers Functionality")
    print("=" * 50)

    # Use temp file instead of in-memory database
    import tempfile

    temp_db = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
    temp_db_path = temp_db.name
    temp_db.close()

    try:
        # Initialize database
        db = Database(temp_db_path)

        # Verify table was created
        conn = db.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='offer_favorites'"
        )
        table_exists = cursor.fetchone() is not None
        conn.close()

        print(f"✓ Database initialized (offer_favorites table exists: {table_exists})")

        # Test user and offer IDs
        test_user_id = 12345
        test_offer_id = 1

        # Test 1: Add to favorites
        print("\n1. Testing add_user_favorite...")
        result = db.add_user_favorite(test_user_id, test_offer_id)
        print(f"   Result: {result}")
        assert result == True, "Failed to add favorite"
        print("   ✓ Added to favorites")

        # Test 2: Check if favorite
        print("\n2. Testing is_offer_favorite...")
        is_fav = db.is_offer_favorite(test_user_id, test_offer_id)
        print(f"   Is favorite: {is_fav}")
        assert is_fav == True, "Should be in favorites"
        print("   ✓ Favorite check works")

        # Test 3: Get user favorites
        print("\n3. Testing get_user_favorite_offers...")
        favorites = db.get_user_favorite_offers(test_user_id)
        print(f"   Favorites: {favorites}")
        assert len(favorites) == 1, "Should have 1 favorite"
        assert favorites[0] == test_offer_id, "Wrong offer ID"
        print("   ✓ Get favorites works")

        # Test 4: Add duplicate (should fail gracefully)
        print("\n4. Testing duplicate add...")
        result = db.add_user_favorite(test_user_id, test_offer_id)
        print(f"   Result: {result}")
        assert result == False, "Should not add duplicate"
        print("   ✓ Duplicate prevention works")

        # Test 5: Add another favorite
        print("\n5. Testing add another favorite...")
        test_offer_id_2 = 2
        result = db.add_user_favorite(test_user_id, test_offer_id_2)
        favorites = db.get_user_favorite_offers(test_user_id)
        print(f"   Favorites count: {len(favorites)}")
        assert len(favorites) == 2, "Should have 2 favorites"
        print("   ✓ Multiple favorites work")

        # Test 6: Remove from favorites
        print("\n6. Testing remove_user_favorite...")
        result = db.remove_user_favorite(test_user_id, test_offer_id)
        print(f"   Result: {result}")
        favorites = db.get_user_favorite_offers(test_user_id)
        print(f"   Favorites count: {len(favorites)}")
        assert len(favorites) == 1, "Should have 1 favorite"
        assert favorites[0] == test_offer_id_2, "Wrong offer remaining"
        print("   ✓ Remove works")

        # Test 7: Check removed favorite
        print("\n7. Testing is_offer_favorite after removal...")
        is_fav = db.is_offer_favorite(test_user_id, test_offer_id)
        print(f"   Is favorite: {is_fav}")
        assert is_fav == False, "Should not be in favorites"
        print("   ✓ Check after removal works")

        print("\n" + "=" * 50)
        print("✓ ALL TESTS PASSED!")
        print("=" * 50)

    finally:
        # Cleanup temp database
        if os.path.exists(temp_db_path):
            os.remove(temp_db_path)


if __name__ == "__main__":
    try:
        test_favorites()
        print("\n✅ Database improvements are working correctly!")
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)
