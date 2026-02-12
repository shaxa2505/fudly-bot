import json

import pytest
from aiohttp.test_utils import make_mocked_request

from app.core.webhook_discovery_routes import build_discovery_handlers


class DummyWebhookCategoriesDb:
    def __init__(self, nearby_by_radius=None, scoped_by_scope=None):
        self._nearby_by_radius = nearby_by_radius or {}
        self._scoped_by_scope = scoped_by_scope or {}
        self.nearby_calls = []
        self.scope_calls = []

    def count_nearby_offers_by_category_grouped(
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
        self.nearby_calls.append(max_distance_km)
        rounded = round(float(max_distance_km or 0), 1)
        return dict(self._nearby_by_radius.get(rounded, {}))

    def count_offers_by_category_grouped(self, city=None, region=None, district=None):
        scope = (city, region, district)
        self.scope_calls.append(scope)
        return dict(self._scoped_by_scope.get(scope, {}))


def _payload_to_counts(payload):
    return {item["id"]: item["count"] for item in payload}


@pytest.mark.asyncio
async def test_webhook_categories_use_nearby_strategy():
    db = DummyWebhookCategoriesDb(
        nearby_by_radius={
            3.0: {},
            7.0: {"dairy": 3, "drinks": 1},
        },
        scoped_by_scope={("Ташкент", None, None): {"bakery": 9}},
    )
    api_categories, _, _ = build_discovery_handlers(db)
    request = make_mocked_request("GET", "/api/v1/categories?city=%D0%A2%D0%B0%D1%88%D0%BA%D0%B5%D0%BD%D1%82&lat=41.3&lon=69.2")
    response = await api_categories(request)
    payload = json.loads(response.text)

    counts = _payload_to_counts(payload)
    assert counts["all"] == 4
    assert counts["dairy"] == 3
    assert counts["drinks"] == 1
    assert db.nearby_calls == [3.0, 7.0]
    assert db.scope_calls == []


@pytest.mark.asyncio
async def test_webhook_categories_fallback_to_scope_when_nearby_empty():
    db = DummyWebhookCategoriesDb(
        nearby_by_radius={
            3.0: {},
            7.0: {},
            15.0: {},
            25.0: {},
        },
        scoped_by_scope={("Ташкент", None, None): {"bakery": 5}},
    )
    api_categories, _, _ = build_discovery_handlers(db)
    request = make_mocked_request("GET", "/api/v1/categories?city=%D0%A2%D0%B0%D1%88%D0%BA%D0%B5%D0%BD%D1%82&lat=41.3&lon=69.2")
    response = await api_categories(request)
    payload = json.loads(response.text)

    counts = _payload_to_counts(payload)
    assert counts["all"] == 5
    assert counts["bakery"] == 5
    assert db.nearby_calls == [3.0, 7.0, 15.0, 25.0]
    assert db.scope_calls[0] == ("Ташкент", None, None)
