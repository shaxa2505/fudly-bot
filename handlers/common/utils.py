"""
Common utilities, constants and middleware.
"""
import html
import json
import logging
import re
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from typing import Any

from aiogram import BaseMiddleware

from database_protocol import DatabaseProtocol
from app.core.utils import (
    CITY_UZ_TO_RU as CORE_CITY_UZ_TO_RU,
    get_offer_field as core_get_offer_field,
    get_order_field as core_get_order_field,
    get_store_field as core_get_store_field,
    normalize_city as core_normalize_city,
)
from localization import get_text

logger = logging.getLogger("fudly")
MAX_CAPTION_LENGTH = 1000


def html_escape(val: Any) -> str:
    """HTML-escape helper for safe rendering in Telegram messages.

    Use this instead of defining _esc() in each module.
    """
    return html.escape(str(val)) if val else ""


def _safe_caption(text: str) -> str:
    if len(text) <= MAX_CAPTION_LENGTH:
        return text
    return text[: MAX_CAPTION_LENGTH - 3] + "..."


# Alias for backward compatibility
_esc = html_escape


def resolve_offer_photo(offer: Any) -> str | None:
    """Resolve the best available offer photo (file_id)."""
    photo = core_get_offer_field(offer, "photo")
    if not photo:
        photo = core_get_offer_field(offer, "photo_id")
    return str(photo) if photo else None


def _extract_photo_from_item(item: Any) -> str | None:
    if isinstance(item, dict):
        for key in ("photo", "photo_id", "offer_photo", "offer_photo_id"):
            value = item.get(key)
            if value:
                return str(value)
    return None


def resolve_order_photo(db: DatabaseProtocol | None, order: Any, offer: Any | None = None) -> str | None:
    """Resolve order photo from order/cart items/offer."""
    if not order:
        return None

    for key in ("offer_photo", "offer_photo_id", "photo", "photo_id"):
        value = core_get_order_field(order, key)
        if value:
            return str(value)

    cart_items = core_get_order_field(order, "cart_items")
    if cart_items:
        try:
            cart_items = json.loads(cart_items) if isinstance(cart_items, str) else cart_items
        except Exception:
            cart_items = None

    if isinstance(cart_items, list):
        for item in cart_items:
            photo = _extract_photo_from_item(item)
            if photo:
                return photo
            offer_id = item.get("offer_id") if isinstance(item, dict) else None
            if offer_id and db and hasattr(db, "get_offer"):
                try:
                    offer_obj = db.get_offer(int(offer_id))
                except Exception:
                    offer_obj = None
                photo = resolve_offer_photo(offer_obj)
                if photo:
                    return photo

    if offer is None:
        offer_id = core_get_order_field(order, "offer_id")
        if offer_id and db and hasattr(db, "get_offer"):
            try:
                offer = db.get_offer(int(offer_id))
            except Exception:
                offer = None

    return resolve_offer_photo(offer)


def can_manage_store(
    db: DatabaseProtocol | None,
    store_id: int | None,
    user_id: int,
    store: Any | None = None,
) -> bool:
    """Check if user can manage store (owner or admin)."""
    if not db or not store_id:
        store_id = core_get_store_field(store, "store_id") if store else None
    if not db or not store_id:
        return False

    owner_id = core_get_store_field(store, "owner_id") if store else None
    try:
        if owner_id is not None and int(owner_id) == user_id:
            return True
    except (TypeError, ValueError):
        pass

    if hasattr(db, "is_store_admin"):
        try:
            return bool(db.is_store_admin(store_id, user_id))
        except Exception as e:
            logger.debug("is_store_admin check failed: %s", e)

    if hasattr(db, "get_store"):
        try:
            store_obj = db.get_store(store_id)
            owner_id = core_get_store_field(store_obj, "owner_id") if store_obj else None
            return owner_id == user_id
        except Exception:
            return False

    return False


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
    "html_escape",
    "_esc",  # Alias for backward compatibility
    "user_view_mode",
    "get_user_view_mode",
    "set_user_view_mode",
    "fix_mojibake_text",
    "normalize_city",
    "get_uzb_time",
    "has_approved_store",
    "get_appropriate_menu",
    "RegistrationCheckMiddleware",
    "UZB_TZ",
    "CITY_UZ_TO_RU",
    "is_main_menu_button",
    "is_cart_button",
    "is_hot_offers_button",
    "is_search_button",
    "is_my_orders_button",
    "is_profile_button",
    "is_support_button",
    "is_partner_button",
    "is_customer_menu_button",
    # Safe message operations
    "safe_delete_message",
    "safe_edit_message",
    "resolve_offer_photo",
    "resolve_order_photo",
    "can_manage_store",
    # Error helpers
    "get_system_error_text",
]

