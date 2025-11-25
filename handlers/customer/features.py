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

    # ============== МОИ БРОНИРОВАНИЯ ==============

    @dp_or_router.message(F.text.in_(["🛒 Корзина", "🛒 Savat"]))
    async def my_bookings(message: types.Message):
        """Show user bookings and orders"""
        lang = db.get_user_language(message.from_user.id)

        # Get bookings and orders
        bookings = db.get_user_bookings(message.from_user.id)
        try:
            orders = db.get_user_orders(message.from_user.id)
        except Exception:
            orders = []  # Table orders not yet created

        if not bookings and not orders:
            empty_text = "Корзина пуста" if lang == "ru" else "Savat bo'sh"
            desc_ru = "Здесь будут ваши бронирования и заказы с доставкой"
            desc_uz = "Bu yerda sizning bronlaringiz va buyurtmalaringiz bo'ladi"
            await message.answer(f"🛒 {empty_text}\n\n{desc_ru if lang == 'ru' else desc_uz}")
            return

        # Helper to safely get field from dict or tuple
        def get_field(item, field, index, default=None):
            if isinstance(item, dict):
                return item.get(field, default)
            if isinstance(item, (list, tuple)) and len(item) > index:
                return item[index]
            return default

        # Split bookings by status (works with both dict and tuple)
        active_bookings = [b for b in bookings if get_field(b, 'status', 3) in ["pending", "confirmed", "active"]]
        completed_bookings = [b for b in bookings if get_field(b, 'status', 3) == "completed"]
        cancelled_bookings = [b for b in bookings if get_field(b, 'status', 3) == "cancelled"]

        # Split orders by status (works with both dict and tuple)
        active_orders = [
            o for o in orders if get_field(o, 'order_status', 10) in ["pending", "confirmed", "preparing", "delivering"]
        ]
        completed_orders = [o for o in orders if get_field(o, 'order_status', 10) == "completed"]
        cancelled_orders = [o for o in orders if get_field(o, 'order_status', 10) == "cancelled"]

        total_text = f"<b>{'Мои заказы' if lang == 'ru' else 'Mening buyurtmalarim'}</b>\n\n"
        total_text += f"<b>{'Самовывоз' if lang == 'ru' else 'Olib ketish'}</b>\n"
        total_text += f"• {'Активные' if lang == 'ru' else 'Faol'} ({len(active_bookings)})\n"
        total_text += f"• {'Завершенные' if lang == 'ru' else 'Yakunlangan'} ({len(completed_bookings)})\n"
        total_text += f"• {'Отмененные' if lang == 'ru' else 'Bekor qilingan'} ({len(cancelled_bookings)})\n\n"
        total_text += f"<b>{'Доставка' if lang == 'ru' else 'Yetkazib berish'}</b>\n"
        total_text += f"• {'Активные' if lang == 'ru' else 'Faol'} ({len(active_orders)})\n"
        total_text += f"• {'Завершенные' if lang == 'ru' else 'Yakunlangan'} ({len(completed_orders)})\n"
        total_text += f"• {'Отмененные' if lang == 'ru' else 'Bekor qilingan'} ({len(cancelled_orders)})"

        await message.answer(
            total_text,
            parse_mode="HTML",
            reply_markup=booking_filters_keyboard(
                lang, len(active_bookings), len(completed_bookings), len(cancelled_bookings)
            ),
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
