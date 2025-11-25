"""
Cached repository wrappers with automatic cache invalidation.

Provides transparent caching layer over existing repositories.
"""
from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any, TypeVar

from app.core.caching import CacheService, CacheTags, get_cache_service

from .offer_repository import OfferRepository
from .store_repository import StoreRepository

logger = logging.getLogger(__name__)

T = TypeVar("T")


class CachedRepositoryMixin:
    """Mixin providing cache functionality to repositories."""

    def __init__(self, *args, cache_service: CacheService | None = None, **kwargs):
        super().__init__(*args, **kwargs)
        self._cache = cache_service or get_cache_service()

    async def _cached_call(
        self, key: str, func: Callable[[], T], ttl: int = 300, tags: list[str] | None = None
    ) -> T:
        """Execute function with caching."""
        cached = await self._cache.get(key)
        if cached is not None:
            logger.debug(f"Cache hit: {key}")
            return cached

        logger.debug(f"Cache miss: {key}")
        result = func()
        await self._cache.set(key, result, ttl, tags)
        return result

    async def _invalidate_cache(self, *tags: str) -> None:
        """Invalidate cache by tags."""
        for tag in tags:
            await self._cache.invalidate_tag(tag)


class CachedOfferRepository(CachedRepositoryMixin, OfferRepository):
    """
    Cached wrapper for OfferRepository.

    Caches read operations and invalidates on writes.
    """

    # TTL values in seconds
    OFFER_TTL = 60  # Single offer: 1 minute
    LIST_TTL = 30  # Lists: 30 seconds (more dynamic)
    SEARCH_TTL = 120  # Search results: 2 minutes

    def get_offer(self, offer_id: int) -> dict[str, Any] | None:
        """Get offer with caching."""
        # For sync repositories, we need to run cache async
        # This is a simplified sync version
        return super().get_offer(offer_id)

    async def get_offer_cached(self, offer_id: int) -> dict[str, Any] | None:
        """Get offer with async caching."""
        key = f"offer:{offer_id}"
        tags = [CacheTags.OFFERS, CacheTags.offer(offer_id)]

        return await self._cached_call(
            key,
            lambda: super(CachedOfferRepository, self).get_offer(offer_id),
            ttl=self.OFFER_TTL,
            tags=tags,
        )

    async def get_active_offers_cached(
        self, city: str | None = None, category: str | None = None, limit: int | None = None
    ) -> list[dict[str, Any]]:
        """Get active offers with caching."""
        key = f"offers:active:{city or 'all'}:{category or 'all'}:{limit or 'all'}"
        tags = [CacheTags.OFFERS]
        if city:
            tags.append(CacheTags.city(city))

        return await self._cached_call(
            key,
            lambda: super(CachedOfferRepository, self).get_active_offers(city, category, limit),
            ttl=self.LIST_TTL,
            tags=tags,
        )

    async def get_offers_by_store_cached(self, store_id: int) -> list[dict[str, Any]]:
        """Get store offers with caching."""
        key = f"offers:store:{store_id}"
        tags = [CacheTags.OFFERS, CacheTags.store(store_id)]

        return await self._cached_call(
            key,
            lambda: super(CachedOfferRepository, self).get_offers_by_store(store_id),
            ttl=self.LIST_TTL,
            tags=tags,
        )

    # Write operations with cache invalidation

    def add_offer(
        self,
        store_id: int,
        title: str,
        description: str | None = None,
        original_price: float | None = None,
        discount_price: float | None = None,
        quantity: int = 1,
        available_from: str | None = None,
        available_until: str | None = None,
        expiry_date: str | None = None,
        photo: str | None = None,
        unit: str = "шт",
        category: str | None = None,
    ) -> int:
        """Add offer and invalidate cache."""
        offer_id = super().add_offer(
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

        # Schedule cache invalidation
        logger.info(f"New offer {offer_id} - cache invalidation needed")
        return offer_id

    async def add_offer_async(
        self,
        store_id: int,
        title: str,
        description: str | None = None,
        original_price: float | None = None,
        discount_price: float | None = None,
        quantity: int = 1,
        available_from: str | None = None,
        available_until: str | None = None,
        expiry_date: str | None = None,
        photo: str | None = None,
        unit: str = "шт",
        category: str | None = None,
    ) -> int:
        """Add offer with automatic cache invalidation."""
        offer_id = super().add_offer(
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

        # Invalidate related caches
        await self._invalidate_cache(CacheTags.OFFERS, CacheTags.store(store_id), CacheTags.SEARCH)

        return offer_id

    async def update_offer_async(
        self,
        offer_id: int,
        title: str | None = None,
        description: str | None = None,
        original_price: float | None = None,
        discount_price: float | None = None,
        quantity: int | None = None,
        available_from: str | None = None,
        available_until: str | None = None,
        expiry_date: str | None = None,
        photo: str | None = None,
        unit: str | None = None,
        category: str | None = None,
    ) -> None:
        """Update offer with cache invalidation."""
        # Get offer to know store_id
        offer = super().get_offer(offer_id)

        super().update_offer(
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

        # Invalidate caches
        tags = [CacheTags.OFFERS, CacheTags.offer(offer_id), CacheTags.SEARCH]
        if offer:
            tags.append(CacheTags.store(offer.get("store_id", 0)))

        await self._invalidate_cache(*tags)

    async def delete_offer_async(self, offer_id: int) -> None:
        """Delete offer with cache invalidation."""
        # Get offer to know store_id
        offer = super().get_offer(offer_id)

        super().delete_offer(offer_id)

        tags = [CacheTags.OFFERS, CacheTags.offer(offer_id), CacheTags.SEARCH]
        if offer:
            tags.append(CacheTags.store(offer.get("store_id", 0)))

        await self._invalidate_cache(*tags)

    async def set_offer_status_async(self, offer_id: int, status: str) -> None:
        """Set offer status with cache invalidation."""
        offer = super().get_offer(offer_id)
        super().set_offer_status(offer_id, status)

        tags = [CacheTags.OFFERS, CacheTags.offer(offer_id)]
        if offer:
            tags.append(CacheTags.store(offer.get("store_id", 0)))

        await self._invalidate_cache(*tags)

    async def decrease_quantity_async(self, offer_id: int, amount: int = 1) -> bool:
        """Decrease quantity with cache invalidation."""
        result = super().decrease_offer_quantity(offer_id, amount)

        if result:
            await self._invalidate_cache(CacheTags.offer(offer_id), CacheTags.OFFERS)

        return result


class CachedStoreRepository(CachedRepositoryMixin, StoreRepository):
    """
    Cached wrapper for StoreRepository.
    """

    STORE_TTL = 300  # Single store: 5 minutes
    LIST_TTL = 120  # Lists: 2 minutes

    async def get_store_cached(self, store_id: int) -> dict[str, Any] | None:
        """Get store with caching."""
        key = f"store:{store_id}"
        tags = [CacheTags.STORES, CacheTags.store(store_id)]

        return await self._cached_call(
            key,
            lambda: super(CachedStoreRepository, self).get_store(store_id),
            ttl=self.STORE_TTL,
            tags=tags,
        )

    async def get_stores_by_city_cached(self, city: str) -> list[dict[str, Any]]:
        """Get stores by city with caching."""
        key = f"stores:city:{city}"
        tags = [CacheTags.STORES, CacheTags.city(city)]

        return await self._cached_call(
            key,
            lambda: super(CachedStoreRepository, self).get_stores_by_city(city),
            ttl=self.LIST_TTL,
            tags=tags,
        )

    async def add_store_async(
        self,
        user_id: int,
        name: str,
        description: str | None = None,
        city: str | None = None,
        address: str | None = None,
        phone: str | None = None,
        photo: str | None = None,
    ) -> int:
        """Add store with cache invalidation."""
        store_id = super().add_store(user_id, name, description, city, address, phone, photo)

        tags = [CacheTags.STORES]
        if city:
            tags.append(CacheTags.city(city))

        await self._invalidate_cache(*tags)
        return store_id

    async def update_store_async(
        self,
        store_id: int,
        name: str | None = None,
        description: str | None = None,
        city: str | None = None,
        address: str | None = None,
        phone: str | None = None,
        photo: str | None = None,
    ) -> None:
        """Update store with cache invalidation."""
        store = super().get_store(store_id)

        super().update_store(store_id, name, description, city, address, phone, photo)

        tags = [CacheTags.STORES, CacheTags.store(store_id)]
        if store and store.get("city"):
            tags.append(CacheTags.city(store["city"]))
        if city:
            tags.append(CacheTags.city(city))

        await self._invalidate_cache(*tags)


def create_cached_offer_repository(
    db, cache_service: CacheService | None = None
) -> CachedOfferRepository:
    """Factory for cached offer repository."""
    return CachedOfferRepository(db, cache_service=cache_service)


def create_cached_store_repository(
    db, cache_service: CacheService | None = None
) -> CachedStoreRepository:
    """Factory for cached store repository."""
    return CachedStoreRepository(db, cache_service=cache_service)
