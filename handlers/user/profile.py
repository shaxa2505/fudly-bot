"""User profile and settings handlers."""
from __future__ import annotations

from typing import Any

from aiogram import F, Router, types
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder

from database_protocol import DatabaseProtocol
from handlers.common_states.states import ChangeCity, RegisterStore
from app.keyboards import (
    city_keyboard,
    language_keyboard,
    main_menu_customer,
    main_menu_seller,
    settings_keyboard,
)
from localization import get_text
from logging_config import logger

# Module-level dependencies
db: DatabaseProtocol | None = None
bot: Any | None = None
user_view_mode: dict[int, str] | None = None

router = Router()


def setup_dependencies(
    database: DatabaseProtocol, bot_instance: Any, view_mode_dict: dict[int, str]
) -> None:
    """Setup module dependencies."""
    global db, bot, user_view_mode
    db = database
    bot = bot_instance
    user_view_mode = view_mode_dict


def get_store_field(store: Any, field: str, default: Any = None) -> Any:
    """Extract field from store tuple/dict."""
    if isinstance(store, dict):
        return store.get(field, default)
    field_map = {
        "store_id": 0,
        "user_id": 1,
        "name": 2,
        "city": 3,
        "address": 4,
        "status": 5,
    }
    idx = field_map.get(field)
    if idx is not None and isinstance(store, (tuple, list)) and idx < len(store):
        return store[idx]
    return default


def get_appropriate_menu(user_id: int, lang: str) -> Any:
    """Get appropriate menu based on user view mode."""
    if user_view_mode and user_view_mode.get(user_id) == "seller":
        return main_menu_seller(lang)
    return main_menu_customer(lang)


@router.message(F.text.contains("Профиль") | F.text.contains("Profil"))
async def profile(message: types.Message) -> None:
    """Display user profile with statistics."""
    if not db:
        await message.answer("System error")
        return

    lang = db.get_user_language(message.from_user.id)
    user = db.get_user_model(message.from_user.id)

    if not user:
        await message.answer(
            get_text(lang, "choose_language"), reply_markup=language_keyboard()
        )
        return

    lang_text = "Русский" if lang == "ru" else "Ozbekcha"

    text = f"👤 <b>{get_text(lang, 'your_profile')}</b>\n\n"
    text += f"📝 {get_text(lang, 'name')}: <b>{user.first_name or 'N/A'}</b>\n"
    text += f"📱 {get_text(lang, 'phone')}: <code>{user.phone or 'N/A'}</code>\n"
    text += f"📍 {get_text(lang, 'city')}: <b>{user.city or 'N/A'}</b>\n"
    text += f"🌍 {get_text(lang, 'language')}: {lang_text}\n"

    # Determine current mode for settings keyboard
    current_mode = user_view_mode.get(message.from_user.id, "customer") if user_view_mode else "customer"
    
    # Customer statistics - show when in customer mode
    if current_mode == "customer":
        bookings = db.get_user_bookings(message.from_user.id)
        try:
            orders = db.get_user_orders(message.from_user.id)
        except Exception:
            orders = []

        # Helper to get field from booking/order (dict or tuple)
        def get_field(item, field, index):
            if isinstance(item, dict):
                return item.get(field)
            return item[index] if isinstance(item, (list, tuple)) and len(item) > index else None

        active_bookings = len([b for b in bookings if get_field(b, 'status', 3) in ["pending", "confirmed"]])
        completed_bookings = len([b for b in bookings if get_field(b, 'status', 3) == "completed"])

        active_orders = len(
            [
                o
                for o in orders
                if get_field(o, 'order_status', 10) in ["pending", "confirmed", "preparing", "delivering"]
            ]
        )
        completed_orders = len([o for o in orders if get_field(o, 'order_status', 10) == "completed"])

        total_active = active_bookings + active_orders
        total_completed = completed_bookings + completed_orders

        if total_active > 0 or total_completed > 0:
            text += f"\n📊 <b>{'Статистика покупок' if lang == 'ru' else 'Xaridlar statistikasi'}</b>\n"
            text += f"🟢 {'Активных' if lang == 'ru' else 'Faol'}: {total_active} "
            text += f"({'из них доставок' if lang == 'ru' else 'shulardan yetkazish'}: {active_orders})\n"
            text += f"✅ {'Завершено' if lang == 'ru' else 'Yakunlangan'}: {total_completed} "
            text += f"({'из них доставок' if lang == 'ru' else 'shulardan yetkazish'}: {completed_orders})\n"

    # Seller statistics - show when in seller mode
    elif current_mode == "seller" or user.role == "seller":
        stores = db.get_user_stores(message.from_user.id)
        if stores:
            total_bookings = 0
            total_orders = 0
            total_revenue = 0

            for store in stores:
                store_id = get_store_field(store, "store_id")
                if not store_id and isinstance(store, (tuple, list)) and len(store) > 0:
                    store_id = store[0]  # Fallback for tuple format
                store_bookings = db.get_store_bookings(store_id)

                # Filter completed bookings - handle dict format from PostgreSQL
                completed_bookings = []
                for b in store_bookings:
                    status = b.get('status') if isinstance(b, dict) else (b[3] if len(b) > 3 else None)
                    if status == "completed":
                        completed_bookings.append(b)
                
                total_bookings += len(completed_bookings)

                for booking in completed_bookings:
                    try:
                        if isinstance(booking, dict):
                            quantity = int(booking.get('quantity', 1))
                            # Calculate price from offer
                            offer = db.get_offer(booking.get('offer_id'))
                            if offer:
                                price = float(offer.get('discount_price', 0)) if isinstance(offer, dict) else float(offer[5]) if len(offer) > 5 else 0
                                total_revenue += int(quantity * price)
                        else:
                            quantity = int(booking[6]) if len(booking) > 6 else 1
                            price = float(booking[9]) if len(booking) > 9 else 0
                            total_revenue += int(quantity * price)
                    except Exception:
                        pass

            if total_bookings > 0 or total_orders > 0:
                text += f"\n📊 <b>{'Статистика продаж' if lang == 'ru' else 'Sotish statistikasi'}</b>\n"
                text += f"✅ {'Завершенных бронирований' if lang == 'ru' else 'Yakunlangan bronlar'}: {total_bookings}\n"
                if total_orders > 0:
                    text += f"🚚 {'Завершенных доставок' if lang == 'ru' else 'Yakunlangan yetkazishlar'}: {total_orders}\n"
                if total_revenue > 0:
                    text += f"💰 {'Выручка' if lang == 'ru' else 'Daromad'}: {total_revenue:,} {'сум' if lang == 'ru' else 'sum'}\n"

    await message.answer(
        text,
        parse_mode="HTML",
        reply_markup=settings_keyboard(
            user.notifications_enabled if hasattr(user, 'notifications_enabled') else True,
            lang,
            role=user.role or "customer",
            current_mode=current_mode,
        ),
    )


