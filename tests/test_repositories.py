"""Tests for repository layer."""
from __future__ import annotations

from typing import Any
from unittest.mock import Mock

import pytest

from app.core.exceptions import (
    BookingNotFoundException,
    DatabaseException,
    OfferNotFoundException,
    StoreNotFoundException,
    UserNotFoundException,
)
from app.repositories import (
    BookingRepository,
    OfferRepository,
    StoreRepository,
    UserRepository,
)


class MockDatabase:
    """Mock database for testing."""

    def __init__(self):
        """Initialize mock database."""
        self.users = {}
        self.stores = {}
        self.offers = {}
        self.bookings = {}

    def get_user(self, user_id: int) -> dict[str, Any] | None:
        """Get user by ID."""
        return self.users.get(user_id)

    def add_user(
        self,
        user_id: int,
        language: str = "ru",
        first_name: str | None = None,
        phone: str | None = None,
        city: str | None = None,
    ) -> None:
        """Add user."""
        self.users[user_id] = {
            "id": user_id,
            "language": language,
            "first_name": first_name,
            "phone": phone,
            "city": city,
        }

    def get_store(self, store_id: int) -> dict[str, Any] | None:
        """Get store by ID."""
        return self.stores.get(store_id)

    def add_store(
        self,
        owner_id: int,
        name: str,
        city: str,
        address: str | None = None,
        description: str | None = None,
        category: str | None = None,
        phone: str | None = None,
        business_type: str = "individual",
    ) -> int:
        """Add store."""
        store_id = len(self.stores) + 1
        self.stores[store_id] = {
            "store_id": store_id,
            "owner_id": owner_id,
            "name": name,
            "city": city,
            "address": address,
            "description": description,
            "category": category,
            "phone": phone,
            "business_type": business_type,
        }
        return store_id

    def get_offer(self, offer_id: int) -> dict[str, Any] | None:
        """Get offer by ID."""
        return self.offers.get(offer_id)

    def get_booking(self, booking_id: int) -> dict[str, Any] | None:
        """Get booking by ID."""
        return self.bookings.get(booking_id)


class TestUserRepository:
    """Tests for UserRepository."""

    def test_get_user_success(self):
        """Test getting existing user."""
        db = MockDatabase()
        db.users[123] = {"id": 123, "language": "ru", "first_name": "Test"}
        repo = UserRepository(db)

        user = repo.get_user(123)
        assert user is not None
        assert user["id"] == 123
        assert user["first_name"] == "Test"

    def test_get_user_not_found(self):
        """Test getting non-existent user."""
        db = MockDatabase()
        repo = UserRepository(db)

        user = repo.get_user(999)
        assert user is None

    def test_get_user_or_raise_success(self):
        """Test get_user_or_raise with existing user."""
        db = MockDatabase()
        db.users[123] = {"id": 123, "language": "ru"}
        repo = UserRepository(db)

        user = repo.get_user_or_raise(123)
        assert user["id"] == 123

    def test_get_user_or_raise_not_found(self):
        """Test get_user_or_raise raises exception."""
        db = MockDatabase()
        repo = UserRepository(db)

        with pytest.raises(UserNotFoundException):
            repo.get_user_or_raise(999)

    def test_add_user(self):
        """Test adding new user."""
        db = MockDatabase()
        repo = UserRepository(db)

        repo.add_user(123, "en", "John", "+1234567890", "New York")
        user = db.users[123]
        assert user["id"] == 123
        assert user["language"] == "en"
        assert user["first_name"] == "John"


class TestStoreRepository:
    """Tests for StoreRepository."""

    def test_get_store_success(self):
        """Test getting existing store."""
        db = MockDatabase()
        db.stores[1] = {"store_id": 1, "name": "Test Store"}
        repo = StoreRepository(db)

        store = repo.get_store(1)
        assert store is not None
        assert store["name"] == "Test Store"

    def test_get_store_not_found(self):
        """Test getting non-existent store."""
        db = MockDatabase()
        repo = StoreRepository(db)

        store = repo.get_store(999)
        assert store is None

    def test_get_store_or_raise_not_found(self):
        """Test get_store_or_raise raises exception."""
        db = MockDatabase()
        repo = StoreRepository(db)

        with pytest.raises(StoreNotFoundException):
            repo.get_store_or_raise(999)

    def test_add_store(self):
        """Test adding new store."""
        db = MockDatabase()
        repo = StoreRepository(db)

        store_id = repo.add_store(
            owner_id=123,
            name="Test Store",
            city="Tashkent",
            address="Test Address",
            description="Test Description",
        )
        assert store_id == 1
        assert db.stores[1]["name"] == "Test Store"
        assert db.stores[1]["city"] == "Tashkent"


class TestOfferRepository:
    """Tests for OfferRepository."""

    def test_get_offer_success(self):
        """Test getting existing offer."""
        db = MockDatabase()
        db.offers[1] = {"offer_id": 1, "title": "Test Offer"}
        repo = OfferRepository(db)

        offer = repo.get_offer(1)
        assert offer is not None
        assert offer["title"] == "Test Offer"

    def test_get_offer_not_found(self):
        """Test getting non-existent offer."""
        db = MockDatabase()
        repo = OfferRepository(db)

        offer = repo.get_offer(999)
        assert offer is None

    def test_get_offer_or_raise_not_found(self):
        """Test get_offer_or_raise raises exception."""
        db = MockDatabase()
        repo = OfferRepository(db)

        with pytest.raises(OfferNotFoundException):
            repo.get_offer_or_raise(999)


class TestBookingRepository:
    """Tests for BookingRepository."""

    def test_get_booking_success(self):
        """Test getting existing booking."""
        db = MockDatabase()
        db.bookings[1] = {"booking_id": 1, "user_id": 123}
        repo = BookingRepository(db)

        booking = repo.get_booking(1)
        assert booking is not None
        assert booking["user_id"] == 123

    def test_get_booking_not_found(self):
        """Test getting non-existent booking."""
        db = MockDatabase()
        repo = BookingRepository(db)

        booking = repo.get_booking(999)
        assert booking is None

    def test_get_booking_or_raise_not_found(self):
        """Test get_booking_or_raise raises exception."""
        db = MockDatabase()
        repo = BookingRepository(db)

        with pytest.raises(BookingNotFoundException):
            repo.get_booking_or_raise(999)


class TestDatabaseError:
    """Tests for database error handling."""

    def test_user_repository_handles_error(self):
        """Test that UserRepository handles database errors."""
        db = Mock()
        db.get_user.side_effect = Exception("Database connection failed")
        repo = UserRepository(db)

        with pytest.raises(DatabaseException) as exc_info:
            repo.get_user(123)
        assert "get_user" in str(exc_info.value)
        assert "Database connection failed" in str(exc_info.value)

    def test_store_repository_handles_error(self):
        """Test that StoreRepository handles database errors."""
        db = Mock()
        db.get_store.side_effect = Exception("Database connection failed")
        repo = StoreRepository(db)

        with pytest.raises(DatabaseException) as exc_info:
            repo.get_store(1)
        assert "get_store" in str(exc_info.value)
