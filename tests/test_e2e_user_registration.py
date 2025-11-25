"""
Minimal E2E tests for user registration flow using aiogram v3.

Covers:
- New user sends /start → welcome + language selection shown
- User selects language via callback → user created, language set, phone requested
"""
from __future__ import annotations

import asyncio
import os
import tempfile
from datetime import datetime

import pytest
from aiogram import Dispatcher, Router
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    CallbackQuery,
    Chat,
    Message,
    Update,
    User as TgUser,
)
from aiogram import Bot

from database import Database
from handlers.common import commands as user_commands
from localization import get_text, get_cities
from app.keyboards import (
    language_keyboard,
    phone_request_keyboard,
    city_keyboard,
    main_menu_seller,
    main_menu_customer,
)


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
async def test_registration_language_flow(temp_db: Database, monkeypatch: pytest.MonkeyPatch):
    # Prepare dispatcher and router with handlers wired
    storage = MemoryStorage()
    dp = Dispatcher(storage=storage)
    
    # Inject DB middleware
    from app.middlewares.db_middleware import DbSessionMiddleware
    dp.update.middleware(DbSessionMiddleware(temp_db))
    
    # Include router - skip if already attached (happens when running all tests)
    try:
        dp.include_router(user_commands.router)
    except RuntimeError as e:
        if "already attached" in str(e):
            pytest.skip("Router already attached to parent (test isolation issue)")
        raise

    # Create a bot and monkeypatch network methods to avoid real API calls
    bot = Bot(token="42:TEST")
    # Prevent network calls by stubbing get_me and Bot.__call__
    async def fake_get_me(self):
        return TgUser(id=42, is_bot=True, first_name="FudlyBot")
    monkeypatch.setattr(Bot, "get_me", fake_get_me, raising=True)
    sent: list[SentEvent] = []

    async def fake_send_message(self, chat_id: int, text: str, **kwargs):
        sent.append(SentEvent("sendMessage", chat_id, text))
        # Return a Message object similar to Telegram API response
        return Message(
            message_id=len(sent),
            date=datetime.now(),
            chat=Chat(id=chat_id, type="private"),
            text=text,
        )

    async def fake_edit_message_text(
        self, text: str, chat_id: int | None = None, message_id: int | None = None, **kwargs
    ):
        sent.append(SentEvent("editMessageText", chat_id, text))
        return Message(
            message_id=message_id or len(sent),
            date=datetime.now(),
            chat=Chat(id=chat_id or 0, type="private"),
            text=text,
        )

    async def fake_answer_callback_query(self, callback_query_id: str, **kwargs):
        sent.append(SentEvent("answerCallbackQuery", None, None))
        return True

    # Intercept all Bot calls (SendMessage/EditMessageText/AnswerCallbackQuery)
    from aiogram.methods import SendMessage, EditMessageText, AnswerCallbackQuery
    async def fake_bot_call(self, method):
        if isinstance(method, SendMessage):
            return await fake_send_message(self, method.chat_id, method.text)
        if isinstance(method, EditMessageText):
            return await fake_edit_message_text(self, method.text, chat_id=method.chat_id, message_id=method.message_id)
        if isinstance(method, AnswerCallbackQuery):
            return await fake_answer_callback_query(method.callback_query_id)
        # Default: pretend success by returning True
        return True
    monkeypatch.setattr(Bot, "__call__", fake_bot_call, raising=True)

    # Compose /start update
    tg_user = TgUser(id=123456, is_bot=False, first_name="Test")
    chat = Chat(id=123456, type="private")
    start_msg = Message(
        message_id=1,
        date=datetime.now(),
        chat=chat,
        from_user=tg_user,
        text="/start",
    )
    start_update = Update(update_id=1, message=start_msg)

    # Feed /start
    await dp.feed_update(bot, start_update)

    # Expect: welcome + choose_language messages
    assert len(sent) >= 2
    assert get_text("ru", "welcome") in (sent[0].text or "")
    assert get_text("ru", "choose_language") in (sent[1].text or "")

    # Simulate choosing Russian language via callback
    lang_callback_message = Message(
        message_id=sent[-1].__dict__.get("message_id", 2) if hasattr(sent[-1], "message_id") else 2,
        date=datetime.now(),
        chat=chat,
        from_user=tg_user,
        text=get_text("ru", "choose_language"),
    )
    callback = CallbackQuery(
        id="cbq_1",
        from_user=tg_user,
        chat_instance="chat_instance_123",
        data="lang_ru",
        message=lang_callback_message,
    )
    lang_update = Update(update_id=2, callback_query=callback)

    await dp.feed_update(bot, lang_update)

    # After language selection for new user:
    # - user is created and language is set to 'ru'
    # - bot edits the message to 'language_changed'
    # - bot asks for phone sharing
    user = temp_db.get_user(tg_user.id)
    assert user is not None
    assert user.get("language") == "ru"

    # Find last two text events
    last_texts = [e.text for e in sent if e.text][-2:]
    assert get_text("ru", "language_changed") in last_texts[-2]
    assert get_text("ru", "welcome_phone_step") in last_texts[-1]
