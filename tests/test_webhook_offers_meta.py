import json

import pytest
from aiohttp.test_utils import make_mocked_request

from app.core.webhook_offers_routes import build_offer_store_handlers


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


class DummyWebhookOffersDb:
    def __init__(self, nearby_by_radius=None, scoped_by_scope=None, nearby_total=0, scoped_total=0):
        self._nearby_by_radius = nearby_by_radius or {}
        self._scoped_by_scope = scoped_by_scope or {}
        self._nearby_total = nearby_total
        self._scoped_total = scoped_total
        self.count_scope_calls = []

    def get_nearby_offers(
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
        rounded = round(float(max_distance_km or 0), 1)
        return list(self._nearby_by_radius.get(rounded, []))

    def get_hot_offers(
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
    ):
        return list(self._scoped_by_scope.get((city, region, district), []))

    def count_nearby_offers(
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

    def count_offers_by_filters(
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
        self.count_scope_calls.append((city, region, district))
        return self._scoped_total


@pytest.mark.asyncio
async def test_webhook_offers_meta_uses_nearby_total_when_available():
    db = DummyWebhookOffersDb(
        nearby_by_radius={
            3.0: [],
            7.0: [_sample_offer(2)],
        },
        nearby_total=4,
    )
    api_offers, _, _, _, _ = build_offer_store_handlers(bot=None, db=db)
    request = make_mocked_request(
        "GET",
        "/api/v1/offers?city=%D0%A2%D0%B0%D1%88%D0%BA%D0%B5%D0%BD%D1%82&lat=41.3&lon=69.2&include_meta=true&limit=1",
    )
    response = await api_offers(request)
    payload = json.loads(response.text)

    assert payload["location_strategy"] == "nearby"
    assert payload["used_radius_km"] == 7.0
    assert payload["total"] == 4
    assert payload["has_more"] is True
    assert payload["next_offset"] == 1
    assert db.count_scope_calls == []


@pytest.mark.asyncio
async def test_webhook_offers_meta_scope_fallback_uses_scope_total():
    db = DummyWebhookOffersDb(
        nearby_by_radius={
            3.0: [],
            7.0: [],
            15.0: [],
            25.0: [],
        },
        scoped_by_scope={
            ("Ташкент", None, None): [_sample_offer(1)],
        },
        scoped_total=3,
    )
    api_offers, _, _, _, _ = build_offer_store_handlers(bot=None, db=db)
    request = make_mocked_request(
        "GET",
        "/api/v1/offers?city=%D0%A2%D0%B0%D1%88%D0%BA%D0%B5%D0%BD%D1%82&lat=41.3&lon=69.2&include_meta=true&limit=1",
    )
    response = await api_offers(request)
    payload = json.loads(response.text)

    assert payload["location_strategy"] == "scope"
    assert payload["used_fallback"] is True
    assert payload["total"] == 3
    assert payload["has_more"] is True
    assert payload["next_offset"] == 1
    assert db.count_scope_calls == [("Ташкент", None, None)]
