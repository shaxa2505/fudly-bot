"""Partner registration handlers."""
from __future__ import annotations

import re
from typing import Any

from aiogram import F, Router, types
from aiogram import types as _ai_types
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext

from app.keyboards import (
    cancel_keyboard,
    category_inline_keyboard,
    category_keyboard,
    city_inline_keyboard,
    city_keyboard,
    language_keyboard,
    main_menu_customer,
    main_menu_seller,
)
from app.core.geocoding import geocode_store_address, reverse_geocode_store
from database_protocol import DatabaseProtocol
from handlers.common.states import RegisterStore
from handlers.common.utils import (
    get_appropriate_menu as _get_appropriate_menu,
)
from handlers.common.utils import (
    get_user_view_mode,
    has_approved_store,
    is_partner_button,
    normalize_city,
    set_user_view_mode,
)
from localization import get_categories, get_cities, get_text
from logging_config import logger


async def _safe_answer_or_send(msg_like, user_id: int, text: str, **kwargs) -> None:
    """Try to answer via message.answer, fallback to bot.send_message."""
    if isinstance(msg_like, _ai_types.Message):
        try:
            await msg_like.answer(text, **kwargs)
            return
        except Exception:
            pass
    # Fallback to bot-level send
    if bot:
        try:
            await bot.send_message(user_id, text, **kwargs)
        except Exception:
            pass


def get_appropriate_menu(user_id: int, lang: str) -> Any:
    """Get appropriate menu based on user view mode."""
    if not db:
        return main_menu_customer(lang)
    return _get_appropriate_menu(user_id, lang, db)


# Module-level dependencies
db: DatabaseProtocol | None = None
bot: Any | None = None

router = Router()


def setup_dependencies(
    database: DatabaseProtocol, bot_instance: Any, view_mode_dict: dict | None = None
) -> None:
    """Setup module dependencies. view_mode_dict is deprecated and ignored."""
    global db, bot
    db = database
    bot = bot_instance


def normalize_business_type(cat_text: str) -> str:
    """Normalize business type name to Russian for DB consistency."""
    cat_map = {
        "Restoran": "Ресторан",
        "Kafe": "Кафе",
        "Do'kon": "Магазин",
        "Supermarket": "Супермаркет",
        "Pishiriqxona": "Пекарня",
        "Boshqa": "Другое",
    }
    return cat_map.get(cat_text, cat_text)


def _strip_leading_marker(text: str) -> str:
    return re.sub(r"^[^\\w]+\\s*", "", (text or "")).strip()


