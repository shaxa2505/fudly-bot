"""
User-related handlers: bookings, favorites, notifications, settings
Extracted from bot.py for better modularity
"""
from __future__ import annotations

import logging
from typing import Any, Callable

from aiogram import F, Router, types
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder

from database_protocol import DatabaseProtocol

logger = logging.getLogger(__name__)
router = Router()


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
    async def my_cart(message: types.Message):
        """Show user's cart with active bookings and orders"""
        user_id = message.from_user.id
        lang = db.get_user_language(user_id)

        # Get bookings and orders
        try:
            bookings = db.get_user_bookings(user_id) or []
        except Exception as e:
            logger.error(f"Failed to get bookings for user {user_id}: {e}")
            bookings = []
            
        try:
            orders = db.get_user_orders(user_id) or []
        except Exception as e:
            logger.error(f"Failed to get orders for user {user_id}: {e}")
            orders = []

        # Helper to safely get field from dict or tuple
        def get_field(item, field, index=None, default=None):
            """Get field from dict (PostgreSQL) or tuple (SQLite)."""
            if item is None:
                return default
            if isinstance(item, dict):
                return item.get(field, default)
            if isinstance(item, (list, tuple)) and index is not None and len(item) > index:
                return item[index]
            return default

        # Debug: log what we got
        logger.info(f"Cart: user={user_id}, bookings_count={len(bookings)}, orders_count={len(orders)}")
        if bookings:
            first = bookings[0]
            if isinstance(first, dict):
                logger.info(f"First booking: status='{first.get('status')}', title='{first.get('title')}'")
                # Log all statuses to debug
                all_statuses = [b.get('status') for b in bookings if isinstance(b, dict)]
                logger.info(f"All booking statuses: {all_statuses}")
            else:
                logger.info(f"First booking is tuple: {first}")

        # Filter active items only  
        active_bookings = [b for b in bookings if get_field(b, 'status', 3) in ["pending", "confirmed", "active"]]
        active_orders = [o for o in orders if get_field(o, 'order_status', 10) in ["pending", "confirmed", "preparing", "delivering"]]
        
        # Recent completed (last 3)
        recent_completed = [b for b in bookings if get_field(b, 'status', 3) in ["completed"]][:3]
        
        logger.info(f"Cart: active_bookings={len(active_bookings)}, active_orders={len(active_orders)}, recent_completed={len(recent_completed)}")

        if not active_bookings and not active_orders:
            # Show empty cart but with recent history if exists
            empty_text = "🛒 Корзина пуста" if lang == "ru" else "🛒 Savat bo'sh"
            hint_ru = "Выберите товар и нажмите «Забронировать» или «Заказать доставку»"
            hint_uz = "Mahsulotni tanlang va «Buyurtma berish» tugmasini bosing"
            
            text = f"{empty_text}\n\n{hint_ru if lang == 'ru' else hint_uz}"
            
            # Show recent completed bookings
            if recent_completed:
                text += f"\n\n📜 <b>{'Недавние заказы' if lang == 'ru' else 'Oxirgi buyurtmalar'}:</b>\n"
                for b in recent_completed:
                    title = get_field(b, 'title', 8, 'Товар')
                    status = get_field(b, 'status', 3, 'completed')
                    emoji = "✔️" if status == "completed" else "❌"
                    text += f"{emoji} {title}\n"
            
            await message.answer(text, parse_mode="HTML")
            return

        # Build detailed cart view
        text_parts = []
        text_parts.append(f"🛒 <b>{'Моя корзина' if lang == 'ru' else 'Mening savatim'}</b>\n")

        # === ACTIVE BOOKINGS (Pickup) ===
        if active_bookings:
            text_parts.append(f"\n🏪 <b>{'Самовывоз' if lang == 'ru' else 'Olib ketish'}</b> ({len(active_bookings)})\n")
            text_parts.append("━━━━━━━━━━━━━━━━━━")
            
            for b in active_bookings[:5]:  # Limit to 5
                booking_id = get_field(b, 'booking_id', 0)
                status = get_field(b, 'status', 3, 'pending')
                code = get_field(b, 'booking_code', 4, '')
                quantity = get_field(b, 'quantity', 6, 1)
                title = get_field(b, 'title', 8, 'Товар')
                price = get_field(b, 'discount_price', 9, 0)
                store_name = get_field(b, 'name', 11, 'Магазин')
                address = get_field(b, 'address', 12, '')
                
                total = int(price * quantity)
                currency = "сум" if lang == "ru" else "so'm"
                
                # Status emoji
                status_emoji = "⏳" if status == "pending" else "✅"
                status_text = {
                    "pending": "Ожидает подтверждения" if lang == "ru" else "Tasdiq kutilmoqda",
                    "confirmed": "Подтверждено" if lang == "ru" else "Tasdiqlangan"
                }.get(status, status)
                
                text_parts.append(f"\n{status_emoji} <b>{title}</b>")
                text_parts.append(f"   📦 {quantity} × {int(price):,} = <b>{total:,}</b> {currency}")
                text_parts.append(f"   🏪 {store_name}")
                if address:
                    text_parts.append(f"   📍 {address}")
                
                # Status-specific messages
                if status == "pending":
                    pending_text = "Ожидает подтверждения продавца" if lang == "ru" else "Sotuvchi tasdigini kutmoqda"
                    text_parts.append(f"   ⏳ {pending_text}")
                elif status == "confirmed" and code:
                    confirmed_text = "Подтверждено" if lang == "ru" else "Tasdiqlangan"
                    hint_text = "Покажите код продавцу" if lang == "ru" else "Kodni sotuvchiga korsating"
                    text_parts.append(f"   ✅ {confirmed_text}")
                    text_parts.append(f"   🎫 <b>Код:</b> <code>{code}</code>")
                    text_parts.append(f"   💡 {hint_text}")
                elif status == "active":
                    active_text = "Активно" if lang == "ru" else "Faol"
                    text_parts.append(f"   🔵 {active_text}")
                
                text_parts.append("")

        # === ACTIVE ORDERS (Delivery) ===
        if active_orders:
            text_parts.append(f"\n🚚 <b>{'Доставка' if lang == 'ru' else 'Yetkazib berish'}</b> ({len(active_orders)})\n")
            text_parts.append("━━━━━━━━━━━━━━━━━━")
            
            for o in active_orders[:5]:  # Limit to 5
                order_id = get_field(o, 'order_id', 0)
                status = get_field(o, 'order_status', 10, 'pending')
                quantity = get_field(o, 'quantity', 9, 1)
                total_price = get_field(o, 'total_price', 11, 0)
                delivery_address = get_field(o, 'delivery_address', 4, '')
                
                # Get offer title (may need separate query)
                offer_id = get_field(o, 'offer_id', 2)
                offer = db.get_offer(offer_id) if offer_id else None
                title = get_field(offer, 'title', 2, 'Товар') if offer else 'Товар'
                
                status_emoji = {"pending": "⏳", "confirmed": "✅", "preparing": "👨‍🍳", "delivering": "🚗"}.get(status, "📦")
                status_text = {
                    "pending": "Ожидает подтверждения" if lang == "ru" else "Tasdiq kutilmoqda",
                    "confirmed": "Подтверждён" if lang == "ru" else "Tasdiqlangan",
                    "preparing": "Готовится" if lang == "ru" else "Tayyorlanmoqda",
                    "delivering": "В пути" if lang == "ru" else "Yo'lda"
                }.get(status, status)
                
                currency = "сум" if lang == "ru" else "so'm"
                text_parts.append(f"\n{status_emoji} <b>{title}</b>")
                text_parts.append(f"   💰 <b>{int(total_price):,}</b> {currency}")
                if delivery_address:
                    text_parts.append(f"   📍 {delivery_address[:50]}...")
                text_parts.append(f"   📊 {status_text}")
                text_parts.append("")

        # Summary
        total_items = len(active_bookings) + len(active_orders)
        text_parts.append(f"━━━━━━━━━━━━━━━━━━")
        text_parts.append(f"{'Всего активных заказов' if lang == 'ru' else 'Jami faol buyurtmalar'}: <b>{total_items}</b>")

        # Build keyboard with cancel buttons for each booking
        kb = InlineKeyboardBuilder()
        
        # Build keyboard with cancel buttons for each booking
        kb = InlineKeyboardBuilder()
        
        # Add cancel button for each active booking (max 3)
        for b in active_bookings[:3]:
            booking_id = get_field(b, 'booking_id', 0)
            title = get_field(b, 'title', 8, 'Товар')[:15]
            cancel_text = f"❌ {title}"
            kb.button(text=cancel_text, callback_data=f"cancel_booking_{booking_id}")
        
        # Add navigation buttons on new row
        if active_bookings:
            kb.button(
                text=f"🏪 {'Подробнее' if lang == 'ru' else 'Batafsil'}", 
                callback_data="bookings_active"
            )
        if active_orders:
            kb.button(
                text=f"🚚 {'Доставка' if lang == 'ru' else 'Yetkazib'} ({len(active_orders)})", 
                callback_data="orders_active"
            )
        kb.button(
            text=f"📜 {'История' if lang == 'ru' else 'Tarix'}", 
            callback_data="bookings_completed"
        )
        
        # Layout: cancel buttons (1 per row), then nav buttons (2-3 in a row)
        rows = [1] * len(active_bookings[:3])  # One cancel button per row
        rows.append(min(3, 1 + (1 if active_orders else 0) + 1))  # nav buttons in one row
        kb.adjust(*rows)

        await message.answer(
            "\n".join(text_parts),
            parse_mode="HTML",
            reply_markup=kb.as_markup(),
        )

    # ============== ИЗБРАННОЕ ==============

    @dp_or_router.message(F.text.in_(["❤️ Избранное", "❤️ Sevimlilar"]))
    async def show_favorites(message: types.Message):
        """Show favorite stores"""
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
            store_id = store.get('store_id') if isinstance(store, dict) else store[0]
            store_name = store.get('name') if isinstance(store, dict) else (store[2] if len(store) > 2 else 'Без названия')
            category = store.get('category') if isinstance(store, dict) else (store[6] if len(store) > 6 else 'Магазин')
            address = store.get('address') if isinstance(store, dict) else (store[4] if len(store) > 4 else '')
            description = store.get('description') if isinstance(store, dict) else (store[5] if len(store) > 5 else '')
            
            avg_rating = db.get_store_average_rating(store_id)
            ratings = db.get_store_ratings(store_id)

            text = f"""🏪 <b>{store_name}</b>
🏷 {category}
📍 {address}
📝 {description}
⭐ Рейтинг: {avg_rating:.1f}/5 ({len(ratings)} отзывов)"""

            keyboard = InlineKeyboardBuilder()
            keyboard.button(text="🛍 Товары магазина", callback_data=f"store_offers_{store_id}")
            keyboard.button(
                text="💔 Удалить из избранного", callback_data=f"unfavorite_{store_id}"
            )
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
                text, parse_mode="HTML", reply_markup=settings_keyboard(new_enabled, lang, role=role)
            )
        except Exception:
            # If couldn't edit (possibly wrong message), just send new one
            await callback.message.answer(
                text, reply_markup=settings_keyboard(new_enabled, lang, role=role)
            )

        await callback.answer()

    @dp_or_router.callback_query(F.data == "delete_account")
    async def delete_account_prompt(callback: types.CallbackQuery):
        """Ask for confirmation before deleting account"""
        lang = db.get_user_language(callback.from_user.id)

        # Confirmation with two buttons (aiogram 3.x syntax)
        builder = InlineKeyboardBuilder()
        builder.button(text=get_text(lang, "yes_delete"), callback_data="confirm_delete_yes")
        builder.button(text=get_text(lang, "no_cancel"), callback_data="confirm_delete_no")
        builder.adjust(2)

        # Edit message (or send new) with warning
        try:
            await callback.message.edit_text(
                get_text(lang, "confirm_delete_account"),
                parse_mode="HTML",
                reply_markup=builder.as_markup(),
            )
        except Exception:
            await callback.message.answer(
                get_text(lang, "confirm_delete_account"),
                parse_mode="HTML",
                reply_markup=builder.as_markup(),
            )

        await callback.answer()

    @dp_or_router.callback_query(F.data == "confirm_delete_yes")
    async def confirm_delete_account(callback: types.CallbackQuery, state: FSMContext):
        """Delete user account"""
        lang = db.get_user_language(callback.from_user.id)
        user_id = callback.from_user.id

        try:
            # Delete user data
            db.delete_user(user_id)
            await state.clear()

            await callback.message.edit_text(
                get_text(lang, "account_deleted"), parse_mode="HTML"
            )
            
            # Show welcome message for re-registration
            from app.keyboards import language_keyboard
            await callback.message.answer(
                get_text('ru', 'welcome'),
                parse_mode="HTML"
            )
            await callback.message.answer(
                get_text('ru', 'choose_language'),
                reply_markup=language_keyboard()
            )
            
            await callback.answer()
        except Exception as e:
            await callback.answer(
                f"❌ Ошибка при удалении аккаунта: {str(e)}", show_alert=True
            )

    @dp_or_router.callback_query(F.data == "confirm_delete_no")
    async def cancel_delete_account(callback: types.CallbackQuery):
        """Cancel account deletion"""
        lang = db.get_user_language(callback.from_user.id)
        user = db.get_user_model(callback.from_user.id)
        role = user.role if user else "customer"
        notifications_enabled = user.notifications_enabled if user else True

        try:
            await callback.message.edit_text(
                get_text(lang, "settings"),
                parse_mode="HTML",
                reply_markup=settings_keyboard(notifications_enabled, lang, role=role),
            )
        except Exception:
            await callback.message.answer(
                get_text(lang, "operation_cancelled"),
                reply_markup=settings_keyboard(notifications_enabled, lang, role=role),
            )

        await callback.answer()
