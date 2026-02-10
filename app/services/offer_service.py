"""Offer-related domain services and data transfer objects."""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from app.core.cache import CacheManager
from app.core.utils import get_field, get_offer_field, get_store_field
from app.repositories import OfferRepository, StoreRepository


@dataclass(slots=True)
class OfferListItem:
    id: int
    store_id: int
    title: str
    original_price: float
    discount_price: float
    discount_percent: float
    store_name: str
    store_address: str | None = None
    store_category: str | None = None
    quantity: int | None = None
    unit: str | None = None
    available_from: str | None = None
    available_until: str | None = None
    expiry_date: str | None = None
    delivery_enabled: bool = False
    delivery_price: float = 0.0
    min_order_amount: float = 0.0
    photo: str | None = None
    category: str = "other"


@dataclass(slots=True)
class OfferDetails(OfferListItem):
    description: str | None = None
    photo: str | None = None
    category: str = "other"
    store_city: str | None = None
    store_description: str | None = None
    store_phone: str | None = None
    delivery_enabled: bool = False
    delivery_price: float = 0.0
    min_order_amount: float = 0.0


@dataclass(slots=True)
class StoreSummary:
    id: int
    name: str
    city: str | None
    address: str | None
    business_type: str
    offers_count: int
    rating: float
    ratings_count: int


@dataclass(slots=True)
class StoreDetails(StoreSummary):
    description: str | None = None
    phone: str | None = None
    delivery_enabled: bool = False
    delivery_price: float = 0.0
    min_order_amount: float = 0.0


@dataclass(slots=True)
class OfferListResult:
    items: list[OfferListItem]
    total: int