# Main menu button texts (Russian and Uzbek)
MAIN_MENU_BUTTONS = {
    # Customer menu
    "🥗 Еда со скидкой",
    "🥗 Chegirmali taomlar",
    "🛍 Акции и магазины",
    "🛍 Aksiyalar va do'konlar",
    "🏪 Горячее",
    "🏪 Issiq takliflar",
    "🏪 Заведения",
    "🏪 Do'konlar",
    "🔍 Поиск",
    "🔍 Qidirish",
    "🛒 Корзина",
    "🛒 Savat",
    "🧾 Заказы",
    "🧾 Buyurtmalar",
    "💙 Избранное",
    "💙 Sevimlilar",
    "👤 Профиль",
    "👤 Profil",
    "🆘 Поддержка",
    "🆘 Yordam",
    # Seller menu
    "📦 Мои товары",
    "📦 Mening tovarlarim",
    "📦 Товары",
    "📦 Mahsulotlar",
    "Мои товары",
    "Mening mahsulotlarim",
    "Товары",
    "Mahsulotlar",
    "➕ Добавить",
    "➕ Qo'shish",
    "➕ Добавить товар",
    "➕ Tovar qo'shish",
    "🧾 Заказы партнёра",
    "🧾 Hamkor buyurtmalari",
    "📊 Статистика",
    "📊 Statistika",
    "📈 Статистика",
    "📈 Statistika",
    "📊 Аналитика",
    "📊 Analitika",
    "Аналитика",
    "Analitika",
    "📥 Импорт",
    "📥 Import",
    "🏠 Мой магазин",
    "🏠 Mening do'konim",
    "\U0001F4CA \u041F\u0430\u043D\u0435\u043B\u044C",
    "\U0001F4CA Panel",
    "\U0001F5A5 \u0412\u0435\u0431-\u043F\u0430\u043D\u0435\u043B\u044C",
    "\U0001F5A5 Veb-panel",
    # Common
    "❌ Отмена",
    "❌ Bekor qilish",
    "Отмена",
    "Bekor qilish",
}

LEGACY_MAIN_MENU_BUTTONS = {
    # Hot offers legacy labels
    "🏪 Горячее",
    "🏪 Issiq takliflar",
    "🏪 Заведения",
    "🏪 Do'konlar",
    "🛍 Акции и магазины",
    "🛍 Aksiyalar va do'konlar",
    # Search legacy
    "🔍 Поиск",
    "🔍 Qidirish",
    # Cart
    "🛒 Корзина",
    "🛒 Savat",
    # Orders
    "📋 Мои заказы",
    "📋 Mening buyurtmalarim",
    "🧾 Заказы",
    "🧾 Buyurtmalar",
    # Profile
    "👤 Профиль",
    "👤 Profil",
}

@lru_cache(maxsize=1)
def _menu_labels() -> dict[str, set[str]]:
    """Return localized menu labels for RU and UZ."""
    keys = ["hot_offers", "search", "my_cart", "my_orders", "profile", "support"]
    labels: dict[str, set[str]] = {}
    for key in keys:
        labels[key] = {get_text("ru", key), get_text("uz", key)}
    return labels


def _strip(text: str | None) -> str:
    return (text or "").strip()


def fix_mojibake_text(text: str | bytes | None) -> str:
    """Fix cp1251/latin1-decoded UTF-8 text (mojibake) if detected."""
    if text is None:
        return ""
    if isinstance(text, bytes):
        try:
            text = text.decode("utf-8")
        except UnicodeDecodeError:
            text = text.decode("cp1251", errors="replace")
    original = str(text)
    for encoding in ("cp1251", "latin1", "cp866"):
        try:
            candidate = original.encode(encoding).decode("utf-8")
        except (UnicodeDecodeError, UnicodeEncodeError):
            continue
        if candidate != original and _strip(candidate):
            return candidate
    return original


