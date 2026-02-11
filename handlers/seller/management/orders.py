"""Seller order management - unified with new notification system.

Shows all orders in ONE message with inline pagination.
Uses UnifiedOrderService for status changes and notifications.
"""
from __future__ import annotations

from typing import Any
import json
from datetime import datetime

from aiogram import F, Router, types
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.domain.order_labels import status_label
from app.core.utils import UZB_TZ, get_order_field, to_uzb_datetime
from app.services.unified_order_service import (
    OrderStatus,
    PaymentStatus,
    get_unified_order_service,
    init_unified_order_service,
)
from handlers.common.utils import can_manage_store, html_escape
from handlers.bookings.utils import format_price
from localization import get_text
from logging_config import logger

from .utils import get_db, get_store_field

router = Router()

PAGE_SIZE = 5


def _get_field(entity: Any, field: str, default: Any = None) -> Any:
    """Safely get field from dict or object."""
    if isinstance(entity, dict):
        return entity.get(field, default)
    return getattr(entity, field, default)


def _is_paid_online_order(order: Any) -> bool:
    payment_method = _get_field(order, "payment_method")
    payment_status = _get_field(order, "payment_status")
    payment_proof_photo_id = _get_field(order, "payment_proof_photo_id")

    method_norm = PaymentStatus.normalize_method(payment_method)
    if method_norm not in ("click", "payme"):
        return False
    status_norm = PaymentStatus.normalize(
        payment_status,
        payment_method=payment_method,
        payment_proof_photo_id=payment_proof_photo_id,
    )
    return status_norm == PaymentStatus.CONFIRMED


def _shorten(text: Any, limit: int = 28) -> str:
    value = str(text) if text is not None else ""
    if len(value) <= limit:
        return value
    if limit <= 3:
        return value[:limit]
    return value[: max(0, limit - 3)] + "..."


def _parse_dt(value: Any) -> datetime | None:
    return to_uzb_datetime(value)


def _format_time(value: Any) -> str | None:
    base = _parse_dt(value)
    if not base:
        return None
    return base.strftime("%H:%M")


def _status_dot(status: str) -> str:
    return {
        OrderStatus.PENDING: "🟡",
        OrderStatus.PREPARING: "🟢",
        OrderStatus.READY: "🟣",
        OrderStatus.DELIVERING: "🟣",
        OrderStatus.COMPLETED: "⚪",
        OrderStatus.REJECTED: "⚪",
        OrderStatus.CANCELLED: "⚪",
    }.get(status, "⚪")


def _format_quantity_short(value: Any) -> str:
    try:
        qty = float(value)
    except (TypeError, ValueError):
        return str(value) if value is not None else "1"
    if qty.is_integer():
        return str(int(qty))
    return f"{qty:.2f}".rstrip("0").rstrip(".")


def _extract_cart_items(order: Any) -> list:
    raw = get_order_field(order, "cart_items")
    if not raw:
        return []
    try:
        items = json.loads(raw) if isinstance(raw, str) else raw
    except Exception:
        return []
    return items if isinstance(items, list) else []


def _get_order_title_qty(order: Any, lang: str) -> tuple[str, float]:
    title = (
        get_order_field(order, "item_title")
        or get_order_field(order, "offer_title")
        or get_order_field(order, "title")
        or get_text(lang, "label_item")
    )
    qty = get_order_field(order, "quantity") or 1
    cart_items = _extract_cart_items(order)
    if cart_items:
        first = cart_items[0] or {}
        title = first.get("title") or title
        qty = first.get("quantity", qty) or qty
        if len(cart_items) > 1:
            more = get_text(lang, "label_items_more", count=len(cart_items) - 1)
            title = f"{title} {more}"
    try:
        qty_value = float(qty)
    except (TypeError, ValueError):
        qty_value = 1.0
    return title, qty_value


def _get_total_price(order: Any, qty_value: float) -> int:
    total = get_order_field(order, "total_price")
    if total is not None and total != "":
        try:
            return int(float(total))
        except (TypeError, ValueError):
            pass
    item_price = (
        get_order_field(order, "item_price")
        or get_order_field(order, "discount_price")
        or get_order_field(order, "offer_price")
    )
    try:
        return int(float(item_price) * float(qty_value))
    except (TypeError, ValueError):
        return 0


