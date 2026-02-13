from __future__ import annotations

from datetime import time as dt_time

from handlers.seller.create_offer import _resolve_offer_default_times


def test_resolve_offer_default_times_uses_store_working_hours() -> None:
    start, end = _resolve_offer_default_times({"working_hours": "10:00 - 23:00"})
    assert start == dt_time(hour=10, minute=0)
    assert end == dt_time(hour=23, minute=0)


def test_resolve_offer_default_times_uses_open_close_fallback() -> None:
    start, end = _resolve_offer_default_times({"open_time": "09:30", "close_time": "21:15"})
    assert start == dt_time(hour=9, minute=30)
    assert end == dt_time(hour=21, minute=15)


def test_resolve_offer_default_times_falls_back_to_global_default() -> None:
    start, end = _resolve_offer_default_times({"working_hours": "invalid"})
    assert start == dt_time(hour=8, minute=0)
    assert end == dt_time(hour=23, minute=0)
