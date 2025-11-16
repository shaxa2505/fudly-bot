"""
User command handlers (start, language selection, city selection, cancel actions)
"""
from typing import Optional, Any, Callable
from database_protocol import DatabaseProtocol
from aiogram import types, Router, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder

router = Router()


def setup(
    dp_or_router: Any,
    db: DatabaseProtocol,
    get_text: Callable[..., str],
    get_cities: Callable[[str], Any],
    city_keyboard: Callable[[str], Any],
    language_keyboard: Callable[[], Any],
    phone_request_keyboard: Callable[[str], Any],
    main_menu_seller: Callable[[str], Any],
    main_menu_customer: Callable[[str], Any]
) -> None:
    """Setup user command handlers with dependencies"""
    from handlers.common import Registration, user_view_mode, has_approved_store
    
    @dp_or_router.message(F.text == "Мой город")
    async def change_city(message: types.Message, state: Optional[FSMContext] = None):
        user_id = message.from_user.id  # type: ignore[union-attr]  # type: ignore[union-attr]
        lang = db.get_user_language(user_id)
        user = db.get_user_model(user_id)
        current_city = user.city if user else get_cities(lang)[0]
        if not current_city:
            current_city = get_cities(lang)[0]
        
        # Get city statistics
        stats_text = ""
        try:
            stores_count = len(db.get_stores_by_city(current_city))
            offers_count = len(db.get_active_offers(city=current_city))
            stats_text = f"\n\n📊 В вашем городе:\n🏪 Магазинов: {stores_count}\n🍽 Предложений: {offers_count}"
        except:
            pass
        
        # Create inline keyboard with buttons
        builder = InlineKeyboardBuilder()
        builder.button(
            text="✏️ Изменить город" if lang == 'ru' else "✏️ Shaharni o'zgartirish",
            callback_data="change_city"
        )
        builder.button(
            text="◀️ Назад" if lang == 'ru' else "◀️ Orqaga",
            callback_data="back_to_menu"
        )
        builder.adjust(1)
        
        await message.answer(
            f"{get_text(lang, 'your_city')}: {current_city}{stats_text}",
            reply_markup=builder.as_markup(),
            parse_mode="HTML"
        )

    @dp_or_router.callback_query(F.data == "change_city")
    async def show_city_selection(callback: types.CallbackQuery, state: FSMContext):
        """Show list of cities for selection"""
        lang = db.get_user_language(callback.from_user.id)
        await callback.message.edit_text(  # type: ignore[union-attr]
            get_text(lang, 'choose_city'),
            reply_markup=city_keyboard(lang)
        )
    @dp_or_router.callback_query(F.data == "back_to_menu")
    async def back_to_main_menu(callback: types.CallbackQuery):
        """Return to main menu"""
        lang = db.get_user_language(callback.from_user.id)
        user = db.get_user_model(callback.from_user.id)
        user_role = user.role if user else 'customer'
        
        # Initialize user_view_mode for sellers
        from handlers import common_user
        if common_user.user_view_mode is not None and user_role == 'seller':
            # If not set, default to seller mode for sellers
            if callback.from_user.id not in common_user.user_view_mode:
                common_user.user_view_mode[callback.from_user.id] = 'seller'
        
        menu = main_menu_seller(lang) if user_role == "seller" else main_menu_customer(lang)
        
        await callback.message.delete()  # type: ignore[union-attr]
        await callback.message.answer(  # type: ignore[union-attr]
            get_text(lang, 'main_menu') if 'main_menu' in dir() else "Главное меню",
            reply_markup=menu
        )
        await callback.answer()

    @dp_or_router.message(F.text.in_(get_cities('ru') + get_cities('uz')))
    async def change_city(message: types.Message, state: Optional[FSMContext] = None):
        """Quick city change handler (without FSM state)"""
        user_id = message.from_user.id
        lang = db.get_user_language(user_id)
        user = db.get_user_model(user_id)
        
        # IMPORTANT: Check current FSM state
        # If user is in registration process (store or self), skip
        if state:
            current_state = await state.get_state()
            if current_state and (current_state.startswith('RegisterStore:') or current_state.startswith('Registration:')):
                # User is in registration process — don't touch, let corresponding handler process
                return
        
        new_city = message.text
        
        # Save new city
        db.update_user_city(user_id, new_city)
        
        # Get updated main menu
        user_role = user.role or 'customer' if user else 'customer'
        menu = main_menu_seller(lang) if user_role == "seller" else main_menu_customer(lang)
        
        await message.answer(
            f"✅ {get_text(lang, 'city_changed', city=new_city)}\n\n"
            f"Теперь вы будете видеть предложения из города {new_city}",
            reply_markup=menu,
            parse_mode="HTML"
        )

    @dp_or_router.message(Command("start"))
    async def cmd_start(message: types.Message, state: FSMContext):
        user = db.get_user_model(message.from_user.id)  # type: ignore[union-attr]
        
        if not user:
            # New user - show welcome message + language selection
            await message.answer(
                get_text('ru', 'welcome'),
                parse_mode="HTML"
            )
            await message.answer(
                get_text('ru', 'choose_language'),
                reply_markup=language_keyboard()
            )
            return
        
        lang = db.get_user_language(message.from_user.id)
        
        # Both backends now return dict
        # Extract user data to check if already registered
        user_phone = user.phone
        user_city = user.city
        user_role = user.role or 'customer'
        
        # Check phone (city will be set automatically with phone)
        if not user_phone:
            await message.answer(
                get_text(lang, 'welcome_phone_step'),
                parse_mode="HTML",
                reply_markup=phone_request_keyboard(lang)
            )
            await state.set_state(Registration.phone)
            return
        
        # Initialize user_view_mode based on user role
        # This is handled in bot.py - user_view_mode dict is shared
        # Set default mode based on role
        from handlers import common_user
        if common_user.user_view_mode is not None and user_role == 'seller':
            # If user is seller, default to seller mode
            common_user.user_view_mode[message.from_user.id] = 'seller'
        
        # Welcome message
        menu = main_menu_seller(lang) if user_role == "seller" else main_menu_customer(lang)
        await message.answer(
            get_text(lang, 'welcome_back', name=message.from_user.first_name, city=user_city or 'Ташкент'),  # type: ignore[union-attr]
            parse_mode="HTML",
            reply_markup=menu
        )

    @dp_or_router.callback_query(F.data.startswith("lang_"))
    async def choose_language(callback: types.CallbackQuery, state: FSMContext):
        lang = callback.data.split("_")[1]  # type: ignore[union-attr]
        
        # Show menu after language selection
        user = db.get_user_model(callback.from_user.id)
        
        # CHECK: if user is not in DB (new user)
        if not user:
            # Create new user WITH selected language
            db.add_user(callback.from_user.id, callback.from_user.username, callback.from_user.first_name)
            db.update_user_language(callback.from_user.id, lang)
            await callback.message.edit_text(get_text(lang, 'language_changed'))  # type: ignore[union-attr]
            await callback.message.answer(  # type: ignore[union-attr]
                get_text(lang, 'welcome_phone_step'),
                parse_mode="HTML",
                reply_markup=phone_request_keyboard(lang)
            )
            await state.set_state(Registration.phone)
            return
        
        # If user already exists — just update language
        db.update_user_language(callback.from_user.id, lang)
        await callback.message.edit_text(get_text(lang, 'language_changed'))
        
        # Extract user data
        user_phone = user.phone
        user_city = user.city
        
        # If no phone - request it (city will be set automatically)
        if not user_phone:
            await callback.message.answer(
                get_text(lang, 'welcome_phone_step'),
                parse_mode="HTML",
                reply_markup=phone_request_keyboard(lang)
            )
            await state.set_state(Registration.phone)
            return
        
        # Show main menu
        user_role = user.role or 'customer' if user else 'customer'
        menu = main_menu_seller(lang) if user_role == "seller" else main_menu_customer(lang)
        await callback.message.answer(
            get_text(lang, 'welcome_back', name=callback.from_user.first_name, city=user_city or 'Ташкент'),
            parse_mode="HTML",
            reply_markup=menu
        )

    @dp_or_router.message(F.text.contains("Отмена") | F.text.contains("Bekor qilish"))
    async def cancel_action(message: types.Message, state: FSMContext):
        lang = db.get_user_language(message.from_user.id)
        current_state = await state.get_state()
        
        # BLOCK cancellation of mandatory registration
        if current_state in ['Registration:phone', 'Registration:city']:
            user = db.get_user_model(message.from_user.id)  # type: ignore[union-attr]
            # If no phone number — registration is mandatory, cancellation prohibited
            user_phone = user.phone if user else None
            if not user or not user_phone:
                await message.answer(
                    "❌ Регистрация обязательна для использования бота.\n\n"
                    "📱 Пожалуйста, поделитесь номером телефона.",
                    reply_markup=phone_request_keyboard(lang)
                )
                return
        
        # For all other states — allow cancellation
        await state.clear()

        # Map state group to preferred menu context
        seller_groups = {"RegisterStore", "CreateOffer", "BulkCreate", "ConfirmOrder"}
        customer_groups = {"Registration", "BookOffer", "ChangeCity"}

        preferred_menu = None
        if current_state:
            try:
                state_group = str(current_state).split(":", 1)[0]
                if state_group in seller_groups:
                    preferred_menu = "seller"
                elif state_group in customer_groups:
                    preferred_menu = "customer"
            except Exception:
                preferred_menu = None

        user = db.get_user_model(message.from_user.id)
        role = user.role if user else 'customer'
        
        # CRITICAL: When cancelling RegisterStore ALWAYS return to customer menu
        # because user does NOT YET have an approved store
        if current_state and str(current_state).startswith("RegisterStore"):
            # Cancel store registration - return to customer menu
            await message.answer(
                get_text(lang, 'operation_cancelled'),
                reply_markup=main_menu_customer(lang)
            )
            return
        
        # IMPORTANT: Check for approved store for partners
        if role == "seller":
            # Use ready function has_approved_store for checking
            if not has_approved_store(message.from_user.id, db):
                # No approved store — show customer menu
                role = "customer"
                preferred_menu = "customer"
        
        # View mode override has priority if set
        view_override = user_view_mode.get(message.from_user.id)
        target = preferred_menu or view_override or ("seller" if role == "seller" else "customer")
        menu = main_menu_seller(lang) if target == "seller" else main_menu_customer(lang)

        await message.answer(
            get_text(lang, 'operation_cancelled'),
            reply_markup=menu
        )

    @dp_or_router.callback_query(F.data == "cancel_offer")
    async def cancel_offer_callback(callback: types.CallbackQuery, state: FSMContext):
        """Handler for offer creation cancel button"""
        lang = db.get_user_language(callback.from_user.id)
        await state.clear()
        
        await callback.message.edit_text(
            f"❌ {'Создание товара отменено' if lang == 'ru' else 'Mahsulot yaratish bekor qilindi'}",
            parse_mode="HTML"
        )
        
        await callback.message.answer(
            get_text(lang, 'operation_cancelled'),
            reply_markup=main_menu_seller(lang)
        )
        
        await callback.answer()
