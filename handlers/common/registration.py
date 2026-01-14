"""
User registration handlers (phone and city collection).
"""
from aiogram import F, Router, types
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.core.location_data import get_districts_for_city_index, get_districts_for_region, get_region_key_for_city_index
from app.core.sanitize import sanitize_phone
from app.core.security import logger, rate_limiter, secure_user_input, validator
from app.core.utils import normalize_city
from app.keyboards import (
    city_inline_keyboard,
    main_menu_customer,
    phone_request_keyboard,
)
from database_protocol import DatabaseProtocol
from handlers.common.states import Registration
from handlers.common.webapp import webapp_keyboard
from localization import get_cities, get_text

router = Router(name="registration")
REGISTRATION_COMPLETE_STICKER_ID = None


def _build_district_keyboard(
    options: list[tuple[str, str]],
) -> types.InlineKeyboardMarkup | None:
    if not options:
        return None
    builder = InlineKeyboardBuilder()
    for idx, (label, _value) in enumerate(options):
        builder.button(text=label, callback_data=f"reg_district_{idx}")
    builder.adjust(1)
    return builder.as_markup()


async def _after_phone_saved(
    message: types.Message, state: FSMContext, db: DatabaseProtocol, lang: str
) -> None:
    data = await state.get_data()
    pending_order = data.get("pending_order")
    pending_cart_checkout = data.get("pending_cart_checkout")

    from aiogram.types import ReplyKeyboardRemove

    if pending_cart_checkout:
        await message.answer(
            get_text(lang, "phone_saved"),
            reply_markup=ReplyKeyboardRemove(),
        )

        try:
            from handlers.customer.cart.router import show_cart

            await show_cart(message, state, is_callback=False)
        except Exception as e:  # pragma: no cover - defensive logging
            logger.warning(f"Failed to resume cart after phone: {e}")
            from app.keyboards import main_menu_customer

            await message.answer(
                get_text(lang, "registration_resume_cart"),
                reply_markup=main_menu_customer(lang),
            )

        await state.clear()
        return

    if pending_order:
        await message.answer(
            get_text(lang, "phone_saved"),
            reply_markup=ReplyKeyboardRemove(),
        )

        data = await state.get_data()
        offer_id = data.get("offer_id")
        store_id = data.get("store_id")
        delivery_method = data.get("selected_delivery")

        if not offer_id or not store_id or not delivery_method:
            await state.clear()
            from app.keyboards import main_menu_customer

            await message.answer(
                get_text(lang, "registration_continue_offers"),
                reply_markup=main_menu_customer(lang),
            )
            return

        from aiogram.utils.keyboard import InlineKeyboardBuilder

        kb = InlineKeyboardBuilder()
        kb.button(
            text=get_text(lang, "registration_continue_button"),
            callback_data=f"pbook_confirm_{offer_id}",
        )

        await message.answer(
            get_text(lang, "registration_continue_prompt"),
            reply_markup=kb.as_markup(),
        )
        return

    user_city_raw = None
    if hasattr(db, "get_user"):
        user_data = db.get_user(message.from_user.id)
        if isinstance(user_data, dict):
            user_city_raw = user_data.get("city")
        elif user_data and len(user_data) > 4:
            user_city_raw = user_data[4]

    default_city = normalize_city(get_cities("ru")[0])
    user_city = normalize_city(user_city_raw) if user_city_raw else None

    if user_city and user_city != default_city:
        await state.clear()
        from app.keyboards import main_menu_customer

        await message.answer(
            get_text(lang, "phone_saved"),
            reply_markup=ReplyKeyboardRemove(),
        )

        await message.answer(
            get_text(lang, "registration_choose_action"),
            reply_markup=main_menu_customer(lang),
        )
        return

    city_text = "\n\n".join(
        [
            get_text(lang, "phone_saved"),
            f"<b>{get_text(lang, 'registration_city_title')}</b>",
            get_text(lang, "registration_city_hint"),
        ]
    )

    await state.set_state(Registration.city)
    await message.answer(
        city_text,
        parse_mode="HTML",
        reply_markup=ReplyKeyboardRemove(),
    )
    await message.answer(
        get_text(lang, "registration_city_title"),
        reply_markup=city_inline_keyboard(lang, allow_cancel=False),
    )


async def _send_completion_menu(message: types.Message, lang: str) -> None:
    menu = main_menu_customer(lang)
    if REGISTRATION_COMPLETE_STICKER_ID:
        try:
            await message.answer_sticker(
                REGISTRATION_COMPLETE_STICKER_ID,
                reply_markup=menu,
            )
            return
        except Exception:
            pass
    await message.answer(
        get_text(lang, "registration_choose_action"),
        reply_markup=menu,
    )


async def _save_phone(
    message: types.Message,
    db: DatabaseProtocol,
    lang: str,
    raw_phone: str | None,
    error_text: str,
) -> str | None:
    if not raw_phone:
        await message.answer("System error")
        return None

    phone = sanitize_phone(raw_phone)
    if not validator.validate_phone(phone):
        await message.answer(
            error_text,
            reply_markup=phone_request_keyboard(lang),
        )
        return None

    db.update_user_phone(message.from_user.id, phone)
    return phone


