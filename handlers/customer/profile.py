"""User profile and settings handlers."""
from __future__ import annotations

from typing import Any

from aiogram import F, Router, types
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import ReplyKeyboardRemove
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.core.location_data import (
    get_districts_for_city_index,
    get_districts_for_region,
    get_region_key_for_city_index,
)
from app.core.utils import get_field, get_store_field, normalize_city
from app.integrations.sentry_integration import capture_exception
from app.keyboards import (
    city_inline_keyboard,
    language_keyboard,
    main_menu_customer,
    main_menu_seller,
    settings_keyboard,
)
from database_protocol import DatabaseProtocol
from handlers.common.states import ChangeCity
from handlers.common.utils import (
    get_appropriate_menu as _get_appropriate_menu,
)
from handlers.common.utils import (
    get_user_view_mode,
    has_approved_store,
    is_profile_button,
    set_user_view_mode,
)
from localization import get_cities, get_text
from logging_config import logger

# Module-level dependencies
db: DatabaseProtocol | None = None
bot: Any | None = None

router = Router()


def setup_dependencies(
    database: DatabaseProtocol, bot_instance: Any, view_mode_dict: dict[int, str] | None = None
) -> None:
    """Setup module dependencies. view_mode_dict is deprecated and ignored."""
    global db, bot
    db = database
    bot = bot_instance


def get_appropriate_menu(user_id: int, lang: str) -> Any:
    """Get appropriate menu based on user view mode."""
    if not db:
        from app.keyboards import main_menu_customer

        return main_menu_customer(lang)
    return _get_appropriate_menu(user_id, lang, db)


