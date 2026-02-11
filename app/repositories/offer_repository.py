"""Offer repository for offer-related database operations."""
from __future__ import annotations

from typing import Any

from app.core.exceptions import OfferNotFoundException

from .base import BaseRepository


class OfferRepository(BaseRepository):
    """Repository for offer-related database operations."""

    def get_offer(self, offer_id: int) -> dict[str, Any] | None:
        """Get offer by ID.

        Args:
            offer_id: Offer ID

        Returns:
            Offer data as dict or None if not found

        Raises:
            DatabaseException: If database operation fails
        """
        try:
            return self.db.get_offer(offer_id)
        except Exception as e:
            self._handle_db_error("get_offer", e)

    def get_offer_or_raise(self, offer_id: int) -> dict[str, Any]:
        """Get offer by ID or raise exception.

        Args:
            offer_id: Offer ID

        Returns:
            Offer data as dict

        Raises:
            OfferNotFoundException: If offer not found
            DatabaseException: If database operation fails
        """
        offer = self.get_offer(offer_id)
        if not offer:
            raise OfferNotFoundException(offer_id)
        return offer

    def add_offer(
        self,
        store_id: int,
        title: str,
        description: str | None = None,
        original_price: float | None = None,
        discount_price: float | None = None,
        quantity: float = 1,
        available_from: str | None = None,
        available_until: str | None = None,
        expiry_date: str | None = None,
        photo: str | None = None,
        unit: str = "piece",
        category: str | None = None,
    ) -> int:
        """Add new offer.

        Args:
            store_id: Store ID
            title: Offer title
            description: Offer description
            original_price: Original price
            discount_price: Discounted price
            quantity: Available quantity
            available_from: Start datetime
            available_until: End datetime
            expiry_date: Product expiry date
            photo: Photo file ID
            unit: Unit of measurement
            category: Offer category

        Returns:
            New offer ID

        Raises:
            DatabaseException: If database operation fails
        """
        try:
            return self.db.add_offer(
                store_id,
                title,
                description,
                original_price,
                discount_price,
                quantity,
                available_from,
                available_until,
                expiry_date,
                photo,
                unit,
                category,
            )
        except Exception as e:
            self._handle_db_error("add_offer", e)
            return -1

    def update_offer(
        self,
        offer_id: int,
        title: str | None = None,
        description: str | None = None,
        original_price: float | None = None,
        discount_price: float | None = None,
        quantity: float | None = None,
        available_from: str | None = None,
        available_until: str | None = None,
        expiry_date: str | None = None,
        photo: str | None = None,
        unit: str | None = None,
        category: str | None = None,
    ) -> None:
        """Update offer data.

        Args:
            offer_id: Offer ID
            title: New title
            description: New description
            original_price: New original price
            discount_price: New discount price
            quantity: New quantity
            available_from: New start datetime
            available_until: New end datetime
            expiry_date: New expiry date
            photo: New photo file ID
            unit: New unit
            category: New category

        Raises:
            DatabaseException: If database operation fails
        """
        try:
            self.db.update_offer(
                offer_id,
                title,
                description,
                original_price,
                discount_price,
                quantity,
                available_from,
                available_until,
                expiry_date,
                photo,
                unit,
                category,
            )
        except Exception as e:
            self._handle_db_error("update_offer", e)

    def set_offer_status(self, offer_id: int, status: str) -> None:
        """Set offer status.

        Args:
            offer_id: Offer ID
            status: New status (active, sold, expired, cancelled)

        Raises:
            DatabaseException: If database operation fails
        """
        try:
            self.db.set_offer_status(offer_id, status)
        except Exception as e:
            self._handle_db_error("set_offer_status", e)

    def get_active_offers(
        self, city: str | None = None, category: str | None = None, limit: int | None = None
    ) -> list[dict[str, Any]]:
        """Get active offers.

        Args:
            city: Filter by city
            category: Filter by category
            limit: Maximum number of offers to return

        Returns:
            List of offer dicts

        Raises:
            DatabaseException: If database operation fails
        """
        try:
            return self.db.get_active_offers(city, category, limit)
        except Exception as e:
            self._handle_db_error("get_active_offers", e)
            return []

    def get_offers_by_store(self, store_id: int) -> list[dict[str, Any]]:
        """Get all offers for a store.

        Args:
            store_id: Store ID

        Returns:
            List of offer dicts

        Raises:
            DatabaseException: If database operation fails
        """
        try:
            return self.db.get_offers_by_store(store_id)
        except Exception as e:
            self._handle_db_error("get_offers_by_store", e)
            return []

    def delete_offer(self, offer_id: int) -> None:
        """Delete offer.

        Args:
            offer_id: Offer ID

        Raises:
            DatabaseException: If database operation fails
        """
        try:
            self.db.delete_offer(offer_id)
        except Exception as e:
            self._handle_db_error("delete_offer", e)

    def decrease_offer_quantity(self, offer_id: int, amount: float = 1) -> bool:
        """Decrease offer quantity.

        Args:
            offer_id: Offer ID
            amount: Amount to decrease

        Returns:
            True if successful, False otherwise

        Raises:
            DatabaseException: If database operation fails
        """
        try:
            self.db.decrease_offer_quantity(offer_id, amount)
            return True
        except Exception as e:
            self._handle_db_error("decrease_offer_quantity", e)
            return False
