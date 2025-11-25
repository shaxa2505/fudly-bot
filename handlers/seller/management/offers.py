"""Seller offer management handlers - CRUD operations for offers."""
from __future__ import annotations

import asyncio
import re
from datetime import datetime, timedelta

from aiogram import F, Router, types
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.keyboards import main_menu_seller
from handlers.common.states import EditOffer
from localization import get_text
from logging_config import logger

from .utils import get_db, get_offer_field, get_store_field, send_offer_card, update_offer_message

router = Router()


@router.message(F.text.contains("Мои товары") | F.text.contains("Mening mahsulotlarim"))
async def my_offers(message: types.Message) -> None:
    """Display seller's offers with management buttons."""
    db = get_db()
    lang = db.get_user_language(message.from_user.id)
    stores = db.get_user_stores(message.from_user.id)

    logger.info(f"my_offers: user {message.from_user.id}, stores count: {len(stores)}")

    if not stores:
        await message.answer(get_text(lang, "no_stores"))
        return

    all_offers = []
    for store in stores:
        store_id = get_store_field(store, "store_id")
        store_name = get_store_field(store, "name", "Магазин")
        offers = db.get_store_offers(store_id)
        logger.info(f"Store {store_id} ({store_name}), offers count: {len(offers)}")
        all_offers.extend(offers)

    logger.info(f"Total offers: {len(all_offers)}")

    if not all_offers:
        await message.answer(
            "📦 <b>" + ("Ваши товары" if lang == "ru" else "Sizning mahsulotlaringiz") + "</b>\n\n"
            "❌ " + get_text(lang, "no_offers_yet") + "\n\n"
            "💡 "
            + (
                "Нажмите ➕ Добавить чтобы создать первый товар"
                if lang == "ru"
                else "➕ Qo'shish tugmasini bosing"
            ),
            parse_mode="HTML",
        )
        return

    # Count active and inactive
    active_count = sum(1 for o in all_offers if get_offer_field(o, "status") == "active")
    inactive_count = len(all_offers) - active_count

    # Filter menu
    filter_kb = InlineKeyboardBuilder()
    filter_kb.button(text=f"✅ Активные ({active_count})", callback_data="filter_offers_active")
    filter_kb.button(
        text=f"❌ Неактивные ({inactive_count})", callback_data="filter_offers_inactive"
    )
    filter_kb.button(text=f"📋 Все ({len(all_offers)})", callback_data="filter_offers_all")
    filter_kb.adjust(2, 1)

    await message.answer(
        "┌─────────────────────────┐\n"
        f"│  📦 <b>{'ВАШИ ТОВАРЫ' if lang == 'ru' else 'MAHSULOTLARINGIZ'}</b>  │\n"
        "└─────────────────────────┘\n\n"
        f"✅ Активных: <b>{active_count}</b>\n"
        f"❌ Неактивных: <b>{inactive_count}</b>\n"
        f"📊 Всего: <b>{len(all_offers)}</b>",
        parse_mode="HTML",
        reply_markup=filter_kb.as_markup(),
    )

    # Show first 10 offers
    for offer in all_offers[:10]:
        await send_offer_card(message, offer, lang)
        await asyncio.sleep(0.1)

    if len(all_offers) > 10:
        await message.answer(
            f"ℹ️ {'Показано первые 10 товаров из' if lang == 'ru' else 'Birinchi 10 ta mahsulot'} {len(all_offers)}\n"
            f"{'Используйте фильтры выше для поиска' if lang == 'ru' else 'Qidirish uchun filtrlardan foydalaning'}"
        )


