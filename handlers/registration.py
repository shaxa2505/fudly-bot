"""
User registration handlers (phone and city collection)
"""
from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext

from handlers.common import Registration

router = Router()


def setup(dp_or_router, db, get_text, get_cities, city_keyboard, phone_request_keyboard, main_menu_customer, 
          validator, rate_limiter, logger, secure_user_input):
    """Setup registration handlers with dependencies"""
    
    @dp_or_router.message(Registration.phone, F.contact)
    async def process_phone(message: types.Message, state: FSMContext):
        # User must be created when choosing language
        lang = db.get_user_language(message.from_user.id)
        phone = message.contact.phone_number
        
        # Validate phone format
        if not validator.validate_phone(phone):
            await message.answer(
                "Неверный формат номера. Используйте кнопку ниже." if lang == 'ru' else "Telefon raqami noto'g'ri. Quyidagi tugmadan foydalaning.",
                reply_markup=phone_request_keyboard(lang)
            )
            return
        
        # Save phone and set default city (Tashkent)
        db.update_user_phone(message.from_user.id, phone)
        db.update_user_city(message.from_user.id, "Ташкент")
        
        # Clear state and show main menu
        await state.clear()
        
        # Compact, professional message
        welcome_text = (
            f"Регистрация завершена.\n"
            f"Ваш город: <b>Ташкент</b>\n\n"
            f"Изменить город можно в Профиле."
            if lang == 'ru' else
            f"Ro'yxatdan o'tish yakunlandi.\n"
            f"Sizning shahringiz: <b>Toshkent</b>\n\n"
            f"Shaharni Profilda o'zgartirish mumkin."
        )
        
        await message.answer(
            get_text(lang, "registration_complete"),
            parse_mode="HTML",
            reply_markup=main_menu_customer(lang)
        )

    @dp_or_router.message(Registration.city)
    @secure_user_input
    async def process_city(message: types.Message, state: FSMContext):
        """Handle city selection (now used only when changing city from profile)"""
        lang = db.get_user_language(message.from_user.id)
        
        # Rate limiting check
        try:
            if not rate_limiter.is_allowed(message.from_user.id, 'city_selection', max_requests=5, window_seconds=60):
                await message.answer(get_text(lang, 'rate_limit_exceeded'))
                return
        except Exception as e:
            logger.warning(f"Rate limiter error: {e}")
        
        cities = get_cities(lang)
        city_text = validator.sanitize_text(message.text.replace("📍 ", "").strip())
        
        # Validate city input
        if not validator.validate_city(city_text):
            await message.answer(get_text(lang, 'invalid_city'))
            return
        
        if city_text in cities:
            db.update_user_city(message.from_user.id, city_text)
            await state.clear()
            
            # Compact confirmation
            await callback.message.answer(
                f"Город изменён на <b>{city_text}</b>" if lang == 'ru' else f"Shahar <b>{city_text}</b>ga o'zgartirildi",
                parse_mode="HTML",
                reply_markup=main_menu_customer(lang)
            )
