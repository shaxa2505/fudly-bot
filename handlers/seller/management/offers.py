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
    filter_kb.button(text=f"✅ Активные ({active_count})", callback_data="filter_offers_active_0")
    filter_kb.button(
        text=f"❌ Неактивные ({inactive_count})", callback_data="filter_offers_inactive_0"
    )
    filter_kb.button(text=f"📋 Все ({len(all_offers)})", callback_data="filter_offers_all_0")
    filter_kb.button(text="🔍 Поиск", callback_data="search_my_offers")
    filter_kb.adjust(2, 1, 1)

    await message.answer(
        "┌─────────────────────────┐\n"
        f"│  📦 <b>{'ВАШИ ТОВАРЫ' if lang == 'ru' else 'MAHSULOTLARINGIZ'}</b>  │\n"
        "└─────────────────────────┘\n\n"
        f"✅ Активных: <b>{active_count}</b>\n"
        f"❌ Неактивных: <b>{inactive_count}</b>\n"
        f"📊 Всего: <b>{len(all_offers)}</b>\n\n"
        f"{'Выберите категорию для просмотра:' if lang == 'ru' else 'Kategoriyani tanlang:'}",
        parse_mode="HTML",
        reply_markup=filter_kb.as_markup(),
    )


@router.callback_query(F.data.startswith("filter_offers_"))
async def filter_offers(callback: types.CallbackQuery) -> None:
    """Filter offers by status with pagination."""
    db = get_db()
    lang = db.get_user_language(callback.from_user.id)
    stores = db.get_user_stores(callback.from_user.id)

    if not stores:
        await callback.answer(get_text(lang, "no_stores"), show_alert=True)
        return

    # Parse filter type and page: filter_offers_active_0
    parts = callback.data.split("_")
    filter_type = parts[2] if len(parts) > 2 else "all"  # active, inactive, all
    page = int(parts[3]) if len(parts) > 3 and parts[3].isdigit() else 0
    
    ITEMS_PER_PAGE = 5

    all_offers = []
    for store in stores:
        store_id = get_store_field(store, "store_id")
        offers = db.get_store_offers(store_id)
        all_offers.extend(offers)

    # Apply filter
    if filter_type == "active":
        filtered = [o for o in all_offers if get_offer_field(o, "status") == "active"]
        title = "✅ Активные" if lang == "ru" else "✅ Faol"
    elif filter_type == "inactive":
        filtered = [o for o in all_offers if get_offer_field(o, "status") != "active"]
        title = "❌ Неактивные" if lang == "ru" else "❌ Nofaol"
    else:
        filtered = all_offers
        title = "📋 Все" if lang == "ru" else "📋 Hammasi"

    if not filtered:
        await callback.answer(
            f"{'Нет товаров в этой категории' if lang == 'ru' else 'Bu kategoriyada mahsulot yo`q'}",
            show_alert=True,
        )
        return

    # Pagination
    total_pages = (len(filtered) + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE
    page = min(page, total_pages - 1)
    start_idx = page * ITEMS_PER_PAGE
    end_idx = start_idx + ITEMS_PER_PAGE
    page_offers = filtered[start_idx:end_idx]

    # Build compact list
    text = f"<b>{title}</b> ({len(filtered)})\n"
    text += f"{'Страница' if lang == 'ru' else 'Sahifa'} {page + 1}/{total_pages}\n\n"

    for i, offer in enumerate(page_offers, start=start_idx + 1):
        offer_id = get_offer_field(offer, "offer_id")
        offer_title = get_offer_field(offer, "title", "Товар")[:25]
        price = get_offer_field(offer, "discount_price", 0)
        qty = get_offer_field(offer, "quantity", 0)
        status = get_offer_field(offer, "status", "active")
        
        status_icon = "✅" if status == "active" else "❌"
        qty_icon = "🟢" if qty > 0 else "🔴"
        
        text += f"{i}. {status_icon} <b>{offer_title}</b>\n"
        text += f"   💰 {price:,} | {qty_icon} {qty} шт\n"

    # Navigation buttons
    nav_kb = InlineKeyboardBuilder()
    
    # Add item buttons for quick access
    for offer in page_offers:
        offer_id = get_offer_field(offer, "offer_id")
        offer_title = get_offer_field(offer, "title", "Товар")[:15]
        nav_kb.button(text=f"📝 {offer_title}", callback_data=f"edit_offer_{offer_id}")
    
    nav_kb.adjust(2)  # 2 buttons per row for items
    
    # Pagination row
    pagination_buttons = []
    if page > 0:
        pagination_buttons.append(("◀️", f"filter_offers_{filter_type}_{page - 1}"))
    pagination_buttons.append((f"{page + 1}/{total_pages}", "noop"))
    if page < total_pages - 1:
        pagination_buttons.append(("▶️", f"filter_offers_{filter_type}_{page + 1}"))
    
    for btn_text, btn_data in pagination_buttons:
        nav_kb.button(text=btn_text, callback_data=btn_data)
    
    # Back button
    nav_kb.button(text="🔙 Назад" if lang == "ru" else "🔙 Orqaga", callback_data="back_to_offers_menu")
    
    # Adjust: items (2 per row), then pagination (3), then back (1)
    nav_kb.adjust(2, 2, len(pagination_buttons), 1)

    await callback.answer()
    
    try:
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=nav_kb.as_markup())
    except Exception:
        await callback.message.answer(text, parse_mode="HTML", reply_markup=nav_kb.as_markup())


