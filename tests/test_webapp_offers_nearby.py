import importlib
import os

import pytest
from starlette.requests import Request


def _get_offers():
    os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test-token")
    from app.api.webapp import routes_offers

    importlib.reload(routes_offers)
    return routes_offers.get_offers


class DummyOffersDb:
    def __init__(self, hot_offers, nearby_offers, nearby_by_radius=None):
        self._hot_offers = hot_offers
        self._nearby_offers = nearby_offers
        self._nearby_by_radius = nearby_by_radius or {}
        self.nearby_calls = []

    async def get_hot_offers(
        self,
        city=None,
        limit=20,
        offset=0,
        region=None,
        district=None,
        sort_by=None,
        min_price=None,
        max_price=None,
        min_discount=None,
        category=None,
        store_id=None,
        only_today=False,
        latitude=None,
        longitude=None,
    ):
        return list(self._hot_offers)

    async def get_nearby_offers(
        self,
        latitude,
        longitude,
        limit=20,
        offset=0,
        category=None,
        sort_by=None,
        min_price=None,
        max_price=None,
        min_discount=None,
        max_distance_km=None,
        store_id=None,
        only_today=False,
    ):
        self.nearby_calls.append(max_distance_km)
        if self._nearby_by_radius:
            rounded = round(float(max_distance_km or 0), 1)
            return list(self._nearby_by_radius.get(rounded, []))
        return list(self._nearby_offers)

    async def count_offers_by_filters(
        self,
        city=None,
        region=None,
        district=None,
        category=None,
        min_price=None,
        max_price=None,
        min_discount=None,
        store_id=None,
        only_today=False,
    ):
        return len(self._hot_offers)


class DummyOffersDbWithNearbyCount(DummyOffersDb):
    def __init__(self, hot_offers, nearby_offers, nearby_total, nearby_by_radius=None):
        super().__init__(hot_offers, nearby_offers, nearby_by_radius=nearby_by_radius)
        self._nearby_total = nearby_total

    async def count_nearby_offers(
        self,
        latitude,
        longitude,
        category=None,
        business_type=None,
        max_distance_km=None,
        min_price=None,
        max_price=None,
        min_discount=None,
        store_id=None,
        only_today=False,
    ):
        return self._nearby_total


def _sample_offer(offer_id):
    return {
        "offer_id": offer_id,
        "store_id": 1,
        "title": f"Offer {offer_id}",
        "original_price": 10000,
        "discount_price": 8000,
        "quantity": 1,
        "category": "other",
    }


async def _call_offers(get_offers, db, **overrides):
    params = {
        "request": Request(
            {
                "type": "http",
                "method": "GET",
                "path": "/offers",
                "headers": [],
                "client": ("127.0.0.1", 1234),
            }
        ),
        "city": None,
        "region": None,
        "district": None,
        "lat": None,
        "lon": None,
        "latitude": None,
        "longitude": None,
        "max_distance_km": None,
        "category": "all",
        "store_id": None,
        "search": None,
        "min_price": None,
        "max_price": None,
        "min_discount": None,
        "sort_by": None,
        "limit": 50,
        "offset": 0,
        "include_meta": False,
    }
    params.update(overrides)
    return await get_offers(db=db, **params)


@pytest.mark.asyncio
async def test_nearby_preferred_over_city_when_coordinates_present():
    db = DummyOffersDb(hot_offers=[_sample_offer(1)], nearby_offers=[_sample_offer(2)])
    get_offers = _get_offers()
    result = await _call_offers(get_offers, db, city="Tashkent", lat=41.3, lon=69.2)

    assert [item.id for item in result] == [2]


@pytest.mark.asyncio
async def test_nearby_used_when_no_city_offers():
    db = DummyOffersDb(hot_offers=[], nearby_offers=[_sample_offer(2)])
    get_offers = _get_offers()
    result = await _call_offers(get_offers, db, city="Tashkent", lat=41.3, lon=69.2)

    assert [item.id for item in result] == [2]


@pytest.mark.asyncio
async def test_nearby_radius_expands_until_results():
    db = DummyOffersDb(
        hot_offers=[_sample_offer(1)],
        nearby_offers=[],
        nearby_by_radius={
            3.0: [],
            7.0: [_sample_offer(2)],
        },
    )
    get_offers = _get_offers()
    result = await _call_offers(get_offers, db, city="Tashkent", lat=41.3, lon=69.2)

    assert [item.id for item in result] == [2]
    assert db.nearby_calls == [3.0, 7.0]


@pytest.mark.asyncio
async def test_scoped_fallback_used_if_nearby_empty():
    db = DummyOffersDb(
        hot_offers=[_sample_offer(1)],
        nearby_offers=[],
        nearby_by_radius={
            3.0: [],
            7.0: [],
            15.0: [],
            25.0: [],
        },
    )
    get_offers = _get_offers()
    result = await _call_offers(get_offers, db, city="Tashkent", lat=41.3, lon=69.2)

    assert [item.id for item in result] == [1]
    assert db.nearby_calls == [3.0, 7.0, 15.0, 25.0]


@pytest.mark.asyncio
async def test_meta_reports_nearby_strategy_and_radius():
    db = DummyOffersDb(
        hot_offers=[_sample_offer(1)],
        nearby_offers=[],
        nearby_by_radius={
            3.0: [],
            7.0: [_sample_offer(2)],
        },
    )
    get_offers = _get_offers()
    result = await _call_offers(
        get_offers,
        db,
        city="Tashkent",
        lat=41.3,
        lon=69.2,
        include_meta=True,
    )

    assert [item.id for item in result.items] == [2]
    assert result.location_strategy == "nearby"
    assert result.used_radius_km == 7.0
    assert result.used_fallback is False
    assert result.total is None


@pytest.mark.asyncio
async def test_meta_reports_scope_fallback_when_nearby_empty():
    db = DummyOffersDb(
        hot_offers=[_sample_offer(1)],
        nearby_offers=[],
        nearby_by_radius={
            3.0: [],
            7.0: [],
            15.0: [],
            25.0: [],
        },
    )
    get_offers = _get_offers()
    result = await _call_offers(
        get_offers,
        db,
        city="Tashkent",
        lat=41.3,
        lon=69.2,
        include_meta=True,
    )

    assert [item.id for item in result.items] == [1]
    assert result.location_strategy == "scope"
    assert result.used_radius_km is None
    assert result.used_fallback is True
    assert result.total == 1


@pytest.mark.asyncio
async def test_meta_reports_scope_total_without_coordinates():
    db = DummyOffersDb(hot_offers=[_sample_offer(1)], nearby_offers=[])
    get_offers = _get_offers()
    result = await _call_offers(
        get_offers,
        db,
        city="Tashkent",
        include_meta=True,
    )

    assert [item.id for item in result.items] == [1]
    assert result.location_strategy == "scope"
    assert result.used_fallback is False
    assert result.total == 1


@pytest.mark.asyncio
async def test_meta_reports_nearby_total_when_counter_supported():
    db = DummyOffersDbWithNearbyCount(
        hot_offers=[],
        nearby_offers=[],
        nearby_total=3,
        nearby_by_radius={
            3.0: [],
            7.0: [_sample_offer(2)],
        },
    )
    get_offers = _get_offers()
    result = await _call_offers(
        get_offers,
        db,
        city="Tashkent",
        lat=41.3,
        lon=69.2,
        include_meta=True,
        limit=1,
    )

    assert [item.id for item in result.items] == [2]
    assert result.location_strategy == "nearby"
    assert result.used_radius_km == 7.0
    assert result.total == 3
    assert result.has_more is True
    assert result.next_offset == 1