class OfferService:
    """Aggregate offer/stores data for handlers."""

    def __init__(
        self,
        db: Any,
        cache: CacheManager | None = None,
        offer_repo: OfferRepository | None = None,
        store_repo: StoreRepository | None = None,
    ):
        self._db = db
        self._cache = cache
        # Initialize repositories if not provided
        self._offer_repo = offer_repo or OfferRepository(db)
        self._store_repo = store_repo or StoreRepository(db)

    # ------------------------------------------------------------------
    # Hot offers
    # ------------------------------------------------------------------
    def list_hot_offers(
        self,
        city: str | None = None,
        limit: int = 20,
        offset: int = 0,
        region: str | None = None,
        district: str | None = None,
        latitude: float | None = None,
        longitude: float | None = None,
        sort_by: str | None = None,
        min_price: float | None = None,
        max_price: float | None = None,
        min_discount: float | None = None,
        category: str | list[str] | None = None,
        store_id: int | None = None,
        only_today: bool = False,
    ) -> OfferListResult:
        """Return hot offers with optional location scoping and fallback."""
        raw_offers: list[Any] = []
        used_scope = (None, None, None)
        scopes = self._build_location_scopes(city, region, district)

        for scope_city, scope_region, scope_district in scopes:
            raw_offers = self._fetch_hot_offers(
                scope_city,
                scope_region,
                scope_district,
                limit,
                offset,
                sort_by,
                min_price,
                max_price,
                min_discount,
                category,
                store_id,
                only_today,
                latitude,
                longitude,
            )
            used_scope = (scope_city, scope_region, scope_district)
            if raw_offers:
                break

        total = 0
        if raw_offers:
            if hasattr(self._db, "count_offers_by_filters"):
                total = int(
                    self._db.count_offers_by_filters(
                        city=used_scope[0],
                        region=used_scope[1],
                        district=used_scope[2],
                        category=category,
                        min_price=min_price,
                        max_price=max_price,
                        min_discount=min_discount,
                        store_id=store_id,
                        only_today=only_today,
                    )
                )
            elif hasattr(self._db, "count_hot_offers"):
                total = int(
                    self._db.count_hot_offers(
                        used_scope[0],
                        region=used_scope[1],
                        district=used_scope[2],
                    )
                )
        elif latitude is not None and longitude is not None and hasattr(self._db, "get_nearby_offers"):
            raw_offers = self._db.get_nearby_offers(
                latitude=latitude,
                longitude=longitude,
                limit=limit,
                offset=offset,
                category=category,
                sort_by=sort_by,
                min_price=min_price,
                max_price=max_price,
                min_discount=min_discount,
                store_id=store_id,
                only_today=only_today,
            )
            total = len(raw_offers)

        items = [self._to_offer_list_item(row) for row in raw_offers]
        return OfferListResult(items=items, total=total)

    # ------------------------------------------------------------------
    # Stores filtering
    # ------------------------------------------------------------------
    def list_stores_by_type(
        self,
        city: str | None,
        business_type: str,
        region: str | None = None,
        district: str | None = None,
        latitude: float | None = None,
        longitude: float | None = None,
    ) -> list[StoreSummary]:
        """Return stores for a business type with cached fallback."""
        normalized = self._map_business_type(business_type)

        from logging import getLogger

        logger = getLogger(__name__)
        logger.info(
            f"à??ٍ list_stores_by_type: city={city}, business_type={business_type}, normalized={normalized}"
        )

        raw_stores: list[Any] = []
        scopes = self._build_location_scopes(city, region, district)
        for scope_city, scope_region, scope_district in scopes:
            if business_type == "delivery":
                raw_stores = self._fetch_delivery_enabled_stores(
                    scope_city, scope_region, scope_district, normalized
                )
            else:
                raw_stores = self._fetch_stores_by_scope(
                    scope_city, scope_region, scope_district, normalized
                )
            if raw_stores:
                break

        if (
            not raw_stores
            and latitude is not None
            and longitude is not None
            and hasattr(self._db, "get_nearby_stores")
        ):
            raw_stores = self._db.get_nearby_stores(
                latitude=latitude,
                longitude=longitude,
                business_type=normalized,
            )
            if business_type == "delivery":
                raw_stores = [
                    row for row in raw_stores if get_store_field(row, "delivery_enabled", 0)
                ]

        logger.info(f"à??ٍ Found {len(raw_stores)} raw stores")

        return [self._to_store_summary(store) for store in raw_stores]

    def list_active_stores(
        self,
        city: str | None,
        region: str | None = None,
        district: str | None = None,
        latitude: float | None = None,
        longitude: float | None = None,
    ) -> list[StoreSummary]:
        """Return stores with active offers, sorted by offers count."""
        raw_stores: list[Any] = []
        scopes = self._build_location_scopes(city, region, district)

        for scope_city, scope_region, scope_district in scopes:
            if hasattr(self._db, "get_stores_by_location"):
                raw_stores = self._db.get_stores_by_location(
                    city=scope_city,
                    region=scope_region,
                    district=scope_district,
                    business_type=None,
                )
            elif scope_city and hasattr(self._db, "get_stores_by_city"):
                raw_stores = self._db.get_stores_by_city(scope_city)
            if raw_stores:
                break

        if (
            not raw_stores
            and latitude is not None
            and longitude is not None
            and hasattr(self._db, "get_nearby_stores")
        ):
            raw_stores = self._db.get_nearby_stores(
                latitude=latitude,
                longitude=longitude,
                limit=1000,
                offset=0,
                business_type=None,
            )

        stores = [self._to_store_summary(store) for store in raw_stores]
        active = [store for store in stores if (store.offers_count or 0) > 0]
        return sorted(active, key=lambda s: (-s.offers_count, s.name or ""))

    def _fetch_delivery_enabled_stores(
        self,
        city: str | None,
        region: str | None,
        district: str | None,
        normalized: str,
    ) -> list[Any]:
        stores: list[Any] = []
        if region or district:
            raw = self._fetch_stores_by_scope(city, region, district, normalized)
            stores = [row for row in raw if get_store_field(row, "delivery_enabled", 0)]
            return stores

        if hasattr(self._db, "get_stores_with_delivery"):
            stores = self._db.get_stores_with_delivery(city) or []
        if not stores:
            raw = self._fetch_stores_by_scope(city, None, None, normalized)
            stores = [row for row in raw if get_store_field(row, "delivery_enabled", 0)]
        return stores

    @staticmethod
    def _map_business_type(business_type: str) -> str:
        mapping = {
            "supermarket": "supermarket",
            "restaurant": "restaurant",
            "bakery": "bakery",
            "cafe": "cafe",
            "pharmacy": "pharmacy",
            "delivery": "supermarket",
        }
        return mapping.get(business_type, "supermarket")

    def _build_location_scopes(
        self,
        city: str | None,
        region: str | None,
        district: str | None,
    ) -> list[tuple[str | None, str | None, str | None]]:
        scopes: list[tuple[str | None, str | None, str | None]] = []
        if city and not region and not district and hasattr(self._db, "resolve_geo_location"):
            try:
                resolved = self._db.resolve_geo_location(region=None, district=city, city=city)
            except Exception:
                resolved = None
            if resolved and isinstance(resolved, Mapping):
                resolved_region = resolved.get("region_name_ru")
                resolved_district = resolved.get("district_name_ru")
                if resolved_district:
                    scopes.append((None, resolved_region, resolved_district))
                if resolved_region:
                    scopes.append((None, resolved_region, None))
        if district:
            scopes.append((None, region, district))
        if region:
            scopes.append((None, region, None))
        if city:
            scopes.append((city, None, None))
            if not region:
                scopes.append((None, city, None))
        if not scopes:
            scopes.append((None, None, None))
        seen: set[tuple[str | None, str | None, str | None]] = set()
        deduped: list[tuple[str | None, str | None, str | None]] = []
        for scope in scopes:
            if scope in seen:
                continue
            seen.add(scope)
            deduped.append(scope)
        return deduped

    def _fetch_hot_offers(
        self,
        city: str | None,
        region: str | None,
        district: str | None,
        limit: int,
        offset: int,
        sort_by: str | None,
        min_price: float | None,
        max_price: float | None,
        min_discount: float | None,
        category: str | list[str] | None,
        store_id: int | None,
        only_today: bool,
        latitude: float | None,
        longitude: float | None,
    ) -> list[Any]:
        use_cache = (
            self._cache is not None
            and city is not None
            and not region
            and not district
            and offset == 0
            and sort_by is None
            and min_price is None
            and max_price is None
            and min_discount is None
            and category is None
            and store_id is None
            and not only_today
            and latitude is None
            and longitude is None
        )
        if use_cache:
            return self._cache.get_hot_offers(city, limit, offset)
        return self._db.get_hot_offers(
            city,
            limit=limit,
            offset=offset,
            region=region,
            district=district,
            sort_by=sort_by,
            min_price=min_price,
            max_price=max_price,
            min_discount=min_discount,
            category=category,
            store_id=store_id,
            only_today=only_today,
            latitude=latitude,
            longitude=longitude,
        )

    def _fetch_stores_by_scope(
        self,
        city: str | None,
        region: str | None,
        district: str | None,
        business_type: str,
    ) -> list[Any]:
        if region or district or city is None:
            if hasattr(self._db, "get_stores_by_location"):
                return self._db.get_stores_by_location(
                    city=city,
                    region=region,
                    district=district,
                    business_type=business_type,
                )
            return self._db.get_stores_by_business_type(business_type, city)
        if self._cache:
            return self._cache.get_stores_by_type(city, business_type)
        return self._db.get_stores_by_business_type(business_type, city)

    # ------------------------------------------------------------------
    # Store details
    # ------------------------------------------------------------------
    def get_store(self, store_id: int) -> StoreDetails | None:
        store = self._store_repo.get_store(store_id)
        if not store:
            return None
        summary = self._to_store_summary(store)
        return StoreDetails(
            id=summary.id,
            name=summary.name,
            city=summary.city,
            address=summary.address,
            business_type=summary.business_type,
            offers_count=summary.offers_count,
            rating=summary.rating,
            ratings_count=summary.ratings_count,
            description=get_store_field(store, "description", ""),
            phone=get_store_field(store, "phone", ""),
            delivery_enabled=bool(get_store_field(store, "delivery_enabled", 0)),
            delivery_price=float(get_store_field(store, "delivery_price", 0) or 0),
            min_order_amount=float(get_store_field(store, "min_order_amount", 0) or 0),
        )

    def list_store_offers(self, store_id: int) -> list[OfferListItem]:
        # Prefer DB-level `get_store_offers` which returns all offers for a store
        # (including inactive / out-of-stock) so callers can choose how to display them.
        if hasattr(self._db, "get_store_offers"):
            raw = self._db.get_store_offers(store_id) or []
        else:
            raw = self._offer_repo.get_offers_by_store(store_id) or []
        return [self._to_offer_list_item(row) for row in raw]

    def list_active_offers_by_store(self, store_id: int) -> list[OfferListItem]:
        raw = self._db.get_active_offers(store_id=store_id) or []
        return [self._to_offer_list_item(row) for row in raw]

    def list_offers_by_category(
        self,
        city: str | None,
        category: str,
        limit: int = 20,
        offset: int = 0,
        region: str | None = None,
        district: str | None = None,
    ) -> list[OfferListItem]:
        raw: list[Any] = []
        scopes = self._build_location_scopes(city, region, district)
        for scope_city, scope_region, scope_district in scopes:
            raw = (
                self._db.get_offers_by_city_and_category(
                    city=scope_city,
                    category=category,
                    limit=limit,
                    offset=offset,
                    region=scope_region,
                    district=scope_district,
                )
                or []
            )
            if raw:
                break
        return [self._to_offer_list_item(row) for row in raw]

    def list_top_offers(
        self,
        city: str | None,
        limit: int = 20,
        offset: int = 0,
        region: str | None = None,
        district: str | None = None,
        sort_by: str | None = "discount",
    ) -> list[OfferListItem]:
        result = self.list_hot_offers(
            city=city,
            limit=limit,
            offset=offset,
            region=region,
            district=district,
            sort_by=sort_by,
        )
        return result.items

    def get_offer_details(self, offer_id: int) -> OfferDetails | None:
        offer = self._offer_repo.get_offer(offer_id)
        if not offer:
            return None
        base = self._to_offer_list_item(offer)
        store = self._store_repo.get_store(base.store_id) if base.store_id else None
        # Manually unpack fields from dataclass with slots=True (no __dict__)
        return OfferDetails(
            id=base.id,
            store_id=base.store_id,
            title=base.title,
            original_price=base.original_price,
            discount_price=base.discount_price,
            discount_percent=base.discount_percent,
            store_name=base.store_name,
            store_address=base.store_address,
            store_category=base.store_category,
            quantity=base.quantity,
            unit=base.unit,
            available_from=base.available_from,
            available_until=base.available_until,
            expiry_date=base.expiry_date,
            description=get_offer_field(offer, "description", ""),
            photo=get_offer_field(offer, "photo") or get_offer_field(offer, "photo_id"),
            category=get_offer_field(offer, "category", "other"),
            store_city=get_store_field(store, "city", "") if store else None,
            store_description=get_store_field(store, "description", "") if store else None,
            store_phone=get_store_field(store, "phone", "") if store else None,
            delivery_enabled=bool(get_store_field(store, "delivery_enabled", 0))
            if store
            else False,
            delivery_price=float(get_store_field(store, "delivery_price", 0) or 0)
            if store
            else 0.0,
            min_order_amount=float(get_store_field(store, "min_order_amount", 0) or 0)
            if store
            else 0.0,
        )

    def get_store_reviews(self, store_id: int) -> tuple[float, Sequence[Any]]:
        ratings = self._db.get_store_ratings(store_id) or []
        average = float(self._db.get_store_average_rating(store_id) or 0.0)
        return average, ratings

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _safe_float(value: Any, default: float = 0.0) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    def _to_offer_list_item(self, data: Any) -> OfferListItem:
        offer_id = int(get_offer_field(data, "offer_id", get_field(data, 0, 0)) or 0)
        store_id = int(get_offer_field(data, "store_id", get_field(data, 1, 0)) or 0)
        title = str(get_offer_field(data, "title", get_field(data, 2, "Товар")))
        original_price = self._safe_float(
            get_offer_field(data, "original_price", get_field(data, 4, 0))
        )
        discount_price = self._safe_float(
            get_offer_field(data, "discount_price", get_field(data, 5, 0))
        )
        quantity = get_offer_field(data, "quantity", get_field(data, 6, 0))
        available_from = get_offer_field(data, "available_from", get_field(data, 7, ""))
        available_until = get_offer_field(data, "available_until", get_field(data, 8, ""))
        expiry_date = get_offer_field(data, "expiry_date", get_field(data, 9, ""))
        store_name = str(get_field(data, "store_name", get_field(data, 14, "Магазин")))
        store_address = get_field(data, "address", get_field(data, 15, ""))
        store_category = get_field(data, "store_category", get_field(data, 17, ""))
        unit = get_offer_field(data, "unit", get_field(data, 13, "шт"))
        discount_percent_src = get_field(data, "discount_percent", get_field(data, 18, 0))
        discount_percent = self._safe_float(discount_percent_src, 0.0)
        # Safe discount calculation - handle edge cases
        if not discount_percent and original_price and original_price > discount_price:
            discount_percent = min(
                99.0, max(0.0, round((1 - (discount_price / original_price)) * 100, 1))
            )

        # Extract delivery info from joined store fields (indices 19, 20, 21)
        delivery_enabled = bool(get_field(data, "delivery_enabled", get_field(data, 19, 0)))
        delivery_price = self._safe_float(
            get_field(data, "delivery_price", get_field(data, 20, 0)), 0.0
        )
        min_order_amount = self._safe_float(
            get_field(data, "min_order_amount", get_field(data, 21, 0)), 0.0
        )

        # Try to get photo from 'photo' or 'photo_id'
        photo = get_offer_field(data, "photo")
        if not photo:
            photo = get_offer_field(data, "photo_id")
        # Fallback to index 8 if neither found (legacy tuple support)
        if not photo:
            photo = get_field(data, 8, None)

        # Get category field (index 12 in offers table)
        category = str(get_offer_field(data, "category", get_field(data, 12, "other")))

        return OfferListItem(
            id=offer_id,
            store_id=store_id,
            title=title,
            original_price=original_price,
            discount_price=discount_price,
            discount_percent=discount_percent,
            store_name=store_name,
            store_address=store_address,
            store_category=store_category,
            quantity=int(quantity or 0),
            unit=unit,
            available_from=str(available_from) if available_from else None,
            available_until=str(available_until) if available_until else None,
            expiry_date=expiry_date,
            delivery_enabled=delivery_enabled,
            delivery_price=delivery_price,
            min_order_amount=min_order_amount,
            photo=photo,
            category=category,
        )

    def _to_store_summary(self, store: Any) -> StoreSummary:
        store_id = int(get_store_field(store, "store_id", get_field(store, 0, 0)) or 0)
        name = get_store_field(store, "name", get_field(store, 2, "Магазин"))
        city = get_store_field(store, "city", get_field(store, 3, ""))
        address = get_store_field(store, "address", get_field(store, 4, ""))
        business_type = get_store_field(store, "business_type", get_field(store, 11, "supermarket"))
        offers_count = self._extract_offers_count(store)
        
        # Try to get pre-joined rating fields to avoid N+1
        rating = float(get_store_field(store, "avg_rating", get_field(store, "rating", 0.0)) or 0.0)
        ratings_count = int(get_store_field(store, "ratings_count", get_field(store, "total_ratings", 0)) or 0)
        
        # Fallback to DB queries only if not available in joined data
        if rating == 0.0:
            rating = float(self._db.get_store_average_rating(store_id) or 0.0)
        if ratings_count == 0:
            ratings = self._db.get_store_ratings(store_id) or []
            ratings_count = len(ratings)
            
        return StoreSummary(
            id=store_id,
            name=name,
            city=city,
            address=address,
            business_type=business_type,
            offers_count=offers_count,
            rating=rating,
            ratings_count=ratings_count,
        )

    def _extract_offers_count(self, store: Any) -> int:
        """Extract offers count, falling back to DB query if needed."""
        # First, try to get from the store object
        if isinstance(store, dict):
            value = store.get("offers_count", 0)
        else:
            value = store[-1] if isinstance(store, Sequence) and len(store) > 12 else 0

        try:
            count = int(value or 0)
        except (TypeError, ValueError):
            count = 0

        # If no count in store object, query DB for actual count
        if count == 0:
            store_id = int(get_store_field(store, "store_id", get_field(store, 0, 0)) or 0)
            if store_id and hasattr(self._db, "get_store_offers"):
                offers = self._db.get_store_offers(store_id) or []
                count = len(offers)

        return count

    def search_offers(
        self,
        query: str,
        city: str | None = None,
        region: str | None = None,
        district: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[OfferListItem]:
        """Search active offers by title or store name."""
        # This is a simplified search. Ideally, this should be done in the repository/DB layer.
        # For now, we'll fetch all active offers and filter in Python.
        # Optimization: Add search method to repository later.

        search_city = city or None

        # Fetch active offers directly from DB if possible, otherwise fallback to hot offers
        if hasattr(self._db, "search_offers"):
            raw_offers = self._db.search_offers(
                query,
                search_city,
                limit=limit,
                offset=offset,
                region=region,
                district=district,
            )
            return [self._to_offer_list_item(row) for row in raw_offers]

        result = self.list_hot_offers(
            city=search_city,
            limit=1000,
            region=region,
            district=district,
        )  # Fetch a reasonable amount
        all_offers = result.items
        query = query.lower()

        results = []
        for offer in all_offers:
            if (
                query in offer.title.lower()
                or query in offer.store_name.lower()
                or (offer.store_category and query in offer.store_category.lower())
            ):
                results.append(offer)

        return results

