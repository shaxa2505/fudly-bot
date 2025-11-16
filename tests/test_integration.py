"""
Integration tests for complete user flows

Tests end-to-end scenarios:
1. User registration → Browse offers → Book → Confirm → Rate
2. Seller registration → Create store → Add offer → Manage bookings
3. Admin workflow → Approve store → View stats
"""
from __future__ import annotations

import os
import tempfile
from datetime import datetime, timedelta

import pytest

from database import Database


class TestUserFlow:
    """Test complete user journey from registration to booking completion"""
    
    @pytest.fixture
    def db(self):
        """Create temporary database for integration tests"""
        fd, path = tempfile.mkstemp(suffix='.db')
        os.close(fd)
        
        db_instance = Database(path)
        
        yield db_instance
        
        if os.path.exists(path):
            os.remove(path)
    
    def test_complete_buyer_flow(self, db):
        """
        Test full buyer journey:
        1. User registers
        2. Updates profile with city
        3. Browses offers in their city
        4. Creates booking
        5. Confirms pickup
        6. Rates the experience
        """
        # Step 1: User registration
        user_id = 123456789
        username = "hungry_buyer"
        db.add_user(user_id, username)
        
        user = db.get_user(user_id)
        assert user is not None
        assert user.get('username') == username
        assert user.get('role') == 'customer'  # Default role is 'customer'
        
        # Step 2: Update profile
        db.update_user_profile(
            user_id=user_id,
            city="Tashkent",
            phone="+998901234567",
            full_name="Test Buyer"
        )
        
        user = db.get_user(user_id)
        assert user.get('city') == "Tashkent"
        assert user.get('phone') == "+998901234567"
        
        # Step 3: Create seller and offer for browsing
        seller_id = 987654321
        db.add_user(seller_id, "test_seller")
        db.update_user_role(seller_id, "seller")
        
        store_id = db.add_store(
            owner_id=seller_id,
            name="Pizza Paradise",
            city="Tashkent",
            category="Restaurant",
            address="Amir Temur Avenue 123",
            phone="+998901111111"
        )
        
        offer_id = db.add_offer(
            store_id=store_id,
            title="Pizza Margherita",
            description="Fresh from oven",
            original_price=60000.0,
            discount_price=30000.0,
            quantity=3,
            available_from="18:00",
            available_until="22:00"
        )
        
        # Browse offers in user's city
        offers = db.get_offers_by_city("Tashkent")
        assert len(offers) > 0
        found_offer = next((o for o in offers if o.get('offer_id') == offer_id), None)
        assert found_offer is not None
        
        # Step 4: Create booking
        ok, booking_id, booking_code = db.create_booking_atomic(offer_id, user_id, quantity=1)
        assert ok is True
        assert booking_id is not None
        assert booking_code is not None
        
        # Verify booking created
        booking = db.get_booking(booking_id)
        assert booking is not None
        assert booking[3] == 'pending'  # status
        assert booking[2] == user_id  # user_id
        assert booking[1] == offer_id  # offer_id
        
        # Step 5: Confirm pickup (seller confirms)
        db.update_booking_status(booking_id, "confirmed")
        
        booking = db.get_booking(booking_id)
        assert booking[3] == 'confirmed'  # status
        
        # Step 6: Rate the experience
        rating_id = db.add_rating(
            booking_id=booking_id,
            user_id=user_id,
            store_id=store_id,
            rating=5,
            comment="Amazing pizza!"
        )
        
        assert rating_id is not None
        
        # Verify rating saved
        ratings = db.get_store_ratings(store_id)
        assert len(ratings) == 1
        assert ratings[0][4] == 5  # rating column
        assert ratings[0][5] == "Amazing pizza!"  # comment column
    
    def test_complete_seller_flow(self, db):
        """
        Test full seller journey:
        1. Seller registration
        2. Create store (pending approval)
        3. Admin approves store
        4. Seller adds offer
        5. Customer books offer
        6. Seller confirms booking
        7. Seller views booking history
        """
        # Step 1: Seller registration
        seller_id = 555555555
        db.add_user(seller_id, "bakery_owner")
        db.update_user_role(seller_id, "seller")
        
        seller = db.get_user(seller_id)
        assert seller.get('role') == 'seller'
        
        # Step 2: Create store
        store_id = db.add_store(
            owner_id=seller_id,
            name="Daily Bread Bakery",
            city="Samarkand",
            category="Bakery",
            address="Registan Street 45",
            phone="+998902222222"
        )
        
        store = db.get_store(store_id)
        assert store is not None
        assert store.get('status') == 'pending'
        
        # Step 3: Admin approves store
        admin_id = 111111111
        db.add_user(admin_id, "admin_user")
        db.update_user_role(admin_id, "admin")
        
        db.update_store_status(store_id, "approved")
        
        store = db.get_store(store_id)
        assert store.get('status') == 'approved'
        
        # Step 4: Seller adds offer
        offer_id = db.add_offer(
            store_id=store_id,
            title="Fresh Bread",
            description="Baked this morning",
            original_price=10000.0,
            discount_price=5000.0,
            quantity=10,
            available_from="08:00",
            available_until="12:00"
        )
        
        offer = db.get_offer(offer_id)
        assert offer is not None
        
        # Step 5: Customer books offer
        customer_id = 999999999
        db.add_user(customer_id, "bread_lover")
        
        ok, booking_id, code = db.create_booking_atomic(offer_id, customer_id, quantity=2)
        assert ok is True
        
        # Step 6: Seller confirms booking
        db.update_booking_status(booking_id, "confirmed")
        
        # Step 7: Seller views booking history
        bookings = db.get_bookings_for_store(store_id)
        assert len(bookings) == 1
        assert bookings[0].get('booking_id') == booking_id
        assert bookings[0].get('status') == 'confirmed'
    
    def test_favorites_flow(self, db):
        """
        Test favorites functionality:
        1. User adds store to favorites
        2. User views favorites
        3. User removes from favorites
        """
        user_id = 777777777
        db.add_user(user_id, "foodie")
        
        seller_id = 888888888
        db.add_user(seller_id, "restaurant_owner")
        db.update_user_role(seller_id, "seller")
        
        store_id = db.add_store(
            owner_id=seller_id,
            name="Sushi House",
            city="Tashkent",
            category="Restaurant",
            address="Amir Temur 100",
            phone="+998903333333"
        )
        
        # Add to favorites
        db.add_favorite(user_id, store_id)
        
        # Check favorites
        favorites = db.get_user_favorites(user_id)
        assert len(favorites) == 1
        assert favorites[0][0] == store_id  # store_id is first column
        
        # Check if is favorite
        is_fav = db.is_favorite(user_id, store_id)
        assert is_fav is True
        
        # Remove from favorites
        db.remove_favorite(user_id, store_id)
        
        favorites = db.get_user_favorites(user_id)
        assert len(favorites) == 0
        
        is_fav = db.is_favorite(user_id, store_id)
        assert is_fav is False