@router.callback_query(F.data.startswith("filter_offers_"))
async def filter_offers(callback: types.CallbackQuery) -> None:
    """Filter offers by status."""
    db = get_db()
    filter_type = callback.data.split("_")[-1]  # active, inactive, all
    lang = db.get_user_language(callback.from_user.id)
    stores = db.get_user_stores(callback.from_user.id)

    if not stores:
        await callback.answer(get_text(lang, "no_stores"), show_alert=True)
        return

    all_offers = []
    for store in stores:
        store_id = get_store_field(store, "store_id")
        offers = db.get_store_offers(store_id)
        all_offers.extend(offers)

    # Apply filter
    if filter_type == "active":
        filtered = [o for o in all_offers if get_offer_field(o, "status") == "active"]
        title = "✅ Активные товары"
    elif filter_type == "inactive":
        filtered = [o for o in all_offers if get_offer_field(o, "status") != "active"]
        title = "❌ Неактивные товары"
    else:
        filtered = all_offers
        title = "📋 Все товары"

    if not filtered:
        await callback.answer(
            f"{'Нет товаров в этой категории' if lang == 'ru' else 'Bu kategoriyada mahsulot yo`q'}",
            show_alert=True,
        )
        return

    await callback.answer()

    await callback.message.answer(
        f"<b>{title}</b>\n\n" f"{'Найдено' if lang == 'ru' else 'Topildi'}: <b>{len(filtered)}</b>",
        parse_mode="HTML",
    )

    for offer in filtered[:10]:
        await send_offer_card(callback.message, offer, lang)
        await asyncio.sleep(0.1)

    if len(filtered) > 10:
        await callback.message.answer(
            f"ℹ️ {'Показано первые 10 из' if lang == 'ru' else 'Birinchi 10 ta'} {len(filtered)}"
        )


@router.callback_query(F.data.startswith("qty_add_"))
async def quantity_add(callback: types.CallbackQuery) -> None:
    """Increase offer quantity by 1."""
    db = get_db()
    lang = db.get_user_language(callback.from_user.id)

    try:
        offer_id = int(callback.data.rsplit("_", 1)[-1])
    except (ValueError, IndexError) as e:
        logger.error(f"Invalid offer_id in callback data: {callback.data}, error: {e}")
        await callback.answer(get_text(lang, "error"), show_alert=True)
        return

    offer = db.get_offer(offer_id)
    if not offer:
        await callback.answer(get_text(lang, "offer_not_found"), show_alert=True)
        return

    offer_store_id = get_offer_field(offer, "store_id")
    user_stores = db.get_user_stores(callback.from_user.id)
    if not any(get_store_field(store, "store_id") == offer_store_id for store in user_stores):
        await callback.answer(get_text(lang, "not_your_offer"), show_alert=True)
        return

    try:
        new_quantity = db.increment_offer_quantity_atomic(offer_id, 1)
    except Exception as e:
        logger.error(f"Failed to increment quantity for {offer_id}: {e}")
        await callback.answer(get_text(lang, "error"), show_alert=True)
        return

    await update_offer_message(callback, offer_id, lang)
    await callback.answer(f"✅ +1 (теперь {new_quantity})")


@router.callback_query(F.data.startswith("qty_sub_"))
async def quantity_subtract(callback: types.CallbackQuery) -> None:
    """Decrease offer quantity by 1."""
    db = get_db()
    lang = db.get_user_language(callback.from_user.id)

    try:
        offer_id = int(callback.data.rsplit("_", 1)[-1])
    except (ValueError, IndexError) as e:
        logger.error(f"Invalid offer_id in callback data: {callback.data}, error: {e}")
        await callback.answer(get_text(lang, "error"), show_alert=True)
        return

    offer = db.get_offer(offer_id)
    if not offer:
        await callback.answer(get_text(lang, "offer_not_found"), show_alert=True)
        return

    offer_store_id = get_offer_field(offer, "store_id")
    user_stores = db.get_user_stores(callback.from_user.id)
    if not any(get_store_field(store, "store_id") == offer_store_id for store in user_stores):
        await callback.answer(get_text(lang, "not_your_offer"), show_alert=True)
        return

    try:
        new_quantity = db.increment_offer_quantity_atomic(offer_id, -1)
    except Exception as e:
        logger.error(f"Failed to decrement quantity for {offer_id}: {e}")
        await callback.answer(get_text(lang, "error"), show_alert=True)
        return

    await update_offer_message(callback, offer_id, lang)

    if new_quantity == 0:
        await callback.answer("⚠️ Количество 0 - товар снят с продажи", show_alert=True)
    else:
        await callback.answer(f"✅ -1 (теперь {new_quantity})")


