"""User favorites and city management handlers."""
from __future__ import annotations

from typing import Any

from aiogram import F, Router, types
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.keyboards import city_keyboard
from database_protocol import DatabaseProtocol
from handlers.common.states import ChangeCity
from handlers.common.utils import get_appropriate_menu as _get_appropriate_menu, is_main_menu_button
from localization import get_cities, get_text
from logging_config import logger
from security import secure_user_input, validator

# Module-level dependencies
db: DatabaseProtocol | None = None
bot: Any | None = None

router = Router()


def _t(lang: str, ru: str, uz: str) -> str:
    return ru if lang == "ru" else uz


def _lang_code(user: types.User | None) -> str:
    code = (user.language_code or "ru") if user else "ru"
    return "uz" if code.startswith("uz") else "ru"


def _service_unavailable(lang: str) -> str:
    return _t(
        lang,
        "Сервис временно недоступен. Попробуйте позже.",
        "Xizmat vaqtincha mavjud emas. Keyinroq urinib ko'ring.",
    )


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
        return main_menu_customer(lang, user_id=user_id)
    return _get_appropriate_menu(user_id, lang, db)


@router.message(F.text.contains("Мой город") | F.text.contains("Mening shahrim"))
async def show_my_city(message: types.Message, state: FSMContext) -> None:
    """Show current city and offer change."""
    if not db:
        await message.answer(_service_unavailable(_lang_code(message.from_user)))
        return

    user_id = message.from_user.id
    lang = db.get_user_language(user_id)
    user = db.get_user_model(user_id)
    current_city = user.city if user else _t(lang, "Не выбран", "Tanlanmagan")

    text = (
        f"{get_text(lang, 'your_city')}: {current_city}\n\n"
        f"{get_text(lang, 'change_city_prompt')}"
    )

    await message.answer(text, reply_markup=city_keyboard(lang))
    await state.set_state(ChangeCity.city)


@router.message(ChangeCity.city)
@secure_user_input
async def change_city_process(message: types.Message, state: FSMContext) -> None:
    """Process city change."""
    if not db:
        await message.answer(_service_unavailable(_lang_code(message.from_user)))
        return

    # Check if user pressed main menu button - clear state and let other handlers process
    if is_main_menu_button(message.text):
        await state.clear()
        return

    lang = db.get_user_language(message.from_user.id)
    cities = get_cities(lang)
    city_text = message.text.replace("📍 ", "").strip()

    if not validator.validate_city(city_text):
        await message.answer(get_text(lang, "invalid_city"))
        return

    if city_text in cities:
        db.update_user_city(message.from_user.id, city_text)
        await state.clear()
        menu = get_appropriate_menu(message.from_user.id, lang)
        await message.answer(
            get_text(lang, "registration_complete"), parse_mode="HTML", reply_markup=menu
        )


@router.message(F.text.contains("Избранное") | F.text.contains("Sevimlilar"))
async def show_favorites(message: types.Message) -> None:
    """Show favorite stores."""
    if not db:
        await message.answer(_service_unavailable(_lang_code(message.from_user)))
        return

    lang = db.get_user_language(message.from_user.id)
    user_id = message.from_user.id

    favorites = db.get_favorites(user_id)

    if not favorites:
        await message.answer(get_text(lang, "no_favorites"))
        return

    heading = _t(lang, "Ваши избранные магазины", "Sevimli do'konlar")
    await message.answer(f"<b>{heading}</b> ({len(favorites)})", parse_mode="HTML")

    for store in favorites:
        # Support both dict (PostgreSQL) and tuple (SQLite) formats
        if isinstance(store, dict):
            store_id = store["store_id"]
            store_name = store["name"]
            category = store.get("category", "Магазин")
            address = store.get("address", "")
            description = store.get("description", "")
        else:
            # PostgreSQL now returns dict, but keep as fallback
            store_id = store[0] if len(store) > 0 else 0
            store_name = store[2] if len(store) > 2 else "Без названия"
            category = store[6] if len(store) > 6 else "Магазин"
            address = store[4] if len(store) > 4 else ""
            description = store[5] if len(store) > 5 else ""

        avg_rating = db.get_store_average_rating(store_id)
        ratings = db.get_store_ratings(store_id)

        reviews_label = _t(lang, "отзывов", "ta sharh")
        text_lines = [f"<b>{store_name}</b>"]
        if category:
            text_lines.append(f"{_t(lang, 'Категория', 'Kategoriya')}: {category}")
        if address:
            text_lines.append(f"{_t(lang, 'Адрес', 'Manzil')}: {address}")
        if description:
            text_lines.append(f"{_t(lang, 'Описание', 'Taʼrif')}: {description}")
        text_lines.append(
            f"{_t(lang, 'Рейтинг', 'Reyting')}: {avg_rating:.1f}/5 ({len(ratings)} {reviews_label})"
        )
        text = "\n".join(text_lines)

        keyboard = InlineKeyboardBuilder()
        keyboard.button(
            text=_t(lang, "Товары магазина", "Do'kon mahsulotlari"),
            callback_data=f"store_offers_{store_id}",
        )
        keyboard.button(
            text=_t(lang, "Удалить из избранного", "Sevimlilardan o'chirish"),
            callback_data=f"unfavorite_{store_id}",
        )
        keyboard.adjust(1)

        await message.answer(text, parse_mode="HTML", reply_markup=keyboard.as_markup())


@router.callback_query(F.data.startswith("favorite_"))
async def toggle_favorite(callback: types.CallbackQuery) -> None:
    """Add store to favorites."""
    if not db:
        await callback.answer(_service_unavailable(_lang_code(callback.from_user)))
        return

    user_id = callback.from_user.id
    lang = db.get_user_language(user_id)

    try:
        store_id = int(callback.data.split("_")[1])
    except (ValueError, IndexError) as e:
        logger.error(f"Invalid store_id in callback data: {callback.data}, error: {e}")
        await callback.answer(get_text(lang, "error"), show_alert=True)
        return

    if db.is_favorite(user_id, store_id):
        await callback.answer(get_text(lang, "already_in_favorites"), show_alert=True)
    else:
        db.add_favorite(user_id, store_id)
        await callback.answer(get_text(lang, "added_to_favorites"), show_alert=True)


@router.callback_query(F.data.startswith("unfavorite_"))
async def remove_favorite(callback: types.CallbackQuery) -> None:
    """Remove store from favorites."""
    if not db:
        await callback.answer(_service_unavailable(_lang_code(callback.from_user)))
        return

    user_id = callback.from_user.id
    lang = db.get_user_language(user_id)

    try:
        store_id = int(callback.data.split("_")[1])
    except (ValueError, IndexError) as e:
        logger.error(f"Invalid store_id in callback data: {callback.data}, error: {e}")
        await callback.answer(get_text(lang, "error"), show_alert=True)
        return

    db.remove_favorite(user_id, store_id)
    await callback.message.delete()
    await callback.answer(get_text(lang, "removed_from_favorites"), show_alert=True)
