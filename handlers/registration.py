"""
User registration handlers (phone and city collection)
"""
from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext

from handlers.common import Registration
from database_protocol import DatabaseProtocol
from localization import get_text, get_cities
from app.keyboards import city_keyboard, phone_request_keyboard, main_menu_customer
from app.core.security import validator, rate_limiter, secure_user_input, logger

router = Router()


def setup(dp_or_router, db, get_text, get_cities, city_keyboard, phone_request_keyboard, main_menu_customer, 
          validator, rate_limiter, logger, secure_user_input):
    """Setup registration handlers with dependencies"""
    # Kept for backward compatibility
    pass
    
@router.message(Registration.phone, F.contact)
async def process_phone(message: types.Message, state: FSMContext, db: DatabaseProtocol):
    """Process phone number with improved messaging."""
    lang = db.get_user_language(message.from_user.id)
    phone = message.contact.phone_number
    
    # Validate phone format
    if not validator.validate_phone(phone):
        await message.answer(
            "❌ Неверный формат номера. Используйте кнопку ниже." if lang == 'ru' else "❌ Telefon raqami noto'g'ri. Quyidagi tugmadan foydalaning.",
            reply_markup=phone_request_keyboard(lang)
        )
        return
    
    # Save phone
    db.update_user_phone(message.from_user.id, phone)
    
    # Ask for city with improved text
    await state.set_state(Registration.city)
    await message.answer(
        get_text(lang, "welcome_city_step"),
        parse_mode="HTML",
        reply_markup=city_keyboard(lang)
    )

@router.message(Registration.city)
@secure_user_input
async def process_city(message: types.Message, state: FSMContext, db: DatabaseProtocol):
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
        await message.answer(
            get_text(lang, "registration_complete"),
            parse_mode="HTML",
            reply_markup=main_menu_customer(lang)
        )
