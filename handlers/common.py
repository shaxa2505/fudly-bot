"""
Common utilities, state classes, and middleware
"""
from aiogram import BaseMiddleware
from datetime import datetime, timedelta, timezone
from typing import Any, Awaitable, Callable, Dict
import logging

from database_protocol import DatabaseProtocol
from handlers.common_states.states import (
    BookOffer,
    BrowseOffers,
    BulkCreate,
    ChangeCity,
    ConfirmOrder,
    CreateOffer,
    EditOffer,
    OrderDelivery,
    Registration,
    RegisterStore,
)

logger = logging.getLogger('fudly')

# Export states for backward compatibility
__all__ = [
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
    "user_view_mode",
    "normalize_city",
    "get_uzb_time",
    "has_approved_store",
    "get_appropriate_menu",
    "RegistrationCheckMiddleware",
]

# In-memory per-session view mode override: {'seller'|'customer'}
user_view_mode = {}

# Uzbek city names mapping to Russian
CITY_UZ_TO_RU = {
    "Toshkent": "Ташкент",
    "Samarqand": "Самарканд",
    "Buxoro": "Бухара",
    "Andijon": "Андижан",
    "Namangan": "Наманган",
    "Farg'ona": "Фергана",
    "Xiva": "Хива",
    "Nukus": "Нукус"
}

# Uzbek timezone (UTC+5)
UZB_TZ = timezone(timedelta(hours=5))


def normalize_city(city: str) -> str:
    """Convert city name to Russian format for database search"""
    return CITY_UZ_TO_RU.get(city, city)


def get_uzb_time():
    """Get current time in Uzbek timezone (UTC+5)"""
    return datetime.now(UZB_TZ)


def has_approved_store(user_id: int, db: DatabaseProtocol) -> bool:
    """Check if user has an approved store"""
    stores = db.get_user_stores(user_id)
    # stores: now unified dict format
    return any(store.get('status') == "active" for store in stores)


def get_appropriate_menu(
    user_id: int,
    lang: str,
    db: DatabaseProtocol,
    main_menu_seller: Callable[[str], Any],
    main_menu_customer: Callable[[str], Any]
) -> Any:
    """Return appropriate menu for user based on their store approval status"""
    user = db.get_user(user_id)
    if not user:
        return main_menu_customer(lang)
    
    # Both backends now return dict
    role = user.get('role', 'customer')
    
    # Unify roles: store_owner -> seller
    if role == 'store_owner':
        role = 'seller'
    
    # If partner - check for approved store
    if role == "seller":
        if has_approved_store(user_id, db):
            return main_menu_seller(lang)
        else:
            # No approved store - show customer menu
            return main_menu_customer(lang)
    
    return main_menu_customer(lang)


# ============== MIDDLEWARE: REGISTRATION CHECK ==============

class RegistrationCheckMiddleware(BaseMiddleware):
    """Check that user is registered (has phone number) before any action"""
    
    def __init__(
        self,
        db: DatabaseProtocol,
        get_text_func: Callable[[str, str], str] | Callable[..., str],
        phone_request_keyboard_func: Callable[[str], Any]
    ):
        self.db = db
        self.get_text = get_text_func
        self.phone_request_keyboard = phone_request_keyboard_func
        super().__init__()
    
    async def __call__(
        self,
        handler: Callable[[Any, Dict[str, Any]], Awaitable[Any]],
        event: Any,
        data: Dict[str, Any]
    ) -> Any:
        # Robust attribute access (aiogram runtime object shape)
        msg = getattr(event, 'message', None)
        cb = getattr(event, 'callback_query', None)
        user_id = None
        if msg and getattr(msg, 'from_user', None):
            user_id = msg.from_user.id
        elif cb and getattr(cb, 'from_user', None):
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

        allowed_commands = ['/start', '/help']
        allowed_callbacks = ['lang_ru', 'lang_uz']

        if msg:
            if msg.text and any(msg.text.startswith(cmd) for cmd in allowed_commands):
                return await handler(event, data)
            if msg.contact:
                return await handler(event, data)
            if msg.photo:
                return await handler(event, data)

        if cb and cb.data in allowed_callbacks:
            return await handler(event, data)

        state = data.get('state')
        if state:
            current_state = await state.get_state()
            if current_state:
                return await handler(event, data)

        user = self.db.get_user(user_id)
        # Both backends now return dict
        user_phone = user.get('phone') if user else None
        if not user or not user_phone:
            lang = self.db.get_user_language(user_id) if user else 'ru'
            if msg:
                await msg.answer(
                    self.get_text(lang, 'registration_required'),
                    parse_mode="HTML",
                    reply_markup=self.phone_request_keyboard(lang)
                )
            elif cb:
                await cb.answer(
                    self.get_text(lang, 'registration_required'),
                    show_alert=True
                )
            return

        return await handler(event, data)