class TestAdminFlow:
    """Test admin operations and store management"""
    
    @pytest.fixture
    def db(self):
        """Create temporary database"""
        fd, path = tempfile.mkstemp(suffix='.db')
        os.close(fd)
        
        db_instance = Database(path)
        
        yield db_instance
        
        if os.path.exists(path):
            os.remove(path)
    
    def test_admin_store_approval_workflow(self, db):
        """
        Test admin reviewing and approving stores:
        1. Multiple sellers create stores
        2. Admin views pending stores
        3. Admin approves some, rejects others
        4. Verify final states
        """
        # Create admin
        admin_id = 100000000
        db.add_user(admin_id, "super_admin")
        db.update_user_role(admin_id, "admin")
        
        # Create multiple sellers with stores
        sellers_and_stores = []
        for i in range(5):
            seller_id = 200000000 + i
            db.add_user(seller_id, f"seller_{i}")
            db.update_user_role(seller_id, "seller")
            
            store_id = db.add_store(
                owner_id=seller_id,
                name=f"Store {i}",
                city="Tashkent",
                category="Restaurant",
                address=f"Address {i}",
                phone=f"+99890{i:07d}"
            )
            
            sellers_and_stores.append((seller_id, store_id))
        
        # Admin views pending stores
        pending = db.get_stores_by_status("pending")
        assert len(pending) == 5
        
        # Approve first 3 stores
        for _, store_id in sellers_and_stores[:3]:
            db.update_store_status(store_id, "approved")
        
        # Reject last 2 stores
        for _, store_id in sellers_and_stores[3:]:
            db.update_store_status(store_id, "rejected")
        
        # Verify final counts
        approved = db.get_stores_by_status("approved")
        rejected = db.get_stores_by_status("rejected")
        pending = db.get_stores_by_status("pending")
        
        assert len(approved) == 3
        assert len(rejected) == 2
        assert len(pending) == 0


class TestErrorHandling:
    """Test error cases and edge conditions"""
    
    @pytest.fixture
    def db(self):
        """Create temporary database"""
        fd, path = tempfile.mkstemp(suffix='.db')
        os.close(fd)
        
        db_instance = Database(path)
        
        yield db_instance
        
        if os.path.exists(path):
            os.remove(path)
    
    def test_booking_nonexistent_offer_fails(self, db):
        """Test that booking a non-existent offer fails gracefully"""
        user_id = 123456
        db.add_user(user_id, "test_user")
        
        fake_offer_id = 999999
        ok, booking_id, code = db.create_booking_atomic(fake_offer_id, user_id, quantity=1)
        
        assert ok is False
        assert booking_id is None
        assert code is None
    
    def test_get_nonexistent_user(self, db):
        """Test that getting non-existent user returns None"""
        user = db.get_user(999999999)
        assert user is None
    
    def test_get_nonexistent_store(self, db):
        """Test that getting non-existent store returns None"""
        store = db.get_store(999999)
        assert store is None
    
    def test_duplicate_favorite_ignored(self, db):
        """Test that adding same favorite twice doesn't create duplicates"""
        user_id = 111111
        db.add_user(user_id, "user")
        
        seller_id = 222222
        db.add_user(seller_id, "seller")
        db.update_user_role(seller_id, "seller")
        
        store_id = db.add_store(
            owner_id=seller_id,
            name="Test Store",
            city="Tashkent",
            category="Cafe",
            address="Address",
            phone="+998901234567"
        )
        
        # Add favorite twice
        db.add_favorite(user_id, store_id)
        db.add_favorite(user_id, store_id)
        
        # Should only appear once
        favorites = db.get_user_favorites(user_id)
        assert len(favorites) == 1
