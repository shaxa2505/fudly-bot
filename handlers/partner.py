"""Partner registration handlers."""
from __future__ import annotations

from typing import Any

from aiogram import F, Router, types
from aiogram.fsm.context import FSMContext

from database_protocol import DatabaseProtocol
from handlers.common_states.states import RegisterStore
from app.keyboards import (
    cancel_keyboard,
    category_keyboard,
    category_inline_keyboard,
    city_keyboard,
    city_inline_keyboard,
    language_keyboard,
    main_menu_customer,
    main_menu_seller,
)
from localization import get_categories, get_cities, get_text
from logging_config import logger


def get_appropriate_menu(user_id: int, lang: str) -> Any:
    """Get appropriate menu based on user view mode."""
    if user_view_mode and user_view_mode.get(user_id) == "seller":
        return main_menu_seller(lang)
    return main_menu_customer(lang)

# Module-level dependencies
db: DatabaseProtocol | None = None
bot: Any | None = None
user_view_mode: dict | None = None  # Tracks seller/customer view preference

router = Router()


def setup_dependencies(
    database: DatabaseProtocol, bot_instance: Any, view_mode_dict: dict
) -> None:
    """Setup module dependencies."""
    global db, bot, user_view_mode
    db = database
    bot = bot_instance
    user_view_mode = view_mode_dict


def has_approved_store(user_id: int) -> bool:
    """Check if user has an approved store."""
    if not db:
        return False
    stores = db.get_user_stores(user_id)
    for store in stores:
        # Store tuple: [0]id, ..., [8]status
        status = store[6] if len(store) > 6 else "pending"
        if status == "active":
            return True
    return False


def normalize_city(city_text: str) -> str:
    """Normalize city name to Russian for DB consistency."""
    city_map = {
        "Toshkent": "Ташкент",
        "Samarqand": "Самарканд",
        "Buxoro": "Бухара",
        "Andijon": "Андижан",
        "Namangan": "Наманган",
        "Farg'ona": "Фергана",
        "Qo'qon": "Коканд",
    }
    return city_map.get(city_text, city_text)


def normalize_category(cat_text: str) -> str:
    """Normalize category name to Russian for DB consistency."""
    cat_map = {
        "Restoran": "Ресторан",
        "Kafe": "Кафе",
        "Do'kon": "Магазин",
        "Supermarket": "Супермаркет",
        "Pishiriqxona": "Пекарня",
        "Boshqa": "Другое",
    }
    return cat_map.get(cat_text, cat_text)


@router.message(F.text.contains("Стать партнером") | F.text.contains("Hamkor bolish"))
async def become_partner(message: types.Message, state: FSMContext) -> None:
    """Start partner registration or switch to seller mode."""
    if not db:
        await message.answer("System error")
        return
    
    lang = db.get_user_language(message.from_user.id)
    user = db.get_user_model(message.from_user.id)
    
    # Check if user exists in DB
    if not user:
        await message.answer(
            get_text(lang, "choose_language"), reply_markup=language_keyboard()
        )
        return
    
    # If already a seller with approved store - switch to seller mode
    if user.role == "seller":
        if has_approved_store(message.from_user.id):
            # Remember seller view preference
            if user_view_mode is not None:
                user_view_mode[message.from_user.id] = "seller"
            await message.answer(
                get_text(lang, "switched_to_seller"),
                reply_markup=main_menu_seller(lang),
            )
            return
        else:
            # No approved store - show status
            stores = db.get_user_stores(message.from_user.id)
            if stores:
                # Has store(s) but not approved
                status = stores[0][6] if len(stores[0]) > 6 else "pending"
                if status == "pending":
                    await message.answer(
                        get_text(lang, "no_approved_stores"),
                        reply_markup=main_menu_customer(lang),
                    )
                elif status == "rejected":
                    # Can reapply
                    await message.answer(
                        get_text(lang, "store_rejected")
                        + "\n\nПодайте заявку заново:",
                        reply_markup=main_menu_customer(lang),
                    )
                    # Continue with new registration below
                else:
                    await message.answer(
                        get_text(lang, "no_approved_stores"),
                        reply_markup=main_menu_customer(lang),
                    )
                return
    
    # Not a seller or no store - start registration
    await message.answer(
        get_text(lang, "become_partner_text"),
        parse_mode="HTML",
        reply_markup=city_keyboard(lang),
    )
    await state.set_state(RegisterStore.city)


