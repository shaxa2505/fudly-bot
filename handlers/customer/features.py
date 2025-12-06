"""
User-related handlers: bookings, favorites, notifications, settings
Extracted from bot.py for better modularity
"""
from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from aiogram import F, Router, types
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.core.utils import get_field
from database_protocol import DatabaseProtocol

logger = logging.getLogger(__name__)
router = Router()


# =============================================================================
# CART HELPERS
# =============================================================================

_RU = "ru"
_CURRENCY = {"ru": "сум", "uz": "so'm"}
_BOOKING_STATUS = {
    "pending": {"ru": "⏳ Ожидает", "uz": "⏳ Kutilmoqda"},
    "confirmed": {"ru": "✅ Подтверждено", "uz": "✅ Tasdiqlangan"},
}
_ORDER_STATUS = {
    "pending": {"ru": "⏳ Ожидает", "uz": "⏳ Kutilmoqda", "emoji": "⏳"},
    "confirmed": {"ru": "✅ Подтверждён", "uz": "✅ Tasdiqlangan", "emoji": "✅"},
    "preparing": {"ru": "👨‍🍳 Готовится", "uz": "👨‍🍳 Tayyorlanmoqda", "emoji": "👨‍🍳"},
    "delivering": {"ru": "🚗 В пути", "uz": "🚗 Yo'lda", "emoji": "🚗"},
}


def _t(lang: str, ru: str, uz: str) -> str:
    """Quick translate helper."""
    return ru if lang == _RU else uz


def _format_booking(b: Any, lang: str) -> list[str]:
    """Format single booking for cart display."""
    status = get_field(b, "status", "pending")
    code = get_field(b, "booking_code", "")
    qty = get_field(b, "quantity", 1)
    title = get_field(b, "title", "Товар")
    price = get_field(b, "discount_price", 0)
    store = get_field(b, "name", "")
    cur = _CURRENCY.get(lang, "сум")

    emoji = "⏳" if status == "pending" else "✅"
    lines = [
        f"{emoji} <b>{title}</b>",
        f"   📦 {qty} × {int(price):,} = <b>{int(price * qty):,}</b> {cur}",
    ]
    if store:
        lines.append(f"   🏪 {store}")

    if status == "confirmed" and code:
        hint = _t(lang, "покажите продавцу", "sotuvchiga ko'rsating")
        lines.append(f"   🎫 <code>{code}</code> — {hint}")

    return lines


def _format_order(o: Any, title: str, lang: str) -> list[str]:
    """Format single order for cart display."""
    status = get_field(o, "order_status", "pending")
    total = get_field(o, "total_price", 0)
    addr = get_field(o, "delivery_address", "")
    cur = _CURRENCY.get(lang, "сум")

    st = _ORDER_STATUS.get(status, _ORDER_STATUS["pending"])
    emoji = st.get("emoji", "📦")
    st_text = st.get(lang, status)

    lines = [
        f"{emoji} <b>{title}</b>",
        f"   💰 <b>{int(total):,}</b> {cur} • {st_text}",
    ]
    if addr:
        lines.append(f"   📍 {addr[:40]}{'...' if len(addr) > 40 else ''}")
    return lines


