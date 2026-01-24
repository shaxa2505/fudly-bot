"""Tests for favorites (stores)."""
from __future__ import annotations


def test_favorites(db):
    """Test favorite stores functionality."""
    buyer_id = 12345
    seller_id = 22222
    db.add_user(user_id=buyer_id, username="buyer")
    db.add_user(user_id=seller_id, username="seller")
    db.update_user_role(seller_id, "seller")

    store_id = db.add_store(
        owner_id=seller_id,
        name="Test Store",
        city="Tashkent",
        category="Cafe",
        address="Address",
        phone="+998901234567",
    )
    db.approve_store(store_id)

    db.add_to_favorites(buyer_id, store_id)
    assert db.is_favorite(buyer_id, store_id) is True

    favorites = db.get_favorites(buyer_id)
    assert len(favorites) == 1
    assert favorites[0].get("store_id") == store_id

    # Duplicate add should not create extra rows
    db.add_to_favorites(buyer_id, store_id)
    favorites = db.get_favorites(buyer_id)
    assert len(favorites) == 1

    db.remove_from_favorites(buyer_id, store_id)
    assert db.is_favorite(buyer_id, store_id) is False
    assert db.get_favorites(buyer_id) == []
