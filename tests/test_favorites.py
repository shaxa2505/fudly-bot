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


def test_favorite_offers(db):
    """Test favorite offers functionality."""
    buyer_id = 54321
    seller_id = 33333
    db.add_user(user_id=buyer_id, username="buyer2")
    db.add_user(user_id=seller_id, username="seller2")
    db.update_user_role(seller_id, "seller")

    store_id = db.add_store(
        owner_id=seller_id,
        name="Test Store 2",
        city="Tashkent",
        category="Cafe",
        address="Address",
        phone="+998901234568",
    )
    db.approve_store(store_id)

    offer_id = db.add_offer(
        store_id=store_id,
        title="Test Offer",
        description="Offer desc",
        original_price=10000,
        discount_price=8000,
        quantity=5,
    )

    db.add_offer_favorite(buyer_id, offer_id)
    ids = db.get_favorite_offer_ids(buyer_id)
    assert offer_id in ids

    offers = db.get_favorite_offers(buyer_id)
    assert len(offers) == 1
    assert offers[0].get("offer_id") == offer_id

    db.remove_offer_favorite(buyer_id, offer_id)
    assert db.get_favorite_offer_ids(buyer_id) == []