def is_cart_button(text: str | None) -> bool:
    """Cart button matcher (supports counter suffix)."""
    stripped = _strip(text)
    if not stripped:
        return False
    count_pattern = r"(?: \(\d+(?:[.,]\d+)?\))?"
    for base in _menu_labels()["my_cart"] | {"🛒 Корзина", "🛒 Savat"}:
        if re.fullmatch(rf"{re.escape(base)}{count_pattern}", stripped):
            return True
    return False


def is_hot_offers_button(text: str | None) -> bool:
    stripped = _strip(text)
    if not stripped:
        return False
    return stripped in _menu_labels()["hot_offers"] or stripped in {
        "🥗 Еда со скидкой",
        "🥗 Chegirmali taomlar",
        "🛍 Акции и магазины",
        "🛍 Aksiyalar va do'konlar",
        "🏪 Горячее",
        "🏪 Issiq takliflar",
        "🏪 Акции до -70%",
        "🏪 -70% gacha aksiyalar",
        "🏪 Заведения",
        "🏪 Do'konlar",
    }


def is_search_button(text: str | None) -> bool:
    stripped = _strip(text)
    if not stripped:
        return False
    return stripped in _menu_labels()["search"] or stripped in {"🔍 Поиск", "🔍 Qidirish"}


def is_my_orders_button(text: str | None) -> bool:
    stripped = _strip(text)
    if not stripped:
        return False
    return stripped in _menu_labels()["my_orders"] or stripped in {
        "🧾 Заказы",
        "🧾 Buyurtmalar",
        "📋 Мои заказы",
        "📋 Mening buyurtmalarim",
        "📋 Заказы и бронирования",
        "📋 Buyurtmalar va bronlar",
    }


def is_profile_button(text: str | None) -> bool:
    stripped = _strip(text)
    if not stripped:
        return False
    return stripped in _menu_labels()["profile"] or stripped in {"👤 Профиль", "👤 Profil"}


def is_support_button(text: str | None) -> bool:
    stripped = _strip(text)
    if not stripped:
        return False
    return stripped in _menu_labels()["support"] or stripped in {"🆘 Поддержка", "🆘 Yordam"}


def is_partner_button(text: str | None) -> bool:
    stripped = _strip(text)
    if not stripped:
        return False
    return stripped in {
        get_text("ru", "become_partner"),
        get_text("uz", "become_partner"),
        get_text("ru", "partner_menu"),
        get_text("uz", "partner_menu"),
        get_text("ru", "switched_to_seller"),
        get_text("uz", "switched_to_seller"),
        "🏪 Стать партнером",
        "🏪 Меню партнера",
        "Меню партнера",
        "Режим: партнёр",
        "Режим: партнер",
        "Rejim: hamkor",
        "🏪 Hamkor bo'lish",
        "🏪 Hamkor bolish",
        "🏪 Hamkor menyusi",
    }


def is_customer_menu_button(text: str | None) -> bool:
    stripped = _strip(text)
    if not stripped:
        return False
    return stripped in {
        get_text("ru", "back_to_customer"),
        get_text("uz", "back_to_customer"),
        get_text("ru", "switched_to_customer"),
        get_text("uz", "switched_to_customer"),
        "🛒 Меню покупателя",
        "Меню покупателя",
        "🛒 Режим: покупатель",
        "Режим: покупатель",
        "Rejim: xaridor",
        "🛒 Rejim: xaridor",
        "🛒 Xaridor menyusi",
    }



def is_main_menu_button(text: str | None) -> bool:
    """Check if text is a main menu button (should exit FSM and handle separately)."""
    return any(
        (
            is_hot_offers_button(text),
            is_search_button(text),
            is_cart_button(text),
            is_my_orders_button(text),
            is_profile_button(text),
            is_support_button(text),
            is_partner_button(text),
            is_customer_menu_button(text),
            _strip(text) in MAIN_MENU_BUTTONS,
            _strip(text) in LEGACY_MAIN_MENU_BUTTONS,
        )
    )


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
                caption=_safe_caption(text), parse_mode=parse_mode, reply_markup=reply_markup
            )
        else:
            await message.edit_text(text, parse_mode=parse_mode, reply_markup=reply_markup)
        return True
    except Exception:
        # Message may be too old, already edited, or deleted
        return False


def get_system_error_text(lang: str = "ru") -> str:
    """Get localized system error text.

    Use this instead of hardcoded 'System error' strings.
    """
    from localization import get_text

    return get_text(lang, "system_error")


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


CITY_UZ_TO_RU = CORE_CITY_UZ_TO_RU

