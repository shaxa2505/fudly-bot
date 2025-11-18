"""Seller offer management handlers."""
from __future__ import annotations

import asyncio
import re
from datetime import datetime, timedelta
from typing import Any

from aiogram import F, Router, types
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder

from database_protocol import DatabaseProtocol
from handlers.common_states.states import EditOffer
from app.keyboards import main_menu_seller
from localization import get_text
from logging_config import logger

# Module-level dependencies
db: DatabaseProtocol | None = None
bot: Any | None = None

router = Router()


def setup_dependencies(database: DatabaseProtocol, bot_instance: Any) -> None:
    """Setup module dependencies."""
    global db, bot
    db = database
    bot = bot_instance


def get_store_field(store: Any, field: str, default: Any = None) -> Any:
    """Extract field from store tuple/dict."""
    if isinstance(store, dict):
        return store.get(field, default)
    field_map = {
        "store_id": 0,
        "owner_id": 1,
        "name": 2,
        "city": 3,
        "address": 4,
        "description": 5,
        "status": 6,
        "category": 7,
        "phone": 8,
        "rating": 9,
    }
    idx = field_map.get(field)
    if idx is not None and isinstance(store, (tuple, list)) and idx < len(store):
        return store[idx]
    return default


@router.message(
    F.text.contains("Мои товары") | F.text.contains("Mening mahsulotlarim")
)
async def my_offers(message: types.Message) -> None:
    """Display seller's offers with management buttons."""
    if not db:
        await message.answer("System error")
        return

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
        await message.answer(get_text(lang, "no_offers_yet"))
        return

    await message.answer(
        f"📦 <b>{'Ваши товары' if lang == 'ru' else 'Sizning mahsulotlaringiz'}</b>\n"
        f"{'Найдено' if lang == 'ru' else 'Topildi'}: {len(all_offers)} {'товаров' if lang == 'ru' else 'mahsulot'}",
        parse_mode="HTML",
    )

    for offer in all_offers[:20]:
        # Dict-compatible access
        offer_id = offer.get('offer_id') if isinstance(offer, dict) else offer[0]
        title = offer.get('title') if isinstance(offer, dict) else (offer[2] if len(offer) > 2 else 'Без названия')
        original_price = int(offer.get('original_price', 0) if isinstance(offer, dict) else (offer[4] if len(offer) > 4 else 0))
        discount_price = int(offer.get('discount_price', 0) if isinstance(offer, dict) else (offer[5] if len(offer) > 5 else 0))
        quantity = offer.get('quantity', 0) if isinstance(offer, dict) else (offer[6] if len(offer) > 6 else 0)
        status = offer.get('status', 'active') if isinstance(offer, dict) else (offer[10] if len(offer) > 10 else "active")

        unit = offer[13] if len(offer) >= 14 and offer[13] else "шт"

        discount_percent = (
            int((1 - discount_price / original_price) * 100) if original_price > 0 else 0
        )

        status_emoji = "✅" if status == "active" else "❌"
        text = f"{status_emoji} <b>{title}</b>\n\n"
        text += f"💰 {original_price:,} ➜ <b>{discount_price:,}</b> сум (-{discount_percent}%)\n"
        text += f"📦 {'Осталось' if lang == 'ru' else 'Qoldi'}: <b>{quantity}</b> {unit}\n"

        if len(offer) > 9 and offer[9]:
            expiry_info = db.get_time_remaining(offer[9])
            if expiry_info:
                text += f"{expiry_info}\n"
            else:
                text += f"📅 До: {offer[9]}\n"

        text += f"🕐 {offer[7]} - {offer[8]}"

        builder = InlineKeyboardBuilder()

        if status == "active":
            builder.button(text="➕ +1", callback_data=f"qty_add_{offer_id}")
            builder.button(text="➖ -1", callback_data=f"qty_sub_{offer_id}")
            builder.button(
                text="📝 Изменить" if lang == "ru" else "📝 Tahrirlash",
                callback_data=f"edit_offer_{offer_id}",
            )
            builder.button(
                text="🔄 Продлить" if lang == "ru" else "🔄 Uzaytirish",
                callback_data=f"extend_offer_{offer_id}",
            )
            builder.button(
                text="❌ Снять" if lang == "ru" else "❌ O'chirish",
                callback_data=f"deactivate_offer_{offer_id}",
            )
            builder.adjust(2, 2, 1)
        else:
            builder.button(
                text="✅ Активировать" if lang == "ru" else "✅ Faollashtirish",
                callback_data=f"activate_offer_{offer_id}",
            )
            builder.button(
                text="🗑 Удалить" if lang == "ru" else "🗑 O'chirish",
                callback_data=f"delete_offer_{offer_id}",
            )
            builder.adjust(2)

        if len(offer) > 11 and offer[11]:
            try:
                await message.answer_photo(
                    photo=offer[11],
                    caption=text,
                    parse_mode="HTML",
                    reply_markup=builder.as_markup(),
                )
            except Exception:
                await message.answer(
                    text, parse_mode="HTML", reply_markup=builder.as_markup()
                )
        else:
            await message.answer(
                text, parse_mode="HTML", reply_markup=builder.as_markup()
            )

        await asyncio.sleep(0.1)

    if len(all_offers) > 20:
        await message.answer(
            f"... {'и ещё' if lang == 'ru' else 'va yana'} {len(all_offers) - 20} {'товаров' if lang == 'ru' else 'mahsulot'}"
        )