def _build_entry(order: Any, order_type: str) -> dict[str, Any]:
    status_raw = (
        get_order_field(order, "order_status")
        or get_order_field(order, "status")
        or OrderStatus.PENDING
    )
    status_norm = OrderStatus.normalize(str(status_raw).strip().lower())
    return {
        "order": order,
        "order_type": order_type,
        "status_raw": status_raw,
        "status": status_norm,
        "created_at": _parse_dt(get_order_field(order, "created_at")),
        "updated_at": _parse_dt(get_order_field(order, "updated_at")),
    }


def _build_entries(pickup_orders: list, delivery_orders: list) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for order in pickup_orders:
        entries.append(_build_entry(order, "pickup"))
    for order in delivery_orders:
        entries.append(_build_entry(order, "delivery"))
    return entries


def _count_statuses(entries: list[dict[str, Any]]) -> dict[str, int]:
    counts = {"pending": 0, "in_work": 0, "ready": 0, "history": 0}
    for entry in entries:
        status = entry["status"]
        if status == OrderStatus.PENDING:
            counts["pending"] += 1
        elif status == OrderStatus.PREPARING:
            counts["in_work"] += 1
        elif status in (OrderStatus.READY, OrderStatus.DELIVERING):
            counts["ready"] += 1
        elif status in (OrderStatus.COMPLETED, OrderStatus.REJECTED, OrderStatus.CANCELLED):
            counts["history"] += 1
    return counts


def _filter_entries(entries: list[dict[str, Any]], filter_type: str) -> list[dict[str, Any]]:
    status_map = {
        "pending": {OrderStatus.PENDING},
        "in_work": {OrderStatus.PREPARING},
        "ready": {OrderStatus.READY, OrderStatus.DELIVERING},
        "history": {OrderStatus.COMPLETED, OrderStatus.REJECTED, OrderStatus.CANCELLED},
        "active": {
            OrderStatus.PREPARING,
            OrderStatus.READY,
            OrderStatus.DELIVERING,
        },
        "completed": {OrderStatus.COMPLETED, OrderStatus.REJECTED, OrderStatus.CANCELLED},
    }
    targets = status_map.get(filter_type, status_map["pending"])
    return [entry for entry in entries if entry["status"] in targets]


def _sort_entries(entries: list[dict[str, Any]], filter_type: str) -> list[dict[str, Any]]:
    def _sort_key(entry: dict[str, Any]) -> datetime:
        if filter_type in ("history", "completed"):
            base = entry.get("updated_at") or entry.get("created_at")
        else:
            base = entry.get("created_at")
        return base or datetime.min.replace(tzinfo=UZB_TZ)

    return sorted(entries, key=_sort_key, reverse=True)


def _filter_header_key(filter_type: str) -> str:
    mapping = {
        "pending": "partner_orders_filter_new",
        "in_work": "partner_orders_filter_in_work",
        "ready": "partner_orders_filter_ready",
        "history": "partner_orders_filter_history",
        "active": "partner_orders_filter_in_work",
        "completed": "partner_orders_filter_history",
    }
    return mapping.get(filter_type, "partner_orders_filter_new")


def _status_to_filter(status: str) -> str:
    if status == OrderStatus.PENDING:
        return "pending"
    if status == OrderStatus.PREPARING:
        return "in_work"
    if status in (OrderStatus.READY, OrderStatus.DELIVERING):
        return "ready"
    return "history"


def _partner_status_label(status_raw: Any, lang: str, order_type: str) -> str:
    raw = str(status_raw or "").strip().lower()
    normalized = OrderStatus.normalize(raw or OrderStatus.PENDING)

    if raw == "confirmed":
        return get_text(lang, "status_confirmed")
    if normalized == OrderStatus.PREPARING:
        return get_text(lang, "partner_status_preparing")
    if normalized == OrderStatus.READY and order_type == "delivery":
        return get_text(lang, "seller_status_ready_delivery")
    if normalized == OrderStatus.DELIVERING and order_type == "delivery":
        return get_text(lang, "seller_status_handed_over")
    if normalized == OrderStatus.REJECTED:
        return get_text(lang, "partner_status_rejected")
    if normalized == OrderStatus.CANCELLED:
        return get_text(lang, "partner_status_cancelled")
    return status_label(normalized, lang, order_type)


