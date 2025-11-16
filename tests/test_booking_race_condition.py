"""
Race condition tests for booking system

Tests that create_booking_atomic() properly handles concurrent bookings
and prevents overbooking when multiple users try to book the same offer.
"""
from __future__ import annotations

import os
import tempfile
import threading
import time
from typing import List, Tuple

import pytest

from database import Database


class TestBookingRaceCondition:
    """Test concurrent booking scenarios to prevent overbooking"""
    
    @pytest.fixture
    def db(self):
        """Create temporary SQLite database for testing"""
        fd, path = tempfile.mkstemp(suffix='.db')
        os.close(fd)
        
        db_instance = Database(path)
        
        yield db_instance
        
        # Cleanup (Windows-friendly: ensure connections closed and retry remove)
        try:
            # Give SQLite a brief moment to release file handles
            time.sleep(0.1)
            if os.path.exists(path):
                os.remove(path)
        except PermissionError:
            # Retry a few times on Windows if file is locked
            for _ in range(10):
                time.sleep(0.2)
                try:
                    if os.path.exists(path):
                        os.remove(path)
                    break
                except PermissionError:
                    continue
    
    @pytest.fixture
    def sample_offer(self, db):
        """Create a sample offer with limited quantity"""
        # Create test seller
        seller_id = 111111
        db.add_user(seller_id, "test_seller")
        db.update_user_role(seller_id, "seller")
        
        # Create test store
        store_id = db.add_store(
            owner_id=seller_id,
            name="Test Store",
            city="Tashkent",
            category="Bakery",
            address="Test Address 123",
            phone="+998901234567"
        )
        
        # Create offer with 5 items available
        offer_id = db.add_offer(
            store_id=store_id,
            title="Test Pizza",
            description="Limited quantity test item",
            original_price=100000.0,
            discount_price=50000.0,
            quantity=5,  # Only 5 items available
            available_from="18:00",
            available_until="22:00"
        )
        
        return offer_id
    
    def test_single_booking_succeeds(self, db, sample_offer):
        """Test that a single booking works correctly"""
        user_id = 222222
        db.add_user(user_id, "test_buyer")
        
        ok, booking_id, code = db.create_booking_atomic(sample_offer, user_id, quantity=1)
        
        assert ok is True
        assert booking_id is not None
        assert code is not None
        assert len(code) == 6  # 6-character booking code
        
        # Verify offer quantity decreased
        offer = db.get_offer(sample_offer)
        assert offer is not None
        quantity_field = offer[6]  # quantity is at index 6
        assert quantity_field == 4  # 5 - 1 = 4
    
    def test_concurrent_bookings_no_overbooking(self, db, sample_offer):
        """
        Test that 10 concurrent threads trying to book 1 item each
        results in only 5 successful bookings (matching available quantity)
        """
        num_threads = 10
        available_quantity = 5
        
        results: List[Tuple[bool, int | None, str | None]] = []
        results_lock = threading.Lock()
        
        def book_item(user_id: int):
            """Each thread tries to book 1 item"""
            db.add_user(user_id, f"concurrent_user_{user_id}")
            ok, booking_id, code = db.create_booking_atomic(sample_offer, user_id, quantity=1)
            
            with results_lock:
                results.append((ok, booking_id, code))
        
        # Create threads
        threads = []
        base_user_id = 300000
        for i in range(num_threads):
            thread = threading.Thread(target=book_item, args=(base_user_id + i,))
            threads.append(thread)
        
        # Start all threads at once
        for thread in threads:
            thread.start()
        
        # Wait for all threads to complete
        for thread in threads:
            thread.join()
        
        # Count successful bookings
        successful_bookings = sum(1 for ok, _, _ in results if ok)
        failed_bookings = sum(1 for ok, _, _ in results if not ok)
        
        # Assert exactly 5 succeeded (matching available quantity)
        assert successful_bookings == available_quantity, \
            f"Expected {available_quantity} successful bookings, got {successful_bookings}"
        
        # Assert exactly 5 failed (10 - 5 = 5)
        assert failed_bookings == (num_threads - available_quantity), \
            f"Expected {num_threads - available_quantity} failed bookings, got {failed_bookings}"
        
        # Verify offer quantity is now 0
        offer = db.get_offer(sample_offer)
        quantity_field = offer[6]  # quantity is at index 6
        assert quantity_field == 0, f"Expected quantity 0, got {quantity_field}"
        
        # Verify offer status changed to inactive
        status_field = offer[10]  # status is at index 10
        assert status_field == 'inactive', f"Expected status 'inactive', got {status_field}"
    
    def test_concurrent_large_quantity_bookings(self, db, sample_offer):
        """
        Test that 3 threads trying to book 2 items each
        results in only 2 successful bookings (2+2=4, then 1 item left)
        """
        num_threads = 3
        quantity_per_booking = 2
        
        results: List[Tuple[bool, int | None, str | None]] = []
        results_lock = threading.Lock()
        
        def book_items(user_id: int):
            """Each thread tries to book 2 items"""
            db.add_user(user_id, f"bulk_user_{user_id}")
            ok, booking_id, code = db.create_booking_atomic(sample_offer, user_id, quantity=quantity_per_booking)
            
            with results_lock:
                results.append((ok, booking_id, code))
        
        # Create threads
        threads = []
        base_user_id = 400000
        for i in range(num_threads):
            thread = threading.Thread(target=book_items, args=(base_user_id + i,))
            threads.append(thread)
        
        # Start all threads
        for thread in threads:
            thread.start()
        
        # Wait for completion
        for thread in threads:
            thread.join()
        
        # Count results
        successful_bookings = sum(1 for ok, _, _ in results if ok)
        
        # Should be exactly 2 successful (2+2=4 items booked, 1 item left insufficient for 3rd booking)
        assert successful_bookings == 2, \
            f"Expected 2 successful bookings of 2 items each, got {successful_bookings}"
        
        # Verify final quantity
        offer = db.get_offer(sample_offer)
        quantity_field = offer[6]  # quantity is at index 6
        assert quantity_field == 1, f"Expected 1 item remaining (5-2-2=1), got {quantity_field}"
    
    def test_booking_inactive_offer_fails(self, db, sample_offer):
        """Test that booking an inactive offer fails"""
        # Mark offer as inactive
        conn = db.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute('UPDATE offers SET status = ? WHERE offer_id = ?', ('inactive', sample_offer))
            conn.commit()
        finally:
            try:
                conn.close()
            except Exception:
                pass
        
        user_id = 555555
        db.add_user(user_id, "test_user")
        
        ok, booking_id, code = db.create_booking_atomic(sample_offer, user_id, quantity=1)
        
        assert ok is False
        assert booking_id is None
        assert code is None
    
    def test_booking_more_than_available_fails(self, db, sample_offer):
        """Test that booking more items than available fails"""
        user_id = 666666
        db.add_user(user_id, "greedy_user")
        
        # Try to book 10 items when only 5 available
        ok, booking_id, code = db.create_booking_atomic(sample_offer, user_id, quantity=10)
        
        assert ok is False
        assert booking_id is None
        assert code is None
        
        # Verify quantity unchanged
        offer = db.get_offer(sample_offer)
        quantity_field = offer[6]  # quantity is at index 6
        assert quantity_field == 5, "Quantity should remain 5 after failed booking"
    
    def test_unique_booking_codes(self, db, sample_offer):
        """Test that all booking codes are unique"""
        codes = set()
        
        for i in range(5):  # Book all 5 items
            user_id = 700000 + i
            db.add_user(user_id, f"user_{i}")
            
            ok, booking_id, code = db.create_booking_atomic(sample_offer, user_id, quantity=1)
            
            assert ok is True
            assert code not in codes, f"Duplicate booking code generated: {code}"
            codes.add(code)
        
        assert len(codes) == 5, "Should have 5 unique booking codes"
