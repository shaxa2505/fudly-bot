"""
Common utilities, constants and middleware.
"""
import logging
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta, timezone
from typing import Any

from aiogram import BaseMiddleware

from database_protocol import DatabaseProtocol

logger = logging.getLogger("fudly")

# Re-export states for backward compatibility
from handlers.common.states import (  # noqa: E402
    BookOffer,
    Browse,
    BrowseOffers,
    BulkCreate,
    ChangeCity,
    ConfirmOrder,
    CreateOffer,
    EditOffer,
    OrderDelivery,
    RegisterStore,
    Registration,
    Search,
)

__all__ = [
    # States
    "Registration",
    "RegisterStore",
    "CreateOffer",
    "BulkCreate",
    "ChangeCity",
    "EditOffer",
    "ConfirmOrder",
    "BookOffer",
    "BrowseOffers",
    "OrderDelivery",
    "Search",
    "Browse",
    # Utils
    "user_view_mode",
    "get_user_view_mode",
    "set_user_view_mode",
    "normalize_city",
    "get_uzb_time",
    "has_approved_store",
    "get_appropriate_menu",
    "RegistrationCheckMiddleware",
    "UZB_TZ",
    "CITY_UZ_TO_RU",
    "is_main_menu_button",
    # Safe message operations
    "safe_delete_message",
    "safe_edit_message",
]

# Main menu button texts (Russian and Uzbek)
MAIN_MENU_BUTTONS = {
    # Customer menu
    "🔥 Горячее",
    "🔥 Issiq takliflar",
    "🏪 Заведения",
    "🏪 Do'konlar",
    "🔍 Поиск",
    "🔍 Qidirish",
    "🛒 Корзина",
    "🛒 Savat",
    "❤️ Избранное",
    "❤️ Sevimlilar",
    "👤 Профиль",
    "👤 Profil",
    # Seller menu
    "📦 Мои товары",
    "📦 Mening tovarlarim",
    "➕ Добавить товар",
    "➕ Tovar qo'shish",
    "📊 Статистика",
    "📊 Statistika",
    "🏪 Мой магазин",
    "🏪 Mening do'konim",
    # Common
    "❌ Отмена",
    "❌ Bekor qilish",
}


def is_main_menu_button(text: str | None) -> bool:
    """Check if text is a main menu button (should exit FSM and handle separately)."""
    if not text:
        return False
    return text.strip() in MAIN_MENU_BUTTONS


# =============================================================================
# Safe Message Operations (no silent failures)
# =============================================================================


async def safe_delete_message(message: Any) -> bool:
    """Safely delete a message, returning True if successful.
    
    Does not raise exceptions - message may already be deleted.
    """
    try:
        await message.delete()
        return True
    except Exception:
        # Message may already be deleted or user blocked bot
        return False


async def safe_edit_message(
    message: Any,
    text: str,
    parse_mode: str = "HTML",
    reply_markup: Any = None,
) -> bool:
    """Safely edit a message, returning True if successful.
    
    Does not raise exceptions - message may be too old or already edited.
    """
    try:
        if hasattr(message, "photo") and message.photo:
            await message.edit_caption(
                caption=text, parse_mode=parse_mode, reply_markup=reply_markup
            )
        else:
            await message.edit_text(text, parse_mode=parse_mode, reply_markup=reply_markup)
        return True
    except Exception:
        # Message may be too old, already edited, or deleted
        return False


# In-memory per-session view mode override: {'seller'|'customer'}
# DEPRECATED: Use get_user_view_mode()/set_user_view_mode() with database instead
# Kept for backward compatibility during migration
user_view_mode: dict[int, str] = {}


def get_user_view_mode(user_id: int, db: DatabaseProtocol) -> str:
    """Get user view mode from database. Falls back to in-memory dict for compatibility."""
    # Try database first
    try:
        mode = db.get_user_view_mode(user_id)
        if mode:
            return mode
    except AttributeError:
        logger.debug("get_user_view_mode not available in database")
    except Exception as e:
        logger.debug("Could not get user view mode: %s", e)
    # Fallback to in-memory dict
    return user_view_mode.get(user_id, "customer")


def set_user_view_mode(user_id: int, mode: str, db: DatabaseProtocol) -> None:
    """Set user view mode in database and in-memory dict for compatibility."""
    if mode not in ("customer", "seller"):
        mode = "customer"
    # Update database
    try:
        db.set_user_view_mode(user_id, mode)
    except AttributeError:
        logger.debug("set_user_view_mode not available in database")
    except Exception as e:
        logger.debug("Could not set user view mode: %s", e)
    # Also update in-memory dict for backward compatibility
    user_view_mode[user_id] = mode