@router.message(F.text.func(is_profile_button))
async def profile(message: types.Message, state: FSMContext) -> None:
    """Display user profile with statistics."""
    # Clear any active FSM state when returning to main menu
    await state.clear()

    if not db:
        lang_code = (message.from_user.language_code or "ru") if message.from_user else "ru"
        if lang_code.startswith("uz"):
            text = "❌ Xizmat vaqtincha mavjud emas. Keyinroq urinib ko'ring."
        else:
            text = "❌ Сервис временно недоступен. Попробуйте позже."
        await message.answer(text)
        return

    lang = db.get_user_language(message.from_user.id)
    user = db.get_user_model(message.from_user.id)

    if not user:
        await message.answer(get_text(lang, "choose_language"), reply_markup=language_keyboard())
        return
    lang_text = "Русский" if lang == "ru" else "Ozbekcha"
    city_display = normalize_city(user.city) if user.city else "-"

    empty_value = "-"
    lines = [
        f"<b>{get_text(lang, 'your_profile')}</b>",
        f"{get_text(lang, 'name')}: <b>{user.first_name or empty_value}</b>",
        f"{get_text(lang, 'phone')}: <code>{user.phone or empty_value}</code>",
        f"{get_text(lang, 'city')}: <b>{city_display}</b>",
        f"{get_text(lang, 'language')}: {lang_text}",
    ]

    # Determine user role - check both DB role and if has approved store
    # This handles case where role wasn't updated but store was approved
    effective_role = user.role or "customer"
    if effective_role != "seller" and has_approved_store(message.from_user.id, db):
        effective_role = "seller"
        # Also fix the role in DB for future
        try:
            with db.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "UPDATE users SET role = 'seller' WHERE user_id = %s", (message.from_user.id,)
                )
        except Exception:
            pass

    # Determine current mode for settings keyboard
    # If user is seller, check their current mode, otherwise always customer
    # Default to customer mode if not explicitly set (safer - matches the menu they see after /start)
    if effective_role == "seller":
        current_mode = get_user_view_mode(message.from_user.id, db)
    else:
        current_mode = "customer"

    if effective_role == "seller":
        mode_label = "Режим" if lang == "ru" else "Rejim"
        if current_mode == "seller":
            mode_value = "Партнер" if lang == "ru" else "Hamkor"
        else:
            mode_value = "Покупатель" if lang == "ru" else "Xaridor"
        lines.append(f"{mode_label}: {mode_value}")

    # Customer statistics - show when in customer mode
    if current_mode == "customer":
        bookings = db.get_user_bookings(message.from_user.id)
        try:
            orders = db.get_user_orders(message.from_user.id)
        except Exception:
            orders = []

        active_bookings = len(
            [b for b in bookings if get_field(b, "status", 3) in ["pending", "confirmed"]]
        )
        completed_bookings = len([b for b in bookings if get_field(b, "status", 3) == "completed"])

        active_orders = len(
            [
                o
                for o in orders
                if get_field(o, "order_status", 10)
                in ["pending", "confirmed", "preparing", "delivering"]
            ]
        )
        completed_orders = len(
            [o for o in orders if get_field(o, "order_status", 10) == "completed"]
        )

        total_active = active_bookings + active_orders
        total_completed = completed_bookings + completed_orders

        if total_active > 0 or total_completed > 0:
            stats_title = "Статистика" if lang == "ru" else "Statistika"
            active_label = "Активные" if lang == "ru" else "Faol"
            done_label = "Завершенные" if lang == "ru" else "Yakunlangan"
            lines.append("")
            lines.append(f"<b>{stats_title}</b>")
            if total_active > 0:
                lines.append(f"{active_label}: {total_active}")
            if total_completed > 0:
                lines.append(f"{done_label}: {total_completed}")

    # Seller statistics - show when in seller mode
    elif current_mode == "seller" or user.role == "seller":
        stores = db.get_user_stores(message.from_user.id)
        if stores:
            total_bookings = 0
            total_orders = 0
            total_revenue = 0

            for store in stores:
                store_id = get_store_field(store, "store_id")
                if not store_id and isinstance(store, tuple | list) and len(store) > 0:
                    store_id = store[0]  # Fallback for tuple format
                store_bookings = db.get_store_bookings(store_id)

                # Filter completed bookings - handle dict format from PostgreSQL
                completed_bookings = []
                for b in store_bookings:
                    status = (
                        b.get("status") if isinstance(b, dict) else (b[3] if len(b) > 3 else None)
                    )
                    if status == "completed":
                        completed_bookings.append(b)

                total_bookings += len(completed_bookings)

                for booking in completed_bookings:
                    try:
                        if isinstance(booking, dict):
                            quantity = int(booking.get("quantity", 1))
                            # Calculate price from offer
                            offer = db.get_offer(booking.get("offer_id"))
                            if offer:
                                price = (
                                    float(offer.get("discount_price", 0))
                                    if isinstance(offer, dict)
                                    else float(offer[5])
                                    if len(offer) > 5
                                    else 0
                                )
                                total_revenue += int(quantity * price)
                        else:
                            quantity = int(booking[6]) if len(booking) > 6 else 1
                            price = float(booking[9]) if len(booking) > 9 else 0
                            total_revenue += int(quantity * price)
                    except Exception:
                        pass

            if total_bookings > 0 or total_orders > 0 or total_revenue > 0:
                stats_title = "Статистика" if lang == "ru" else "Statistika"
                bookings_label = "Брони" if lang == "ru" else "Bronlar"
                orders_label = "Заказы" if lang == "ru" else "Buyurtmalar"
                revenue_label = "Выручка" if lang == "ru" else "Daromad"
                currency = "сум" if lang == "ru" else "so'm"
                lines.append("")
                lines.append(f"<b>{stats_title}</b>")
                if total_bookings > 0:
                    lines.append(f"{bookings_label}: {total_bookings}")
                if total_orders > 0:
                    lines.append(f"{orders_label}: {total_orders}")
                if total_revenue > 0:
                    revenue_value = f"{total_revenue:,}".replace(",", " ")
                    lines.append(f"{revenue_label}: {revenue_value} {currency}")

    text = "\n".join(lines)
    await message.answer(
        text,
        parse_mode="HTML",
        reply_markup=settings_keyboard(
            user.notifications_enabled if hasattr(user, "notifications_enabled") else True,
            lang,
            role=effective_role,
            current_mode=current_mode,
        ),
    )