@router.message(RegisterStore.city)
async def register_store_city(message: types.Message, state: FSMContext) -> None:
    """City selected for store registration (text fallback for reply keyboard)."""
    if not db:
        await message.answer("System error")
        return
    
    # Check if we're actually in the city state
    current_state = await state.get_state()
    if current_state != RegisterStore.city:
        # Not in city selection state, ignore
        return
    
    lang = db.get_user_language(message.from_user.id)
    cities = get_cities(lang)
    city_text = message.text.replace("📍 ", "").strip()
    
    if city_text in cities:
        # CRITICAL: Normalize city to Russian for DB consistency
        normalized_city = normalize_city(city_text)
        await state.update_data(city=normalized_city)
        await message.answer(
            get_text(lang, "store_category"), reply_markup=category_keyboard(lang)
        )
        await state.set_state(RegisterStore.category)


@router.message(RegisterStore.category)
async def register_store_category(message: types.Message, state: FSMContext) -> None:
    """Category selected for store registration (text fallback for reply keyboard)."""
    if not db:
        await message.answer("System error")
        return
    
    # Check if we're actually in the category state
    current_state = await state.get_state()
    if current_state != RegisterStore.category:
        # Not in category selection state, ignore
        return
    
    lang = db.get_user_language(message.from_user.id)
    categories = get_categories(lang)
    cat_text = message.text.replace("🏷 ", "").replace("▫️ ", "").strip()
    
    if cat_text in categories:
        # CRITICAL: Normalize category to Russian for DB consistency
        normalized_category = normalize_category(cat_text)
        await state.update_data(category=normalized_category)
        await message.answer(
            get_text(lang, "store_name"), reply_markup=cancel_keyboard(lang)
        )
        await state.set_state(RegisterStore.name)


@router.message(RegisterStore.name)
async def register_store_name(message: types.Message, state: FSMContext) -> None:
    """Store name entered."""
    if not db:
        await message.answer("System error")
        return
    
    lang = db.get_user_language(message.from_user.id)
    await state.update_data(name=message.text)
    await message.answer(get_text(lang, "store_address"))
    await state.set_state(RegisterStore.address)


@router.message(RegisterStore.address)
async def register_store_address(message: types.Message, state: FSMContext) -> None:
    """Store address entered."""
    if not db:
        await message.answer("System error")
        return
    
    lang = db.get_user_language(message.from_user.id)
    logger.info(
        f"Handler register_store_address called, user {message.from_user.id}, address: {message.text}"
    )
    await state.update_data(address=message.text)
    description_text = get_text(lang, "store_description")
    logger.info(f"Sending description prompt: {description_text}")
    await message.answer(description_text, reply_markup=cancel_keyboard(lang))
    await state.set_state(RegisterStore.description)


@router.message(RegisterStore.description)
async def register_store_description(message: types.Message, state: FSMContext) -> None:
    """Store description entered - create store application."""
    if not db or not bot:
        await message.answer("System error")
        return
    
    lang = db.get_user_language(message.from_user.id)
    await state.update_data(description=message.text)
    data = await state.get_data()
    
    # Use phone from user profile
    user = db.get_user_model(message.from_user.id)
    owner_phone = user.phone if user else None
    
    # Create store application (status: pending)
    store_id = db.add_store(
        message.from_user.id,
        data["name"],
        data["city"],
        data["address"],
        data["description"],
        data["category"],
        owner_phone,
    )
    
    await state.clear()
    
    # Notify user about moderation
    await message.answer(
        get_text(
            lang,
            "store_pending",
            name=data["name"],
            city=data["city"],
            address=data["address"],
            category=data["category"],
            description=data["description"],
            phone=owner_phone or "—",
        ),
        parse_mode="HTML",
        reply_markup=main_menu_customer(lang),
    )
    
    # Notify ALL admins about new application
    admins = db.get_all_admins()
    for admin in admins:
        try:
            admin_text = (
                f"🔔 <b>Новая заявка на партнерство!</b>\n\n"
                f"От: {message.from_user.full_name} (@{message.from_user.username or 'нет'})\n"
                f"ID: <code>{message.from_user.id}</code>\n\n"
                f"🏪 Название: {data['name']}\n"
                f"📍 Город: {data['city']}\n"
                f"🏠 Адрес: {data['address']}\n"
                f"🏷 Категория: {data['category']}\n"
                f"📝 Описание: {data['description']}\n"
                f"📱 Телефон: {owner_phone or '—'}\n\n"
                f"Перейдите в админ панель для модерации."
            )
            await bot.send_message(admin[0], admin_text, parse_mode="HTML")
        except Exception:
            pass


