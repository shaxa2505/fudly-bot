"""User profile and settings handlers."""
from __future__ import annotations

from typing import Any

from aiogram import F, Router, types
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder

from database_protocol import DatabaseProtocol
from handlers.common_states.states import ChangeCity, RegisterStore
from keyboards import (
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


def get_user_field(user: Any, field: str, default: Any = None) -> Any:
    """Extract field from user tuple/dict."""
    if isinstance(user, dict):
        return user.get(field, default)
    field_map = {
        "user_id": 0,
        "username": 1,
        "first_name": 2,
        "name": 2,
        "phone": 3,
        "city": 4,
        "language": 5,
        "role": 6,
        "is_admin": 7,
        "notifications": 8,
        "notifications_enabled": 8,
    }
    idx = field_map.get(field)
    if idx is not None and isinstance(user, (tuple, list)) and idx < len(user):
        return user[idx]
    return default


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
    user = db.get_user(message.from_user.id)

    if not user:
        await message.answer(
            get_text(lang, "choose_language"), reply_markup=language_keyboard()
        )
        return

    lang_text = "Русский" if lang == "ru" else "Ozbekcha"

    text = f"{get_text(lang, 'your_profile')}\n\n"
    text += f"{get_text(lang, 'name')}: {get_user_field(user, 'name')}\n"
    text += f"{get_text(lang, 'phone')}: {get_user_field(user, 'phone')}\n"
    text += f"{get_text(lang, 'city')}: {get_user_field(user, 'city')}\n"
    text += f"{get_text(lang, 'language')}: {lang_text}\n"

    # Customer statistics
    if (get_user_field(user, "role", "customer") == "customer") or (
        user_view_mode and user_view_mode.get(message.from_user.id) == "customer"
    ):
        bookings = db.get_user_bookings(message.from_user.id)
        try:
            orders = db.get_user_orders(message.from_user.id)
        except Exception:
            orders = []

        active_bookings = len([b for b in bookings if b[3] in ["pending", "confirmed"]])
        completed_bookings = len([b for b in bookings if b[3] == "completed"])

        active_orders = len(
            [
                o
                for o in orders
                if o[10] in ["pending", "confirmed", "preparing", "delivering"]
            ]
        )
        completed_orders = len([o for o in orders if o[10] == "completed"])

        total_active = active_bookings + active_orders
        total_completed = completed_bookings + completed_orders

        if total_active > 0 or total_completed > 0:
            text += f"\n📊 <b>{'Статистика покупок' if lang == 'ru' else 'Xaridlar statistikasi'}</b>\n"
            text += f"🟢 {'Активных' if lang == 'ru' else 'Faol'}: {total_active} "
            text += f"({'из них доставок' if lang == 'ru' else 'shulardan yetkazish'}: {active_orders})\n"
            text += f"✅ {'Завершено' if lang == 'ru' else 'Yakunlangan'}: {total_completed} "
            text += f"({'из них доставок' if lang == 'ru' else 'shulardan yetkazish'}: {completed_orders})\n"

    # Seller statistics
    elif get_user_field(user, "role", "customer") == "seller":
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

                completed_bookings = [b for b in store_bookings if b[3] == "completed"]
                total_bookings += len(completed_bookings)

                for booking in completed_bookings:
                    try:
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
            get_user_field(user, "notifications_enabled"),
            lang,
            role=get_user_field(user, "role", "customer"),
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
    if not db or not user_view_mode:
        await callback.answer("System error")
        return

    lang = db.get_user_language(callback.from_user.id)
    user_view_mode[callback.from_user.id] = "customer"
    try:
        await callback.message.edit_text(
            get_text(lang, "switched_to_customer"),
            reply_markup=main_menu_customer(lang),
        )
    except Exception:
        await callback.message.answer(
            get_text(lang, "switched_to_customer"),
            reply_markup=main_menu_customer(lang),
        )
    await callback.answer()


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
    user = db.get_user(callback.from_user.id)
    role = get_user_field(user, "role", "customer")

    try:
        await callback.message.edit_text(
            text,
            parse_mode="HTML",
            reply_markup=settings_keyboard(new_enabled, lang, role=role),
        )
    except Exception:
        await callback.message.answer(
            text, reply_markup=settings_keyboard(new_enabled, lang, role=role)
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

    lang = db.get_user_language(callback.from_user.id)

    try:
        db.delete_user(callback.from_user.id)
    except Exception:
        await callback.answer(get_text(lang, "access_denied"), show_alert=True)
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
    user = db.get_user(callback.from_user.id)

    if not user:
        await callback.message.edit_text(get_text(lang, "account_deleted"))
        await callback.answer()
        return

    try:
        await callback.message.edit_text(
            get_text(lang, "operation_cancelled"),
            reply_markup=settings_keyboard(
                get_user_field(user, "notifications_enabled"),
                lang,
                role=get_user_field(user, "role", "customer"),
            ),
        )
    except Exception:
        await callback.message.answer(
            get_text(lang, "operation_cancelled"),
            reply_markup=settings_keyboard(
                get_user_field(user, "notifications_enabled"),
                lang,
                role=get_user_field(user, "role", "customer"),
            ),
        )

    await callback.answer()


@router.message(F.text.contains("Режим покупателя") | F.text.contains("Xaridor rejimi"))
async def switch_to_customer(message: types.Message) -> None:
    """Switch to customer mode."""
    if not db or not user_view_mode:
        await message.answer("System error")
        return

    lang = db.get_user_language(message.from_user.id)
    user_view_mode[message.from_user.id] = "customer"
    await message.answer(
        get_text(lang, "switched_to_customer"), reply_markup=main_menu_customer(lang)
    )