@router.callback_query(F.data.startswith("qty_add_"))
async def quantity_add(callback: types.CallbackQuery) -> None:
    """Increase offer quantity by 1."""
    if not db:
        await callback.answer("System error")
        return

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
    if not any(get_store_field(store, "store_id") == offer[1] for store in user_stores):
        await callback.answer(get_text(lang, "not_your_offer"), show_alert=True)
        return

    new_quantity = offer[6] + 1
    db.update_offer_quantity(offer_id, new_quantity)

    await update_offer_message(callback, offer_id, lang)
    await callback.answer(f"✅ +1 (теперь {new_quantity})")


@router.callback_query(F.data.startswith("qty_sub_"))
async def quantity_subtract(callback: types.CallbackQuery) -> None:
    """Decrease offer quantity by 1."""
    if not db:
        await callback.answer("System error")
        return

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
    if not any(get_store_field(store, "store_id") == offer[1] for store in user_stores):
        await callback.answer(get_text(lang, "not_your_offer"), show_alert=True)
        return

    new_quantity = max(0, offer[6] - 1)
    db.update_offer_quantity(offer_id, new_quantity)

    await update_offer_message(callback, offer_id, lang)

    if new_quantity == 0:
        await callback.answer(
            "⚠️ Количество 0 - товар снят с продажи", show_alert=True
        )
    else:
        await callback.answer(f"✅ -1 (теперь {new_quantity})")


@router.callback_query(F.data.startswith("extend_offer_"))
async def extend_offer(callback: types.CallbackQuery) -> None:
    """Extend offer expiry date."""
    if not db:
        await callback.answer("System error")
        return

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
    if not any(get_store_field(store, "store_id") == offer[1] for store in user_stores):
        await callback.answer(get_text(lang, "not_your_offer"), show_alert=True)
        return

    today = datetime.now()

    builder = InlineKeyboardBuilder()
    builder.button(
        text=f"Сегодня {today.strftime('%d.%m')}",
        callback_data=f"setexp_{offer_id}_0",
    )
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
    if not db:
        await callback.answer("System error")
        return

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
    if not db:
        await callback.answer("System error")
        return

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
    if not any(get_store_field(store, "store_id") == offer[1] for store in user_stores):
        await callback.answer(get_text(lang, "not_your_offer"), show_alert=True)
        return

    db.deactivate_offer(offer_id)

    await update_offer_message(callback, offer_id, lang)
    await callback.answer("✅ Товар снят с продажи")


@router.callback_query(F.data.startswith("activate_offer_"))
async def activate_offer(callback: types.CallbackQuery) -> None:
    """Activate offer."""
    if not db:
        await callback.answer("System error")
        return

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
    if not any(get_store_field(store, "store_id") == offer[1] for store in user_stores):
        await callback.answer(get_text(lang, "not_your_offer"), show_alert=True)
        return

    db.activate_offer(offer_id)

    await update_offer_message(callback, offer_id, lang)
    await callback.answer("✅ Товар активирован")


@router.callback_query(F.data.startswith("delete_offer_"))
async def delete_offer(callback: types.CallbackQuery) -> None:
    """Delete offer."""
    if not db:
        await callback.answer("System error")
        return

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
    if not any(get_store_field(store, "store_id") == offer[1] for store in user_stores):
        await callback.answer(get_text(lang, "not_your_offer"), show_alert=True)
        return

    db.delete_offer(offer_id)

    await callback.message.delete()
    await callback.answer("🗑 Товар удалён")


@router.callback_query(F.data.startswith("edit_offer_"))
async def edit_offer(callback: types.CallbackQuery) -> None:
    """Show offer edit menu."""
    if not db:
        await callback.answer("System error")
        return

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
    if not any(get_store_field(store, "store_id") == offer[1] for store in user_stores):
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
        text="🔙 Назад" if lang == "ru" else "🔙 Orqaga",
        callback_data=f"back_to_offer_{offer_id}",
    )
    kb.adjust(1)

    try:
        await callback.message.edit_reply_markup(reply_markup=kb.as_markup())
    except Exception:
        await callback.answer(get_text(lang, "edit_unavailable"), show_alert=True)

    await callback.answer()


