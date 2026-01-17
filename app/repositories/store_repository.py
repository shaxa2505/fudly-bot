"""Store repository for store-related database operations."""
from __future__ import annotations

from typing import Any

from app.core.exceptions import StoreNotFoundException

from .base import BaseRepository


class StoreRepository(BaseRepository):
    """Repository for store-related database operations."""

    def get_store(self, store_id: int) -> dict[str, Any] | None:
        """Get store by ID.

        Args:
            store_id: Store ID

        Returns:
            Store data as dict or None if not found

        Raises:
            DatabaseException: If database operation fails
        """
        try:
            return self.db.get_store(store_id)
        except Exception as e:
            self._handle_db_error("get_store", e)

    def get_store_or_raise(self, store_id: int) -> dict[str, Any]:
        """Get store by ID or raise exception.

        Args:
            store_id: Store ID

        Returns:
            Store data as dict

        Raises:
            StoreNotFoundException: If store not found
            DatabaseException: If database operation fails
        """
        store = self.get_store(store_id)
        if not store:
            raise StoreNotFoundException(store_id)
        return store

    def get_store_by_owner(self, owner_id: int) -> dict[str, Any] | None:
        """Get store by owner ID.

        Args:
            owner_id: Owner's Telegram user ID

        Returns:
            Store data as dict or None if not found

        Raises:
            DatabaseException: If database operation fails
        """
        try:
            return self.db.get_store_by_owner(owner_id)
        except Exception as e:
            self._handle_db_error("get_store_by_owner", e)

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
        photo: str | None = None,
    ) -> int:
        """Add new store.

        Args:
            owner_id: Owner's Telegram user ID
            name: Store name
            city: City
            address: Store address
            description: Store description
            category: Store category
            phone: Contact phone
            business_type: Business type (individual/legal)

        Returns:
            New store ID

        Raises:
            DatabaseException: If database operation fails
        """
        try:
            return self.db.add_store(
                owner_id=owner_id,
                name=name,
                city=city,
                address=address,
                description=description,
                category=category,
                phone=phone,
                business_type=business_type,
                photo=photo,
            )
        except Exception as e:
            self._handle_db_error("add_store", e)
            return -1

    def update_store(
        self,
        store_id: int,
        name: str | None = None,
        city: str | None = None,
        address: str | None = None,
        description: str | None = None,
        category: str | None = None,
        phone: str | None = None,
    ) -> None:
        """Update store data.

        Args:
            store_id: Store ID
            name: New store name
            city: New city
            address: New address
            description: New description
            category: New category
            phone: New phone

        Raises:
            DatabaseException: If database operation fails
        """
        try:
            self.db.update_store(store_id, name, city, address, description, category, phone)
        except Exception as e:
            self._handle_db_error("update_store", e)

    def set_store_status(
        self, store_id: int, status: str, rejection_reason: str | None = None
    ) -> None:
        """Set store status.

        Args:
            store_id: Store ID
            status: New status (pending, approved, rejected)
            rejection_reason: Reason for rejection (if rejected)

        Raises:
            DatabaseException: If database operation fails
        """
        try:
            self.db.set_store_status(store_id, status, rejection_reason)
        except Exception as e:
            self._handle_db_error("set_store_status", e)

    def get_stores_by_status(self, status: str) -> list[dict[str, Any]]:
        """Get stores by status.

        Args:
            status: Status to filter by (pending, approved, rejected)

        Returns:
            List of store dicts

        Raises:
            DatabaseException: If database operation fails
        """
        try:
            return self.db.get_stores_by_status(status)
        except Exception as e:
            self._handle_db_error("get_stores_by_status", e)
            return []

    def get_stores_by_city(self, city: str) -> list[dict[str, Any]]:
        """Get stores in specific city.

        Args:
            city: City name

        Returns:
            List of store dicts

        Raises:
            DatabaseException: If database operation fails
        """
        try:
            return self.db.get_stores_by_city(city)
        except Exception as e:
            self._handle_db_error("get_stores_by_city", e)
            return []

    def get_all_stores(self) -> list[dict[str, Any]]:
        """Get all stores.

        Returns:
            List of store dicts

        Raises:
            DatabaseException: If database operation fails
        """
        try:
            return self.db.get_all_stores()
        except Exception as e:
            self._handle_db_error("get_all_stores", e)
            return []

    def delete_store(self, store_id: int) -> None:
        """Delete store.

        Args:
            store_id: Store ID

        Raises:
            DatabaseException: If database operation fails
        """
        try:
            self.db.delete_store(store_id)
        except Exception as e:
            self._handle_db_error("delete_store", e)

    def set_delivery_settings(
        self,
        store_id: int,
        delivery_enabled: bool,
        delivery_price: float | None = None,
        min_order_amount: float | None = None,
    ) -> None:
        """Set store delivery settings.

        Args:
            store_id: Store ID
            delivery_enabled: Whether delivery is enabled
            delivery_price: Delivery price
            min_order_amount: Minimum order amount for delivery

        Raises:
            DatabaseException: If database operation fails
        """
        try:
            self.db.set_delivery_settings(
                store_id, delivery_enabled, delivery_price, min_order_amount
            )
        except Exception as e:
            self._handle_db_error("set_delivery_settings", e)
