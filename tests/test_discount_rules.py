from __future__ import annotations

import pytest

from handlers.seller.create_offer import _parse_discount_value


def test_discount_percent_below_min_rejected():
    with pytest.raises(ValueError):
        _parse_discount_value(10000.0, "10%")


def test_discount_percent_min_accepted():
    percent, price = _parse_discount_value(10000.0, "20%")
    assert percent == 20
    assert int(price) == 8000


def test_discount_price_below_min_percent_rejected():
    # 10000 -> 9000 = 10% discount
    with pytest.raises(ValueError):
        _parse_discount_value(10000.0, "9000")


def test_discount_price_small_value_is_treated_as_price():
    percent, price = _parse_discount_value(10000.0, "10")
    assert percent >= 20
    assert int(price) == 10


def test_discount_price_valid_high_discount():
    percent, price = _parse_discount_value(10000.0, "2000")
    assert percent >= 20
    assert int(price) == 2000
