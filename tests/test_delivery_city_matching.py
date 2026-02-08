import os

import pytest

os.environ.setdefault("TELEGRAM_BOT_TOKEN", "TEST_TOKEN")
os.environ.setdefault("ADMIN_ID", "1")

from app.api.orders import calculate_delivery_cost


class DummyDB:
    def __init__(self, store: dict):
        self._store = store

    async def get_store(self, _store_id: int):
        return self._store


@pytest.mark.asyncio
async def test_delivery_allows_store_district_match():
    store = {
        "store_id": 1,
        "city": "Samarkand",
        "region": "Samarkand",
        "district": "Kattakurgan",
        "delivery_price": 10000,
        "min_order_amount": 30000,
    }

    result = await calculate_delivery_cost(
        "Kattaqo'rg'on shahri",
        "Some address",
        1,
        DummyDB(store),
    )

    assert result.can_deliver is True
    assert result.delivery_cost == 10000.0
    assert result.min_order_amount == 30000.0


@pytest.mark.asyncio
async def test_delivery_blocks_unrelated_city():
    store = {
        "store_id": 1,
        "city": "Samarkand",
        "region": "Samarkand",
        "district": "Kattakurgan",
        "delivery_price": 10000,
        "min_order_amount": 30000,
    }

    result = await calculate_delivery_cost(
        "Tashkent",
        "Some address",
        1,
        DummyDB(store),
    )

    assert result.can_deliver is False
    assert "Samarkand" in (result.message or "")
