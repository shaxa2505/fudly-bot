import pytest

from app.core.units import effective_order_unit, unit_label
from handlers.seller.management.offers import _parse_quantity_value
from handlers.seller.management.utils import format_quantity as seller_format_quantity


def test_seller_format_quantity_keeps_measured_unit_by_default(monkeypatch) -> None:
    monkeypatch.delenv("BOT_MEASURED_UNITS_ENABLED", raising=False)
    text = seller_format_quantity(250, "ml", "ru")
    assert text.endswith(f" {unit_label('ml', 'ru')}")


def test_seller_format_quantity_switches_to_piece_when_disabled(monkeypatch) -> None:
    monkeypatch.setenv("BOT_MEASURED_UNITS_ENABLED", "0")
    text = seller_format_quantity(250, "ml", "ru")
    assert text == f"250 {unit_label('piece', 'ru')}"


def test_parse_quantity_value_allows_zero_for_absolute_stock_edit(monkeypatch) -> None:
    monkeypatch.setenv("BOT_MEASURED_UNITS_ENABLED", "0")
    unit = effective_order_unit("ml")
    assert _parse_quantity_value("0", unit, allow_zero=True) == 0.0


def test_parse_quantity_value_rejects_fraction_in_piece_mode(monkeypatch) -> None:
    monkeypatch.setenv("BOT_MEASURED_UNITS_ENABLED", "0")
    unit = effective_order_unit("ml")
    with pytest.raises(ValueError, match="integer"):
        _parse_quantity_value("1.5", unit, allow_zero=False)


def test_parse_quantity_value_accepts_decimal_for_weight_mode(monkeypatch) -> None:
    monkeypatch.delenv("BOT_MEASURED_UNITS_ENABLED", raising=False)
    unit = effective_order_unit("kg")
    assert _parse_quantity_value("1.2", unit, allow_zero=False) == pytest.approx(1.2)
