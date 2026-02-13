"""Shared helpers for order totals and quantities."""
from __future__ import annotations

import json
from typing import Any

from app.core.units import calc_total_price as calc_line_total_price


def parse_cart_items(cart_items: Any) -> list[dict]:
    if not cart_items:
        return []
    if isinstance(cart_items, str):
        try:
            data = json.loads(cart_items)
        except Exception:
            return []
        return data if isinstance(data, list) else []
    if isinstance(cart_items, list):
        return cart_items
    return []


def calc_items_total(cart_items: list[dict]) -> int:
    total = 0
    for item in cart_items:
        try:
            price = int(item.get("price") or 0)
        except Exception:
            price = 0
        try:
            qty = float(item.get("quantity") or 1)
        except Exception:
            qty = 1
        total += calc_line_total_price(price, qty)
    return total


def calc_quantity(cart_items: list[dict]) -> float:
    qty_total: float = 0.0
    for item in cart_items:
        try:
            qty_total += float(item.get("quantity") or 1)
        except Exception:
            qty_total += 1
    return qty_total


def calc_delivery_fee(
    total_price: int | float | None,
    items_total: int | float | None,
    *,
    delivery_price: int | float | None = None,
    order_type: str | None = None,
) -> int:
    if order_type and order_type not in ("delivery", "taxi"):
        return 0
    if delivery_price is not None:
        try:
            return int(delivery_price or 0)
        except Exception:
            return 0
    if total_price is None:
        return 0
    try:
        return max(0, int(total_price) - int(items_total or 0))
    except Exception:
        return 0


def calc_total_price(
    items_total: int | float,
    delivery_fee: int | float,
    *,
    total_price: int | float | None = None,
) -> int:
    if total_price is None:
        return int(items_total) + int(delivery_fee)
    try:
        return int(total_price or 0)
    except Exception:
        return int(items_total) + int(delivery_fee)
