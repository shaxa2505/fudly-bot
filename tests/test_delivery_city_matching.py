import os

import pytest

os.environ.setdefault("TELEGRAM_BOT_TOKEN", "TEST_TOKEN")
os.environ.setdefault("ADMIN_ID", "1")

from app.api.orders import calculate_delivery_cost
from app.core.constants import MAX_DELIVERY_RADIUS_KM


class DummyDB:
    def __init__(self, store: dict):
        self._store = store

    async def get_store(self, _store_id: int):
        return self._store


@pytest.mark.asyncio
async def test_delivery_requires_coordinates():
    store = {
        "store_id": 1,
        "city": "Samarkand",
        "region": "Samarkand",
        "district": "Kattakurgan",
        "delivery_price": 10000,
        "min_order_amount": 30000,
        "latitude": 39.654,
        "longitude": 66.975,
    }

    result = await calculate_delivery_cost(
        "Samarkand",
        "Some address",
        1,
        DummyDB(store),
    )

    assert result.can_deliver is False
    assert "xaritada" in (result.message or "").lower()


@pytest.mark.asyncio
async def test_delivery_clamps_radius_to_max():
    store = {
        "store_id": 1,
        "city": "Samarkand",
        "region": "Samarkand",
        "district": "Kattakurgan",
        "delivery_price": 10000,
        "min_order_amount": 30000,
        "latitude": 0.0,
        "longitude": 0.0,
        "delivery_radius_km": 1000,
    }

    result = await calculate_delivery_cost(
        "Samarkand",
        "Some address",
        1,
        DummyDB(store),
        delivery_lat=1.2,
        delivery_lon=0.0,
    )

    assert result.can_deliver is False
    assert f"radiusi {MAX_DELIVERY_RADIUS_KM} km" in (result.message or "").lower()


@pytest.mark.asyncio
async def test_delivery_keeps_custom_radius_when_within_max():
    store = {
        "store_id": 1,
        "city": "Samarkand",
        "region": "Samarkand",
        "district": "Kattakurgan",
        "delivery_price": 10000,
        "min_order_amount": 30000,
        "latitude": 0.0,
        "longitude": 0.0,
        "delivery_radius_km": 15,
    }

    result = await calculate_delivery_cost(
        "Samarkand",
        "Some address",
        1,
        DummyDB(store),
        delivery_lat=0.2,
        delivery_lon=0.0,
    )

    assert result.can_deliver is False
    assert "radiusi 15 km" in (result.message or "").lower()
