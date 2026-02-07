"""
Help and FAQ handler - explains how Fudly works.
"""
import os
from html import escape

from aiogram import F, Router, types
from aiogram.filters import Command

from database_protocol import DatabaseProtocol
from handlers.common.utils import user_view_mode
from localization import get_text

router = Router(name="help")


@router.message(F.text.in_(["❓ Как это работает", "❓ Qanday ishlaydi"]))
@router.message(Command("help"))
async def show_help(message: types.Message, db: DatabaseProtocol):
    """Show help information based on current user mode."""
    user_id = message.from_user.id
    lang = db.get_user_language(user_id)
    user = db.get_user_model(user_id)

    current_mode = user_view_mode.get(user_id, "customer")

    if user and user.role == "seller" and current_mode == "seller":
        help_text = get_text(lang, "help_partner")
    else:
        help_text = get_text(lang, "help_customer")

    webapp_url = os.getenv("WEBAPP_URL", "https://fudly-webapp.vercel.app").strip()
    webapp_url = escape(webapp_url, quote=True)
    try:
        help_text = help_text.format(webapp_url=webapp_url)
    except (KeyError, ValueError):
        pass

    await message.answer(help_text, parse_mode="HTML")
