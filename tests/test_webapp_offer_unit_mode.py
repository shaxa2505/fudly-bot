import os

os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test-token")
os.environ.setdefault("ADMIN_ID", "1")

from app.api.webapp.routes_offers import _to_offer_response


def test_webapp_offer_response_uses_piece_when_measured_units_disabled(monkeypatch) -> None:
    monkeypatch.setenv("BOT_MEASURED_UNITS_ENABLED", "0")
    response = _to_offer_response(
        {
            "offer_id": 1,
            "store_id": 1,
            "title": "Test",
            "original_price": 10000,
            "discount_price": 7000,
            "quantity": 20,
            "unit": "ml",
            "category": "other",
        }
    )
    assert response.unit == "piece"


def test_webapp_offer_response_keeps_measured_unit_by_default(monkeypatch) -> None:
    monkeypatch.delenv("BOT_MEASURED_UNITS_ENABLED", raising=False)
    response = _to_offer_response(
        {
            "offer_id": 1,
            "store_id": 1,
            "title": "Test",
            "original_price": 10000,
            "discount_price": 7000,
            "quantity": 20,
            "unit": "ml",
            "category": "other",
        }
    )
    assert response.unit == "ml"