@router.callback_query(F.data.startswith("extend_offer_"))
async def extend_offer(callback: types.CallbackQuery) -> None:
    """Extend offer expiry date."""
    db = get_db()
    lang = db.get_user_language(callback.from_user.id)

    try:
        offer_id = int(callback.data.rsplit("_", 1)[-1])
    except (ValueError, IndexError) as e:
        logger.error(f"Invalid offer_id in callback data: {callback.data}, error: {e}")
        await callback.answer(get_text(lang, "error"), show_alert=True)
        return

    offer = db.get_offer(offer_id)
    if not offer:
        await callback.answer(get_text(lang, "offer_not_found"), show_alert=True)
        return

    user_stores = db.get_user_stores(callback.from_user.id)
    offer_store_id = get_offer_field(offer, "store_id")
    if not any(get_store_field(store, "store_id") == offer_store_id for store in user_stores):
        await callback.answer(get_text(lang, "not_your_offer"), show_alert=True)
        return

    today = datetime.now()

    builder = InlineKeyboardBuilder()
    builder.button(text=f"Сегодня {today.strftime('%d.%m')}", callback_data=f"setexp_{offer_id}_0")
    builder.button(
        text=f"Завтра {(today + timedelta(days=1)).strftime('%d.%m')}",
        callback_data=f"setexp_{offer_id}_1",
    )
    builder.button(
        text=f"+2 дня {(today + timedelta(days=2)).strftime('%d.%m')}",
        callback_data=f"setexp_{offer_id}_2",
    )
    builder.button(
        text=f"+3 дня {(today + timedelta(days=3)).strftime('%d.%m')}",
        callback_data=f"setexp_{offer_id}_3",
    )
    builder.button(
        text=f"Неделя {(today + timedelta(days=7)).strftime('%d.%m')}",
        callback_data=f"setexp_{offer_id}_7",
    )
    builder.button(text="❌ Отмена", callback_data="cancel_extend")
    builder.adjust(2, 2, 1, 1)

    await callback.message.edit_reply_markup(reply_markup=builder.as_markup())
    await callback.answer("📅 Выберите новый срок годности")


@router.callback_query(F.data.startswith("setexp_"))
async def set_expiry(callback: types.CallbackQuery) -> None:
    """Set new expiry date."""
    db = get_db()
    lang = db.get_user_language(callback.from_user.id)
    parts = callback.data.split("_")
    offer_id = int(parts[1])
    days_add = int(parts[2])

    new_expiry = (datetime.now() + timedelta(days=days_add)).strftime("%Y-%m-%d")
    db.update_offer_expiry(offer_id, new_expiry)

    await update_offer_message(callback, offer_id, lang)
    await callback.answer(f"✅ Срок продлён до {new_expiry}")


@router.callback_query(F.data == "cancel_extend")
async def cancel_extend(callback: types.CallbackQuery) -> None:
    """Cancel expiry extension."""
    await callback.answer("❌ Отменено")
    await callback.message.edit_reply_markup(reply_markup=None)


@router.callback_query(F.data.startswith("deactivate_offer_"))
async def deactivate_offer(callback: types.CallbackQuery) -> None:
    """Deactivate offer."""
    db = get_db()
    lang = db.get_user_language(callback.from_user.id)

    try:
        offer_id = int(callback.data.split("_")[2])
    except (ValueError, IndexError) as e:
        logger.error(f"Invalid offer_id in callback data: {callback.data}, error: {e}")
        await callback.answer(get_text(lang, "error"), show_alert=True)
        return

    offer = db.get_offer(offer_id)
    if not offer:
        await callback.answer(get_text(lang, "offer_not_found"), show_alert=True)
        return

    user_stores = db.get_user_stores(callback.from_user.id)
    offer_store_id = get_offer_field(offer, "store_id")
    if not any(get_store_field(store, "store_id") == offer_store_id for store in user_stores):
        await callback.answer(get_text(lang, "not_your_offer"), show_alert=True)
        return

    db.deactivate_offer(offer_id)
    await update_offer_message(callback, offer_id, lang)
    await callback.answer("✅ Товар снят с продажи")


@router.callback_query(F.data.startswith("activate_offer_"))
async def activate_offer(callback: types.CallbackQuery) -> None:
    """Activate offer."""
    db = get_db()
    lang = db.get_user_language(callback.from_user.id)

    try:
        offer_id = int(callback.data.split("_")[2])
    except (ValueError, IndexError) as e:
        logger.error(f"Invalid offer_id in callback data: {callback.data}, error: {e}")
        await callback.answer(get_text(lang, "error"), show_alert=True)
        return

    offer = db.get_offer(offer_id)
    if not offer:
        await callback.answer(get_text(lang, "offer_not_found"), show_alert=True)
        return

    user_stores = db.get_user_stores(callback.from_user.id)
    offer_store_id = get_offer_field(offer, "store_id")
    if not any(get_store_field(store, "store_id") == offer_store_id for store in user_stores):
        await callback.answer(get_text(lang, "not_your_offer"), show_alert=True)
        return

    db.activate_offer(offer_id)
    await update_offer_message(callback, offer_id, lang)
    await callback.answer("✅ Товар активирован")


