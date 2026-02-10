"""Ensure order details no longer include Click payment buttons in bot fallback."""
from __future__ import annotations

import importlib
from datetime import datetime

import pytest
from aiogram.types import CallbackQuery, Chat, Message
from aiogram.types import User as TgUser

import app.integrations.payment_service as payment_service_mod
import handlers.customer.orders.my_orders as my_orders_mod


@pytest.mark.asyncio
async def test_my_orders_detail_shows_open_app_button(db, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CLICK_MERCHANT_ID", "test_merchant")
    monkeypatch.setenv("CLICK_SERVICE_ID", "test_service")
    monkeypatch.setenv("CLICK_SECRET_KEY", "test_secret")
    monkeypatch.setenv("WEBAPP_URL", "https://example.com")
    monkeypatch.setenv("ENVIRONMENT", "test")
    payment_service_mod._payment_service = None

    user_id = 91001
    db.add_user(user_id=user_id, username="buyer", first_name="Buyer")
    db.update_user_language(user_id, "ru")

    seller_id = 92001
    db.add_user(user_id=seller_id, username="seller", first_name="Seller")
    db.update_user_language(seller_id, "ru")
    db.update_user_role(seller_id, "seller")

    store_id = db.add_store(
        owner_id=seller_id,
        name="Test Store",
        city="Test City",
        address="Test address",
        phone="+998900000000",
    )

    offer_id = db.add_offer(
        store_id=store_id,
        title="Test Offer",
        description="Nice",
        original_price=10000,
        discount_price=5000,
        quantity=5,
        available_from="10:00",
        available_until="22:00",
    )

    order_id = db.create_order(
        user_id=user_id,
        store_id=store_id,
        offer_id=offer_id,
        quantity=1,
        order_type="delivery",
        delivery_address="Test address",
        delivery_price=15000,
        payment_method="click",
    )
    assert order_id is not None

    importlib.reload(my_orders_mod)
    my_orders_mod.setup_dependencies(db, bot_instance=None, cart_storage_instance=None)

    captured: dict[str, object] = {}

    async def fake_edit_text(self, text, **kwargs):
        captured["reply_markup"] = kwargs.get("reply_markup")
        return Message(
            message_id=self.message_id,
            date=datetime.now(),
            chat=self.chat,
            text=text,
        )

    monkeypatch.setattr(Message, "edit_text", fake_edit_text, raising=True)

    tg_user = TgUser(id=user_id, is_bot=False, first_name="Buyer")
    chat = Chat(id=user_id, type="private")
    cb_message = Message(
        message_id=1,
        date=datetime.now(),
        chat=chat,
        from_user=tg_user,
        text="Orders",
    )
    cbq = CallbackQuery(
        id="cbq_1",
        from_user=tg_user,
        chat_instance="ci_1",
        data=f"myorder_detail_o_{order_id}",
        message=cb_message,
    )

    await my_orders_mod._show_order_detail(cbq, int(order_id), "ru")

    markup = captured.get("reply_markup")
    assert markup is not None

    urls = [
        button.url
        for row in markup.inline_keyboard
        for button in row
        if getattr(button, "url", None)
    ]
    assert not any("my.click.uz/services/pay" in url for url in urls)

    webapps = [
        button.web_app.url
        for row in markup.inline_keyboard
        for button in row
        if getattr(button, "web_app", None)
    ]
    assert any(f"/order/{order_id}" in url for url in webapps)


@pytest.mark.asyncio
async def test_my_orders_detail_hides_click_button_when_paid(
    db, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CLICK_MERCHANT_ID", "test_merchant")
    monkeypatch.setenv("CLICK_SERVICE_ID", "test_service")
    monkeypatch.setenv("CLICK_SECRET_KEY", "test_secret")
    monkeypatch.setenv("WEBAPP_URL", "https://example.com")
    monkeypatch.setenv("ENVIRONMENT", "test")
    payment_service_mod._payment_service = None

    user_id = 91011
    db.add_user(user_id=user_id, username="buyer_paid", first_name="Buyer")
    db.update_user_language(user_id, "ru")

    seller_id = 92011
    db.add_user(user_id=seller_id, username="seller_paid", first_name="Seller")
    db.update_user_language(seller_id, "ru")
    db.update_user_role(seller_id, "seller")

    store_id = db.add_store(
        owner_id=seller_id,
        name="Paid Store",
        city="Test City",
        address="Test address",
        phone="+998900000000",
    )

    offer_id = db.add_offer(
        store_id=store_id,
        title="Paid Offer",
        description="Nice",
        original_price=10000,
        discount_price=5000,
        quantity=5,
        available_from="10:00",
        available_until="22:00",
    )

    order_id = db.create_order(
        user_id=user_id,
        store_id=store_id,
        offer_id=offer_id,
        quantity=1,
        order_type="delivery",
        delivery_address="Test address",
        delivery_price=15000,
        payment_method="click",
    )
    assert order_id is not None

    if hasattr(db, "update_payment_status"):
        db.update_payment_status(int(order_id), "confirmed")

    importlib.reload(my_orders_mod)
    my_orders_mod.setup_dependencies(db, bot_instance=None, cart_storage_instance=None)

    captured: dict[str, object] = {}

    async def fake_edit_text(self, text, **kwargs):
        captured["reply_markup"] = kwargs.get("reply_markup")
        return Message(
            message_id=self.message_id,
            date=datetime.now(),
            chat=self.chat,
            text=text,
        )

    monkeypatch.setattr(Message, "edit_text", fake_edit_text, raising=True)

    tg_user = TgUser(id=user_id, is_bot=False, first_name="Buyer")
    chat = Chat(id=user_id, type="private")
    cb_message = Message(
        message_id=1,
        date=datetime.now(),
        chat=chat,
        from_user=tg_user,
        text="Orders",
    )
    cbq = CallbackQuery(
        id="cbq_1_paid",
        from_user=tg_user,
        chat_instance="ci_2",
        data=f"myorder_detail_o_{order_id}",
        message=cb_message,
    )

    await my_orders_mod._show_order_detail(cbq, int(order_id), "ru")

    markup = captured.get("reply_markup")
    assert markup is not None

    urls = [
        button.url
        for row in markup.inline_keyboard
        for button in row
        if getattr(button, "url", None)
    ]
    assert not any("my.click.uz/services/pay" in url for url in urls)
