import os

import pytest

os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test-token")
os.environ.setdefault("ADMIN_ID", "1")

from app.core.units import unit_label
from handlers.seller.create_offer import _parse_quantity_value, build_progress_text


def test_create_offer_parse_quantity_uses_piece_rules_when_measured_units_disabled(monkeypatch) -> None:
    monkeypatch.setenv("BOT_MEASURED_UNITS_ENABLED", "0")
    with pytest.raises(ValueError, match="integer"):
        _parse_quantity_value("1.5", "ml")


def test_create_offer_parse_quantity_keeps_measured_rules_by_default(monkeypatch) -> None:
    monkeypatch.delenv("BOT_MEASURED_UNITS_ENABLED", raising=False)
    assert _parse_quantity_value("1.5", "l") == pytest.approx(1.5)


def test_create_offer_progress_shows_piece_stock_when_measured_units_disabled(monkeypatch) -> None:
    monkeypatch.setenv("BOT_MEASURED_UNITS_ENABLED", "0")
    text = build_progress_text({"unit": "ml", "quantity": 250}, "ru", 5)
    assert unit_label("ml", "ru") in text
    assert f"250 {unit_label('piece', 'ru')}" in text
