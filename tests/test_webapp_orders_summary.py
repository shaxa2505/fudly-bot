from __future__ import annotations

import importlib
import os
import sys

import pytest
from fastapi import HTTPException


def _load_routes_orders():
    os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test-token")
    from app.api import rate_limit

    original_limit = rate_limit.limiter.limit
    rate_limit.limiter.limit = lambda *args, **kwargs: (lambda func: func)  # type: ignore[assignment]
    try:
        module_name = "app.api.webapp.routes_orders"
        sys.modules.pop(module_name, None)
        routes_orders = importlib.import_module(module_name)
    finally:
        rate_limit.limiter.limit = original_limit
    return routes_orders


class DummySummaryDb:
    def __init__(
        self,
        *,
        orders: tuple[int, float] = (0, 0.0),
        bookings: tuple[int, float] = (0, 0.0),
        archive: tuple[int, float] = (0, 0.0),
        archive_exists: bool = False,
    ) -> None:
        self._orders = orders
        self._bookings = bookings
        self._archive = archive
        self._archive_exists = archive_exists

    async def execute(self, query: str, params=None):  # noqa: ANN001 - test double
        normalized = " ".join(str(query).lower().split())
        if "to_regclass('public.bookings_archive')" in normalized:
            return [("bookings_archive",)] if self._archive_exists else [(None,)]
        if "from orders" in normalized:
            return [self._orders]
        if "from bookings_archive" in normalized:
            return [self._archive]
        if "from bookings" in normalized:
            return [self._bookings]
        return [(0, 0.0)]


@pytest.mark.asyncio
async def test_orders_summary_requires_authenticated_user():
    routes_orders = _load_routes_orders()
    db = DummySummaryDb()

    with pytest.raises(HTTPException) as exc:
        await routes_orders.get_orders_summary(db=db, user={"id": 0})

    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_orders_summary_aggregates_orders_and_bookings():
    routes_orders = _load_routes_orders()
    db = DummySummaryDb(
        orders=(3, 7.0),
        bookings=(2, 4.5),
        archive_exists=False,
    )

    result = await routes_orders.get_orders_summary(db=db, user={"id": 123})

    assert result.completed_orders == 5
    assert result.completed_quantity == 11.5
    assert result.saved_weight_kg is None


@pytest.mark.asyncio
async def test_orders_summary_includes_archive_when_available():
    routes_orders = _load_routes_orders()
    db = DummySummaryDb(
        orders=(1, 2.0),
        bookings=(1, 1.0),
        archive=(4, 8.0),
        archive_exists=True,
    )

    result = await routes_orders.get_orders_summary(db=db, user={"id": 456})

    assert result.completed_orders == 6
    assert result.completed_quantity == 11.0
    assert result.saved_weight_kg is None
