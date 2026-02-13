from app.core.order_math import calc_items_total, calc_total_price


def test_calc_items_total_multiplies_price_by_quantity() -> None:
    items = [{"price": 7000, "quantity": 250}]
    assert calc_items_total(items) == 1_750_000


def test_calc_total_price_adds_delivery_when_total_missing() -> None:
    assert calc_total_price(15000, 5000) == 20000
