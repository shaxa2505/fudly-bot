import importlib
import os

import pytest


def _get_categories():
    os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test-token")
    from app.api.webapp import routes_offers

    importlib.reload(routes_offers)
    return routes_offers.get_categories


class DummyCategoriesDb:
    def __init__(self, nearby_by_radius=None, scoped_by_scope=None):
        self._nearby_by_radius = nearby_by_radius or {}
        self._scoped_by_scope = scoped_by_scope or {}
        self.nearby_calls = []
        self.scope_calls = []

    async def count_nearby_offers_by_category_grouped(
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

    async def count_offers_by_category_grouped(self, city=None, region=None, district=None):
        scope = (city, region, district)
        self.scope_calls.append(scope)
        return dict(self._scoped_by_scope.get(scope, {}))


def _counts_map(items):
    return {item.id: item.count for item in items}


async def _call_categories(get_categories, db, **overrides):
    params = {
        "city": None,
        "region": None,
        "district": None,
        "lat": None,
        "lon": None,
        "latitude": None,
        "longitude": None,
        "max_distance_km": None,
    }
    params.update(overrides)
    return await get_categories(db=db, **params)


@pytest.mark.asyncio
async def test_categories_use_nearby_counts_with_radius_expansion():
    db = DummyCategoriesDb(
        nearby_by_radius={
            3.0: {},
            7.0: {"dairy": 2, "meat": 1},
        },
        scoped_by_scope={
            ("Ташкент", None, None): {"bakery": 99},
        },
    )
    get_categories = _get_categories()
    result = await _call_categories(get_categories, db, city="Ташкент", lat=41.3, lon=69.2)

    counts = _counts_map(result)
    assert counts["all"] == 3
    assert counts["dairy"] == 2
    assert counts["meat"] == 1
    assert db.nearby_calls == [3.0, 7.0]
    assert db.scope_calls == []


@pytest.mark.asyncio
async def test_categories_fall_back_to_scope_when_nearby_empty():
    db = DummyCategoriesDb(
        nearby_by_radius={
            3.0: {},
            7.0: {},
            15.0: {},
            25.0: {},
        },
        scoped_by_scope={
            ("Ташкент", None, None): {"bakery": 4},
        },
    )
    get_categories = _get_categories()
    result = await _call_categories(get_categories, db, city="Ташкент", lat=41.3, lon=69.2)

    counts = _counts_map(result)
    assert counts["all"] == 4
    assert counts["bakery"] == 4
    assert db.nearby_calls == [3.0, 7.0, 15.0, 25.0]
    assert db.scope_calls[0] == ("Ташкент", None, None)


@pytest.mark.asyncio
async def test_categories_respect_explicit_max_distance():
    db = DummyCategoriesDb(
        nearby_by_radius={
            12.5: {"drinks": 2},
        },
    )
    get_categories = _get_categories()
    result = await _call_categories(
        get_categories,
        db,
        city="Ташкент",
        lat=41.3,
        lon=69.2,
        max_distance_km=12.5,
    )

    counts = _counts_map(result)
    assert counts["all"] == 2
    assert counts["drinks"] == 2
    assert db.nearby_calls == [12.5]