def location_request_keyboard(lang: str) -> types.ReplyKeyboardMarkup:
    """Keyboard for requesting store geolocation."""
    location_text = (
        "Отправить геолокацию" if lang == "ru" else "Joylashuvni yuborish"
    )
    cancel_text = get_text(lang, "cancel")
    return types.ReplyKeyboardMarkup(
        keyboard=[
            [types.KeyboardButton(text=location_text, request_location=True)],
            [types.KeyboardButton(text=cancel_text)],
        ],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


@router.message(F.text.func(is_partner_button))
async def become_partner(message: types.Message, state: FSMContext) -> None:
    """Start partner registration or switch to seller mode."""
    if not db:
        await message.answer("System error")
        return
    assert message.from_user is not None

    assert message.from_user is not None
    lang = db.get_user_language(message.from_user.id)
    user = db.get_user_model(message.from_user.id)

    # Check if user exists in DB
    if not user:
        await message.answer(get_text(lang, "choose_language"), reply_markup=language_keyboard())
        return

    # If already a seller with approved store - switch to seller mode
    if user.role == "seller":
        if has_approved_store(message.from_user.id, db):
            # Remember seller view preference
            set_user_view_mode(message.from_user.id, "seller", db)

            # Get partner panel URL
            from handlers.common.webapp import get_partner_panel_url

            webapp_url = get_partner_panel_url()

            await message.answer(
                get_text(lang, "switched_to_seller"),
                reply_markup=main_menu_seller(lang, webapp_url=webapp_url, user_id=message.from_user.id),
            )
            return
        else:
            # No approved store - show status
            stores = db.get_user_accessible_stores(message.from_user.id)
            if stores:
                # Has store(s) but not approved
                status = stores[0].get("status", "pending")
                if status == "pending":
                    await message.answer(
                        get_text(lang, "no_approved_stores"),
                        reply_markup=main_menu_customer(lang),
                    )
                elif status == "rejected":
                    # Can reapply
                    await message.answer(
                        get_text(lang, "store_rejected") + "\n\nПодайте заявку заново:",
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
    # Prefer inline city selection to avoid free-text ambiguity; keep text fallback
    try:
        await message.answer(
            get_text(lang, "become_partner_text"),
            parse_mode="HTML",
            reply_markup=city_inline_keyboard(lang),
        )
    except Exception:
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

    assert message.from_user is not None
    lang = db.get_user_language(message.from_user.id)
    cities = get_cities(lang)
    raw_text = message.text or ""
    city_text = _strip_leading_marker(raw_text)

    if city_text in cities:
        # CRITICAL: Normalize city to Russian for DB consistency
        normalized_city = normalize_city(city_text)
        await state.update_data(city=normalized_city)
        # Move to category selection: prefer inline keyboard
        try:
            await message.answer(
                get_text(lang, "store_category"), reply_markup=category_inline_keyboard(lang)
            )
        except Exception:
            await message.answer(
                get_text(lang, "store_category"), reply_markup=category_keyboard(lang)
            )
        await state.set_state(RegisterStore.category)


@router.callback_query(F.data.startswith("reg_city_"), StateFilter(RegisterStore.city))
async def register_store_city_cb(callback: types.CallbackQuery, state: FSMContext) -> None:
    """Handle inline city selection for partner registration."""
    if not callback.message:
        await callback.answer("System error", show_alert=True)
        return

    assert callback.from_user is not None
    lang = db.get_user_language(callback.from_user.id) if db else "ru"
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
    await state.update_data(city=normalized_city)
    # Send category selection inline (use safe helper)
    text = get_text(lang, "store_category")
    try:
        await _safe_answer_or_send(
            callback.message,
            callback.from_user.id,
            text,
            reply_markup=category_inline_keyboard(lang),
        )
    except Exception:
        try:
            await _safe_answer_or_send(
                callback.message, callback.from_user.id, text, reply_markup=category_keyboard(lang)
            )
        except Exception:
            pass
    await state.set_state(RegisterStore.category)
    await callback.answer()


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

    assert message.from_user is not None
    lang = db.get_user_language(message.from_user.id)
    categories = get_categories(lang)
    raw_text = message.text or ""
    cat_text = _strip_leading_marker(raw_text)

    if cat_text in categories:
        # CRITICAL: Normalize business type to Russian for DB consistency
        normalized_category = normalize_business_type(cat_text)
        await state.update_data(category=normalized_category)
        await message.answer(get_text(lang, "store_name"), reply_markup=cancel_keyboard(lang))
        await state.set_state(RegisterStore.name)


@router.callback_query(F.data.startswith("reg_cat_"))
async def register_store_category_cb(callback: types.CallbackQuery, state: FSMContext) -> None:
    """Handle inline category selection for partner registration."""
    if not callback.message:
        await callback.answer("System error", show_alert=True)
        return

    # Only proceed if user is in the RegisterStore.category state
    current_state = await state.get_state()
    if current_state != RegisterStore.category:
        await callback.answer()
        return

    assert callback.from_user is not None
    lang = db.get_user_language(callback.from_user.id) if db else "ru"
    try:
        raw = callback.data or ""
        parts = raw.split("_", 2)
        cat_id = parts[2] if len(parts) > 2 else ""
        if not cat_id:
            raise ValueError("empty cat_id")
    except Exception:
        await callback.answer(get_text(lang, "error"), show_alert=True)
        return

    # Map common category ids to Russian display names
    cat_name_map = {
        "supermarket": "Супермаркет",
        "restaurant": "Ресторан",
        "bakery": "Пекарня",
        "cafe": "Кафе",
        "confectionery": "Кондитерская",
        "fastfood": "Фастфуд",
    }
    normalized_category = cat_name_map.get(cat_id, cat_id)
    await state.update_data(category=normalized_category)
    name_prompt = get_text(lang, "store_name")
    try:
        await _safe_answer_or_send(
            callback.message, callback.from_user.id, name_prompt, reply_markup=cancel_keyboard(lang)
        )
    except Exception:
        try:
            await _safe_answer_or_send(callback.message, callback.from_user.id, name_prompt)
        except Exception:
            pass
    await state.set_state(RegisterStore.name)
    await callback.answer()


@router.message(RegisterStore.name)
async def register_store_name(message: types.Message, state: FSMContext) -> None:
    """Store name entered."""
    if not db:
        await message.answer("System error")
        return

    assert message.from_user is not None
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

    assert message.from_user is not None
    lang = db.get_user_language(message.from_user.id)
    logger.info(
        f"Handler register_store_address called, user {message.from_user.id}, address: {message.text}"
    )
    await state.update_data(address=message.text)
    location_text = (
        "<b>Шаг 5/7: геолокация</b>\n"
        "Отправьте геолокацию магазина кнопкой ниже. Это обязательно."
        if lang == "ru"
        else "<b>5/7-qadam: joylashuv</b>\n"
        "Do'kon geolokatsiyasini pastdagi tugma orqali yuboring. Bu majburiy."
    )
    await message.answer(location_text, reply_markup=location_request_keyboard(lang))
    await state.set_state(RegisterStore.location)


@router.message(RegisterStore.location, F.location)
async def register_store_location(message: types.Message, state: FSMContext) -> None:
    """Store location shared - proceed to description."""
    if not db:
        await message.answer("System error")
        return

    assert message.from_user is not None
    assert message.location is not None
    lang = db.get_user_language(message.from_user.id)

    latitude = message.location.latitude
    longitude = message.location.longitude

    region = None
    district = None
    try:
        geo = await reverse_geocode_store(latitude, longitude)
        if geo:
            region = geo.get("region")
            district = geo.get("district")
    except Exception as e:
        logger.warning(f"Reverse geocode failed during registration: {e}")

    await state.update_data(
        latitude=latitude,
        longitude=longitude,
        region=region,
        district=district,
    )

    description_text = get_text(lang, "store_description")
    await message.answer(description_text, reply_markup=cancel_keyboard(lang))
    await state.set_state(RegisterStore.description)


@router.message(RegisterStore.location)
async def register_store_location_invalid(message: types.Message, state: FSMContext) -> None:
    """Require location message during registration."""
    if not db:
        await message.answer("System error")
        return

    assert message.from_user is not None
    lang = db.get_user_language(message.from_user.id)
    text = (
        "Отправьте геолокацию магазина кнопкой ниже."
        if lang == "ru"
        else "Do'kon geolokatsiyasini pastdagi tugma orqali yuboring."
    )
    await message.answer(text, reply_markup=location_request_keyboard(lang))


@router.message(RegisterStore.description)
async def register_store_description(message: types.Message, state: FSMContext) -> None:
    """Store description entered - ask for photo."""
    if not db or not bot:
        await message.answer("System error")
        return

    assert message.from_user is not None
    lang = db.get_user_language(message.from_user.id)
    await state.update_data(description=message.text)

    # Ask for store photo (required)
    photo_prompt = (
        "<b>Шаг 7/7: фото</b>\n"
        "Отправьте фото магазина или витрины.\n"
        "Фото обязательно."
        if lang == "ru"
        else "<b>7/7-qadam: foto</b>\n"
        "Do'kon yoki vitrina fotosuratini yuboring.\n"
        "Foto majburiy."
    )

    await message.answer(photo_prompt, parse_mode="HTML", reply_markup=cancel_keyboard(lang))
    await state.set_state(RegisterStore.photo)


@router.message(RegisterStore.photo, F.photo)
async def register_store_photo(message: types.Message, state: FSMContext) -> None:
    """Store photo uploaded - create store application."""
    if not db or not bot:
        await message.answer("System error")
        return
    assert message.from_user is not None
    lang = db.get_user_language(message.from_user.id)

    # Get the largest photo if present (defensive)
    photo_id = None
    if getattr(message, "photo", None):
        try:
            photo_id = message.photo[-1].file_id
        except Exception:
            photo_id = None
    elif (
        getattr(message, "document", None)
        and getattr(message.document, "mime_type", None)
        and message.document.mime_type.startswith("image/")
    ):
        try:
            photo_id = message.document.file_id
        except Exception:
            photo_id = None

    if not photo_id:
        await message.answer(
            get_text(lang, "please_send_photo") if lang == "ru" else "Iltimos, fotosurat yuboring"
        )
        return

    await state.update_data(photo=photo_id)
    await create_store_from_data(message, state)


@router.message(RegisterStore.photo, F.text)
async def register_store_photo_text(message: types.Message, state: FSMContext) -> None:
    """Handle text input during photo upload - photo is required."""
    if not db or not bot:
        await message.answer("System error")
        return
    assert message.from_user is not None
    lang = db.get_user_language(message.from_user.id)
    text = (message.text or "").lower().strip()

    # Check for cancel command
    if "отмена" in text or "bekor" in text or text == "/cancel":
        await state.clear()
        from app.keyboards.user import main_menu_customer

        await message.answer(
            get_text(lang, "action_cancelled"), reply_markup=main_menu_customer(lang)
        )
        return

    # Any other text - require photo
    await message.answer(
        "Пожалуйста, отправьте фото магазина. Это обязательный шаг."
        if lang == "ru"
        else "Iltimos, do'kon fotosuratini yuboring. Bu majburiy qadam."
    )


@router.message(RegisterStore.photo)
async def register_store_photo_invalid(message: types.Message, state: FSMContext) -> None:
    """Handle any other input - require photo."""
    if not db:
        await message.answer("System error")
        return
    assert message.from_user is not None
    lang = db.get_user_language(message.from_user.id)

    # Show error - photo is required
    await message.answer(
        "Отправьте фото магазина (изображение). Это обязательный шаг."
        if lang == "ru"
        else "Do'kon fotosuratini yuboring (rasm). Bu majburiy qadam."
    )


async def create_store_from_data(message: types.Message, state: FSMContext) -> None:
    """Helper function to create store from state data."""
    if not db or not bot:
        await message.answer("System error")
        return
    assert message.from_user is not None
    lang = db.get_user_language(message.from_user.id)
    data = await state.get_data()

    # Use phone from user profile
    user = db.get_user_model(message.from_user.id)
    owner_phone = user.phone if user else None

    manual_lat = data.get("latitude")
    manual_lon = data.get("longitude")
    has_manual_coords = manual_lat is not None and manual_lon is not None

    geo = None
    if not has_manual_coords or not data.get("region") or not data.get("district"):
        try:
            geo = await geocode_store_address(data.get("address"), data.get("city"))
        except Exception as e:
            logger.warning(f"Geocode failed for store owner {message.from_user.id}: {e}")

    region = data.get("region") or (geo.get("region") if geo else None)
    district = data.get("district") or (geo.get("district") if geo else None)
    latitude = manual_lat if has_manual_coords else (geo.get("latitude") if geo else None)
    longitude = manual_lon if has_manual_coords else (geo.get("longitude") if geo else None)

    # Create store application (status: pending)
    store_id = db.add_store(
        owner_id=message.from_user.id,
        name=data["name"],
        city=data["city"],
        region=region,
        district=district,
        address=data["address"],
        description=data["description"],
        category=data["category"],
        phone=owner_phone,
        business_type=data.get("business_type", "supermarket"),
        photo=data.get("photo"),  # Add photo parameter
    )

    if latitude is not None and longitude is not None:
        try:
            db.update_store_location(
                store_id,
                float(latitude),
                float(longitude),
                region=region,
                district=district,
            )
        except Exception as e:
            logger.warning(f"Failed to save store coordinates for {store_id}: {e}")

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

    if latitude is None or longitude is None:
        if lang == "ru":
            await message.answer(
                "Не удалось определить координаты магазина автоматически. "
                "Установите геолокацию в настройках магазина."
            )
        else:
            await message.answer(
                "Do'kon koordinatalarini avtomatik aniqlab bo'lmadi. "
                "Do'kon sozlamalarida geolokatsiyani o'rnating."
            )

    # Notify ALL admins about new application
    admins = db.get_all_admins()
    for admin in admins:
        try:
            admin_text = (
                f"<b>Новая заявка на партнёрство</b>\n\n"
                f"От: {message.from_user.full_name} (@{message.from_user.username or 'нет'})\n"
                f"ID: <code>{message.from_user.id}</code>\n\n"
                f"Название: {data['name']}\n"
                f"Город: {data['city']}\n"
                f"Адрес: {data['address']}\n"
                f"Категория: {data['category']}\n"
                f"Описание: {data['description']}\n"
                f"Телефон: {owner_phone or '—'}\n\n"
                f"Откройте админ-панель для модерации."
            )

            # Send with photo if available
            if data.get("photo"):
                try:
                    await bot.send_photo(
                        admin[0], photo=data["photo"], caption=admin_text, parse_mode="HTML"
                    )
                except Exception:
                    # Fallback to text if photo fails
                    try:
                        await _safe_answer_or_send(None, admin[0], admin_text, parse_mode="HTML")
                    except Exception:
                        pass
            else:
                try:
                    await _safe_answer_or_send(None, admin[0], admin_text, parse_mode="HTML")
                except Exception:
                    pass
        except Exception:
            pass


@router.callback_query(F.data == "become_partner_cb")
async def become_partner_cb(callback: types.CallbackQuery, state: FSMContext) -> None:
    """Start partner registration from profile (inline)."""
    if not db:
        await callback.answer("System error")
        return

    assert callback.from_user is not None
    lang = db.get_user_language(callback.from_user.id)
    user = db.get_user_model(callback.from_user.id)

    if not user:
        try:
            await _safe_answer_or_send(
                callback.message,
                callback.from_user.id,
                get_text(lang, "choose_language"),
                reply_markup=language_keyboard(),
            )
        except Exception:
            pass
        await callback.answer()
        return

    # If already seller - check store status
    if user.role == "seller":
        stores = db.get_user_stores(callback.from_user.id)
        # Check for approved store (status == "active")
        approved_stores = [s for s in stores if s[6] == "active"]

        if approved_stores:
            # Has approved store - switch to seller mode
            set_user_view_mode(callback.from_user.id, "seller", db)
            try:
                await _safe_answer_or_send(
                    callback.message,
                    callback.from_user.id,
                    get_text(lang, "switched_to_seller"),
                    reply_markup=get_appropriate_menu(callback.from_user.id, lang),
                )
            except Exception:
                pass
            await callback.answer()
            return
        elif stores:
            # Has store but not approved
            pending_stores = [s for s in stores if s[6] == "pending"]
            if pending_stores:
                await callback.answer(
                    "Ваш магазин на модерации. Ожидайте одобрения администратора.",
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
        await _safe_answer_or_send(
            callback.message,
            callback.from_user.id,
            get_text(lang, "become_partner_text"),
            parse_mode="HTML",
            reply_markup=city_inline_keyboard(lang),
        )
    except Exception:
        try:
            await _safe_answer_or_send(
                callback.message,
                callback.from_user.id,
                get_text(lang, "become_partner_text"),
                parse_mode="HTML",
                reply_markup=city_keyboard(lang),
            )
        except Exception:
            pass
    await state.set_state(RegisterStore.city)
    await callback.answer()


@router.callback_query(F.data.startswith("reg_cat_"))
async def register_store_category_callback(
    callback: types.CallbackQuery, state: FSMContext
) -> None:
    """Category selected for store registration via inline button."""
    if not db:
        await callback.answer("System error", show_alert=True)
        return

    assert callback.from_user is not None
    lang = db.get_user_language(callback.from_user.id)
    category_id = (callback.data or "").replace("reg_cat_", "")

    # Map category ID to display name
    category_map = {
        "supermarket": "Супермаркет" if lang == "ru" else "Supermarket",
        "restaurant": "Ресторан" if lang == "ru" else "Restaurant",
        "bakery": "Пекарня" if lang == "ru" else "Nonvoyxona",
        "cafe": "Кафе" if lang == "ru" else "Kafe",
        "confectionery": "Кондитерская" if lang == "ru" else "Qandolatchilik",
        "fastfood": "Фастфуд" if lang == "ru" else "Fastfud",
    }

    category = category_map.get(category_id, category_id)
    await state.update_data(category=category, business_type=category_id)

    name_prompt = get_text(lang, "store_name")
    try:
        try:
            await _safe_answer_or_send(
                callback.message, callback.from_user.id, name_prompt, reply_markup=None
            )
        except Exception:
            try:
                await _safe_answer_or_send(callback.message, callback.from_user.id, name_prompt)
            except Exception:
                pass
    except Exception:
        pass

    await state.set_state(RegisterStore.name)
    await callback.answer()


@router.callback_query(F.data == "reg_cancel")
async def register_cancel_callback(callback: types.CallbackQuery, state: FSMContext) -> None:
    """Cancel partner registration via inline button."""
    if not db:
        await callback.answer("System error", show_alert=True)
        return

    assert callback.from_user is not None
    lang = db.get_user_language(callback.from_user.id)
    await state.clear()

    cancel_text = get_text(lang, "operation_cancelled")

    # Delete the inline keyboard message
    try:
        await callback.message.delete()
    except Exception:
        pass

    # Send cancel confirmation with customer menu
    try:
        await callback.message.answer(
            cancel_text,
            reply_markup=main_menu_customer(lang),
        )
    except Exception:
        pass

    await callback.answer()
