"""Offer pricing business rules shared across layers."""
from __future__ import annotations

from decimal import Decimal, InvalidOperation


MIN_OFFER_DISCOUNT_PERCENT = 20
MIN_OFFER_DISCOUNT_MESSAGE = (
    "Минимальная скидка — 20%. Укажите цену со скидкой ниже на 20% или больше."
)
INVALID_OFFER_PRICE_MESSAGE = "Цена должна быть больше 0."
DISCOUNT_MUST_BE_LOWER_MESSAGE = "Цена со скидкой должна быть меньше обычной цены."


def _to_decimal(value: int | float | str, field_name: str) -> Decimal:
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError(f"Некорректное значение поля {field_name}.") from exc


def is_min_discount_reached(
    original_price: int | float | str,
    discount_price: int | float | str,
    *,
    min_discount_percent: int = MIN_OFFER_DISCOUNT_PERCENT,
) -> bool:
    """Return True when discount is >= min_discount_percent using strict math."""
    original = _to_decimal(original_price, "original_price")
    discount = _to_decimal(discount_price, "discount_price")
    threshold = Decimal(100 - min_discount_percent)
    return discount * Decimal(100) <= original * threshold


def validate_offer_prices(
    original_price: int | float | str | None,
    discount_price: int | float | str | None,
    *,
    require_both: bool = True,
    min_discount_percent: int = MIN_OFFER_DISCOUNT_PERCENT,
) -> None:
    """Validate offer price pair and raise ValueError with unified messages."""
    if original_price is None or discount_price is None:
        if require_both:
            raise ValueError("Необходимо указать обе цены: обычную и со скидкой.")
        return

    original = _to_decimal(original_price, "original_price")
    discount = _to_decimal(discount_price, "discount_price")

    if original <= 0 or discount <= 0:
        raise ValueError(INVALID_OFFER_PRICE_MESSAGE)
    if discount >= original:
        raise ValueError(DISCOUNT_MUST_BE_LOWER_MESSAGE)
    if not is_min_discount_reached(original, discount, min_discount_percent=min_discount_percent):
        raise ValueError(MIN_OFFER_DISCOUNT_MESSAGE)