def _format_order_card(entry: dict[str, Any], lang: str) -> list[str]:
    order = entry["order"]
    order_type = entry["order_type"]
    order_id = get_order_field(order, "order_id") or (
        order[0] if isinstance(order, (list, tuple)) and len(order) > 0 else 0
    )
    status = entry["status"]
    type_label = (
        get_text(lang, "order_type_delivery")
        if order_type == "delivery"
        else get_text(lang, "order_type_pickup")
    )
    icon = "🚚" if order_type == "delivery" else _status_dot(status)

    title, qty_value = _get_order_title_qty(order, lang)
    qty_text = _format_quantity_short(qty_value)
    title_safe = html_escape(_shorten(title))
    lines = [f"<b>{icon} #{order_id} {type_label}</b>", f"{title_safe} ×{qty_text}"]

    total_price = _get_total_price(order, qty_value)
    lines.append(format_price(total_price, lang))

    if order_type == "delivery":
        address = get_order_field(order, "delivery_address") or ""
        address_safe = (
            html_escape(_shorten(address, 36)) if address else get_text(lang, "value_unknown")
        )
        lines.append(f"{get_text(lang, 'address')}: {address_safe}")
    else:
        created_time = _format_time(entry.get("created_at")) or get_text(lang, "value_unknown")
        lines.append(f"{get_text(lang, 'label_created')}: {created_time}")

    return lines


def _build_main_text(counts: dict[str, int], lang: str) -> str:
    lines: list[str] = [
        f"<b>{get_text(lang, 'partner_orders_header')}</b>",
        "",
        get_text(lang, "partner_orders_summary_pending", count=counts.get("pending", 0)),
        get_text(lang, "partner_orders_summary_in_work", count=counts.get("in_work", 0)),
        get_text(lang, "partner_orders_summary_ready", count=counts.get("ready", 0)),
        get_text(lang, "partner_orders_summary_history", count=counts.get("history", 0)),
    ]
    return "\n".join(lines)


def _build_list_text(
    entries: list[dict[str, Any]], lang: str, filter_type: str
) -> str:
    lines: list[str] = []

    header_key = _filter_header_key(filter_type)
    lines.append(f"<b>{get_text(lang, header_key)}</b>")
    lines.append("")

    if not entries:
        lines.append(f"<i>{get_text(lang, 'partner_orders_list_empty')}</i>")
    else:
        for entry in entries:
            lines.extend(_format_order_card(entry, lang))
            lines.append("")

    while lines and not lines[-1].strip():
        lines.pop()
    return "\n".join(lines)


def _build_main_keyboard(lang: str) -> InlineKeyboardBuilder:
    kb = InlineKeyboardBuilder()
    filter_buttons = [
        ("seller_filter_pending", get_text(lang, "partner_orders_btn_new")),
        ("seller_filter_in_work", get_text(lang, "partner_orders_btn_in_work")),
        ("seller_filter_ready", get_text(lang, "partner_orders_btn_ready")),
        ("seller_filter_history", get_text(lang, "partner_orders_btn_history")),
    ]

    row: list[types.InlineKeyboardButton] = []
    for cb, text_label in filter_buttons:
        row.append(types.InlineKeyboardButton(text=text_label, callback_data=cb))
        if len(row) == 2:
            kb.row(*row, width=2)
            row = []
    if row:
        kb.row(*row, width=2)

    kb.row(
        types.InlineKeyboardButton(
            text=get_text(lang, "partner_orders_btn_refresh"),
            callback_data="seller_orders_refresh:main",
        )
    )

    return kb


def _build_list_keyboard(
    entries: list[dict[str, Any]],
    lang: str,
    filter_type: str,
    page: int,
    total_pages: int,
) -> InlineKeyboardBuilder:
    kb = InlineKeyboardBuilder()

    order_buttons: list[types.InlineKeyboardButton] = []
    for entry in entries:
        order = entry["order"]
        order_id = get_order_field(order, "order_id") or (
            order[0] if isinstance(order, (list, tuple)) and len(order) > 0 else 0
        )
        order_buttons.append(
            types.InlineKeyboardButton(
                text=f"#{order_id}",
                callback_data=f"seller_view_o_{order_id}:{filter_type}:{page}",
            )
        )

    if order_buttons:
        kb.row(*order_buttons, width=min(len(order_buttons), PAGE_SIZE))

    prev_page = page - 1 if page > 1 else 1
    next_page = page + 1 if page < total_pages else total_pages

    kb.row(
        types.InlineKeyboardButton(
            text="??",
            callback_data=f"seller_orders_page:{filter_type}:{prev_page}",
        ),
        types.InlineKeyboardButton(
            text=get_text(lang, "partner_orders_page", page=page, total=total_pages),
            callback_data="seller_orders_page_info",
        ),
        types.InlineKeyboardButton(
            text="??",
            callback_data=f"seller_orders_page:{filter_type}:{next_page}",
        ),
        width=3,
    )

    kb.row(
        types.InlineKeyboardButton(
            text=get_text(lang, "partner_orders_btn_refresh"),
            callback_data=f"seller_orders_refresh:{filter_type}:{page}",
        )
    )

    kb.row(
        types.InlineKeyboardButton(
            text=get_text(lang, "partner_order_btn_back"),
            callback_data="seller_orders_main",
        )
    )

    return kb


