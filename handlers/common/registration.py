"""
User registration handlers (phone and city collection).
"""
from aiogram import F, Router, types
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext

from app.core.sanitize import sanitize_phone
from app.core.security import logger, rate_limiter, secure_user_input, validator
from app.core.utils import normalize_city
from app.keyboards import (
    city_inline_keyboard,
    city_keyboard,
    main_menu_customer,
    phone_request_keyboard,
)
from database_protocol import DatabaseProtocol
from handlers.common.states import Registration
from localization import get_cities, get_text

router = Router(name="registration")


async def _after_phone_saved(
    message: types.Message, state: FSMContext, db: DatabaseProtocol, lang: str
) -> None:
    data = await state.get_data()
    pending_order = data.get("pending_order")
    pending_cart_checkout = data.get("pending_cart_checkout")

    from aiogram.types import ReplyKeyboardRemove

    ru_phone_saved = "✅ Телефон сохранен!"
    uz_phone_saved = "✅ Telefon saqlandi!"

    if pending_cart_checkout:
        await message.answer(
            ru_phone_saved if lang == "ru" else uz_phone_saved,
            reply_markup=ReplyKeyboardRemove(),
        )

        try:
            from handlers.customer.cart.router import show_cart

            await show_cart(message, state, is_callback=False)
        except Exception as e:  # pragma: no cover - defensive logging
            logger.warning(f"Failed to resume cart after phone: {e}")
            from app.keyboards import main_menu_customer

            ru_text = (
                "Теперь откройте "
                "<Сават> и нажмите "
                "<Оформить заказ> заново."
            )
            uz_text = "Endi <Savat> ni ochib, <Buyurtma berish> ni qayta bosing."

            await message.answer(
                ru_text if lang == "ru" else uz_text,
                reply_markup=main_menu_customer(lang),
            )

        await state.clear()
        return

    if pending_order:
        await message.answer(
            ru_phone_saved if lang == "ru" else uz_phone_saved,
            reply_markup=ReplyKeyboardRemove(),
        )

        data = await state.get_data()
        offer_id = data.get("offer_id")
        store_id = data.get("store_id")
        delivery_method = data.get("selected_delivery")

        if not offer_id or not store_id or not delivery_method:
            await state.clear()
            from app.keyboards import main_menu_customer

            ru_text = "Продолжите через <Акции>"
            uz_text = "Aksiyalar orqali davom eting"

            await message.answer(
                ru_text if lang == "ru" else uz_text,
                reply_markup=main_menu_customer(lang),
            )
            return

        from aiogram.utils.keyboard import InlineKeyboardBuilder

        kb = InlineKeyboardBuilder()
        ru_button = "✅ Продолжить"
        uz_button = "✅ Davom ettirish"
        kb.button(
            text=ru_button if lang == "ru" else uz_button,
            callback_data=f"pbook_confirm_{offer_id}",
        )

        ru_text = (
            "Нажмите кнопку ниже, "
            "чтобы продолжить:"
        )
        uz_text = "Davom etish uchun tugmani bosing:"

        await message.answer(
            ru_text if lang == "ru" else uz_text,
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
            ru_phone_saved if lang == "ru" else uz_phone_saved,
            reply_markup=ReplyKeyboardRemove(),
        )

        choose_text = "Tanlang" if lang == "uz" else "Выберите"
        await message.answer(
            f"👉 {choose_text}:",
            reply_markup=main_menu_customer(lang),
        )
        return

    ru_city_title = "Выберите ваш город"
    uz_city_title = "Shahringizni tanlang"
    ru_city_hint = "Покажем предложения рядом"
    uz_city_hint = "Yaqin takliflarni ko'rsatamiz"

    city_text = (
        f"✅ {uz_phone_saved if lang == 'uz' else ru_phone_saved}\n\n"
        f"📍 <b>{uz_city_title if lang == 'uz' else ru_city_title}</b>\n\n"
        f"{uz_city_hint if lang == 'uz' else ru_city_hint}"
    )

    await state.set_state(Registration.city)
    await message.answer(
        city_text,
        parse_mode="HTML",
        reply_markup=ReplyKeyboardRemove(),
    )
    choose_text = "Tanlang" if lang == "uz" else "Выберите"
    await message.answer(
        f"👉 {choose_text}:",
        reply_markup=city_inline_keyboard(lang, allow_cancel=False),
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


@router.callback_query(F.data.startswith("reg_city_"), StateFilter(Registration.city, None))
async def registration_city_callback(
    callback: types.CallbackQuery, state: FSMContext, db: DatabaseProtocol
):
    """Handle city selection - complete registration."""
    if not db or not callback.message:
        await callback.answer("System error", show_alert=True)
        return

    lang = db.get_user_language(callback.from_user.id)

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
    try:
        db.update_user_city(callback.from_user.id, normalized_city)
        logger.info(f"City updated for user {callback.from_user.id}: {normalized_city}")
    except Exception as e:
        logger.error(f"Failed to update city: {e}")

    await state.clear()

    user = db.get_user_model(callback.from_user.id)
    name = user.first_name if user else callback.from_user.first_name

    title = "Tayyor!" if lang == "uz" else "Готово!"
    welcome = "Xush kelibsiz" if lang == "uz" else "Добро пожаловать"
    city_label = "Shahar" if lang == "uz" else "Город"
    can_do = "Endi siz qila olasiz" if lang == "uz" else "Теперь вы можете"
    offers = "Aksiyalar" if lang == "uz" else "Акции"
    offers_hint = "70% gacha chegirmalar" if lang == "uz" else "скидки до 70%"
    stores = "Do'konlar" if lang == "uz" else "Магазины"
    stores_hint = "barcha do'konlar" if lang == "uz" else "все магазины"
    search = "Qidirish" if lang == "uz" else "Поиск"
    search_hint = "mahsulot topish" if lang == "uz" else "найти товар"

    complete_text = (
        f"🎉 <b>{title}</b>\n\n"
        f"👋 {welcome}, {name}!\n"
        f"📍 {city_label}: {city}\n\n"
        f"{can_do}:\n"
        f"🔥 <b>{offers}</b> ? {offers_hint}\n"
        f"🏪 <b>{stores}</b> ? {stores_hint}\n"
        f"🔎 <b>{search}</b> ? {search_hint}"
    )

    try:
        await callback.message.edit_text(complete_text, parse_mode="HTML")
    except Exception:
        pass

    choose_text = "Tanlang" if lang == "uz" else "Выберите"
    await callback.message.answer(
        f"👉 {choose_text}:",
        reply_markup=main_menu_customer(lang),
    )
    await callback.answer()


# OLD TEXT-BASED CITY HANDLER REMOVED
# City is now selected ONLY via inline buttons (select_city:) in commands.py
# This prevents accidental triggering when user types numbers during registration
