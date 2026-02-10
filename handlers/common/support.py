"""
Support handler - opens chat with support.
"""
from aiogram import F, Router, types
from aiogram.utils.keyboard import InlineKeyboardBuilder

from database_protocol import DatabaseProtocol
from handlers.common.utils import is_support_button
from localization import get_text

router = Router(name="support")

SUPPORT_USERNAME = "fudly_support"
SUPPORT_URL = f"https://t.me/{SUPPORT_USERNAME}"


@router.message(F.text.func(is_support_button))
async def open_support_chat(message: types.Message, db: DatabaseProtocol) -> None:
    """Send a support message with a direct chat link."""
    if not message.from_user:
        return

    lang = db.get_user_language(message.from_user.id)

    builder = InlineKeyboardBuilder()
    builder.button(text=get_text(lang, "support_open_chat"), url=SUPPORT_URL)
    builder.adjust(1)

    await message.answer(
        get_text(lang, "support_message"),
        parse_mode="HTML",
        reply_markup=builder.as_markup(),
    )
