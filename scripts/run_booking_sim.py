import asyncio
import importlib
from datetime import datetime

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import CallbackQuery, Chat, Message, Update
from aiogram.types import User as TgUser

from app.core.cache import CacheManager
from database import Database


async def main():
    # prepare db
    db = Database(":memory:")
    user_id = 111001
    db.add_user(user_id, "buyer", first_name="Buyer")
    db.update_user_language(user_id, "ru")
    db.update_user_phone(user_id, "+998901234567")
    db.update_user_city(user_id, "Ташкент")

    seller_id = 222002
    db.add_user(seller_id, "seller", first_name="Seller")
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

    import handlers.bookings as bookings_mod

    importlib.reload(bookings_mod)

    storage = MemoryStorage()
    dp = Dispatcher(storage=storage)
    dp.include_router(bookings_mod.router)

    bot = Bot(token="42:TEST")
    sent = []

    async def fake_send_message(self, chat_id: int, text: str, **kwargs):
        sent.append((chat_id, text))

        class Dummy:
            def __init__(self):
                self.message_id = len(sent)

        return Dummy()

    async def fake_answer_callback_query(callback_query_id: str, **kwargs):
        sent.append((None, "answer"))
        return True

    async def fake_get_me(self):
        return TgUser(id=42, is_bot=True, first_name="FudlyBot")

    from aiogram.methods import AnswerCallbackQuery, EditMessageText, SendMessage

    async def fake_bot_call(self, method, request_timeout=None):
        if isinstance(method, SendMessage):
            return await fake_send_message(self, method.chat_id, method.text)
        if isinstance(method, EditMessageText):
            sent.append((method.chat_id, method.text))

            class Dummy:
                pass

            return Dummy()
        if isinstance(method, AnswerCallbackQuery):
            return await fake_answer_callback_query(method.callback_query_id)
        return True

    Bot.get_me = fake_get_me
    Bot.__call__ = fake_bot_call

    cache = CacheManager(db)
    bookings_mod.setup_dependencies(db, cache, bot, metrics={"bookings_created": 0})

    tg_user = TgUser(id=user_id, is_bot=False, first_name="Buyer")
    chat = Chat(id=user_id, type="private")
    cb_message = Message(
        message_id=1, date=datetime.now(), chat=chat, from_user=tg_user, text="Hot offers"
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
    print("Sent messages:")
    for s in sent:
        print(s)


if __name__ == "__main__":
    asyncio.run(main())