# Uzbek city names mapping to Russian
CITY_UZ_TO_RU = {
    "Toshkent": "Ташкент",
    "Samarqand": "Самарканд",
    "Buxoro": "Бухара",
    "Andijon": "Андижан",
    "Namangan": "Наманган",
    "Farg'ona": "Фергана",
    "Qo'qon": "Коканд",
    "Xiva": "Хива",
    "Nukus": "Нукус",
}

# Uzbekistan timezone (UTC+5)
UZB_TZ = timezone(timedelta(hours=5))


def normalize_city(city: str) -> str:
    """Convert city name to Russian format for database search."""
    return CITY_UZ_TO_RU.get(city, city)


def get_uzb_time() -> datetime:
    """Get current time in Uzbekistan timezone (UTC+5)."""
    return datetime.now(UZB_TZ)


def has_approved_store(user_id: int, db: DatabaseProtocol) -> bool:
    """Check if user has an approved store (owned or admin access)."""
    stores = db.get_user_accessible_stores(user_id)
    return any(store.get("status") == "active" for store in stores)


def get_appropriate_menu(
    user_id: int,
    lang: str,
    db: DatabaseProtocol,
    main_menu_seller: Callable[[str], Any],
    main_menu_customer: Callable[[str], Any],
) -> Any:
    """Return appropriate menu for user based on their store approval status and current mode."""
    user = db.get_user_model(user_id)
    if not user:
        return main_menu_customer(lang)

    role = user.role
    if role == "store_owner":
        role = "seller"

    current_mode = get_user_view_mode(user_id, db)

    if role == "seller":
        if has_approved_store(user_id, db):
            if current_mode == "seller":
                return main_menu_seller(lang)
            else:
                return main_menu_customer(lang)
        else:
            return main_menu_customer(lang)

    return main_menu_customer(lang)


class RegistrationCheckMiddleware(BaseMiddleware):
    """Check that user is registered (has phone number) before any action."""

    def __init__(
        self,
        db: DatabaseProtocol,
        get_text_func: Callable[[str, str], str] | Callable[..., str],
        phone_request_keyboard_func: Callable[[str], Any],
    ):
        self.db = db
        self.get_text = get_text_func
        self.phone_request_keyboard = phone_request_keyboard_func
        super().__init__()

    async def __call__(
        self,
        handler: Callable[[Any, dict[str, Any]], Awaitable[Any]],
        event: Any,
        data: dict[str, Any],
    ) -> Any:
        msg = getattr(event, "message", None)
        cb = getattr(event, "callback_query", None)
        user_id = None
        if msg and getattr(msg, "from_user", None):
            user_id = msg.from_user.id
        elif cb and getattr(cb, "from_user", None):
            user_id = cb.from_user.id

        if not user_id:
            return await handler(event, data)

        content_type = None
        if msg:
            if msg.photo:
                content_type = "photo"
            elif msg.text:
                content_type = f"text: {msg.text[:30]}"
            elif msg.contact:
                content_type = "contact"
        logger.debug(f"[Middleware] User {user_id}, type: {content_type}")

        allowed_commands = ["/start", "/help"]
        allowed_callbacks = ["lang_ru", "lang_uz"]
        allowed_callback_patterns = [
            "book_",
            "order_delivery_",
            "store_info_",
            "store_offers_",
            "store_reviews_",
            "back_to_store_",
            "hot_offers_",
            "filter_",
        ]

        if msg:
            if msg.text and any(msg.text.startswith(cmd) for cmd in allowed_commands):
                return await handler(event, data)
            if msg.contact:
                return await handler(event, data)
            if msg.photo:
                return await handler(event, data)

        if cb and cb.data:
            if cb.data in allowed_callbacks:
                return await handler(event, data)
            if any(cb.data.startswith(pattern) for pattern in allowed_callback_patterns):
                return await handler(event, data)

        state = data.get("state")
        if state:
            current_state = await state.get_state()
            if current_state:
                return await handler(event, data)

        user = self.db.get_user_model(user_id)
        user_phone = user.phone if user else None
        if not user or not user_phone:
            lang = self.db.get_user_language(user_id) if user else "ru"
            if msg:
                await msg.answer(
                    self.get_text(lang, "registration_required"),
                    parse_mode="HTML",
                    reply_markup=self.phone_request_keyboard(lang),
                )
            elif cb:
                await cb.answer(self.get_text(lang, "registration_required"), show_alert=True)
            return

        return await handler(event, data)
