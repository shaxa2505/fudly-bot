"""
E2E booking flow using bookings router:
- Prepare DB: user, store, offer
- Simulate callback "book_{offer_id}" -> quantity prompt
- Send quantity message -> booking created and confirmation message sent
"""
from __future__ import annotations

import importlib
from datetime import datetime

import pytest
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import CallbackQuery, Chat, Message, Update
from aiogram.types import User as TgUser

from app.core.cache import CacheManager


class SentEvent:
    def __init__(self, method: str, chat_id: int | None, text: str | None):
        self.method = method
        self.chat_id = chat_id
        self.text = text


@pytest.mark.asyncio
async def test_book_offer_quantity_flow(db, monkeypatch: pytest.MonkeyPatch):
    # Seed DB: user with language and phone, seller, store, offer
    user_id = 111001
    db.add_user(user_id=user_id, username="buyer", first_name="Buyer")
    db.update_user_language(user_id, "ru")
    db.update_user_phone(user_id, "+998901234567")
    db.update_user_city(user_id, "Ташкент")

    seller_id = 222002
    db.add_user(user_id=seller_id, username="seller", first_name="Seller")
    db.update_user_language(seller_id, "ru")
    db.update_user_role(seller_id, "seller")

    store_id = db.add_store(
        owner_id=seller_id,
        name="Test Store",
        city="Ташкент",
        address="Some address",
        description="",
        category="Ресторан",
        phone="+998900000000",
    )

    offer_id = db.add_offer(
        store_id=store_id,
        title="Test Offer",
        description="Nice",
        original_price=10000.0,
        discount_price=5000.0,
        quantity=3,
        available_from="10:00",
        available_until="22:00",
    )

    # Reload module to get a fresh router each test
    import handlers.bookings as bookings_mod

    importlib.reload(bookings_mod)

    # Dispatcher with bookings router
    storage = MemoryStorage()
    dp = Dispatcher(storage=storage)
    dp.include_router(bookings_mod.router)

    # Mock bot I/O
    bot = Bot(token="42:TEST")
    sent: list[SentEvent] = []

    async def fake_send_message(self, chat_id: int, text: str, **kwargs):
        sent.append(SentEvent("sendMessage", chat_id, text))
        return Message(
            message_id=len(sent),
            date=datetime.now(),
            chat=Chat(id=chat_id, type="private"),
            text=text,
        )

    async def fake_answer_callback_query(callback_query_id: str, **kwargs):
        sent.append(SentEvent("answerCallbackQuery", None, None))
        return True

    # Patch Bot methods
    async def fake_get_me(self):
        return TgUser(id=42, is_bot=True, first_name="FudlyBot")

    monkeypatch.setattr(Bot, "get_me", fake_get_me, raising=True)
    from aiogram.methods import AnswerCallbackQuery, EditMessageCaption, EditMessageText, SendMessage

    async def fake_bot_call(self, method, request_timeout=None):
        if isinstance(method, SendMessage):
            return await fake_send_message(self, method.chat_id, method.text)
        if isinstance(method, EditMessageText):
            # Track edited messages too (new UX edits in place)
            sent.append(SentEvent("editMessageText", method.chat_id, method.text))
            return Message(
                message_id=99,
                date=datetime.now(),
                chat=Chat(id=method.chat_id or 0, type="private"),
                text=method.text,
            )
        if isinstance(method, EditMessageCaption):
            # Track edited captions (for photo messages)
            sent.append(SentEvent("editMessageCaption", method.chat_id, method.caption))
            return Message(
                message_id=99,
                date=datetime.now(),
                chat=Chat(id=method.chat_id or 0, type="private"),
                text=method.caption,
            )
        if isinstance(method, AnswerCallbackQuery):
            return await fake_answer_callback_query(method.callback_query_id)
        return True

    monkeypatch.setattr(Bot, "__call__", fake_bot_call, raising=True)

    # Wire bookings module dependencies
    cache = CacheManager(db)
    bookings_mod.setup_dependencies(db, cache, bot, metrics={"bookings_created": 0})

    # Patch Message.edit_text and edit_caption for inline editing
    async def fake_edit_text(self, text, **kwargs):
        sent.append(SentEvent("editMessageText", self.chat.id if self.chat else 0, text))
        return Message(
            message_id=self.message_id,
            date=datetime.now(),
            chat=self.chat,
            text=text,
        )

    async def fake_edit_caption(self, caption, **kwargs):
        sent.append(SentEvent("editMessageCaption", self.chat.id if self.chat else 0, caption))
        return Message(
            message_id=self.message_id,
            date=datetime.now(),
            chat=self.chat,
            text=caption,
        )

    monkeypatch.setattr(Message, "edit_text", fake_edit_text, raising=True)
    monkeypatch.setattr(Message, "edit_caption", fake_edit_caption, raising=True)

    # Simulate callback "book_{offer_id}"
    tg_user = TgUser(id=user_id, is_bot=False, first_name="Buyer")
    chat = Chat(id=user_id, type="private")
    cb_message = Message(
        message_id=1,
        date=datetime.now(),
        chat=chat,
        from_user=tg_user,
        text="Hot offers",
    )
    cbq = CallbackQuery(
        id="cbq_1",
        from_user=tg_user,
        chat_instance="ci_1",
        data=f"book_{offer_id}",
        message=cb_message,
    )
    update1 = Update(update_id=100, callback_query=cbq)

    await dp.feed_update(bot, update1)

    # Simulate quantity input
    qty_message = Message(
        message_id=2,
        date=datetime.now(),
        chat=chat,
        from_user=tg_user,
        text="1",
    )
    update2 = Update(update_id=101, message=qty_message)

    await dp.feed_update(bot, update2)

    # Booking should be created in DB
    bookings = db.get_user_bookings(user_id)
    assert any(b.get("offer_id") == offer_id for b in bookings)