def _get_all_orders(db, user_id: int) -> tuple[list, list]:
    """
    Get all pickup and delivery orders for seller's stores (v24+ unified orders).
    Returns (pickup_orders, delivery_orders) for compatibility with existing code.
    """
    stores = db.get_user_accessible_stores(user_id) or []

    pickup_orders = []
    delivery_orders = []

    for store in stores:
        store_id = get_store_field(store, "store_id")
        if not store_id:
            continue

        # v24+: all orders in unified table
        orders = db.get_store_orders(store_id) or []

        visible_orders = []
        for order in orders:
            payment_method = _get_field(order, "payment_method")
            payment_status = _get_field(order, "payment_status")
            payment_proof_photo_id = _get_field(order, "payment_proof_photo_id")

            if PaymentStatus.is_cleared(
                payment_status,
                payment_method=payment_method,
                payment_proof_photo_id=payment_proof_photo_id,
            ):
                visible_orders.append(order)

        # Split by order_type for display compatibility
        for order in visible_orders:
            order_type = _get_field(order, "order_type")
            if not order_type:
                delivery_address = _get_field(order, "delivery_address")
                order_type = "delivery" if delivery_address else "pickup"
            if order_type == "pickup":
                pickup_orders.append(order)
            else:
                delivery_orders.append(order)

    return pickup_orders, delivery_orders


def _build_main_view(user_id: int, lang: str) -> tuple[str, InlineKeyboardBuilder]:
    db = get_db()
    pickup_orders, delivery_orders = _get_all_orders(db, user_id)
    entries = _build_entries(pickup_orders, delivery_orders)
    counts = _count_statuses(entries)

    text = _build_main_text(counts, lang)
    kb = _build_main_keyboard(lang)
    return text, kb


def _build_list_view(
    user_id: int, lang: str, filter_type: str, page: int | str | None = 1
) -> tuple[str, InlineKeyboardBuilder]:
    db = get_db()
    pickup_orders, delivery_orders = _get_all_orders(db, user_id)
    entries = _build_entries(pickup_orders, delivery_orders)
    filtered_entries = _filter_entries(entries, filter_type)
    sorted_entries = _sort_entries(filtered_entries, filter_type)

    total_count = len(sorted_entries)
    total_pages = max(1, (total_count + PAGE_SIZE - 1) // PAGE_SIZE)
    try:
        current_page = int(page) if page is not None else 1
    except (TypeError, ValueError):
        current_page = 1
    current_page = max(1, min(current_page, total_pages))

    start_index = (current_page - 1) * PAGE_SIZE
    page_entries = sorted_entries[start_index : start_index + PAGE_SIZE]

    text = _build_list_text(page_entries, lang, filter_type)
    kb = _build_list_keyboard(page_entries, lang, filter_type, current_page, total_pages)
    return text, kb


# =============================================================================
# MAIN VIEW
# =============================================================================


@router.message(
    F.text.contains("Заказы партнёра")
    | F.text.contains("Заказы продавца")
    | F.text.contains("Buyurtmalar (sotuvchi)")
    | F.text.contains(get_text("ru", "orders"))
    | F.text.contains(get_text("uz", "orders"))
)
async def seller_orders_main(message: types.Message, state: FSMContext) -> Any:
    """Main seller orders view - single message."""
    db = get_db()

    await state.clear()

    try:
        stores = db.get_user_accessible_stores(message.from_user.id)
        if not stores:
            raise ValueError("No stores")
    except Exception as e:
        # If seller has no accessible stores, show a friendly message instead of failing silently.
        logger.debug(f"seller_orders skipped: {e}")
        try:
            lang = db.get_user_language(message.from_user.id)
        except Exception:
            lang = "ru"

        if lang == "uz":
            text = (
                "Sizda hali tasdiqlangan do'kon yo'q.\n"
                "Hamkor sifatida buyurtmalarni boshqarish uchun profil bo'limida ro'yxatdan o'tishni yakunlang."
            )
        else:
            text = (
                "У вас пока нет одобренного магазина.\n"
                "Чтобы управлять заказами как партнёр, завершите регистрацию в разделе профиля."
            )

        await message.answer(text)
        return

    lang = db.get_user_language(message.from_user.id)
    text, kb = _build_main_view(message.from_user.id, lang)

    await message.answer(text, parse_mode="HTML", reply_markup=kb.as_markup())


@router.callback_query(F.data == "seller_orders_main")
async def seller_orders_main_callback(callback: types.CallbackQuery) -> None:
    """Return to main orders summary screen."""
    db = get_db()
    lang = db.get_user_language(callback.from_user.id)

    text, kb = _build_main_view(callback.from_user.id, lang)

    try:
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=kb.as_markup())
    except Exception:
        pass
    await callback.answer()