@router.callback_query(F.data == "profile_change_city")
async def profile_change_city(callback: types.CallbackQuery, state: FSMContext) -> None:
    """Start city change from profile."""
    if not db:
        await callback.answer("System error")
        return

    lang = db.get_user_language(callback.from_user.id)
    try:
        await callback.message.edit_text(
            get_text(lang, "choose_city"),
            parse_mode="HTML",
            reply_markup=city_keyboard(lang),
        )
    except Exception:
        await callback.message.answer(
            get_text(lang, "choose_city"),
            parse_mode="HTML",
            reply_markup=city_keyboard(lang),
        )
    await state.set_state(ChangeCity.city)
    await callback.answer()


@router.callback_query(F.data == "switch_to_customer")
async def switch_to_customer_cb(callback: types.CallbackQuery) -> None:
    """Switch to customer mode from profile."""
    if not db or user_view_mode is None:
        logger.error(f"❌ switch_to_customer_cb: db={db is not None}, user_view_mode={user_view_mode is not None}")
        await callback.answer("System error", show_alert=True)
        return

    try:
        lang = db.get_user_language(callback.from_user.id)
        user_view_mode[callback.from_user.id] = "customer"
        logger.info(f"✅ User {callback.from_user.id} switched to customer mode")
        
        # Send new message with ReplyKeyboard (cannot use edit_text with ReplyKeyboard)
        await callback.message.answer(
            get_text(lang, "switched_to_customer"),
            reply_markup=main_menu_customer(lang),
        )
        await callback.answer()
    except Exception as e:
        logger.error(f"❌ Error in switch_to_customer_cb: {e}", exc_info=True)
        await callback.answer("Произошла ошибка", show_alert=True)


@router.callback_query(F.data == "switch_to_seller")
async def switch_to_seller_cb(callback: types.CallbackQuery) -> None:
    """Switch to seller mode from profile."""
    if not db or user_view_mode is None:
        logger.error(f"❌ switch_to_seller_cb: db={db is not None}, user_view_mode={user_view_mode is not None}")
        await callback.answer("System error", show_alert=True)
        return

    try:
        lang = db.get_user_language(callback.from_user.id)
        user = db.get_user_model(callback.from_user.id)
        
        # Check if user is actually a seller
        if not user or user.role != "seller":
            await callback.answer(
                "Только партнеры могут использовать этот режим" if lang == "ru" else "Faqat hamkorlar bu rejimdan foydalanishlari mumkin",
                show_alert=True
            )
            return
        
        user_view_mode[callback.from_user.id] = "seller"
        logger.info(f"✅ User {callback.from_user.id} switched to seller mode")
        
        # Send new message with ReplyKeyboard
        await callback.message.answer(
            "Переключено в режим партнера" if lang == "ru" else "Hamkor rejimiga o'tkazildi",
            reply_markup=main_menu_seller(lang),
        )
        await callback.answer()
    except Exception as e:
        logger.error(f"❌ Error in switch_to_seller_cb: {e}", exc_info=True)
        await callback.answer("Произошла ошибка", show_alert=True)


