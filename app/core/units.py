"""Helpers for unit types, quantity parsing/formatting, and totals."""
from __future__ import annotations

import os
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any

from localization import get_text

UNIT_PIECE = "piece"
UNIT_KG = "kg"
UNIT_G = "g"
UNIT_L = "l"
UNIT_ML = "ml"

UNIT_TYPES = {UNIT_PIECE, UNIT_KG, UNIT_G, UNIT_L, UNIT_ML}

UNIT_ALIASES = {
    # Pieces
    "шт": UNIT_PIECE,
    "штук": UNIT_PIECE,
    "штука": UNIT_PIECE,
    "piece": UNIT_PIECE,
    "pieces": UNIT_PIECE,
    "pcs": UNIT_PIECE,
    "dona": UNIT_PIECE,
    "pieceu": UNIT_PIECE,
    # Kg
    "кг": UNIT_KG,
    "kg": UNIT_KG,
    "килограмм": UNIT_KG,
    "kilogram": UNIT_KG,
    "kilogramm": UNIT_KG,
    # G
    "г": UNIT_G,
    "гр": UNIT_G,
    "g": UNIT_G,
    "gram": UNIT_G,
    "gramm": UNIT_G,
    # L
    "л": UNIT_L,
    "l": UNIT_L,
    "liter": UNIT_L,
    "litre": UNIT_L,
    # ML
    "мл": UNIT_ML,
    "ml": UNIT_ML,
}

WEIGHT_UNITS = {UNIT_KG, UNIT_G}
VOLUME_UNITS = {UNIT_L, UNIT_ML}

KG_L_STEP = Decimal("0.1")
_TRUE_VALUES = {"1", "true", "yes", "on"}


def normalize_unit(value: str | None) -> str:
    if not value:
        return UNIT_PIECE
    raw = str(value).strip().lower()
    if raw in UNIT_TYPES:
        return raw
    return UNIT_ALIASES.get(raw, UNIT_PIECE)


def unit_label(unit: str, lang: str = "ru") -> str:
    unit_type = normalize_unit(unit)
    if unit_type == UNIT_PIECE:
        return get_text(lang, "unit_piece")
    if unit_type == UNIT_KG:
        return get_text(lang, "unit_kg")
    if unit_type == UNIT_G:
        return get_text(lang, "unit_g")
    if unit_type == UNIT_L:
        return get_text(lang, "unit_l")
    if unit_type == UNIT_ML:
        return get_text(lang, "unit_ml")
    return get_text(lang, "unit_piece")


def measured_units_enabled() -> bool:
    """Whether non-piece units should be treated as weighted/volumetric quantities."""
    raw = os.getenv("BOT_MEASURED_UNITS_ENABLED", "1").strip().lower()
    return raw in _TRUE_VALUES


def effective_order_unit(unit: str | None) -> str:
    """Resolve unit for order/cart quantity math.

    When BOT_MEASURED_UNITS_ENABLED=0, non-piece units are treated as piece for
    quantity controls and totals (price per item behavior, aligned with WebApp).
    """
    unit_type = normalize_unit(unit)
    if unit_type == UNIT_PIECE:
        return UNIT_PIECE
    if measured_units_enabled():
        return unit_type
    return UNIT_PIECE


def quantity_step(unit: str) -> Decimal:
    unit_type = normalize_unit(unit)
    if unit_type in (UNIT_KG, UNIT_L):
        return KG_L_STEP
    return Decimal("1")


def is_piece_unit(unit: str) -> bool:
    return normalize_unit(unit) == UNIT_PIECE


def is_weight_unit(unit: str) -> bool:
    return normalize_unit(unit) in WEIGHT_UNITS


def is_volume_unit(unit: str) -> bool:
    return normalize_unit(unit) in VOLUME_UNITS


def _to_decimal(value: Any) -> Decimal:
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def format_quantity(value: Any, unit: str, lang: str = "ru") -> str:
    unit_type = normalize_unit(unit)
    qty = _to_decimal(value)
    if unit_type in (UNIT_KG, UNIT_L):
        qty = qty.quantize(KG_L_STEP, rounding=ROUND_HALF_UP)
    else:
        qty = qty.quantize(Decimal("1"), rounding=ROUND_HALF_UP)

    text = format(qty, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text


def parse_quantity_input(raw: str, unit: str) -> Decimal:
    if raw is None:
        raise ValueError("empty")
    cleaned = raw.strip().lower().replace(",", ".")
    cleaned = cleaned.replace(" ", "")
    if not cleaned:
        raise ValueError("empty")

    try:
        value = Decimal(cleaned)
    except (InvalidOperation, ValueError):
        raise ValueError("invalid")

    if value <= 0:
        raise ValueError("invalid")

    unit_type = normalize_unit(unit)
    step = quantity_step(unit)

    if unit_type in (UNIT_KG, UNIT_L):
        # enforce 0.1 step
        scaled = (value / step).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
        if scaled * step != value:
            raise ValueError("step")
        return value

    # piece, g, ml -> integer only
    if value != value.to_integral_value(rounding=ROUND_HALF_UP):
        raise ValueError("integer")
    return value


def clamp_quantity(value: Decimal, max_value: Decimal) -> Decimal:
    if value > max_value:
        return max_value
    return value


def coerce_quantity(value: Any, default: float = 1.0) -> float:
    """Coerce stored quantity to float with a safe default."""
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def format_quantity_with_unit(value: Any, unit: str, lang: str = "ru") -> str:
    """Format quantity with localized unit label."""
    return f"{format_quantity(value, unit, lang)} {unit_label(unit, lang)}"


def calc_total_price(price: int | float, quantity: Any) -> int:
    qty = _to_decimal(quantity)
    total = Decimal(str(price)) * qty
    return int(total.quantize(Decimal("1"), rounding=ROUND_HALF_UP))