@router.callback_query(F.data.startswith("seller_orders_refresh"))
async def seller_orders_refresh(callback: types.CallbackQuery) -> None:
    """Refresh orders list (v24+ unified orders)."""
    db = get_db()
    lang = db.get_user_language(callback.from_user.id)

    data = callback.data or ""
    parts = data.split(":")

    view = "main"
    filter_type = "pending"
    page = 1

    if len(parts) >= 2 and parts[1]:
        if parts[1] == "main":
            view = "main"
        else:
            view = "list"
            filter_type = parts[1]
            if len(parts) >= 3:
                try:
                    page = int(parts[2])
                except ValueError:
                    page = 1

    if view == "main":
        text, kb = _build_main_view(callback.from_user.id, lang)
    else:
        text, kb = _build_list_view(callback.from_user.id, lang, filter_type, page)

    try:
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=kb.as_markup())
    except Exception:
        pass

    await callback.answer()


# =============================================================================
# PAGINATION
# =============================================================================


@router.callback_query(F.data.startswith("seller_orders_page:"))
async def seller_orders_page(callback: types.CallbackQuery) -> None:
    """Switch orders list page."""
    db = get_db()
    lang = db.get_user_language(callback.from_user.id)

    data = callback.data or ""
    parts = data.split(":")
    filter_type = parts[1] if len(parts) > 1 and parts[1] else "pending"
    try:
        page = int(parts[2]) if len(parts) > 2 else 1
    except ValueError:
        page = 1

    text, kb = _build_list_view(callback.from_user.id, lang, filter_type, page)

    try:
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=kb.as_markup())
    except Exception:
        pass
    await callback.answer()


@router.callback_query(F.data == "seller_orders_page_info")
async def seller_orders_page_info(callback: types.CallbackQuery) -> None:
    """No-op for page indicator button."""
    await callback.answer()


# =============================================================================
# FILTERS
# =============================================================================


@router.callback_query(F.data == "seller_filter_pending")
async def seller_filter_pending(callback: types.CallbackQuery) -> None:
    """Show pending orders."""
    db = get_db()
    lang = db.get_user_language(callback.from_user.id)

    text, kb = _build_list_view(callback.from_user.id, lang, "pending", 1)

    try:
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=kb.as_markup())
    except Exception:
        pass
    await callback.answer()


@router.callback_query(F.data == "seller_filter_in_work")
async def seller_filter_in_work(callback: types.CallbackQuery) -> None:
    """Show in-work orders (confirmed/preparing)."""
    db = get_db()
    lang = db.get_user_language(callback.from_user.id)

    text, kb = _build_list_view(callback.from_user.id, lang, "in_work", 1)

    try:
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=kb.as_markup())
    except Exception:
        pass
    await callback.answer()


@router.callback_query(F.data == "seller_filter_ready")
async def seller_filter_ready(callback: types.CallbackQuery) -> None:
    """Show ready orders (ready/delivering)."""
    db = get_db()
    lang = db.get_user_language(callback.from_user.id)

    text, kb = _build_list_view(callback.from_user.id, lang, "ready", 1)

    try:
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=kb.as_markup())
    except Exception:
        pass
    await callback.answer()


@router.callback_query(F.data == "seller_filter_history")
async def seller_filter_history(callback: types.CallbackQuery) -> None:
    """Show history orders."""
    db = get_db()
    lang = db.get_user_language(callback.from_user.id)

    text, kb = _build_list_view(callback.from_user.id, lang, "history", 1)

    try:
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=kb.as_markup())
    except Exception:
        pass
    await callback.answer()


@router.callback_query(F.data.startswith("seller_history_more_"))
async def seller_history_more(callback: types.CallbackQuery) -> None:
    """Show more history orders (pagination)."""
    db = get_db()
    lang = db.get_user_language(callback.from_user.id)

    try:
        offset = int(callback.data.split("_")[-1])
    except Exception:
        offset = 0
    page = max(1, offset // PAGE_SIZE + 1)

    text, kb = _build_list_view(callback.from_user.id, lang, "history", page)

    try:
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=kb.as_markup())
    except Exception:
        pass
    await callback.answer()