@router.callback_query(F.data == "change_language")
async def change_language(callback: types.CallbackQuery) -> None:
    """Start language change."""
    if not db:
        await callback.answer("System error")
        return

    lang = db.get_user_language(callback.from_user.id)
    await callback.message.answer(
        get_text(lang, "choose_language"), reply_markup=language_keyboard()
    )
    await callback.answer()


@router.callback_query(F.data == "toggle_notifications")
async def toggle_notifications_callback(callback: types.CallbackQuery) -> None:
    """Toggle user notifications."""
    if not db:
        await callback.answer("System error")
        return

    lang = db.get_user_language(callback.from_user.id)
    try:
        new_enabled = db.toggle_notifications(callback.from_user.id)
    except Exception:
        await callback.answer(get_text(lang, "access_denied"), show_alert=True)
        return

    text = (
        get_text(lang, "notifications_enabled")
        if new_enabled
        else get_text(lang, "notifications_disabled")
    )
    user = db.get_user_model(callback.from_user.id)
    role = user.role if user else "customer"
    current_mode = user_view_mode.get(callback.from_user.id, "customer") if user_view_mode else "customer"

    try:
        await callback.message.edit_text(
            text,
            parse_mode="HTML",
            reply_markup=settings_keyboard(new_enabled, lang, role=role, current_mode=current_mode),
        )
    except Exception:
        await callback.message.answer(
            text, reply_markup=settings_keyboard(new_enabled, lang, role=role, current_mode=current_mode)
        )

    await callback.answer()


@router.callback_query(F.data == "delete_account")
async def delete_account_prompt(callback: types.CallbackQuery) -> None:
    """Prompt for account deletion confirmation."""
    if not db:
        await callback.answer("System error")
        return

    lang = db.get_user_language(callback.from_user.id)

    builder = InlineKeyboardBuilder()
    builder.button(
        text=get_text(lang, "yes_delete"), callback_data="confirm_delete_yes"
    )
    builder.button(text=get_text(lang, "no_cancel"), callback_data="confirm_delete_no")
    builder.adjust(2)

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


@router.callback_query(F.data == "confirm_delete_yes")
async def confirm_delete_yes(callback: types.CallbackQuery) -> None:
    """Confirm account deletion."""
    if not db:
        await callback.answer("System error")
        return

    # Get language BEFORE deleting user
    lang = db.get_user_language(callback.from_user.id)

    try:
        db.delete_user(callback.from_user.id)
        logger.info(f"User {callback.from_user.id} deleted their account successfully")
    except Exception as e:
        logger.error(f"Error deleting user {callback.from_user.id}: {e}")
        await callback.answer(get_text(lang, "error"), show_alert=True)
        return

    try:
        await callback.message.edit_text(
            get_text(lang, "account_deleted")
            + "\n\n"
            + get_text(lang, "choose_language"),
            parse_mode="HTML",
            reply_markup=language_keyboard(),
        )
    except Exception:
        await callback.message.answer(
            get_text(lang, "account_deleted")
            + "\n\n"
            + get_text(lang, "choose_language"),
            parse_mode="HTML",
            reply_markup=language_keyboard(),
        )

    await callback.answer()


@router.callback_query(F.data == "confirm_delete_no")
async def confirm_delete_no(callback: types.CallbackQuery) -> None:
    """Cancel account deletion."""
    if not db:
        await callback.answer("System error")
        return

    lang = db.get_user_language(callback.from_user.id)
    user = db.get_user_model(callback.from_user.id)

    if not user:
        await callback.message.edit_text(get_text(lang, "account_deleted"))
        await callback.answer()
        return

    role = user.role
    current_mode = user_view_mode.get(callback.from_user.id, "customer") if user_view_mode else "customer"

    try:
        await callback.message.edit_text(
            get_text(lang, "operation_cancelled"),
            reply_markup=settings_keyboard(
                user.notifications_enabled if user else False,
                lang,
                role=user.role if user else "customer",
                current_mode=current_mode,
            ),
        )
    except Exception:
        await callback.message.answer(
            get_text(lang, "operation_cancelled"),
            reply_markup=settings_keyboard(
                user.notifications_enabled if user else False,
                lang,
                role=user.role if user else "customer",
                current_mode=current_mode,
            ),
        )

    await callback.answer()


@router.message(F.text.contains("Режим покупателя") | F.text.contains("Xaridor rejimi"))
async def switch_to_customer(message: types.Message) -> None:
    """Switch to customer mode."""
    if not db or user_view_mode is None:
        await message.answer("System error")
        return

    lang = db.get_user_language(message.from_user.id)
    user = db.get_user_model(message.from_user.id)
    user_view_mode[message.from_user.id] = "customer"
    
    # Check if user is seller to show switch button
    is_seller = user and user.role == "seller"
    
    await message.answer(
        get_text(lang, "switched_to_customer"), 
        reply_markup=main_menu_customer(lang)
    )
