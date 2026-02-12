import importlib


def test_webapp_category_filter_variants():
    from app.api.webapp import routes_offers

    importlib.reload(routes_offers)
    values = routes_offers.expand_category_filter("dairy")
    assert "dairy" in values
    assert "sut" in values

    values = routes_offers.expand_category_filter("Sut")
    assert "dairy" in values
    assert "sut" in values


def test_webhook_category_filter_variants():
    from app.core import webhook_helpers

    importlib.reload(webhook_helpers)
    values = webhook_helpers.expand_category_filter("Sut")
    assert "dairy" in values
    assert "sut" in values
