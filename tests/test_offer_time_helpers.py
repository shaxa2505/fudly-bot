from __future__ import annotations

import os
from datetime import datetime, timezone

os.environ.setdefault("TELEGRAM_BOT_TOKEN", "TEST_TOKEN")

from app.api.webapp.common import is_offer_active, is_offer_available_now, is_store_open_now


def _dt(hour: int, minute: int = 0) -> datetime:
    return datetime(2024, 1, 1, hour, minute, tzinfo=timezone.utc)


def test_is_offer_available_now_within_window():
    offer = {"available_from": "10:00", "available_until": "12:00"}
    assert is_offer_available_now(offer, now=_dt(10, 30)) is True
    assert is_offer_available_now(offer, now=_dt(12, 0)) is True
    assert is_offer_available_now(offer, now=_dt(9, 59)) is False


def test_is_offer_available_now_cross_midnight():
    offer = {"available_from": "22:00", "available_until": "03:00"}
    assert is_offer_available_now(offer, now=_dt(23, 0)) is True
    assert is_offer_available_now(offer, now=_dt(1, 0)) is True
    assert is_offer_available_now(offer, now=_dt(21, 0)) is False


def test_is_store_open_now_basic_window():
    store = {"working_hours": "08:00 - 23:00"}
    assert is_store_open_now(store, now=_dt(8, 0)) is True
    assert is_store_open_now(store, now=_dt(23, 0)) is True
    assert is_store_open_now(store, now=_dt(7, 59)) is False


def test_is_store_open_now_cross_midnight():
    store = {"working_hours": "22:00 - 03:00"}
    assert is_store_open_now(store, now=_dt(23, 0)) is True
    assert is_store_open_now(store, now=_dt(2, 0)) is True
    assert is_store_open_now(store, now=_dt(21, 0)) is False


def test_is_offer_active_status_quantity_expiry():
    assert is_offer_active({"status": "active", "quantity": 1}) is True
    assert is_offer_active({"status": "inactive", "quantity": 1}) is False
    assert is_offer_active({"status": "active", "quantity": 0}) is False
    assert is_offer_active({"status": "active", "quantity": 1, "expiry_date": "2000-01-01"}) is False
