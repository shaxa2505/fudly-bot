"""
Unified FSM Cancel Handler.

Provides consistent cancellation behavior across all FSM flows:
- Single handler for all cancel actions
- Proper cleanup with user feedback
- Analytics tracking for abandoned flows
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from aiogram import F, Router, types
from aiogram.fsm.context import FSMContext

if TYPE_CHECKING:
    from database_protocol import DatabaseProtocol

logger = logging.getLogger("fudly.fsm")

router = Router(name="fsm_cancel")

# All possible cancel texts (Russian and Uzbek)
CANCEL_TEXTS = frozenset(
    {
        # Buttons
        "❌ Отмена",
        "❌ Bekor qilish",
        "❌ Bekor",
        # Commands
        "/cancel",
        # Plain text
        "Отмена",
        "отмена",
        "Bekor",
        "bekor",
        "Cancel",
        "cancel",
    }
)

# Callback data patterns for cancel
CANCEL_CALLBACKS = frozenset(
    {
        "cancel",
        "create_cancel",
        "book_cancel",
        "register_cancel",
        "edit_cancel",
        "search_cancel",
        "cancel_booking_flow",
    }
)

# Human-readable flow names
FLOW_NAMES = {
    "ru": {
        "CreateOffer": "Создание товара",
        "BulkCreate": "Массовое создание",
        "BookOffer": "Бронирование",
        "OrderDelivery": "Оформление доставки",
        "RegisterStore": "Регистрация магазина",
        "Registration": "Регистрация",
        "EditOffer": "Редактирование товара",
        "Search": "Поиск",
        "ChangeCity": "Смена города",
        "ConfirmOrder": "Подтверждение заказа",
        "CourierHandover": "Передача курьеру",
    },
    "uz": {
        "CreateOffer": "Mahsulot yaratish",
        "BulkCreate": "Ko'p yaratish",
        "BookOffer": "Band qilish",
        "OrderDelivery": "Yetkazib berishni rasmiylashtirish",
        "RegisterStore": "Do'konni ro'yxatdan o'tkazish",
        "Registration": "Ro'yxatdan o'tish",
        "EditOffer": "Mahsulotni tahrirlash",
        "Search": "Qidirish",
        "ChangeCity": "Shaharni o'zgartirish",
        "ConfirmOrder": "Buyurtmani tasdiqlash",
        "CourierHandover": "Kuryerga topshirish",
    },
}


def is_cancel_text(text: str | None) -> bool:
    """Check if text is a cancel command."""
    if not text:
        return False
    return text.strip() in CANCEL_TEXTS


def is_cancel_callback(data: str | None) -> bool:
    """Check if callback data is a cancel action."""
    if not data:
        return False
    return data in CANCEL_CALLBACKS or data.endswith("_cancel")


def get_flow_name(state_str: str | None, lang: str) -> str:
    """Extract human-readable flow name from state string."""
    if not state_str:
        return FLOW_NAMES.get(lang, FLOW_NAMES["ru"]).get("default", "Действие")

    # State format: "FlowName:state_name"
    flow_class = state_str.split(":")[0]
    names = FLOW_NAMES.get(lang, FLOW_NAMES["ru"])
    return names.get(flow_class, flow_class)


async def cancel_current_flow(
    state: FSMContext,
    lang: str,
    user_id: int,
    reason: str = "user_cancelled",
) -> str | None:
    """
    Cancel current FSM flow and return cancelled flow name.

    Args:
        state: FSMContext instance
        lang: User language
        user_id: User ID for logging
        reason: Cancellation reason for analytics

    Returns:
        Flow name if there was active flow, None otherwise
    """
    current_state = await state.get_state()

    if not current_state:
        return None

    # Get flow name before clearing
    flow_name = get_flow_name(current_state, lang)

    # Log for analytics
    data = await state.get_data()
    logger.info(
        f"FSM cancelled: user={user_id}, flow={current_state}, "
        f"reason={reason}, data_keys={list(data.keys())}"
    )

    # Clear the state
    await state.clear()

    return flow_name


def get_cancel_message(flow_name: str | None, lang: str) -> str:
    """Generate appropriate cancel message."""
    if not flow_name:
        if lang == "uz":
            return "❌ Bekor qilindi"
        return "❌ Отменено"

    if lang == "uz":
        return f"❌ {flow_name} bekor qilindi"
    return f"❌ {flow_name} отменено"


def setup(dp_or_router: Any, db: DatabaseProtocol, get_menu_func: Any) -> None:
    """
    Setup cancel handlers.

    Args:
        dp_or_router: Dispatcher or Router to attach handlers
        db: Database instance
        get_menu_func: Function to get user's menu keyboard
    """

    @router.message(F.text.in_(CANCEL_TEXTS))
    async def handle_cancel_text(message: types.Message, state: FSMContext) -> None:
        """Handle cancel via text message."""
        if not message.from_user:
            return

        user_id = message.from_user.id
        lang = db.get_user_language(user_id)

        flow_name = await cancel_current_flow(state, lang, user_id, "text_cancel")

        if flow_name:
            msg = get_cancel_message(flow_name, lang)
            await message.answer(msg, reply_markup=get_menu_func(user_id, lang))
        # If no active flow, don't respond (let other handlers process)

    @router.callback_query(lambda c: is_cancel_callback(c.data))
    async def handle_cancel_callback(callback: types.CallbackQuery, state: FSMContext) -> None:
        """Handle cancel via inline button."""
        if not callback.from_user:
            await callback.answer()
            return

        user_id = callback.from_user.id
        lang = db.get_user_language(user_id)

        flow_name = await cancel_current_flow(state, lang, user_id, f"callback_{callback.data}")
        msg = get_cancel_message(flow_name, lang)

        # Try to edit the message
        if callback.message and isinstance(callback.message, types.Message):
            try:
                await callback.message.edit_text(msg)
            except Exception:
                await callback.message.answer(msg, reply_markup=get_menu_func(user_id, lang))

        await callback.answer()

    # Register router
    dp_or_router.include_router(router)


# Export utilities for use in other handlers
__all__ = [
    "is_cancel_text",
    "is_cancel_callback",
    "cancel_current_flow",
    "get_cancel_message",
    "CANCEL_TEXTS",
    "CANCEL_CALLBACKS",
    "setup",
    "router",
]
