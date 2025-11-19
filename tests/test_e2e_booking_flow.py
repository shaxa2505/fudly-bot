"""
E2E booking flow using bookings router:
- Prepare DB: user, store, offer
- Simulate callback "book_{offer_id}" → quantity prompt
- Send quantity message → booking created and confirmation message sent
"""
from __future__ import annotations

import os
import tempfile
from datetime import datetime

import pytest
from aiogram import Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    CallbackQuery,
    Chat,
    Message,
    Update,
    User as TgUser,
)
from aiogram import Bot
import importlib

from database import Database
from app.core.cache import CacheManager
from handlers import bookings


class SentEvent:
    def __init__(self, method: str, chat_id: int | None, text: str | None):
        self.method = method
        self.chat_id = chat_id
        self.text = text


@pytest.fixture
def temp_db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    db = Database(path)
    try:
        yield db
    finally:
        try:
            os.remove(path)
        except FileNotFoundError:
            pass


@pytest.mark.asyncio
async def test_book_offer_quantity_flow(temp_db: Database, monkeypatch: pytest.MonkeyPatch):
    # Seed DB: user with language and phone, seller, store, offer
    user_id = 111001
    temp_db.add_user(user_id, "buyer", first_name="Buyer")
    temp_db.update_user_language(user_id, "ru")
    temp_db.update_user_phone(user_id, "+998901234567")
    temp_db.update_user_city(user_id, "Ташкент")

    seller_id = 222002
    temp_db.add_user(seller_id, "seller", first_name="Seller")
    temp_db.update_user_language(seller_id, "ru")
    temp_db.update_user_role(seller_id, "seller")

    store_id = temp_db.add_store(
        owner_id=seller_id,
        name="Test Store",
        city="Ташкент",
        address="Some address",
        description="",
        category="Ресторан",
        phone="+998900000000",
    )

    offer_id = temp_db.add_offer(
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
    # Avoid network calls: stub get_me and Bot.__call__
    async def fake_get_me(self):
        return TgUser(id=42, is_bot=True, first_name="FudlyBot")
    monkeypatch.setattr(Bot, "get_me", fake_get_me, raising=True)
    from aiogram.methods import SendMessage, EditMessageText, AnswerCallbackQuery
    async def fake_bot_call(self, method, request_timeout=None):
        if isinstance(method, SendMessage):
            return await fake_send_message(self, method.chat_id, method.text)
        if isinstance(method, EditMessageText):
            # Not used here but keep for completeness
            return Message(message_id=99, date=datetime.now(), chat=Chat(id=method.chat_id or 0, type="private"), text=method.text)
        if isinstance(method, AnswerCallbackQuery):
            return await fake_answer_callback_query(method.callback_query_id)
        return True
    monkeypatch.setattr(Bot, "__call__", fake_bot_call, raising=True)

    # Wire bookings module dependencies
    cache = CacheManager(temp_db)
    bookings_mod.setup_dependencies(temp_db, cache, bot, metrics={"bookings_created": 0})

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

    # Expect a quantity prompt message
    assert any("Сколько хотите забронировать" in (e.text or "") for e in sent if e.text)

    # Send quantity = 2
    qty_msg = Message(
        message_id=2,
        date=datetime.now(),
        chat=chat,
        from_user=tg_user,
        text="2",
    )
    update2 = Update(update_id=101, message=qty_msg)
    await dp.feed_update(bot, update2)

    # Validate booking created and confirmation sent
    bookings_list = temp_db.get_user_bookings(user_id)
    assert len(bookings_list) == 1
    assert any("Заказ успешно создан" in (e.text or "") for e in sent if e.text)
@pytest.mark.asyncio
async def test_cancel_booking_via_callback(temp_db: Database, monkeypatch: pytest.MonkeyPatch):
    # Seed DB: user, store, offer, booking
    user_id = 313001
    temp_db.add_user(user_id, "buyer", first_name="Buyer")
    temp_db.update_user_language(user_id, "ru")
    temp_db.update_user_phone(user_id, "+998901234567")
    temp_db.update_user_city(user_id, "Ташкент")

    seller_id = 323002
    temp_db.add_user(seller_id, "seller", first_name="Seller")
    temp_db.update_user_role(seller_id, "seller")
    store_id = temp_db.add_store(seller_id, "S1", "Ташкент")
    offer_id = temp_db.add_offer(store_id, "O1", "", 10000.0, 5000.0, 1, "10:00", "22:00")

    ok, booking_id, code = temp_db.create_booking_atomic(offer_id, user_id, 1)
    assert ok and booking_id

    # Reload module to get a fresh router instance
    import handlers.bookings as bookings_mod2
    importlib.reload(bookings_mod2)

    # Dispatcher
    storage = MemoryStorage()
    dp = Dispatcher(storage=storage)
    dp.include_router(bookings_mod2.router)

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

    async def fake_get_me(self):
        return TgUser(id=42, is_bot=True, first_name="FudlyBot")
    monkeypatch.setattr(Bot, "get_me", fake_get_me, raising=True)
    from aiogram.methods import SendMessage, EditMessageText, AnswerCallbackQuery
    async def fake_bot_call(self, method):
        if isinstance(method, SendMessage):
            return await fake_send_message(self, method.chat_id, method.text)
        if isinstance(method, EditMessageText):
            return Message(message_id=98, date=datetime.now(), chat=Chat(id=method.chat_id or 0, type="private"), text=method.text)
        if isinstance(method, AnswerCallbackQuery):
            return await fake_answer_callback_query(method.callback_query_id)
        return True
    monkeypatch.setattr(Bot, "__call__", fake_bot_call, raising=True)

    cache = CacheManager(temp_db)
    bookings_mod2.setup_dependencies(temp_db, cache, bot, metrics={"bookings_created": 0})

    # Cancel booking via callback
    tg_user = TgUser(id=user_id, is_bot=False, first_name="Buyer")
    chat = Chat(id=user_id, type="private")
    cb_message = Message(
        message_id=1,
        date=datetime.now(),
        chat=chat,
        from_user=tg_user,
        text="My bookings",
    )
    cbq = CallbackQuery(
        id="cbq_2",
        from_user=tg_user,
        chat_instance="ci_2",
        data=f"cancel_booking_{booking_id}",
        message=cb_message,
    )
    update = Update(update_id=200, callback_query=cbq)
    await dp.feed_update(bot, update)

    # Check status cancelled
    booking = temp_db.get_booking(booking_id)
    assert booking is not None
    assert booking[3] == "cancelled"