@router.callback_query(F.data == "become_partner_cb")
async def become_partner_cb(callback: types.CallbackQuery, state: FSMContext) -> None:
    """Start partner registration from profile (inline)."""
    if not db or not bot:
        await callback.answer("System error")
        return
    
    lang = db.get_user_language(callback.from_user.id)
    user = db.get_user_model(callback.from_user.id)
    
    if not user:
        await callback.message.answer(
            get_text(lang, "choose_language"), reply_markup=language_keyboard()
        )
        await callback.answer()
        return
    
    # If already seller - check store status
    if user.role == "seller":
        stores = db.get_user_stores(callback.from_user.id)
        # Check for approved store (status == "active")
        approved_stores = [s for s in stores if s[6] == "active"]
        
        if approved_stores:
            # Has approved store - switch to seller mode
            if user_view_mode is not None:
                user_view_mode[callback.from_user.id] = "seller"
            try:
                await callback.message.edit_text(
                    get_text(lang, "switched_to_seller"),
                    reply_markup=get_appropriate_menu(callback.from_user.id, lang),
                )
            except Exception:
                await callback.message.answer(
                    get_text(lang, "switched_to_seller"),
                    reply_markup=get_appropriate_menu(callback.from_user.id, lang),
                )
            await callback.answer()
            return
        elif stores:
            # Has store but not approved
            pending_stores = [s for s in stores if s[6] == "pending"]
            if pending_stores:
                await callback.answer(
                    "⏳ Ваш магазин на модерации. Ожидайте одобрения администратором.",
                    show_alert=True,
                )
                return
            else:
                # Store rejected - can reapply
                db.update_user_role(callback.from_user.id, "customer")
        else:
            # No stores at all
            db.update_user_role(callback.from_user.id, "customer")
    
    # Start partner registration
    try:
        await callback.message.edit_text(
            get_text(lang, "become_partner_text"),
            parse_mode="HTML",
            reply_markup=city_inline_keyboard(lang),
        )
    except Exception:
        await callback.message.answer(
            get_text(lang, "become_partner_text"),
            parse_mode="HTML",
            reply_markup=city_keyboard(lang),
        )
    await state.set_state(RegisterStore.city)
    await callback.answer()


@router.callback_query(F.data.startswith("reg_city_"))
async def register_store_city_callback(callback: types.CallbackQuery, state: FSMContext) -> None:
    """City selected for store registration via inline button."""
    if not db:
        await callback.answer("System error", show_alert=True)
        return
    
    lang = db.get_user_language(callback.from_user.id)
    city_text = callback.data.replace("reg_city_", "")
    
    # Normalize city to Russian for DB consistency
    normalized_city = normalize_city(city_text)
    await state.update_data(city=normalized_city)
    
    try:
        await callback.message.edit_text(
            get_text(lang, "store_category"),
            reply_markup=category_inline_keyboard(lang)
        )
    except Exception:
        await callback.message.answer(
            get_text(lang, "store_category"),
            reply_markup=category_keyboard(lang)
        )
    
    await state.set_state(RegisterStore.category)
    await callback.answer()


@router.callback_query(F.data.startswith("reg_cat_"))
async def register_store_category_callback(callback: types.CallbackQuery, state: FSMContext) -> None:
    """Category selected for store registration via inline button."""
    if not db:
        await callback.answer("System error", show_alert=True)
        return
    
    lang = db.get_user_language(callback.from_user.id)
    category_id = callback.data.replace("reg_cat_", "")
    
    # Map category ID to display name
    category_map = {
        'supermarket': 'Супермаркет' if lang == 'ru' else 'Supermarket',
        'restaurant': 'Ресторан' if lang == 'ru' else 'Restaurant',
        'bakery': 'Пекарня' if lang == 'ru' else 'Nonvoyxona',
        'cafe': 'Кафе' if lang == 'ru' else 'Kafe',
        'confectionery': 'Кондитерская' if lang == 'ru' else 'Qandolatchilik',
        'fastfood': 'Фастфуд' if lang == 'ru' else 'Fastfud',
    }
    
    category = category_map.get(category_id, category_id)
    await state.update_data(category=category)
    
    name_prompt = get_text(lang, "store_name")
    try:
        await callback.message.edit_text(
            name_prompt,
            reply_markup=None
        )
    except Exception:
        await callback.message.answer(name_prompt)
    
    await state.set_state(RegisterStore.name)
    await callback.answer()


@router.callback_query(F.data == "reg_cancel")
async def register_cancel_callback(callback: types.CallbackQuery, state: FSMContext) -> None:
    """Cancel partner registration via inline button."""
    if not db:
        await callback.answer("System error", show_alert=True)
        return
    
    lang = db.get_user_language(callback.from_user.id)
    await state.clear()
    
    cancel_text = get_text(lang, "cancelled")
    try:
        await callback.message.edit_text(cancel_text)
    except Exception:
        await callback.message.answer(cancel_text)
    
    await callback.answer()


