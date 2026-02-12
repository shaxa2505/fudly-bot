from __future__ import annotations

from datetime import date, timedelta

import pytest
from pydantic import ValidationError

from app.domain.models.offer import OfferCreate, OfferUpdate
from app.domain.offer_rules import MIN_OFFER_DISCOUNT_MESSAGE, validate_offer_prices


def _offer_payload(*, original_price: int, discount_price: int) -> dict:
    return {
        "store_id": 1,
        "title": "Test offer",
        "description": "desc",
        "original_price": original_price,
        "discount_price": discount_price,
        "quantity": 1,
        "unit": "piece",
        "category": "other",
        "available_from": "08:00",
        "available_until": "10:00",
        "expiry_date": date.today() + timedelta(days=1),
        "status": "active",
    }


def test_discount_validation_accepts_20_percent() -> None:
    validate_offer_prices(100, 80, require_both=True)


def test_discount_validation_accepts_above_20_percent() -> None:
    validate_offer_prices(100, 79, require_both=True)


@pytest.mark.parametrize(
    ("original_price", "discount_price"),
    [
        (100, 81),     # 19%
        (100, 80.01),  # 19.99%, strict logic without rounding-up
    ],
)
def test_discount_validation_rejects_below_20_percent(
    original_price: float, discount_price: float
) -> None:
    with pytest.raises(ValueError, match=MIN_OFFER_DISCOUNT_MESSAGE):
        validate_offer_prices(original_price, discount_price, require_both=True)


@pytest.mark.parametrize(
    ("original_price", "discount_price"),
    [
        (0, 0),
        (100, 100),
    ],
)
def test_discount_validation_rejects_invalid_prices(original_price: int, discount_price: int) -> None:
    with pytest.raises(ValueError):
        validate_offer_prices(original_price, discount_price, require_both=True)


def test_offer_create_rejects_discount_below_20_percent() -> None:
    with pytest.raises(ValidationError):
        OfferCreate(**_offer_payload(original_price=100, discount_price=81))


def test_offer_create_accepts_exact_20_percent() -> None:
    model = OfferCreate(**_offer_payload(original_price=100, discount_price=80))
    assert model.discount_price == 80


def test_offer_update_rejects_invalid_pair() -> None:
    with pytest.raises(ValidationError):
        OfferUpdate(original_price=100, discount_price=81)


def test_offer_update_allows_partial_price_update() -> None:
    model = OfferUpdate(original_price=100)
    assert model.original_price == 100
    assert model.discount_price is None

