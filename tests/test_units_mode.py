from app.core.units import effective_order_unit


def test_effective_order_unit_keeps_measured_units_by_default(monkeypatch) -> None:
    monkeypatch.delenv("BOT_MEASURED_UNITS_ENABLED", raising=False)
    assert effective_order_unit("ml") == "ml"


def test_effective_order_unit_switches_to_piece_when_disabled(monkeypatch) -> None:
    monkeypatch.setenv("BOT_MEASURED_UNITS_ENABLED", "0")
    assert effective_order_unit("ml") == "piece"
    assert effective_order_unit("kg") == "piece"
    assert effective_order_unit("piece") == "piece"