@router.callback_query(F.data.startswith("delete_offer_"))
async def delete_offer(callback: types.CallbackQuery) -> None:
    """Delete offer."""
    db = get_db()
    lang = db.get_user_language(callback.from_user.id)

    try:
        offer_id = int(callback.data.split("_")[2])
    except (ValueError, IndexError) as e:
        logger.error(f"Invalid offer_id in callback data: {callback.data}, error: {e}")
        await callback.answer(get_text(lang, "error"), show_alert=True)
        return

    offer = db.get_offer(offer_id)
    if not offer:
        await callback.answer(get_text(lang, "offer_not_found"), show_alert=True)
        return

    user_stores = db.get_user_stores(callback.from_user.id)
    offer_store_id = get_offer_field(offer, "store_id")
    if not any(get_store_field(store, "store_id") == offer_store_id for store in user_stores):
        await callback.answer(get_text(lang, "not_your_offer"), show_alert=True)
        return

    db.delete_offer(offer_id)
    await callback.message.delete()
    await callback.answer("🗑 Товар удалён")


@router.callback_query(F.data.startswith("edit_offer_"))
async def edit_offer(callback: types.CallbackQuery) -> None:
    """Show offer edit menu."""
    db = get_db()
    lang = db.get_user_language(callback.from_user.id)

    try:
        offer_id = int(callback.data.split("_")[2])
    except (ValueError, IndexError) as e:
        logger.error(f"Invalid offer_id in callback data: {callback.data}, error: {e}")
        await callback.answer(get_text(lang, "error"), show_alert=True)
        return

    offer = db.get_offer(offer_id)
    if not offer:
        await callback.answer(get_text(lang, "offer_not_found"), show_alert=True)
        return

    user_stores = db.get_user_stores(callback.from_user.id)
    offer_store_id = get_offer_field(offer, "store_id")
    if not any(get_store_field(store, "store_id") == offer_store_id for store in user_stores):
        await callback.answer(get_text(lang, "not_your_offer"), show_alert=True)
        return

    kb = InlineKeyboardBuilder()
    kb.button(
        text="💰 Изменить цену" if lang == "ru" else "💰 Narxni o'zgartirish",
        callback_data=f"edit_price_{offer_id}",
    )
    kb.button(
        text="📦 Изменить количество" if lang == "ru" else "📦 Sonini o'zgartirish",
        callback_data=f"edit_quantity_{offer_id}",
    )
    kb.button(
        text="🕐 Изменить время" if lang == "ru" else "🕐 Vaqtni o'zgartirish",
        callback_data=f"edit_time_{offer_id}",
    )
    kb.button(
        text="📝 Изменить описание" if lang == "ru" else "📝 Tavsifni o'zgartirish",
        callback_data=f"edit_description_{offer_id}",
    )
    kb.button(
        text="🔙 Назад" if lang == "ru" else "🔙 Orqaga", callback_data=f"back_to_offer_{offer_id}"
    )
    kb.adjust(1)

    try:
        await callback.message.edit_reply_markup(reply_markup=kb.as_markup())
    except Exception:
        await callback.answer(get_text(lang, "edit_unavailable"), show_alert=True)

    await callback.answer()


@router.callback_query(F.data.startswith("back_to_offer_"))
async def back_to_offer(callback: types.CallbackQuery) -> None:
    """Return to offer management view."""
    db = get_db()
    lang = db.get_user_language(callback.from_user.id)
    try:
        offer_id = int(callback.data.rsplit("_", 1)[-1])
    except (ValueError, IndexError) as e:
        logger.error(f"Invalid offer_id in callback data: {callback.data}, error: {e}")
        await callback.answer(get_text(lang, "error"), show_alert=True)
        return

    await update_offer_message(callback, offer_id, lang)
    await callback.answer()