@router.callback_query(F.data == "profile_change_city")
async def profile_change_city(callback: types.CallbackQuery, state: FSMContext) -> None:
    """Start city change from profile."""
    if not db:
        lang_code = (callback.from_user.language_code or "ru") if callback.from_user else "ru"
        if lang_code.startswith("uz"):
            text = "❌ Xizmat vaqtincha mavjud emas. Keyinroq urinib ko'ring."
        else:
            text = "❌ Сервис временно недоступен. Попробуйте позже."
        await callback.answer(text)
        return

    lang = db.get_user_language(callback.from_user.id)
    try:
        await callback.message.edit_text(
            get_text(lang, "choose_city"),
            parse_mode="HTML",
            reply_markup=city_inline_keyboard(lang),
        )
    except Exception:
        await callback.message.answer(
            get_text(lang, "choose_city"),
            parse_mode="HTML",
            reply_markup=city_inline_keyboard(lang),
        )
    await state.set_state(ChangeCity.city)
    await callback.answer()


@router.callback_query(F.data.startswith("reg_city_"), StateFilter(ChangeCity.city))
async def profile_change_city_cb(callback: types.CallbackQuery, state: FSMContext) -> None:
    """Handle inline city selection from profile change flow."""
    if not db or not callback.message:
        lang_code = (callback.from_user.language_code or "ru") if callback.from_user else "ru"
        if lang_code.startswith("uz"):
            text_msg = "⚠️ Xizmat vaqtincha mavjud emas. Keyinroq urinib ko'ring."
        else:
            text_msg = "⚠️ Сервис временно недоступен. Попробуйте позже."
        await callback.answer(text_msg, show_alert=True)
        return

    assert callback.from_user is not None
    lang = db.get_user_language(callback.from_user.id)
    idx: int | None = None
    try:
        raw = callback.data or ""
        parts = raw.split("_", 2)
        idx_raw = parts[2] if len(parts) > 2 else ""
        if idx_raw == "":
            raise ValueError("empty city index")
        cities = get_cities(lang)
        try:
            idx = int(idx_raw)
            if idx < 0 or idx >= len(cities):
                raise IndexError("city index out of range")
            city = cities[idx]
        except ValueError:
            if idx_raw not in cities:
                raise ValueError("city not found")
            city = idx_raw
    except Exception:
        await callback.answer(get_text(lang, "error"), show_alert=True)
        return

    normalized_city = normalize_city(city)
    region_key = get_region_key_for_city_index(idx)
    district_options = get_districts_for_city_index(idx, lang)
    if not district_options:
        district_options = get_districts_for_region(city, lang)
    if district_options:
        region_value = normalize_city(region_key or city)
        await state.update_data(
            region_label=city,
            region_value=region_value,
            region_key=region_key,
        )
        await state.set_state(ChangeCity.district)
        builder = InlineKeyboardBuilder()
        for idx, (label, _value) in enumerate(district_options):
            builder.button(text=f"\U0001F4CD {label}", callback_data=f"select_district:{idx}")
        builder.adjust(2)
        prompt = ("Выберите район/город в области:" if lang == "ru" else "Viloyatdagi tuman/shaharni tanlang:")
        await callback.message.edit_text(prompt, reply_markup=builder.as_markup())
        await callback.answer()
        return

    if hasattr(db, "update_user_location"):
        db.update_user_location(
            callback.from_user.id,
            city=normalized_city,
            clear_region=True,
            clear_district=True,
        )
    else:
        db.update_user_city(callback.from_user.id, normalized_city)
    await state.clear()

    await callback.message.answer(
        get_text(lang, "city_changed_confirm", city=city),
        parse_mode="HTML",
        reply_markup=main_menu_customer(lang),
    )
    await callback.answer()


