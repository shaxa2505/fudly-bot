from __future__ import annotations

import importlib
import os

import pytest


def _load_routes():
    os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test-token")
    from app.api.webapp import routes_search, routes_search_stats, routes_stores

    importlib.reload(routes_stores)
    importlib.reload(routes_search)
    importlib.reload(routes_search_stats)
    return routes_stores, routes_search, routes_search_stats


@pytest.mark.asyncio
async def test_get_stores_supports_sync_db_methods():
    routes_stores, _, _ = _load_routes()

    class SyncDb:
        def get_stores_by_city(self, city):
            return [
                {
                    "store_id": 1,
                    "name": "Test Store",
                    "city": city,
                    "address": "Address",
                    "avg_rating": 4.2,
                    "offers_count": 3,
                }
            ]

    result = await routes_stores.get_stores(
        city="Tashkent",
        region=None,
        district=None,
        lat=None,
        lon=None,
        latitude=None,
        longitude=None,
        business_type=None,
        resolve_coords=False,
        db=SyncDb(),
    )

    assert len(result) == 1
    assert result[0].id == 1
    assert result[0].name == "Test Store"
    assert result[0].city in ("Tashkent", "Ташкент")


@pytest.mark.asyncio
async def test_get_store_uses_sync_helpers_for_counts_and_rating():
    routes_stores, _, _ = _load_routes()

    class SyncDb:
        def get_store(self, store_id):
            return {"store_id": store_id, "name": "Store", "city": "Tashkent", "offers_count": 0}

        def get_store_offers(self, store_id):
            return [{"id": 1}, {"id": 2}]

        def get_store_average_rating(self, store_id):
            return 4.5

    result = await routes_stores.get_store(store_id=10, resolve_coords=False, db=SyncDb())

    assert result.id == 10
    assert result.offers_count == 2
    assert result.rating == 4.5


@pytest.mark.asyncio
async def test_search_routes_accept_sync_db():
    _, routes_search, _ = _load_routes()

    class SyncDb:
        def search_offers(self, query, **kwargs):
            return [
                {
                    "offer_id": 1,
                    "title": "Milk",
                    "store_id": 9,
                    "store_name": "Test",
                    "discount_price": 5000,
                    "original_price": 10000,
                }
            ]

        def search_stores(self, query, **kwargs):
            return [
                {
                    "store_id": 9,
                    "name": "Test",
                    "address": "Address",
                    "rating": 4.8,
                }
            ]

    result = await routes_search.search_all(
        query="milk",
        city=None,
        region=None,
        district=None,
        limit_offers=5,
        limit_stores=5,
        offset_offers=0,
        offset_stores=0,
        db=SyncDb(),
    )

    assert result.query == "milk"
    assert len(result.offers) == 1
    assert result.offers[0].title == "Milk"
    assert len(result.stores) == 1
    assert result.stores[0].name == "Test"


@pytest.mark.asyncio
async def test_search_suggestions_no_cache_with_sync_db(monkeypatch: pytest.MonkeyPatch):
    _, _, routes_search_stats = _load_routes()
    monkeypatch.setenv("WEBAPP_CACHE_SUGGESTIONS_TTL", "0")

    class SyncDb:
        def get_search_suggestions(self, query, **kwargs):
            return ["milk", "milky"]

    result = await routes_search_stats.get_search_suggestions(
        query="mi",
        limit=5,
        city=None,
        region=None,
        district=None,
        db=SyncDb(),
    )

    assert result == ["milk", "milky"]
