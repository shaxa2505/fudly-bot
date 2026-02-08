import json

import pytest


@pytest.mark.asyncio
async def test_webapp_order_rejects_delivery_card(aiohttp_client, app, mocker):
    """
    POST /api/v1/orders should reject delivery card orders (card not supported).
    """
    client = await aiohttp_client(app)

    # Force authenticated user via header (Telegram init data validator mocked to return user_id=123)
    mocker.patch(
        "app.core.webhook_server._get_authenticated_user_id",
        return_value=123,
    )

    # Stub DB methods used by api_create_order
    db = app["db"]
    db.get_offer = mocker.Mock(return_value={"offer_id": 1, "store_id": 10, "discount_price": 10000})
    db.get_store = mocker.Mock(return_value={"store_id": 10, "delivery_price": 5000, "name": "Test"})
    db.create_cart_order = mocker.Mock()  # not used because unified service is preferred

    # UnifiedOrderService mock
    service = mocker.Mock()
    service.create_order = mocker.AsyncMock()
    # Attach service singleton
    import app.services.unified_order_service as uos

    uos._unified_order_service = service  # type: ignore

    payload = {
        "items": [{"offer_id": 1, "quantity": 1}],
        "order_type": "delivery",
        "delivery_address": "Tashkent",
        "payment_method": "card",
    }

    resp = await client.post("/api/v1/orders", data=json.dumps(payload))
    assert resp.status == 400
    data = await resp.json()
    assert "Unsupported payment method" in data.get("detail", "")


@pytest.mark.asyncio
async def test_webapp_order_rejects_card_with_proof(aiohttp_client, app, mocker):
    """
    POST /api/v1/orders should reject card payments even when payment_proof is provided.
    """
    client = await aiohttp_client(app)

    mocker.patch(
        "app.core.webhook_server._get_authenticated_user_id",
        return_value=123,
    )

    db = app["db"]
    db.get_offer = mocker.Mock(return_value={"offer_id": 1, "store_id": 10, "discount_price": 10000})
    db.get_store = mocker.Mock(return_value={"store_id": 10, "delivery_price": 5000, "name": "Test"})
    db.create_cart_order = mocker.Mock()

    # Mock unified order service and return success
    service = mocker.Mock()
    service.create_order = mocker.AsyncMock(
        return_value=mocker.Mock(
            success=True,
            order_ids=[111],
            pickup_codes=[],
            booking_ids=[],
            total_items=1,
            total_price=10000,
            delivery_price=5000,
            grand_total=15000,
            error_message=None,
        )
    )
    import app.services.unified_order_service as uos

    uos._unified_order_service = service  # type: ignore

    payload = {
        "items": [{"offer_id": 1, "quantity": 1}],
        "order_type": "delivery",
        "delivery_address": "Tashkent",
        "payment_method": "card",
        "payment_proof": "data:image/png;base64,xxx",
    }

    resp = await client.post("/api/v1/orders", data=json.dumps(payload))
    assert resp.status == 400
    data = await resp.json()
    assert "Unsupported payment method" in data.get("detail", "")
