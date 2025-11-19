"""Offer-related domain services and data transfer objects."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, List, Sequence

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
    expiry_date: str | None = None
    delivery_enabled: bool = False
    delivery_price: float = 0.0
    min_order_amount: float = 0.0
    photo: str | None = None


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
    items: List[OfferListItem]
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
    def list_hot_offers(self, city: str, limit: int = 20, offset: int = 0) -> OfferListResult:
        """Return cached hot offers plus total count for pagination."""
        raw_offers = (
            self._cache.get_hot_offers(city, limit, offset)
            if self._cache and offset == 0
            else self._db.get_hot_offers(city, limit=limit, offset=offset)
        )
        items = [self._to_offer_list_item(row) for row in raw_offers]
        total = int(self._db.count_hot_offers(city))
        return OfferListResult(items=items, total=total)

    # ------------------------------------------------------------------
    # Stores filtering
    # ------------------------------------------------------------------
    def list_stores_by_type(self, city: str, business_type: str) -> List[StoreSummary]:
        """Return stores for a business type with cached fallback."""
        normalized = self._map_business_type(business_type)
        if business_type == "delivery":
            raw_stores = self._fetch_delivery_enabled_stores(city, normalized)
        elif self._cache:
            raw_stores = self._cache.get_stores_by_type(city, normalized)
        else:
            raw_stores = self._db.get_stores_by_business_type(normalized, city)
        return [self._to_store_summary(store) for store in raw_stores]

    def _fetch_delivery_enabled_stores(self, city: str, normalized: str) -> List[Any]:
        stores: List[Any] = []
        if hasattr(self._db, "get_stores_with_delivery"):
            stores = self._db.get_stores_with_delivery(city) or []
        if not stores:
            raw = self._db.get_stores_by_business_type(normalized, city)
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

    def list_store_offers(self, store_id: int) -> List[OfferListItem]:
        raw = self._offer_repo.get_offers_by_store(store_id) or []
        return [self._to_offer_list_item(row) for row in raw]

    def list_active_offers_by_store(self, store_id: int) -> List[OfferListItem]:
        raw = self._db.get_active_offers(store_id=store_id) or []
        return [self._to_offer_list_item(row) for row in raw]

    def list_offers_by_category(self, city: str, category: str, limit: int = 20) -> List[OfferListItem]:
        raw = self._db.get_offers_by_city_and_category(city, category, limit=limit) or []
        return [self._to_offer_list_item(row) for row in raw]

    def list_top_offers(self, city: str, limit: int = 20) -> List[OfferListItem]:
        raw = self._db.get_top_offers_by_city(city, limit=limit) or []
        return [self._to_offer_list_item(row) for row in raw]

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
            expiry_date=base.expiry_date,
            description=get_offer_field(offer, "description", ""),
            photo=get_offer_field(offer, "photo") or get_offer_field(offer, "photo_id"),
            category=get_offer_field(offer, "category", "other"),
            store_city=get_store_field(store, "city", "") if store else None,
            store_description=get_store_field(store, "description", "") if store else None,
            store_phone=get_store_field(store, "phone", "") if store else None,
            delivery_enabled=bool(get_store_field(store, "delivery_enabled", 0)) if store else False,
            delivery_price=float(get_store_field(store, "delivery_price", 0) or 0) if store else 0.0,
            min_order_amount=float(get_store_field(store, "min_order_amount", 0) or 0) if store else 0.0,
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
        original_price = self._safe_float(get_offer_field(data, "original_price", get_field(data, 4, 0)))
        discount_price = self._safe_float(get_offer_field(data, "discount_price", get_field(data, 5, 0)))
        quantity = get_offer_field(data, "quantity", get_field(data, 6, 0))
        expiry_date = get_offer_field(data, "expiry_date", get_field(data, 9, ""))
        store_name = str(get_field(data, "store_name", get_field(data, 14, "Магазин")))
        store_address = get_field(data, "address", get_field(data, 15, ""))
        store_category = get_field(data, "store_category", get_field(data, 17, ""))
        unit = get_offer_field(data, "unit", get_field(data, 13, "шт"))
        discount_percent_src = get_field(data, "discount_percent", get_field(data, 18, 0))
        discount_percent = self._safe_float(discount_percent_src, 0.0)
        if not discount_percent and original_price:
            discount_percent = max(0.0, round((1 - (discount_price / original_price)) * 100, 1))
        
        # Extract delivery info from joined store fields (indices 19, 20, 21)
        delivery_enabled = bool(get_field(data, "delivery_enabled", get_field(data, 19, 0)))
        delivery_price = self._safe_float(get_field(data, "delivery_price", get_field(data, 20, 0)), 0.0)
        min_order_amount = self._safe_float(get_field(data, "min_order_amount", get_field(data, 21, 0)), 0.0)
        
        photo = get_offer_field(data, "photo", get_field(data, 8, None))
        
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
            expiry_date=expiry_date,
            delivery_enabled=delivery_enabled,
            delivery_price=delivery_price,
            min_order_amount=min_order_amount,
            photo=photo,
        )

    def _to_store_summary(self, store: Any) -> StoreSummary:
        store_id = int(get_store_field(store, "store_id", get_field(store, 0, 0)) or 0)
        name = get_store_field(store, "name", get_field(store, 2, "Магазин"))
        city = get_store_field(store, "city", get_field(store, 3, ""))
        address = get_store_field(store, "address", get_field(store, 4, ""))
        business_type = get_store_field(store, "business_type", get_field(store, 11, "supermarket"))
        offers_count = self._extract_offers_count(store)
        rating = float(self._db.get_store_average_rating(store_id) or 0.0)
        ratings = self._db.get_store_ratings(store_id) or []
        return StoreSummary(
            id=store_id,
            name=name,
            city=city,
            address=address,
            business_type=business_type,
            offers_count=offers_count,
            rating=rating,
            ratings_count=len(ratings),
        )

    @staticmethod
    def _extract_offers_count(store: Any) -> int:
        if isinstance(store, dict):
            value = store.get("offers_count", 0)
        else:
            value = store[-1] if isinstance(store, Sequence) and len(store) > 12 else 0
        try:
            return int(value or 0)
        except (TypeError, ValueError):
            return 0

    def search_offers(self, query: str, city: str | None = None) -> List[OfferListItem]:
        """Search active offers by title or store name."""
        # This is a simplified search. Ideally, this should be done in the repository/DB layer.
        # For now, we'll fetch all active offers and filter in Python.
        # Optimization: Add search method to repository later.
        
        # Use a default city if None, or handle it in list_hot_offers
        search_city = city or "Ташкент" 
        
        # Fetch active offers directly from DB if possible, otherwise fallback to hot offers
        if hasattr(self._db, "search_offers"):
             raw_offers = self._db.search_offers(query, search_city)
             return [self._to_offer_list_item(row) for row in raw_offers]

        result = self.list_hot_offers(city=search_city, limit=1000) # Fetch a reasonable amount
        all_offers = result.items
        query = query.lower()
        
        results = []
        for offer in all_offers:
            if (query in offer.title.lower() or 
                query in offer.store_name.lower() or 
                (offer.store_category and query in offer.store_category.lower())):
                results.append(offer)
                
        return results
