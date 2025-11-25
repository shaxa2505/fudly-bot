"""
E2E tests for admin legacy approve/reject store callbacks.
"""
from __future__ import annotations

import os
import tempfile
from datetime import datetime

import pytest
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import CallbackQuery, Chat, Message, Update
from aiogram.types import User as TgUser
from aiogram.utils.keyboard import InlineKeyboardBuilder

from database import Database
from handlers.admin import legacy as admin_legacy
from localization import get_text as loc_get_text


class SentEvent:
    def __init__(self, method: str, chat_id: int | None, text: str | None):
        self.method = method
        self.chat_id = chat_id
        self.text = text


def _adapter_get_text(key: str, lang: str, **kwargs):
    # admin.legacy expects get_text(key, lang); adapt our get_text(lang, key)
    return loc_get_text(lang, key, **kwargs)


def _dummy_moderation_keyboard(store_id: int):
    b = InlineKeyboardBuilder()
    b.button(text="Approve", callback_data=f"approve_store_{store_id}")
    b.button(text="Reject", callback_data=f"reject_store_{store_id}")
    b.adjust(2)
    return b.as_markup()


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
async def test_admin_approve_and_reject_store(temp_db: Database, monkeypatch: pytest.MonkeyPatch):
    admin_id = 700001
    owner_id = 700002

    temp_db.add_user(admin_id, "admin")
    temp_db.update_user_role(admin_id, "admin")

    temp_db.add_user(owner_id, "owner", first_name="Owner")
    temp_db.update_user_language(owner_id, "ru")
    store_id = temp_db.add_store(owner_id, "Moderated Store", "Ташкент")

    storage = MemoryStorage()
    dp = Dispatcher(storage=storage)
    dp.include_router(admin_legacy.router)

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
    from aiogram.methods import AnswerCallbackQuery, EditMessageText, SendMessage

    async def fake_bot_call(self, method):
        if isinstance(method, SendMessage):
            return await fake_send_message(self, method.chat_id, method.text)
        if isinstance(method, EditMessageText):
            # Return edited message-like object
            return Message(
                message_id=method.message_id or 1,
                date=datetime.now(),
                chat=Chat(id=method.chat_id or admin_id, type="private"),
                text=method.text,
            )
        if isinstance(method, AnswerCallbackQuery):
            return await fake_answer_callback_query(method.callback_query_id)
        return True

    monkeypatch.setattr(Bot, "__call__", fake_bot_call, raising=True)

    # Wire admin legacy dependencies
    admin_legacy.setup(
        bot,
        temp_db,
        _adapter_get_text,
        _dummy_moderation_keyboard,
        lambda: datetime.now(),
        admin_id,
        database_url=getattr(temp_db, "db_name", ""),
    )

    # Approve callback
    tg_admin = TgUser(id=admin_id, is_bot=False, first_name="Admin")
    chat = Chat(id=admin_id, type="private")
    cb_message = Message(
        message_id=1,
        date=datetime.now(),
        chat=chat,
        from_user=tg_admin,
        text="Moderation list",
    )
    approve_cb = CallbackQuery(
        id="cbq_admin_1",
        from_user=tg_admin,
        chat_instance="ci_admin",
        data=f"approve_store_{store_id}",
        message=cb_message,
    )
    await dp.feed_update(bot, Update(update_id=300, callback_query=approve_cb))

    # Store is activated and owner is seller; owner notified
    store = temp_db.get_store(store_id)
    assert store is not None
    assert store.get("status") in ("active", "approved")
    owner = temp_db.get_user(owner_id)
    assert owner is not None and owner.get("role") == "seller"
    # Notification to owner is best-effort in handler (wrapped in try/except);
    # we don't assert on outbound message to avoid flakiness.

    # Reject callback
    # First set back to pending for test purposes
    temp_db.update_store_status(store_id, "pending")
    reject_cb = CallbackQuery(
        id="cbq_admin_2",
        from_user=tg_admin,
        chat_instance="ci_admin",
        data=f"reject_store_{store_id}",
        message=cb_message,
    )
    await dp.feed_update(bot, Update(update_id=301, callback_query=reject_cb))

    store2 = temp_db.get_store(store_id)
    assert store2 is not None and store2.get("status") == "rejected"