@router.callback_query(F.data.startswith("edit_time_"))
async def edit_time_start(callback: types.CallbackQuery, state: FSMContext) -> None:
    """Start editing pickup time."""
    if not db:
        await callback.answer("System error")
        return

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
    if not any(get_store_field(store, "store_id") == offer[1] for store in user_stores):
        await callback.answer(get_text(lang, "not_your_offer"), show_alert=True)
        return

    await state.update_data(offer_id=offer_id)
    await state.set_state(EditOffer.available_from)

    await callback.message.answer(
        f"🕐 <b>Изменение времени забора</b>\n\n"
        f"Текущее время: {offer[7]} - {offer[8]}\n\n"
        f"{'Введите новое время начала (например: 18:00):' if lang == 'ru' else 'Yangi boshlanish vaqtini kiriting (masalan: 18:00):'}",
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(EditOffer.available_from)
async def edit_time_from(message: types.Message, state: FSMContext) -> None:
    """Process start time."""
    if not db:
        await message.answer("System error")
        return

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
    if not db:
        await message.answer("System error")
        return

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


async def update_offer_message(
    callback: types.CallbackQuery, offer_id: int, lang: str
) -> None:
    """Update offer message with new data."""
    if not db:
        return

    offer = db.get_offer(offer_id)
    if not offer:
        return

    title = offer[2]
    original_price = int(offer[4])
    discount_price = int(offer[5])
    quantity = offer[6]
    status = offer[10] if len(offer) > 10 else "active"

    unit = offer[13] if len(offer) >= 14 and offer[13] else "шт"

    discount_percent = (
        int((1 - discount_price / original_price) * 100) if original_price > 0 else 0
    )

    status_emoji = "✅" if status == "active" else "❌"
    text = f"{status_emoji} <b>{title}</b>\n\n"
    text += f"💰 {original_price:,} ➜ <b>{discount_price:,}</b> сум (-{discount_percent}%)\n"
    text += f"📦 {'Осталось' if lang == 'ru' else 'Qoldi'}: <b>{quantity}</b> {unit}\n"

    if len(offer) > 9 and offer[9]:
        expiry_info = db.get_time_remaining(offer[9])
        if expiry_info:
            text += f"{expiry_info}\n"
        else:
            text += f"📅 До: {offer[9]}\n"

    text += f"🕐 {offer[7]} - {offer[8]}"

    builder = InlineKeyboardBuilder()

    if status == "active":
        builder.button(text="➕ +1", callback_data=f"qty_add_{offer_id}")
        builder.button(text="➖ -1", callback_data=f"qty_sub_{offer_id}")
        builder.button(
            text="📝 Изменить" if lang == "ru" else "📝 Tahrirlash",
            callback_data=f"edit_offer_{offer_id}",
        )
        builder.button(
            text="🔄 Продлить" if lang == "ru" else "🔄 Uzaytirish",
            callback_data=f"extend_offer_{offer_id}",
        )
        builder.button(
            text="❌ Снять" if lang == "ru" else "❌ O'chirish",
            callback_data=f"deactivate_offer_{offer_id}",
        )
        builder.adjust(2, 2, 1)
    else:
        builder.button(
            text="✅ Активировать" if lang == "ru" else "✅ Faollashtirish",
            callback_data=f"activate_offer_{offer_id}",
        )
        builder.button(
            text="🗑 Удалить" if lang == "ru" else "🗑 O'chirish",
            callback_data=f"delete_offer_{offer_id}",
        )
        builder.adjust(2)

    try:
        await callback.message.edit_caption(
            caption=text, parse_mode="HTML", reply_markup=builder.as_markup()
        )
    except Exception:
        try:
            await callback.message.edit_text(
                text, parse_mode="HTML", reply_markup=builder.as_markup()
            )
        except Exception:
            pass


@router.callback_query(F.data.startswith("duplicate_"))
async def duplicate_offer(callback: types.CallbackQuery) -> None:
    """Duplicate offer."""
    if not db:
        await callback.answer("System error")
        return

    lang = db.get_user_language(callback.from_user.id)
    offer_id = int(callback.data.split("_")[1])
    offer = db.get_offer(offer_id)

    if offer:
        unit_val = (
            offer[13]
            if len(offer) > 13 and isinstance(offer[13], str) and len(offer[13]) <= 5
            else "шт"
        )
        category_val = offer[14] if len(offer) > 14 and offer[14] else "other"

        db.add_offer(
            store_id=offer[1],
            title=offer[2],
            description=offer[3],
            original_price=offer[4],
            discount_price=offer[5],
            quantity=offer[6],
            available_from=offer[7],
            available_until=offer[8],
            photo_id=offer[11] if len(offer) > 11 else None,
            expiry_date=offer[9] if len(offer) > 9 else None,
            unit=unit_val,
            category=category_val,
        )
        await callback.answer(get_text(lang, "duplicated"), show_alert=True)