@router.callback_query(F.data == "seller_filter_active")
async def seller_filter_active(callback: types.CallbackQuery) -> None:
    """Show active orders."""
    db = get_db()
    lang = db.get_user_language(callback.from_user.id)

    text, kb = _build_list_view(callback.from_user.id, lang, "in_work", 1)

    try:
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=kb.as_markup())
    except Exception:
        pass
    await callback.answer()


@router.callback_query(F.data == "seller_filter_completed")
async def seller_filter_completed(callback: types.CallbackQuery) -> None:
    """Show completed orders."""
    db = get_db()
    lang = db.get_user_language(callback.from_user.id)

    text, kb = _build_list_view(callback.from_user.id, lang, "history", 1)

    try:
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=kb.as_markup())
    except Exception:
        pass
    await callback.answer()


# =============================================================================
# VIEW BOOKING DETAIL
# =============================================================================


@router.callback_query(F.data.startswith("seller_view_b_"))
async def seller_view_booking(callback: types.CallbackQuery) -> None:
    """Legacy pickup view: redirect to unified order view."""
    booking_id = callback.data.split("_")[-1]
    callback.data = f"seller_view_o_{booking_id}"
    await seller_view_order(callback)


# =============================================================================
# VIEW ORDER DETAIL
# =============================================================================


@router.callback_query(F.data.startswith("seller_view_o_"))
async def seller_view_order(callback: types.CallbackQuery) -> None:
    """View order details with action buttons."""
    db = get_db()
    lang = db.get_user_language(callback.from_user.id)

    data = callback.data or ""
    parts = data.split(":")
    base = parts[0]
    filter_type = parts[1] if len(parts) > 1 and parts[1] else None
    try:
        page = int(parts[2]) if len(parts) > 2 else 1
    except ValueError:
        page = 1

    try:
        order_id = int(base.split("_")[-1])
    except ValueError:
        await callback.answer(
            "Noto'g'ri so'rov" if lang == "uz" else "Неверный запрос", show_alert=True
        )
        return

    order = db.get_order(order_id)
    if not order:
        await callback.answer(
            "Topilmadi" if lang == "uz" else "Заказ не найден", show_alert=True
        )
        return

    store_id = _get_field(order, "store_id")
    if not store_id:
        offer_id = _get_field(order, "offer_id")
        offer = db.get_offer(offer_id) if offer_id else None
        store_id = _get_field(offer, "store_id") if offer else None
    store = db.get_store(store_id) if store_id else None
    if not can_manage_store(db, store_id, callback.from_user.id, store=store):
        await callback.answer(get_text(lang, "no_access"), show_alert=True)
        return

    status_raw = (
        get_order_field(order, "order_status")
        or get_order_field(order, "status")
        or OrderStatus.PENDING
    )
    status = OrderStatus.normalize(str(status_raw).strip().lower())
    if not filter_type:
        filter_type = _status_to_filter(status)
    delivery_address = get_order_field(order, "delivery_address") or ""
    pickup_code = get_order_field(order, "pickup_code") or ""

    order_type = get_order_field(order, "order_type")
    if not order_type:
        order_type = "delivery" if delivery_address else "pickup"
    is_delivery = order_type in ("delivery", "taxi")
    user_id = get_order_field(order, "user_id")

    title, qty_value = _get_order_title_qty(order, lang)
    qty_text = _format_quantity_short(qty_value)
    total_price = _get_total_price(order, qty_value)

    customer = db.get_user_model(user_id) if user_id else None
    customer_default = get_text(lang, "label_customer")
    customer_name = customer.first_name if customer and customer.first_name else customer_default
    customer_phone = (
        customer.phone if customer and customer.phone else get_text(lang, "value_unknown")
    )

    status_text = _partner_status_label(status_raw, lang, "delivery" if is_delivery else "pickup")

    type_label = (
        get_text(lang, "order_type_delivery")
        if is_delivery
        else get_text(lang, "order_type_pickup")
    )

    title_safe = html_escape(title)
    customer_name_safe = html_escape(customer_name)
    address_safe = html_escape(delivery_address) if delivery_address else get_text(lang, "value_unknown")

    items = _extract_cart_items(order)
    items_lines: list[str] = []
    if items:
        for item in items:
            item_title = html_escape(item.get("title") or title)
            item_qty = _format_quantity_short(item.get("quantity", 1))
            items_lines.append(f"• {item_title} ×{item_qty}")
    else:
        items_lines.append(f"• {title_safe} ×{qty_text}")

    lines = [
        f"<b>📦 {get_text(lang, 'label_order')} #{order_id}</b>",
        f"{get_text(lang, 'label_order_type')}: {type_label}",
        f"{get_text(lang, 'label_status')}: <b>{status_text}</b>",
        "",
        f"🛒 {get_text(lang, 'label_items')}:",
        *items_lines,
        "",
        f"💰 {get_text(lang, 'label_amount')}: {format_price(total_price, lang)}",
        "",
        f"👤 {get_text(lang, 'label_customer')}: {customer_name_safe}",
        f"📞 <code>{html_escape(customer_phone)}</code>",
    ]

    if is_delivery:
        lines.append(f"📍 {get_text(lang, 'address')}: {address_safe}")
    elif pickup_code:
        code_label = get_text(lang, "label_code")
        lines.append(f"🔐 {code_label}: <b>{html_escape(pickup_code)}</b>")

    text = "\n".join(lines)

    kb = InlineKeyboardBuilder()

    if status == OrderStatus.PENDING:
        kb.button(
            text="✅ Qabul qilish" if lang == "uz" else "✅ Принять",
            callback_data=f"order_confirm_{order_id}",
        )
        kb.button(
            text="❌ Rad etish" if lang == "uz" else "❌ Отклонить",
            callback_data=f"order_reject_{order_id}",
        )
    elif status == OrderStatus.PREPARING:
        if is_delivery:
            kb.button(
                text="🚚 Topshirishga tayyor" if lang == "uz" else "🚚 Готово к доставке",
                callback_data=f"order_ready_{order_id}",
            )
        else:
            kb.button(
                text="✅ Olib ketishga tayyor" if lang == "uz" else "✅ Готово к выдаче",
                callback_data=f"order_ready_{order_id}",
            )
        kb.button(
            text="🚫 Bekor" if lang == "uz" else "🚫 Отменить",
            callback_data=f"order_cancel_seller_{order_id}",
        )

    elif status == OrderStatus.READY:
        if is_delivery:
            kb.button(
                text="🚚 Kuryerga topshirdim" if lang == "uz" else "🚚 Передал курьеру",
                callback_data=f"order_delivering_{order_id}",
            )
        else:
            kb.button(
                text="✅ Berildi" if lang == "uz" else "✅ Выдан",
                callback_data=f"order_complete_{order_id}",
            )
    elif status == OrderStatus.DELIVERING:
        if is_delivery:
            kb.button(
                text="✅ Topshirildi" if lang == "uz" else "✅ Доставлено",
                callback_data=f"order_complete_{order_id}",
            )
        else:
            kb.button(
                text="✅ Berildi" if lang == "uz" else "✅ Выдан",
                callback_data=f"order_complete_{order_id}",
            )

    kb.button(
        text=get_text(lang, "partner_order_btn_contact"),
        callback_data=f"contact_customer_o_{order_id}:{filter_type}:{page}",
    )
    kb.button(
        text=get_text(lang, "partner_order_btn_back"),
        callback_data=f"seller_orders_page:{filter_type}:{page}",
    )
    kb.adjust(2, 1, 1)

    try:
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=kb.as_markup())
    except Exception:
        await callback.message.answer(text, parse_mode="HTML", reply_markup=kb.as_markup())

    await callback.answer()