@router.callback_query(F.data == "switch_to_customer")
async def switch_to_customer_cb(callback: types.CallbackQuery) -> None:
    """Switch to customer mode from profile."""
    if not db:
        logger.error("❌ switch_to_customer_cb: db is None")
        lang_code = (callback.from_user.language_code or "ru") if callback.from_user else "ru"
        if lang_code.startswith("uz"):
            text = "❌ Xizmat vaqtincha mavjud emas. Keyinroq urinib ko'ring."
        else:
            text = "❌ Сервис временно недоступен. Попробуйте позже."
        await callback.answer(text, show_alert=True)
        return

    if not callback.message:
        logger.error("❌ switch_to_customer_cb: callback.message is None")
        lang_code = (callback.from_user.language_code or "ru") if callback.from_user else "ru"
        if lang_code.startswith("uz"):
            text = "❌ Xizmat vaqtincha mavjud emas. Keyinroq urinib ko'ring."
        else:
            text = "❌ Сервис временно недоступен. Попробуйте позже."
        await callback.answer(text, show_alert=True)
        return

    try:
        user_id = callback.from_user.id
        logger.info(f"🔄 User {user_id} switching to customer mode")

        lang = db.get_user_language(user_id)

        # Set customer mode
        try:
            set_user_view_mode(user_id, "customer", db)
            logger.info(f"✅ User {user_id} switched to customer mode")
        except Exception as e:
            logger.error(f"❌ Error setting user view mode for {user_id}: {e}", exc_info=True)
            await callback.answer(
                "Ошибка при смене режима" if lang == "ru" else "Rejim o'zgartirishda xatolik",
                show_alert=True,
            )
            return

        # Send new message with ReplyKeyboard (cannot use edit_text with ReplyKeyboard)
        try:
            await callback.message.answer(
                get_text(lang, "switched_to_customer"),
                reply_markup=main_menu_customer(lang),
            )
            await callback.answer()
        except Exception as e:
            logger.error(f"❌ Error sending customer menu to user {user_id}: {e}", exc_info=True)
            await callback.answer(
                "Ошибка отправки меню" if lang == "ru" else "Menyu yuborishda xatolik",
                show_alert=True,
            )
    except Exception as e:
        logger.error(f"❌ Unexpected error in switch_to_customer_cb: {e}", exc_info=True)
        try:
            lang = db.get_user_language(callback.from_user.id)
        except Exception:
            lang = "ru"
        await callback.answer(
            f"Произошла ошибка: {str(e)}" if lang == "ru" else f"Xatolik yuz berdi: {str(e)}",
            show_alert=True,
        )


