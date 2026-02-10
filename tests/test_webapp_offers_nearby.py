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
    def __init__(self, hot_offers, nearby_offers):
        self._hot_offers = hot_offers
        self._nearby_offers = nearby_offers

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
        return list(self._nearby_offers)


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
async def test_city_scoped_offers_preferred_over_nearby():
    db = DummyOffersDb(hot_offers=[_sample_offer(1)], nearby_offers=[_sample_offer(2)])
    get_offers = _get_offers()
    result = await _call_offers(get_offers, db, city="Tashkent", lat=41.3, lon=69.2)

    assert [item.id for item in result] == [1]


@pytest.mark.asyncio
async def test_nearby_used_when_no_city_offers():
    db = DummyOffersDb(hot_offers=[], nearby_offers=[_sample_offer(2)])
    get_offers = _get_offers()
    result = await _call_offers(get_offers, db, city="Tashkent", lat=41.3, lon=69.2)

    assert [item.id for item in result] == [2]