# =============================================================================
# CONTACT CUSTOMER
# =============================================================================


@router.callback_query(F.data.startswith("contact_customer_"))
async def contact_customer(callback: types.CallbackQuery) -> None:
    """Show customer contact info."""
    db = get_db()
    lang = db.get_user_language(callback.from_user.id)

    data = callback.data or ""
    parts = data.split(":")
    base = parts[0]
    filter_type = parts[1] if len(parts) > 1 and parts[1] else None
    try:
        page = int(parts[2]) if len(parts) > 2 else 1
    except ValueError:
        page = 1

    base_parts = base.split("_")
    if len(base_parts) < 4:
        await callback.answer(
            "Noto'g'ri so'rov" if lang == "uz" else "Неверный запрос", show_alert=True
        )
        return
    entity_type = base_parts[2]  # 'b' or 'o'
    try:
        entity_id = int(base_parts[3])
    except ValueError:
        await callback.answer(
            "Noto'g'ri so'rov" if lang == "uz" else "Неверный запрос", show_alert=True
        )
        return

    if entity_type == "b":
        entity = db.get_booking(entity_id)
    else:
        entity = db.get_order(entity_id)

    if not entity:
        await callback.answer("Ошибка", show_alert=True)
        return

    store_id = _get_field(entity, "store_id")
    if not store_id:
        offer_id = _get_field(entity, "offer_id")
        offer = db.get_offer(offer_id) if offer_id else None
        store_id = _get_field(offer, "store_id") if offer else None
    store = db.get_store(store_id) if store_id else None
    if not can_manage_store(db, store_id, callback.from_user.id, store=store):
        await callback.answer(get_text(lang, "no_access"), show_alert=True)
        return

    user_id = _get_field(entity, "user_id")
    customer = db.get_user_model(user_id) if user_id else None

    if not customer:
        await callback.answer(
            "Kontakt topilmadi" if lang == "uz" else "Контакт не найден", show_alert=True
        )
        return

    phone = customer.phone or get_text(lang, "value_unknown")
    name = customer.first_name or ("Mijoz" if lang == "uz" else "Клиент")

    text = f"<b>{'Mijoz kontakti' if lang == 'uz' else 'Контакт клиента'}</b>\n\n"
    text += f"{name}\n"
    text += f"<code>{phone}</code>"

    kb = InlineKeyboardBuilder()
    if customer.username:
        kb.button(text="Telegram", url=f"https://t.me/{customer.username}")
    elif user_id:
        kb.button(text="Telegram", url=f"tg://user?id={user_id}")

    back_cb = f"seller_orders_page:{filter_type}:{page}" if filter_type else "seller_orders_main"
    kb.button(text=get_text(lang, "partner_order_btn_back"), callback_data=back_cb)
    kb.adjust(1)

    try:
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=kb.as_markup())
    except Exception:
        pass
    await callback.answer()


