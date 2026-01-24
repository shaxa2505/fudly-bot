"""Unit tests for database modules (PostgreSQL)."""
from __future__ import annotations

import pytest


class TestDatabasePostgres:
    """Tests for PostgreSQL database implementation"""

    def test_get_user_returns_dict(self, db):
        """Test that get_user returns dict format"""
        # Register test user
        user_id = 123456789
        username = "testuser"
        db.add_user(user_id=user_id, username=username)

        # Retrieve user
        user = db.get_user(user_id)

        # Verify dict format
        assert isinstance(user, dict)
        assert user.get("user_id") == user_id
        assert user.get("username") == username
        assert "role" in user
        assert "city" in user

    def test_get_user_nonexistent(self, db):
        """Test that get_user returns None for non-existent user"""
        user = db.get_user(999999999)
        assert user is None

    def test_get_user_stores_returns_list_of_dicts(self, db):
        """Test that get_user_stores returns list of dicts"""
        # Register user
        user_id = 111111111
        db.add_user(user_id=user_id, username="storeowner")

        # Update role to store_owner
        db.update_user_role(user_id, "store_owner")

        # Add store
        db.add_store(
            owner_id=user_id,
            name="Test Store",
            city="Test City",
            address="Test Street 1",
            description="Test Description",
        )

        # Get stores
        stores = db.get_user_stores(user_id)

        # Verify list of dicts
        assert isinstance(stores, list)
        if stores:  # If any stores exist
            assert isinstance(stores[0], dict)
            assert "store_id" in stores[0]
            assert "name" in stores[0]
            assert "city" in stores[0]

    def test_get_stores_by_city_returns_list_of_dicts(self, db):
        """Test that get_stores_by_city returns list of dicts"""
        # Register user and add store
        user_id = 222222222
        db.add_user(user_id=user_id, username="cityowner")
        db.update_user_role(user_id, "store_owner")

        city = "Moscow"
        db.add_store(
            owner_id=user_id,
            name="Moscow Store",
            city=city,
            address="Arbat 1",
            description="Description",
        )

        # Approve store
        stores = db.get_user_stores(user_id)
        if stores:
            store_id = stores[0]["store_id"]
            db.approve_store(store_id)

        # Get stores by city
        city_stores = db.get_stores_by_city(city)

        # Verify list of dicts
        assert isinstance(city_stores, list)
        if city_stores:
            assert isinstance(city_stores[0], dict)
            assert city_stores[0].get("city") == city
            assert "name" in city_stores[0]

    def test_get_approved_stores_returns_list_of_dicts(self, db):
        """Test that get_approved_stores returns list of dicts"""
        # Register user and add approved store
        user_id = 333333333
        db.add_user(user_id=user_id, username="approvedowner")
        db.update_user_role(user_id, "store_owner")

        db.add_store(
            owner_id=user_id,
            name="Approved Store",
            city="City",
            address="Address",
            description="Desc",
        )
        stores = db.get_user_stores(user_id)
        if stores:
            store_id = stores[0]["store_id"]
            db.approve_store(store_id)

        # Get approved stores
        approved = db.get_approved_stores(user_id)

        # Verify list of dicts
        assert isinstance(approved, list)
        if approved:
            assert isinstance(approved[0], dict)
            # Status changes to 'active' after approval
            assert approved[0].get("status") in ["approved", "active"]
            assert "name" in approved[0]

    def test_get_store_returns_dict(self, db):
        """Test that get_store returns dict format"""
        # Register user and add store
        user_id = 444444444
        db.add_user(user_id=user_id, username="singlestore")
        db.update_user_role(user_id, "store_owner")

        store_name = "Single Store"
        db.add_store(
            owner_id=user_id,
            name=store_name,
            city="City",
            address="Address",
            description="Desc",
        )

        # Get store by user stores
        stores = db.get_user_stores(user_id)
        assert stores, "User should have stores"

        store_id = stores[0]["store_id"]

        # Get single store
        store = db.get_store(store_id)

        # Verify dict format
        assert isinstance(store, dict)
        assert store.get("store_id") == store_id
        assert store.get("name") == store_name
        assert "city" in store
        assert "address" in store

    def test_get_store_nonexistent(self, db):
        """Test that get_store returns None for non-existent store"""
        store = db.get_store(999999)
        assert store is None

    def test_register_user_and_retrieve(self, db):
        """Test user registration and retrieval flow"""
        user_id = 555555555
        username = "flowtest"

        # Register
        db.add_user(user_id=user_id, username=username)

        # Retrieve and verify
        user = db.get_user(user_id)
        assert user is not None
        assert user["user_id"] == user_id
        assert user["username"] == username

    def test_update_user_role(self, db):
        """Test role update functionality"""
        user_id = 666666666
        db.add_user(user_id=user_id, username="roletest")

        # Update role
        db.update_user_role(user_id, "store_owner")

        # Verify
        user = db.get_user(user_id)
        assert user["role"] == "store_owner"


class TestDatabaseProtocol:
    """Tests for DatabaseProtocol typing compliance"""

    def test_database_implements_protocol(self, db):
        """Test that Database class implements DatabaseProtocol"""
        # Check that methods exist
        assert hasattr(db, "get_user")
        assert hasattr(db, "get_user_stores")
        assert hasattr(db, "get_stores_by_city")
        assert hasattr(db, "get_approved_stores")
        assert hasattr(db, "get_store")
        assert hasattr(db, "add_user")
        assert hasattr(db, "update_user_role")

        # Type check (static)
        assert callable(db.get_user)
        assert callable(db.get_user_stores)
