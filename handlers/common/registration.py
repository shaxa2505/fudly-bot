"""
User registration handlers (phone and city collection).
"""
from aiogram import F, Router, types
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext

from app.core.security import logger, rate_limiter, secure_user_input, validator
from app.keyboards import (
    city_inline_keyboard,
    city_keyboard,
    main_menu_customer,
    phone_request_keyboard,
)
from database_protocol import DatabaseProtocol
from handlers.common.states import Registration
from localization import get_text

router = Router(name="registration")


@router.message(Registration.phone, F.contact)
async def process_phone(message: types.Message, state: FSMContext, db: DatabaseProtocol):
    """Process phone number - save and continue (order or city selection)."""
    if not db:
        await message.answer("System error")
        return

    lang = db.get_user_language(message.from_user.id)
    phone = message.contact.phone_number

    if not validator.validate_phone(phone):
        await message.answer(
            "❌ Неверный формат номера. Используйте кнопку ниже."
            if lang == "ru"
            else "❌ Telefon raqami noto'g'ri. Quyidagi tugmadan foydalaning.",
            reply_markup=phone_request_keyboard(lang),
        )
        return

    db.update_user_phone(message.from_user.id, phone)

    # Check if there was a pending order
    data = await state.get_data()
    pending_order = data.get("pending_order")
    pending_cart_checkout = data.get("pending_cart_checkout")

    from aiogram.types import ReplyKeyboardRemove

    # Handle cart and order pending states
    if pending_cart_checkout or pending_order:
        await message.answer(
            "✅ Телефон сохранён!"
            if lang == "ru"
            else "✅ Telefon saqlandi!",
            reply_markup=ReplyKeyboardRemove(),
        )
        
        # Get order data to show confirmation button
        data = await state.get_data()
        offer_id = data.get("offer_id")
        store_id = data.get("store_id")
        quantity = data.get("selected_qty", 1)
        delivery_method = data.get("selected_delivery")
        
        # Check if we have minimum required data
        if not offer_id or not store_id or not delivery_method:
            # Data incomplete - show menu
            await state.clear()
            from app.keyboards import main_menu_customer
            await message.answer(
                "⚠️ Продолжите оформление через 🛒 Корзина или 🔥 Горячее"
                if lang == "ru"
                else "⚠️ 🛒 Savat yoki 🔥 Issiq orqali davom eting",
                reply_markup=main_menu_customer(lang),
            )
            return
        
        # Show confirmation button to continue
        from aiogram.utils.keyboard import InlineKeyboardBuilder
        kb = InlineKeyboardBuilder()
        kb.button(
            text="✅ Продолжить оформление" if lang == "ru" else "✅ Davom ettirish",
            callback_data=f"pbook_confirm_{offer_id}"
        )
        
        await message.answer(
            "👇 Нажмите кнопку ниже для продолжения:"
            if lang == "ru"
            else "👇 Davom etish uchun tugmani bosing:",
            reply_markup=kb.as_markup()
        )
        return

    if pending_order:
        # User was trying to place an order but needed to provide phone first
        # DECISION: Don't try to restore complex state - just show menu and let user start fresh
        # This is more reliable and better UX than trying to restore potentially corrupted state
        
        await state.clear()
        
        from aiogram.types import ReplyKeyboardRemove
        from app.keyboards import main_menu_customer

        await message.answer(
            "✅ Телефон сохранён!"
            if lang == "ru"
            else "✅ Telefon saqlandi!",
            reply_markup=ReplyKeyboardRemove(),
        )

        await message.answer(
            "👇 Теперь выберите товар через меню ниже:"
            if lang == "ru"
            else "👇 Endi quyidagi menyudan mahsulot tanlang:",
            reply_markup=main_menu_customer(lang),
        )
        return

    # Check if user already has a city set - skip city selection
    user = db.get_user_model(message.from_user.id)
    if user and user.city:
        # User already has city, complete registration
        await state.clear()

        from aiogram.types import ReplyKeyboardRemove

        from app.keyboards import main_menu_customer

        await message.answer(
            "✅ Телефон сохранён!" if lang == "ru" else "✅ Telefon saqlandi!",
            reply_markup=ReplyKeyboardRemove(),
        )

        # Send main menu
        await message.answer(
            f"👇 {'Tanlang' if lang == 'uz' else 'Выберите'}:",
            reply_markup=main_menu_customer(lang),
        )
        return

    # Normal registration flow - show city selection
    city_text = (
        f"✅ {'Telefon saqlandi!' if lang == 'uz' else 'Телефон сохранён!'}\n\n"
        f"📍 <b>{'Shahringizni tanlang' if lang == 'uz' else 'Выберите ваш город'}</b>\n\n"
        f"{'Yaqin takliflarni koʻrsatamiz' if lang == 'uz' else 'Покажем предложения рядом с вами'}"
    )

    await state.set_state(Registration.city)

    # Remove reply keyboard and show inline cities
    from aiogram.types import ReplyKeyboardRemove

    await message.answer(
        city_text,
        parse_mode="HTML",
        reply_markup=ReplyKeyboardRemove(),
    )
    await message.answer(
        f"👇 {'Tanlang' if lang == 'uz' else 'Выберите'}:",
        reply_markup=city_inline_keyboard(lang),
    )


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
        city = parts[2] if len(parts) > 2 else ""
        if not city:
            raise ValueError("empty city")
    except Exception as e:
        logger.error(f"City parse error: {e}")
        await callback.answer(get_text(lang, "error"), show_alert=True)
        return

    try:
        db.update_user_city(callback.from_user.id, city)
        logger.info(f"City updated for user {callback.from_user.id}: {city}")
    except Exception as e:
        logger.error(f"Failed to update city: {e}")

    await state.clear()

    # Edit message to show completion
    user = db.get_user_model(callback.from_user.id)
    name = user.first_name if user else callback.from_user.first_name

    complete_text = (
        f"🎉 <b>{'Tayyor!' if lang == 'uz' else 'Готово!'}</b>\n\n"
        f"👋 {'Xush kelibsiz' if lang == 'uz' else 'Добро пожаловать'}, {name}!\n"
        f"📍 {'Shahar' if lang == 'uz' else 'Город'}: {city}\n\n"
        f"{'Endi siz qila olasiz' if lang == 'uz' else 'Теперь вы можете'}:\n"
        f"🔥 <b>{'Issiq' if lang == 'uz' else 'Горячее'}</b> — {'eng yaxshi chegirmalar' if lang == 'uz' else 'лучшие скидки'}\n"
        f"🏪 <b>{'Doʻkonlar' if lang == 'uz' else 'Заведения'}</b> — {'barcha doʻkonlar' if lang == 'uz' else 'все магазины'}\n"
        f"🔍 <b>{'Qidirish' if lang == 'uz' else 'Поиск'}</b> — {'mahsulot topish' if lang == 'uz' else 'найти товар'}"
    )

    try:
        await callback.message.edit_text(complete_text, parse_mode="HTML")
    except Exception:
        pass

    # Send main menu (single message)
    await callback.message.answer(
        f"👇 {'Tanlang' if lang == 'uz' else 'Выберите'}:",
        reply_markup=main_menu_customer(lang),
    )
    await callback.answer()


# OLD TEXT-BASED CITY HANDLER REMOVED
# City is now selected ONLY via inline buttons (select_city:) in commands.py
# This prevents accidental triggering when user types numbers during registration
