"""Seller dashboard handlers - compact partner flow entry point."""
from __future__ import annotations

from typing import Any

from aiogram import F, Router, types
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.core.utils import get_field, get_store_field
from app.services.unified_order_service import OrderStatus
from database_protocol import DatabaseProtocol
from localization import get_text

router = Router(name="seller_dashboard")

# Module-level dependencies
db: DatabaseProtocol | None = None
bot: Any | None = None


def setup_dependencies(database: DatabaseProtocol, bot_instance: Any) -> None:
    """Setup module dependencies."""
    global db, bot
    db = database
    bot = bot_instance


class _MessageProxy:
    """Lightweight proxy to reuse message handlers from callback context."""

    def __init__(self, callback: types.CallbackQuery) -> None:
        self.from_user = callback.from_user
        self._callback = callback

    async def answer(self, *args: Any, **kwargs: Any) -> Any:
        if self._callback.message:
            return await self._callback.message.answer(*args, **kwargs)
        return await self._callback.bot.send_message(chat_id=self.from_user.id, *args, **kwargs)


def _normalize_status(raw: Any) -> str:
    status = str(raw or OrderStatus.PENDING).strip().lower()
    return OrderStatus.normalize(status)


def _get_dashboard_stats(user_id: int) -> tuple[int, dict[str, int]]:
    stores = db.get_user_accessible_stores(user_id) if db else []
    active_stores = [
        store
        for store in stores or []
        if get_store_field(store, "status") in ("active", "approved")
    ]
    counts = {"new": 0, "active": 0, "completed": 0, "cancelled": 0}

    from handlers.seller.management.orders import _get_all_orders

    pickup_orders, delivery_orders = _get_all_orders(db, user_id) if db else ([], [])
    for order in (pickup_orders or []) + (delivery_orders or []):
        status = _normalize_status(get_field(order, "order_status"))
        if status == OrderStatus.PENDING:
            counts["new"] += 1
        elif status in (OrderStatus.PREPARING, OrderStatus.READY, OrderStatus.DELIVERING):
            counts["active"] += 1
        elif status == OrderStatus.COMPLETED:
            counts["completed"] += 1
        elif status in (OrderStatus.CANCELLED, OrderStatus.REJECTED):
            counts["cancelled"] += 1

    return len(active_stores), counts


def _build_dashboard_keyboard(lang: str) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text=get_text(lang, "today_stats"), callback_data="seller_dashboard_stats")
    kb.button(text=get_text(lang, "analytics"), callback_data="seller_dashboard_analytics")
    kb.button(text=get_text(lang, "bulk_import"), callback_data="seller_dashboard_add_import")
    kb.button(text=get_text(lang, "store_settings"), callback_data="my_store_settings")
    kb.adjust(2, 2)
    return kb.as_markup()


def _build_dashboard_text(lang: str, store_count: int, counts: dict[str, int]) -> str:
    template = get_text(lang, "partner_dashboard")
    return template.format(
        stores=store_count,
        new=counts.get("new", 0),
        active=counts.get("active", 0),
        completed=counts.get("completed", 0),
        cancelled=counts.get("cancelled", 0),
    )


async def send_partner_dashboard(message: types.Message, user_id: int, lang: str) -> None:
    """Send partner dashboard summary with quick actions."""
    if not db:
        await message.answer(get_text(lang, "system_error"))
        return

    store_count, counts = _get_dashboard_stats(user_id)
    if store_count == 0:
        await message.answer(get_text(lang, "no_stores"))
        return

    text = _build_dashboard_text(lang, store_count, counts)
    await message.answer(text, parse_mode="HTML", reply_markup=_build_dashboard_keyboard(lang))


@router.message(
    F.text.in_(
        {
            get_text("ru", "partner_panel"),
            get_text("uz", "partner_panel"),
        }
    )
)
async def partner_panel(message: types.Message, state: FSMContext) -> None:
    """Open partner dashboard on demand."""
    await state.clear()
    if not message.from_user:
        return
    if not db:
        await message.answer(get_text("ru", "system_error"))
        return
    lang = db.get_user_language(message.from_user.id)
    await send_partner_dashboard(message, message.from_user.id, lang)


@router.callback_query(F.data == "seller_dashboard_orders")
async def dashboard_orders(callback: types.CallbackQuery, state: FSMContext) -> None:
    """Open seller orders from dashboard."""
    from handlers.seller.management.orders import seller_orders_main

    await seller_orders_main(_MessageProxy(callback), state)
    await callback.answer()


@router.callback_query(F.data == "seller_dashboard_items")
async def dashboard_items(callback: types.CallbackQuery, state: FSMContext) -> None:
    """Open seller offers from dashboard."""
    from handlers.seller.management.offers import my_offers

    await my_offers(_MessageProxy(callback), state)
    await callback.answer()


@router.callback_query(F.data == "seller_dashboard_add_full")
async def dashboard_add_full(callback: types.CallbackQuery, state: FSMContext) -> None:
    """Start full add flow from dashboard."""
    from handlers.seller.create_offer import add_offer_start

    await add_offer_start(_MessageProxy(callback), state)
    await callback.answer()


@router.callback_query(F.data == "seller_dashboard_add_quick")
async def dashboard_add_quick(callback: types.CallbackQuery, state: FSMContext) -> None:
    """Start quick add flow from dashboard."""
    from handlers.seller.create_offer import quick_add_start

    await quick_add_start(_MessageProxy(callback), state)
    await callback.answer()


@router.callback_query(F.data == "seller_dashboard_add_import")
async def dashboard_add_import(callback: types.CallbackQuery, state: FSMContext) -> None:
    """Start bulk import flow from dashboard."""
    from handlers.seller.bulk_import import start_bulk_import

    await start_bulk_import(_MessageProxy(callback), state)
    await callback.answer()


@router.callback_query(F.data == "seller_dashboard_stats")
async def dashboard_stats(callback: types.CallbackQuery) -> None:
    """Show partner stats from dashboard."""
    from handlers.seller.stats import partner_stats_today

    await partner_stats_today(_MessageProxy(callback))
    await callback.answer()


@router.callback_query(F.data == "seller_dashboard_analytics")
async def dashboard_analytics(callback: types.CallbackQuery) -> None:
    """Open partner analytics from dashboard."""
    from handlers.seller.analytics import show_analytics

    await show_analytics(_MessageProxy(callback))
    await callback.answer()