@router.message(Registration.phone, F.contact)
async def process_phone(message: types.Message, state: FSMContext, db: DatabaseProtocol):
    """Process phone number - save and continue (order or city selection)."""
    if not db:
        await message.answer("System error")
        return

    lang = db.get_user_language(message.from_user.id)
    if (
        message.contact
        and message.contact.user_id
        and message.contact.user_id != message.from_user.id
    ):
        await message.answer(
            get_text(lang, "error_invalid_number"),
            reply_markup=phone_request_keyboard(lang),
        )
        return
    phone = await _save_phone(
        message,
        db,
        lang,
        message.contact.phone_number,
        get_text(lang, "error_invalid_number"),
    )
    if not phone:
        return

    await _after_phone_saved(message, state, db, lang)


@router.message(Registration.phone, F.text)
async def process_phone_text(message: types.Message, state: FSMContext, db: DatabaseProtocol):
    """Process typed phone number - save and continue."""
    if not db:
        await message.answer("System error")
        return
    if not message.text:
        return

    lang = db.get_user_language(message.from_user.id)
    phone = await _save_phone(
        message,
        db,
        lang,
        message.text,
        get_text(lang, "error_invalid_number"),
    )
    if not phone:
        return

    await _after_phone_saved(message, state, db, lang)


@router.callback_query(F.data.startswith("reg_city_"), StateFilter(Registration.city))
async def registration_city_callback(
    callback: types.CallbackQuery, state: FSMContext, db: DatabaseProtocol
):
    """Handle city selection - complete registration."""
    if not db or not callback.message:
        await callback.answer("System error", show_alert=True)
        return

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
    except Exception as e:
        logger.error(f"City parse error: {e}")
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
        await state.set_state(Registration.district)
        keyboard = _build_district_keyboard(district_options)
        prompt = "Выберите район." if lang == "ru" else "Tumanni tanlang."
        if callback.message:
            try:
                await callback.message.edit_text(prompt, reply_markup=keyboard)
            except Exception:
                await callback.message.answer(prompt, reply_markup=keyboard)
        await callback.answer()
        return

    try:
        if hasattr(db, "update_user_location"):
            db.update_user_location(
                callback.from_user.id,
                city=normalized_city,
                clear_region=True,
                clear_district=True,
            )
        else:
            db.update_user_city(callback.from_user.id, normalized_city)
        logger.info(f"City updated for user {callback.from_user.id}: {normalized_city}")
    except Exception as e:
        logger.error(f"Failed to update city: {e}")

    await state.clear()

    user = db.get_user_model(callback.from_user.id)
    name = user.first_name if user else callback.from_user.first_name

    complete_text = get_text(
        lang,
        "registration_complete_personal",
        name=name,
        city=city,
    )
    webapp_markup = webapp_keyboard(lang)

    try:
        await callback.message.edit_text(
            complete_text,
            parse_mode="HTML",
            reply_markup=webapp_markup,
        )
    except Exception:
        await callback.message.answer(
            complete_text,
            parse_mode="HTML",
            reply_markup=webapp_markup,
        )

    await _send_completion_menu(callback.message, lang)
    await callback.answer()


@router.callback_query(F.data.startswith("reg_district_"), StateFilter(Registration.district))
async def registration_district_callback(
    callback: types.CallbackQuery, state: FSMContext, db: DatabaseProtocol
):
    """Handle district selection - complete registration."""
    if not db or not callback.message:
        await callback.answer("System error", show_alert=True)
        return

    lang = db.get_user_language(callback.from_user.id)
    data = await state.get_data()
    region_label = data.get("region_label")
    region_key = data.get("region_key")
    region_value = data.get("region_value") or normalize_city(region_key or region_label or "")

    try:
        raw = callback.data or ""
        idx_raw = raw.split("_", 2)[2] if "_" in raw else ""
        if idx_raw == "":
            raise ValueError("empty district index")
        options = get_districts_for_region(region_label or region_value, lang)
        idx = int(idx_raw)
        if idx < 0 or idx >= len(options):
            raise IndexError("district index out of range")
        district_label, district_value = options[idx]
    except Exception as e:
        logger.error(f"District parse error: {e}")
        await callback.answer(get_text(lang, "error"), show_alert=True)
        return

    try:
        if hasattr(db, "update_user_location"):
            db.update_user_location(
                callback.from_user.id,
                city=region_value,
                region=region_value,
                district=district_value,
            )
        else:
            db.update_user_city(callback.from_user.id, region_value)
        logger.info(
            "Location updated for user %s: city=%s region=%s district=%s",
            callback.from_user.id,
            region_value,
            region_value,
            district_value,
        )
    except Exception as e:
        logger.error(f"Failed to update district: {e}")

    await state.clear()

    user = db.get_user_model(callback.from_user.id)
    name = user.first_name if user else callback.from_user.first_name
    city_display = region_label or region_key or region_value
    if district_label:
        city_display = f"{city_display} / {district_label}"

    complete_text = get_text(
        lang,
        "registration_complete_personal",
        name=name,
        city=city_display,
    )
    webapp_markup = webapp_keyboard(lang)

    try:
        await callback.message.edit_text(
            complete_text,
            parse_mode="HTML",
            reply_markup=webapp_markup,
        )
    except Exception:
        await callback.message.answer(
            complete_text,
            parse_mode="HTML",
            reply_markup=webapp_markup,
        )

    await _send_completion_menu(callback.message, lang)
    await callback.answer()


# OLD TEXT-BASED CITY HANDLER REMOVED
# City is now selected ONLY via inline buttons (select_city:) in commands.py
# This prevents accidental triggering when user types numbers during registration