# Uzbekistan timezone (UTC+5)
UZB_TZ = timezone(timedelta(hours=5))


def normalize_city(city: str) -> str:
    """Convert city name to Russian format for database search."""
    return core_normalize_city(city)


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
    main_menu_seller: Callable[[str], Any] | None = None,
    main_menu_customer: Callable[[str], Any] | None = None,
) -> Any:
    """Return appropriate menu for user based on their store approval status and current mode.

    If main_menu_seller/main_menu_customer are not provided, imports them from app.keyboards.
    """
    # Import keyboards if not provided (avoids circular imports at module level)
    if main_menu_seller is None or main_menu_customer is None:
        from app.keyboards import main_menu_customer as mmc
        from app.keyboards import main_menu_seller as mms

        main_menu_seller = main_menu_seller or mms
        main_menu_customer = main_menu_customer or mmc

    user = db.get_user_model(user_id)
    if not user:
        return main_menu_customer(lang)

    role = user.role
    if role == "store_owner":
        role = "seller"
    has_active_store = has_approved_store(user_id, db)
    if role != "seller" and has_active_store:
        role = "seller"
        try:
            db.update_user_role(user_id, "seller")
        except Exception:
            pass

    if role == "seller" and not has_active_store:
        has_any_store = False
        try:
            stores = db.get_user_accessible_stores(user_id)
            has_any_store = bool(stores)
        except Exception:
            has_any_store = False
        if not has_any_store and hasattr(db, "get_user_stores"):
            try:
                stores = db.get_user_stores(user_id)
                has_any_store = bool(stores)
            except Exception:
                has_any_store = False

        if not has_any_store:
            try:
                db.update_user_role(user_id, "customer")
            except Exception:
                pass
            try:
                db.set_user_view_mode(user_id, "customer")
            except Exception:
                pass
            return main_menu_customer(lang)

        return main_menu_seller(lang, user_id=user_id)

    if role == "seller":
        return main_menu_seller(lang, user_id=user_id)

    return main_menu_customer(lang)


class RegistrationCheckMiddleware(BaseMiddleware):
    """Check that user exists (has account) before any action.

    Phone is collected during registration; checkout keeps a safety net.
    """

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
        allowed_callbacks = ["lang_ru", "lang_uz", "reg_lang_ru", "reg_lang_uz"]
        allowed_callback_patterns = [
            "book_",
            "order_delivery_",
            "store_info_",
            "store_offers_",
            "store_reviews_",
            "back_to_store_",
            "hot_offers_",
            "filter_",
            "select_city:",  # Allow city selection for new users
            "city_",  # Allow city callbacks
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

        # Only check if user exists, NOT if they have phone
        # Phone is requested during registration (checkout still validates)
        user = None
        if hasattr(self.db, "get_user_model"):
            user = self.db.get_user_model(user_id)
        elif hasattr(self.db, "get_user"):
            user = self.db.get_user(user_id)
        if not user:
            lang = "ru"
            logger.debug(
                "[Middleware] Blocking update for unregistered user %s (registration_required)",
                user_id,
            )
            if msg:
                await msg.answer(
                    self.get_text(lang, "registration_required"),
                    parse_mode="HTML",
                )
            elif cb:
                await cb.answer(self.get_text(lang, "registration_required"), show_alert=True)
            return

        return await handler(event, data)


# =============================================================================
# SAFE MESSAGE HELPERS
# =============================================================================


async def safe_edit_reply_markup(msg_like, **kwargs) -> None:
    """Edit reply markup if message is accessible (Message), otherwise ignore.

    Use this instead of defining _safe_edit_reply_markup() in each module.
    """
    from aiogram import types as _ai_types

    if isinstance(msg_like, _ai_types.Message):
        try:
            await msg_like.edit_reply_markup(**kwargs)
        except Exception:
            pass


async def safe_answer_or_send(msg_like, user_id: int, text: str, bot: Any = None, **kwargs) -> None:
    """Try to answer via message.answer, fallback to bot.send_message.

    Use this instead of defining _safe_answer_or_send() in each module.
    """
    from aiogram import types as _ai_types

    if isinstance(msg_like, _ai_types.Message):
        try:
            await msg_like.answer(text, **kwargs)
            return
        except Exception:
            pass
    # Fallback to bot-level send
    if bot:
        try:
            await bot.send_message(user_id, text, **kwargs)
        except Exception:
            pass