@router.callback_query(F.data.startswith("edit_time_"))
async def edit_time_start(callback: types.CallbackQuery, state: FSMContext) -> None:
    """Start editing pickup time."""
    db = get_db()
    lang = db.get_user_language(callback.from_user.id)

    try:
        offer_id = int(callback.data.split("_")[2])
    except (ValueError, IndexError) as e:
        logger.error(f"Invalid offer_id in callback data: {callback.data}, error: {e}")
        await callback.answer(get_text(lang, "error"), show_alert=True)
        return

    offer = db.get_offer(offer_id)
    if not offer:
        await callback.answer(get_text(lang, "offer_not_found"), show_alert=True)
        return

    user_stores = db.get_user_stores(callback.from_user.id)
    offer_store_id = get_offer_field(offer, "store_id")
    if not any(get_store_field(store, "store_id") == offer_store_id for store in user_stores):
        await callback.answer(get_text(lang, "not_your_offer"), show_alert=True)
        return

    await state.update_data(offer_id=offer_id)
    await state.set_state(EditOffer.available_from)

    available_from = get_offer_field(offer, "available_from", "")
    available_until = get_offer_field(offer, "available_until", "")

    await callback.message.answer(
        f"🕐 <b>Изменение времени забора</b>\n\n"
        f"Текущее время: {available_from} - {available_until}\n\n"
        f"{'Введите новое время начала (например: 18:00):' if lang == 'ru' else 'Yangi boshlanish vaqtini kiriting (masalan: 18:00):'}",
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(EditOffer.available_from)
async def edit_time_from(message: types.Message, state: FSMContext) -> None:
    """Process start time."""
    db = get_db()
    lang = db.get_user_language(message.from_user.id)

    time_pattern = r"^([0-1]?[0-9]|2[0-3]):([0-5][0-9])$"
    if not re.match(time_pattern, message.text.strip()):
        error_msg = (
            "❌ Неверный формат! Введите время в формате ЧЧ:ММ (например: 18:00)"
            if lang == "ru"
            else "❌ Noto'g'ri format! ЧЧ:ММ formatida vaqt kiriting (masalan: 18:00)"
        )
        await message.answer(error_msg)
        return

    await state.update_data(available_from=message.text.strip())
    await message.answer(
        f"{'Введите время окончания (например: 21:00):' if lang == 'ru' else 'Tugash vaqtini kiriting (masalan: 21:00):'}",
        reply_markup=types.ReplyKeyboardRemove(),
    )
    await state.set_state(EditOffer.available_until)


@router.message(EditOffer.available_until)
async def edit_time_until(message: types.Message, state: FSMContext) -> None:
    """Complete time editing."""
    db = get_db()
    lang = db.get_user_language(message.from_user.id)

    time_pattern = r"^([0-1]?[0-9]|2[0-3]):([0-5][0-9])$"
    if not re.match(time_pattern, message.text.strip()):
        error_msg = (
            "❌ Неверный формат! Введите время в формате ЧЧ:ММ (например: 21:00)"
            if lang == "ru"
            else "❌ Noto'g'ri format! ЧЧ:ММ formatida vaqt kiriting (masalan: 21:00)"
        )
        await message.answer(error_msg)
        return

    data = await state.get_data()
    offer_id = data["offer_id"]
    available_from = data["available_from"]
    available_until = message.text.strip()

    with db.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE offers SET available_from = ?, available_until = ? WHERE offer_id = ?",
            (available_from, available_until, offer_id),
        )

    await message.answer(
        f"✅ {'Время забора обновлено!' if lang == 'ru' else 'Olib ketish vaqti yangilandi!'}\n\n"
        f"🕐 {available_from} - {available_until}",
        reply_markup=main_menu_seller(lang),
    )
    await state.clear()


@router.callback_query(F.data.startswith("duplicate_"))
async def duplicate_offer(callback: types.CallbackQuery) -> None:
    """Duplicate offer."""
    db = get_db()
    lang = db.get_user_language(callback.from_user.id)
    offer_id = int(callback.data.split("_")[1])
    offer = db.get_offer(offer_id)

    if offer:
        unit_val = get_offer_field(offer, "unit", "шт")
        if not unit_val or not isinstance(unit_val, str) or len(unit_val) > 5:
            unit_val = "шт"
        category_val = get_offer_field(offer, "category", "other") or "other"

        db.add_offer(
            store_id=get_offer_field(offer, "store_id"),
            title=get_offer_field(offer, "title"),
            description=get_offer_field(offer, "description"),
            original_price=get_offer_field(offer, "original_price"),
            discount_price=get_offer_field(offer, "discount_price"),
            quantity=get_offer_field(offer, "quantity"),
            available_from=get_offer_field(offer, "available_from"),
            available_until=get_offer_field(offer, "available_until"),
            photo_id=get_offer_field(offer, "photo"),
            expiry_date=get_offer_field(offer, "expiry_date"),
            unit=unit_val,
            category=category_val,
        )
        await callback.answer(get_text(lang, "duplicated"), show_alert=True)