def setup(
    dp_or_router: Any,
    db: DatabaseProtocol,
    get_text: Callable[..., str],
    booking_filters_keyboard: Callable[..., Any],
    settings_keyboard: Callable[..., Any],
) -> None:
    """Setup user handlers with dependencies"""

    # ============== МОЯ КОРЗИНА ==============

    @dp_or_router.message(F.text.in_(["🛒 Корзина", "🛒 Savat"]))
    async def my_cart(message: types.Message, state: FSMContext):
        """Show user's cart with items from new cart storage + active bookings/orders."""
        await state.clear()

        user_id = message.from_user.id
        lang = db.get_user_language(user_id)

        # Import new cart storage
        try:
            from handlers.customer.cart.storage import cart_storage
            cart_items = cart_storage.get_items(user_id)
        except Exception:
            cart_items = []

        # Fetch old booking data (with error handling)
        try:
            bookings = db.get_user_bookings(user_id) or []
        except Exception:
            bookings = []

        try:
            orders = db.get_user_orders(user_id) or []
        except Exception:
            orders = []

        # Filter active only
        active_bookings = [b for b in bookings if get_field(b, "status", "") in ("pending", "confirmed")]
        active_orders = [o for o in orders if get_field(o, "order_status", "") in ("pending", "confirmed", "preparing", "delivering")]

        # Empty cart check - now includes new cart items
        if not cart_items and not active_bookings and not active_orders:
            recent = [b for b in bookings if get_field(b, "status", "") == "completed"][:3]
            text = _t(lang, "🛒 Корзина пуста", "🛒 Savat bo'sh")
            text += "\n\n" + _t(
                lang,
                "Добавьте товар через кнопку «🛒 В корзину»",
                "«🛒 Savatga» tugmasi orqali mahsulot qo'shing",
            )
            if recent:
                text += "\n\n📜 <b>" + _t(lang, "Недавние", "Oxirgilar") + ":</b>\n"
                text += "\n".join(f"✔️ {get_field(b, 'title', 'Товар')}" for b in recent)
            await message.answer(text, parse_mode="HTML")
            return

        # Build cart text
        lines = [f"🛒 <b>{_t(lang, 'Моя корзина', 'Mening savatim')}</b>", ""]
        kb = InlineKeyboardBuilder()

        # NEW: Show cart items from new storage
        if cart_items:
            lines.append(f"🛍 <b>{_t(lang, 'Товары в корзине', 'Savatdagi mahsulotlar')}</b> ({len(cart_items)})")
            lines.append("─" * 20)
            total_sum = 0
            for item in cart_items[:5]:
                item_total = item.price * item.quantity
                total_sum += item_total
                lines.append(f"📦 {item.title}")
                lines.append(f"   {item.quantity} × {item.price:,.0f} = {item_total:,.0f} сум")
                lines.append(f"   🏪 {item.store_name}")
                lines.append("")
            lines.append(f"💰 <b>{_t(lang, 'Итого', 'Jami')}: {total_sum:,.0f} сум</b>")
            lines.append("")
            # Add checkout button for cart items
            kb.button(text=f"✅ {_t(lang, 'Оформить заказ', 'Buyurtma berish')}", callback_data="cart_checkout")
            kb.button(text=f"🗑 {_t(lang, 'Очистить', 'Tozalash')}", callback_data="cart_clear")

        # Pickup bookings (old system)
        if active_bookings:
            lines.append(f"🏪 <b>{_t(lang, 'Самовывоз', 'Olib ketish')}</b> ({len(active_bookings)})")
            lines.append("─" * 20)
            for b in active_bookings[:5]:
                lines.extend(_format_booking(b, lang))
                lines.append("")

        # Delivery orders
        if active_orders:
            lines.append(f"🚚 <b>{_t(lang, 'Доставка', 'Yetkazib berish')}</b> ({len(active_orders)})")
            lines.append("─" * 20)
            # Cache offer titles to avoid N+1 queries
            offer_cache: dict[int, str] = {}
            for o in active_orders[:5]:
                offer_id = get_field(o, "offer_id")
                if offer_id and offer_id not in offer_cache:
                    offer = db.get_offer(offer_id)
                    offer_cache[offer_id] = get_field(offer, "title", "Товар") if offer else "Товар"
                title = offer_cache.get(offer_id, "Товар")
                lines.extend(_format_order(o, title, lang))
                lines.append("")

        # Summary
        total = len(cart_items) + len(active_bookings) + len(active_orders)
        lines.append("─" * 20)
        lines.append(f"{_t(lang, 'Активных', 'Faol')}: <b>{total}</b>")

        # Cancel buttons for old bookings
        cancel_count = 0
        for b in active_bookings[:3]:
            bid = get_field(b, "booking_id", 0)
            ttl = get_field(b, "title", "")[:12]
            kb.button(text=f"❌ {ttl}", callback_data=f"cancel_booking_{bid}")
            cancel_count += 1

        # Nav row
        if active_bookings:
            kb.button(text=f"🏪 {_t(lang, 'Подробнее', 'Batafsil')}", callback_data="bookings_active")
        if active_orders:
            kb.button(text=f"🚚 {len(active_orders)}", callback_data="orders_active")
        kb.button(text=f"📜 {_t(lang, 'История', 'Tarix')}", callback_data="bookings_completed")

        # Layout - adjust based on what buttons we have
        if cart_items:
            rows = [2]  # Checkout + Clear buttons
            rows.extend([1] * cancel_count)
            rows.append(min(3, (1 if active_bookings else 0) + (1 if active_orders else 0) + 1))
        else:
            rows = [1] * cancel_count + [min(3, (1 if active_bookings else 0) + (1 if active_orders else 0) + 1)]
        kb.adjust(*rows)

        await message.answer("\n".join(lines), parse_mode="HTML", reply_markup=kb.as_markup())

    # ============== ИЗБРАННОЕ ==============

    @dp_or_router.message(F.text.in_(["❤️ Избранное", "❤️ Sevimlilar"]))
    async def show_favorites(message: types.Message, state: FSMContext):
        """Show favorite stores"""
        # Clear any active FSM state when returning to main menu
        await state.clear()

        lang = db.get_user_language(message.from_user.id)
        user_id = message.from_user.id

        # Get favorite stores
        favorites = db.get_favorites(user_id)

        if not favorites:
            await message.answer(get_text(lang, "no_favorites"))
            return

        await message.answer(
            f"❤️ <b>Ваши избранные магазины ({len(favorites)})</b>", parse_mode="HTML"
        )

        for store in favorites:
            # Dict-compatible access
            store_id = store.get("store_id") if isinstance(store, dict) else store[0]
            store_name = (
                store.get("name")
                if isinstance(store, dict)
                else (store[2] if len(store) > 2 else "Без названия")
            )
            category = (
                store.get("category")
                if isinstance(store, dict)
                else (store[6] if len(store) > 6 else "Магазин")
            )
            address = (
                store.get("address")
                if isinstance(store, dict)
                else (store[4] if len(store) > 4 else "")
            )
            description = (
                store.get("description")
                if isinstance(store, dict)
                else (store[5] if len(store) > 5 else "")
            )

            avg_rating = db.get_store_average_rating(store_id)
            ratings = db.get_store_ratings(store_id)

            text = f"""🏪 <b>{store_name}</b>
🏷 {category}
📍 {address}
📝 {description}
⭐ Рейтинг: {avg_rating:.1f}/5 ({len(ratings)} отзывов)"""

            keyboard = InlineKeyboardBuilder()
            keyboard.button(text="🛍 Товары магазина", callback_data=f"store_offers_{store_id}")
            keyboard.button(text="💔 Удалить из избранного", callback_data=f"unfavorite_{store_id}")
            keyboard.adjust(1)

            await message.answer(text, parse_mode="HTML", reply_markup=keyboard.as_markup())

    @dp_or_router.callback_query(F.data.startswith("favorite_"))
    async def toggle_favorite(callback: types.CallbackQuery):
        """Add store to favorites"""
        user_id = callback.from_user.id
        lang = db.get_user_language(user_id)

        try:
            store_id = int(callback.data.split("_")[1])
        except (ValueError, IndexError) as e:
            logger.error(f"Invalid store_id in callback data: {callback.data}, error: {e}")
            await callback.answer(get_text(lang, "error"), show_alert=True)
            return

        # Check if already in favorites
        if db.is_favorite(user_id, store_id):
            await callback.answer(get_text(lang, "already_in_favorites"), show_alert=True)
        else:
            db.add_favorite(user_id, store_id)
            await callback.answer(get_text(lang, "added_to_favorites"), show_alert=True)

    @dp_or_router.callback_query(F.data.startswith("unfavorite_"))
    async def remove_favorite(callback: types.CallbackQuery):
        """Remove store from favorites"""
        user_id = callback.from_user.id
        lang = db.get_user_language(user_id)

        try:
            store_id = int(callback.data.split("_")[1])
        except (ValueError, IndexError) as e:
            logger.error(f"Invalid store_id in callback data: {callback.data}, error: {e}")
            await callback.answer(get_text(lang, "error"), show_alert=True)
            return

        db.remove_favorite(user_id, store_id)
        await callback.message.delete()
        await callback.answer(get_text(lang, "removed_from_favorites"), show_alert=True)

    # ============== НАСТРОЙКИ И УВЕДОМЛЕНИЯ ==============

    @dp_or_router.callback_query(F.data == "toggle_notifications")
    async def toggle_notifications_callback(callback: types.CallbackQuery):
        """Toggle user notifications and update settings keyboard"""
        lang = db.get_user_language(callback.from_user.id)
        try:
            new_enabled = db.toggle_notifications(callback.from_user.id)
        except Exception:
            await callback.answer(get_text(lang, "access_denied"), show_alert=True)
            return

        # Show notification and update settings keyboard
        text = (
            get_text(lang, "notifications_enabled")
            if new_enabled
            else get_text(lang, "notifications_disabled")
        )

        # Determine role for proper settings keyboard
        user = db.get_user_model(callback.from_user.id)
        role = user.role if user else "customer"

        try:
            await callback.message.edit_text(
                text,
                parse_mode="HTML",
                reply_markup=settings_keyboard(new_enabled, lang, role=role),
            )
        except Exception:
            # If couldn't edit (possibly wrong message), just send new one
            await callback.message.answer(
                text, reply_markup=settings_keyboard(new_enabled, lang, role=role)
            )

        await callback.answer()

    # NOTE: delete_account, confirm_delete_yes, confirm_delete_no handlers
    # are now handled in handlers/customer/profile.py to avoid duplication
