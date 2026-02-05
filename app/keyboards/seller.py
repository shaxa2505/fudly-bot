"""Seller/Partner-specific keyboards."""
from __future__ import annotations

import hashlib
import hmac
import os
import time
import urllib.parse

from aiogram.types import InlineKeyboardMarkup, ReplyKeyboardMarkup, WebAppInfo
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder

from localization import get_text


def _with_signed_uid(url: str, user_id: int | None) -> str:
    """Attach a short-lived signed uid to a URL for fallback auth.

    This is used only when Telegram WebApp initData isn't available (e.g. domain misconfigured).
    """
    if not user_id:
        return url

    bot_token = os.getenv("BOT_TOKEN") or os.getenv("TELEGRAM_BOT_TOKEN")
    if not bot_token:
        # Keep legacy (insecure) uid param only if token isn't available; backend may still reject in production.
        sep = "&" if "?" in url else "?"
        return f"{url}{sep}uid={user_id}"

    auth_date = int(time.time())
    msg = f"uid={user_id}\nauth_date={auth_date}".encode("utf-8")
    sig = hmac.new(bot_token.encode("utf-8"), msg, hashlib.sha256).hexdigest()

    split = urllib.parse.urlsplit(url)
    query = urllib.parse.parse_qsl(split.query, keep_blank_values=True)
    query = [(k, v) for (k, v) in query if k not in ("uid", "auth_date", "sig")]
    query.extend([("uid", str(user_id)), ("auth_date", str(auth_date)), ("sig", sig)])
    new_query = urllib.parse.urlencode(query)
    return urllib.parse.urlunsplit((split.scheme, split.netloc, split.path, new_query, split.fragment))


def main_menu_seller(
    lang: str = "ru", webapp_url: str = None, user_id: int = None
) -> ReplyKeyboardMarkup:
    """Compact partner menu focused on core actions."""
    builder = ReplyKeyboardBuilder()
    builder.button(text=get_text(lang, "orders"))
    builder.button(text=get_text(lang, "add_item"))
    builder.button(text=get_text(lang, "my_items"))
    builder.button(text=get_text(lang, "partner_panel"))
    builder.button(text=f"\U0001F464 {get_text(lang, 'profile')}")
    builder.adjust(2, 2, 1)
    return builder.as_markup(resize_keyboard=True)


def offer_manage_keyboard(offer_id: int, lang: str = "ru") -> InlineKeyboardMarkup:
    """Offer management keyboard."""
    builder = InlineKeyboardBuilder()
    builder.button(text=get_text(lang, "duplicate"), callback_data=f"duplicate_{offer_id}")
    builder.button(text=get_text(lang, "delete"), callback_data=f"delete_offer_{offer_id}")
    builder.adjust(2)
    return builder.as_markup()


def store_keyboard(store_id: int) -> InlineKeyboardMarkup:
    """Store management keyboard."""
    builder = InlineKeyboardBuilder()
    builder.button(text="Статистика", callback_data=f"store_stats_{store_id}")
    builder.button(text="Товары", callback_data=f"store_offers_{store_id}")
    builder.adjust(2)
    return builder.as_markup()


def moderation_keyboard(store_id: int) -> InlineKeyboardMarkup:
    """Store moderation keyboard."""
    builder = InlineKeyboardBuilder()
    builder.button(text="Одобрить", callback_data=f"approve_store_{store_id}")
    builder.button(text="Отклонить", callback_data=f"reject_store_{store_id}")
    builder.adjust(2)
    return builder.as_markup()