@router.callback_query(F.data == "switch_to_seller")
async def switch_to_seller_cb(callback: types.CallbackQuery) -> None:
    """Switch to seller mode from profile."""
    if not db:
        logger.error("❌ switch_to_seller_cb: db is None")
        await callback.answer("System error", show_alert=True)
        return

    if not callback.message:
        logger.error("❌ switch_to_seller_cb: callback.message is None")
        await callback.answer("System error", show_alert=True)
        return

    try:
        user_id = callback.from_user.id
        logger.info(f"🔄 User {user_id} attempting to switch to seller mode")

        lang = db.get_user_language(user_id)
        logger.debug(f"User {user_id} language: {lang}")

        user = db.get_user_model(user_id)
        if not user:
            logger.error(f"❌ User {user_id} not found in database")
            await callback.answer(
                "Пользователь не найден" if lang == "ru" else "Foydalanuvchi topilmadi",
                show_alert=True,
            )
            return

        # Check if user is a seller (role is "seller" or "store_owner") AND has approved store
        user_role = getattr(user, "role", "customer")
        logger.debug(f"User {user_id} role from DB: {user_role}")

        if user_role == "store_owner":
            user_role = "seller"

        # Check for approved store
        try:
            has_store = has_approved_store(user_id, db)
            logger.debug(f"User {user_id} has approved store: {has_store}")
        except Exception as e:
            logger.error(f"❌ Error checking approved store for user {user_id}: {e}", exc_info=True)
            has_store = False

        is_seller = user_role == "seller" and has_store

        if not is_seller:
            logger.info(
                f"❌ User {user_id} denied switch to seller mode (role={user_role}, has_store={has_store})"
            )
            await callback.answer(
                "Только партнеры с одобренным магазином могут использовать этот режим"
                if lang == "ru"
                else "Faqat tasdiqlangan do'konga ega hamkorlar bu rejimdan foydalanishlari mumkin",
                show_alert=True,
            )
            return

        # Set seller mode
        try:
            set_user_view_mode(user_id, "seller", db)
            logger.info(f"✅ User {user_id} switched to seller mode")
        except Exception as e:
            logger.error(f"❌ Error setting user view mode for {user_id}: {e}", exc_info=True)
            await callback.answer(
                "Ошибка при смене режима" if lang == "ru" else "Rejim o'zgartirishda xatolik",
                show_alert=True,
            )
            return

        # Send new message with ReplyKeyboard
        try:
            # Get partner panel URL
            from handlers.common.webapp import get_partner_panel_url

            webapp_url = get_partner_panel_url()

            await callback.message.answer(
                "Переключено в режим партнера" if lang == "ru" else "Hamkor rejimiga o'tkazildi",
                reply_markup=main_menu_seller(lang, webapp_url=webapp_url, user_id=user_id),
            )
            await callback.answer()
        except Exception as e:
            logger.error(f"❌ Error sending seller menu to user {user_id}: {e}", exc_info=True)
            await callback.answer(
                "Ошибка отправки меню" if lang == "ru" else "Menyu yuborishda xatolik",
                show_alert=True,
            )
    except Exception as e:
        logger.error(f"❌ Unexpected error in switch_to_seller_cb: {e}", exc_info=True)
        try:
            lang = db.get_user_language(callback.from_user.id)
        except Exception:
            lang = "ru"
        await callback.answer(
            f"Произошла ошибка: {str(e)}" if lang == "ru" else f"Xatolik yuz berdi: {str(e)}",
            show_alert=True,
        )


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
    current_mode = get_user_view_mode(callback.from_user.id, db)

    try:
        await callback.message.edit_text(
            text,
            parse_mode="HTML",
            reply_markup=settings_keyboard(new_enabled, lang, role=role, current_mode=current_mode),
        )
    except Exception:
        await callback.message.answer(
            text,
            reply_markup=settings_keyboard(new_enabled, lang, role=role, current_mode=current_mode),
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
    builder.button(text=get_text(lang, "yes_delete"), callback_data="confirm_delete_yes")
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
async def confirm_delete_yes(callback: types.CallbackQuery, state: FSMContext) -> None:
    """Confirm account deletion."""
    if not db:
        await callback.answer("System error")
        return

    # Get language BEFORE deleting user
    lang = db.get_user_language(callback.from_user.id)
    user_id = callback.from_user.id

    try:
        # Clear FSM state first
        await state.clear()

        # Clear user view mode cache
        try:
            set_user_view_mode(user_id, "customer", db)
        except Exception:
            pass

        # Delete user from database
        db.delete_user(user_id)
        logger.info(f"User {user_id} deleted their account successfully")
    except Exception as e:
        logger.error(f"Error deleting user {user_id}: {e}")
        capture_exception(e, user_id=user_id, action="delete_account")
        await callback.answer(get_text(lang, "error"), show_alert=True)
        return

    # Remove Reply keyboard first
    try:
        await callback.message.answer(
            get_text(lang, "account_deleted"),
            reply_markup=ReplyKeyboardRemove(),
        )
    except Exception:
        pass

    try:
        await callback.message.edit_text(
            get_text(lang, "choose_language"),
            parse_mode="HTML",
            reply_markup=language_keyboard(),
        )
    except Exception:
        await callback.message.answer(
            get_text(lang, "choose_language"),
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

    current_mode = get_user_view_mode(callback.from_user.id, db)

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
    if not db:
        await message.answer("System error")
        return

    lang = db.get_user_language(message.from_user.id)
    set_user_view_mode(message.from_user.id, "customer", db)

    await message.answer(
        get_text(lang, "switched_to_customer"), reply_markup=main_menu_customer(lang)
    )