@router.callback_query(F.data == "back_to_offers_menu")
async def back_to_offers_menu(callback: types.CallbackQuery) -> None:
    """Return to main offers menu."""
    db = get_db()
    lang = db.get_user_language(callback.from_user.id)
    stores = db.get_user_stores(callback.from_user.id)

    all_offers = []
    for store in stores:
        store_id = get_store_field(store, "store_id")
        offers = db.get_store_offers(store_id)
        all_offers.extend(offers)

    active_count = sum(1 for o in all_offers if get_offer_field(o, "status") == "active")
    inactive_count = len(all_offers) - active_count

    filter_kb = InlineKeyboardBuilder()
    filter_kb.button(text=f"✅ Активные ({active_count})", callback_data="filter_offers_active_0")
    filter_kb.button(
        text=f"❌ Неактивные ({inactive_count})", callback_data="filter_offers_inactive_0"
    )
    filter_kb.button(text=f"📋 Все ({len(all_offers)})", callback_data="filter_offers_all_0")
    filter_kb.button(text="🔍 Поиск", callback_data="search_my_offers")
    filter_kb.adjust(2, 1, 1)

    await callback.answer()
    await callback.message.edit_text(
        "┌─────────────────────────┐\n"
        f"│  📦 <b>{'ВАШИ ТОВАРЫ' if lang == 'ru' else 'MAHSULOTLARINGIZ'}</b>  │\n"
        "└─────────────────────────┘\n\n"
        f"✅ Активных: <b>{active_count}</b>\n"
        f"❌ Неактивных: <b>{inactive_count}</b>\n"
        f"📊 Всего: <b>{len(all_offers)}</b>\n\n"
        f"{'Выберите категорию для просмотра:' if lang == 'ru' else 'Kategoriyani tanlang:'}",
        parse_mode="HTML",
        reply_markup=filter_kb.as_markup(),
    )


@router.callback_query(F.data == "noop")
async def noop_handler(callback: types.CallbackQuery) -> None:
    """Handle noop button press (pagination indicator)."""
    await callback.answer()


@router.callback_query(F.data == "search_my_offers")
async def search_my_offers_start(callback: types.CallbackQuery, state: FSMContext) -> None:
    """Start search for seller's offers."""
    db = get_db()
    lang = db.get_user_language(callback.from_user.id)
    
    await state.set_state(EditOffer.search_query)
    await callback.answer()
    await callback.message.answer(
        f"🔍 {'Введите название товара для поиска:' if lang == 'ru' else 'Qidiruv uchun mahsulot nomini kiriting:'}",
        parse_mode="HTML",
    )


@router.message(EditOffer.search_query)
async def search_my_offers_process(message: types.Message, state: FSMContext) -> None:
    """Process search query for seller's offers."""
    db = get_db()
    lang = db.get_user_language(message.from_user.id)
    query = (message.text or "").strip().lower()
    
    # Check for cancel
    if "отмена" in query or "bekor" in query or query.startswith("/"):
        await state.clear()
        await message.answer(
            "❌ " + ("Поиск отменён" if lang == "ru" else "Qidiruv bekor qilindi"),
            reply_markup=main_menu_seller(lang),
        )
        return
    
    if len(query) < 2:
        await message.answer(
            "❌ " + ("Минимум 2 символа" if lang == "ru" else "Kamida 2 ta belgi")
        )
        return
    
    await state.clear()
    
    stores = db.get_user_stores(message.from_user.id)
    all_offers = []
    for store in stores:
        store_id = get_store_field(store, "store_id")
        offers = db.get_store_offers(store_id)
        all_offers.extend(offers)
    
    # Search
    results = []
    for offer in all_offers:
        title = get_offer_field(offer, "title", "").lower()
        if query in title:
            results.append(offer)
    
    if not results:
        await message.answer(
            f"🔍 {'Ничего не найдено по запросу' if lang == 'ru' else 'Topilmadi'}: <b>{query}</b>",
            parse_mode="HTML",
        )
        return
    
    # Show results
    text = f"🔍 {'Результаты поиска' if lang == 'ru' else 'Qidiruv natijalari'}: <b>{query}</b>\n"
    text += f"{'Найдено' if lang == 'ru' else 'Topildi'}: {len(results)}\n\n"
    
    nav_kb = InlineKeyboardBuilder()
    
    for offer in results[:10]:
        offer_id = get_offer_field(offer, "offer_id")
        offer_title = get_offer_field(offer, "title", "Товар")[:25]
        price = get_offer_field(offer, "discount_price", 0)
        qty = get_offer_field(offer, "quantity", 0)
        status = get_offer_field(offer, "status", "active")
        
        status_icon = "✅" if status == "active" else "❌"
        
        text += f"{status_icon} <b>{offer_title}</b>\n"
        text += f"   💰 {price:,} | 📦 {qty} шт\n"
        
        nav_kb.button(text=f"📝 {offer_title[:15]}", callback_data=f"edit_offer_{offer_id}")
    
    nav_kb.button(text="🔙 Назад" if lang == "ru" else "🔙 Orqaga", callback_data="back_to_offers_menu")
    nav_kb.adjust(2, 1)
    
    await message.answer(text, parse_mode="HTML", reply_markup=nav_kb.as_markup())


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
        text="🔄 Копировать" if lang == "ru" else "🔄 Nusxalash",
        callback_data=f"copy_offer_{offer_id}",
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