# =============================================================================
# ORDER ACTIONS (using UnifiedOrderService)
# =============================================================================
# NOTE: order_confirm_, order_reject_, order_ready_, order_delivering_ handlers
# are in handlers/common/unified_order/seller.py to avoid duplication.
# We keep only order_cancel_seller_ here for seller-specific cancellation.


@router.callback_query(F.data.startswith("order_cancel_seller_"))
async def cancel_order_seller_handler(callback: types.CallbackQuery) -> None:
    """Cancel order by seller."""
    db = get_db()
    lang = db.get_user_language(callback.from_user.id)

    try:
        order_id = int(callback.data.split("_")[-1])
    except ValueError:
        await callback.answer("Ошибка", show_alert=True)
        return

    order = db.get_order(order_id)
    if not order:
        await callback.answer(get_text(lang, "order_not_found"), show_alert=True)
        return

    store_id = _get_field(order, "store_id")
    if not store_id:
        offer_id = _get_field(order, "offer_id")
        offer = db.get_offer(offer_id) if offer_id else None
        store_id = _get_field(offer, "store_id") if offer else None
    store = db.get_store(store_id) if store_id else None
    if not can_manage_store(db, store_id, callback.from_user.id, store=store):
        await callback.answer(get_text(lang, "no_access"), show_alert=True)
        return

    if _is_paid_online_order(order):
        await callback.answer(get_text(lang, "paid_click_reject_blocked"), show_alert=True)
        return

    service = get_unified_order_service()
    if not service and callback.bot:
        service = init_unified_order_service(db, callback.bot)
    if not service:
        logger.error("UnifiedOrderService is not initialized for order_cancel_seller handler")
        await callback.answer(get_text(lang, "error") or "System error", show_alert=True)
        return

    try:
        await service.cancel_order(order_id, "order")
        await callback.answer("Bekor qilindi" if lang == "uz" else "Отменено")

        await seller_orders_refresh(callback)
    except Exception as e:
        logger.error(f"cancel_order error: {e}")
        await callback.answer(
            f"Xatolik: {e}" if lang == "uz" else f"Ошибка: {e}", show_alert=True
        )


# =============================================================================
# LEGACY HANDLERS (backward compatibility)
# =============================================================================


@router.callback_query(F.data == "seller_orders_pending")
async def legacy_filter_pending(callback: types.CallbackQuery) -> None:
    await seller_filter_pending(callback)


@router.callback_query(F.data == "seller_orders_active")
async def legacy_filter_active(callback: types.CallbackQuery) -> None:
    await seller_filter_active(callback)


@router.callback_query(F.data == "seller_orders_completed")
async def legacy_filter_completed(callback: types.CallbackQuery) -> None:
    await seller_filter_completed(callback)


@router.callback_query(F.data.startswith("booking_details_seller_"))
async def legacy_booking_details(callback: types.CallbackQuery) -> None:
    booking_id = callback.data.split("_")[-1]
    callback.data = f"seller_view_o_{booking_id}"
    await seller_view_order(callback)
