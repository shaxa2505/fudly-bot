"""Store browsing and store-offer handlers split from browse.py."""
from __future__ import annotations

from typing import Any

from aiogram import Dispatcher, F, types
from aiogram.fsm.context import FSMContext

from app.core.constants import STORES_PER_PAGE
from app.core.utils import normalize_city
from app.keyboards import business_type_keyboard, offers_category_filter
from app.keyboards import offers as offer_keyboards
from app.services.offer_service import OfferDetails, OfferListItem, OfferService
from app.templates import offers as offer_templates
from handlers.common import BrowseOffers
from handlers.common.utils import safe_delete_message, safe_edit_message
from localization import get_product_categories, get_text

from .browse_helpers import (
    callback_message as _callback_message,
)
from .browse_helpers import (
    invalid_number_text as _invalid_number_text,
)
from .browse_helpers import (
    no_stores_text as _no_stores_text,
)
from .browse_helpers import (
    range_text as _range_text,
)

_CATEGORY_IDS = ["bakery", "dairy", "meat", "fruits", "vegetables", "drinks", "snacks", "frozen"]


def _category_label(lang: str, category: str) -> str:
    if category == "all":
        return "Все товары" if lang == "ru" else "Barcha mahsulotlar"
    categories = get_product_categories(lang)
    mapping = dict(zip(_CATEGORY_IDS, categories))
    return mapping.get(category, category.replace("_", " ").title())


def _format_money(value: float | int) -> str:
    return f"{int(value):,}".replace(",", " ")


def _short_title(title: str, limit: int = 26) -> str:
    cleaned = title or ""
    if cleaned.startswith("Пример:"):
        cleaned = cleaned[7:].strip()
    return cleaned if len(cleaned) <= limit else f"{cleaned[: limit - 2]}.."


def _offer_price_line(offer: OfferDetails | OfferListItem, lang: str) -> str:
    currency = "so'm" if lang == "uz" else "сум"
    current = getattr(offer, "discount_price", 0) or getattr(offer, "price", 0) or 0
    original = getattr(offer, "original_price", 0) or 0
    if original and original > current:
        discount_pct = round((1 - current / original) * 100)
        discount_pct = min(99, max(1, discount_pct))
        return f"💰 {_format_money(current)} {currency} (-{discount_pct}%)"
    return f"💰 {_format_money(current)} {currency}"


def register_stores(
    dp: Dispatcher,
    db: Any,
    offer_service: OfferService,
    logger: Any,
) -> None:
    """Register store and store-offer related handlers on dispatcher."""

    @dp.callback_query(F.data.startswith("biztype_"))
    async def business_type_selected(callback: types.CallbackQuery, state: FSMContext) -> None:
        if not callback.from_user:
            await callback.answer()
            return
        msg = _callback_message(callback)
        if not msg:
            await callback.answer()
            return
        lang = db.get_user_language(callback.from_user.id)
        user = db.get_user_model(callback.from_user.id)
        if not user:
            await callback.answer(get_text(lang, "error"))
            return
        data = callback.data or ""
        business_type = data.replace("biztype_", "")
        city = user.city or "Ташкент"
        region = getattr(user, "region", None)
        district = getattr(user, "district", None)
        latitude = getattr(user, "latitude", None)
        longitude = getattr(user, "longitude", None)
        search_city = normalize_city(city)
        search_region = normalize_city(region) if region else None
        search_district = normalize_city(district) if district else None

        logger.info(
            f"🏪 Browse stores: business_type={business_type}, user_city={city}, search_city={search_city}"
        )

        stores = offer_service.list_stores_by_type(
            search_city,
            business_type,
            region=search_region,
            district=search_district,
            latitude=latitude,
            longitude=longitude,
        )

        logger.info(f"🏪 Found {len(stores)} stores for {business_type} in {search_city}")

        if not stores:
            if not await safe_edit_message(msg, _no_stores_text(lang, business_type)):
                await safe_delete_message(msg)
                await msg.answer(_no_stores_text(lang, business_type))
            await callback.answer()
            return
        await state.set_state(BrowseOffers.store_list)
        # Save store list and business type for pagination
        await state.update_data(
            store_list=[store.id for store in stores],
            current_business_type=business_type,
            store_list_page=0,
        )
        text = offer_templates.render_business_type_store_list(lang, business_type, city, stores, page=0, per_page=STORES_PER_PAGE)
        # Compact keyboard with pagination
        keyboard = offer_keyboards.store_list_keyboard(lang, stores, page=0)
        if not await safe_edit_message(msg, text, reply_markup=keyboard):
            await safe_delete_message(msg)
            await msg.answer(text, parse_mode="HTML", reply_markup=keyboard)
        await callback.answer()

    @dp.callback_query(F.data.startswith("select_store_"))
    async def select_store_callback(callback: types.CallbackQuery, state: FSMContext) -> None:
        """Select store by inline button - show store info."""
        if not callback.from_user or not callback.data:
            await callback.answer()
            return
        msg = _callback_message(callback)
        if not msg:
            await callback.answer()
            return
        lang = db.get_user_language(callback.from_user.id)

        try:
            store_id = int(callback.data.split("_")[-1])
        except (ValueError, IndexError):
            await callback.answer(get_text(lang, "error"), show_alert=True)
            return

        await state.set_state(None)

        # Get store info and show full card
        store = offer_service.get_store(store_id)
        if not store:
            await callback.answer(
                "Магазин не найден" if lang == "ru" else "Do'kon topilmadi",
                show_alert=True,
            )
            return

        # Render full store card
        text = offer_templates.render_store_card(lang, store)
        keyboard = offer_keyboards.store_card_keyboard(
            lang,
            store_id,
            store.offers_count,
            store.ratings_count,
            back_callback="back_to_store_list",
        )

        # Try to get photo from raw store data
        photo = None
        try:
            raw_store = db.get_store(store_id) if db else None
            if isinstance(raw_store, dict):
                photo = raw_store.get("photo") or raw_store.get("photo_id")
        except Exception:
            photo = None

        if photo:
            try:
                await msg.answer_photo(
                    photo=photo, caption=text, parse_mode="HTML", reply_markup=keyboard
                )
                await safe_delete_message(msg)
                await callback.answer()
                return
            except Exception:
                pass

        if not await safe_edit_message(msg, text, reply_markup=keyboard):
            await safe_delete_message(msg)
            await msg.answer(text, parse_mode="HTML", reply_markup=keyboard)
        await callback.answer()

    @dp.message(BrowseOffers.store_list, F.text.regexp(r"^\d+$"))
    async def select_store_by_number(message: types.Message, state: FSMContext) -> None:
        """Select store by number - show categories directly."""
        if not message.from_user:
            return
        lang = db.get_user_language(message.from_user.id)
        data = await state.get_data()
        store_list: list[int] = data.get("store_list", [])
        if not store_list:
            await message.answer(get_text(lang, "error"))
            await state.clear()
            return
        try:
            if not message.text:
                await message.answer(_invalid_number_text(lang, "магазина"))
                return
            number = int(message.text)
        except ValueError:
            await message.answer(_invalid_number_text(lang, "магазина"))
            return
        if number < 1 or number > len(store_list):
            await message.answer(_range_text(lang, len(store_list), "магазина"))
            return
        store_id = store_list[number - 1]
        await state.set_state(None)

        # Get store info
        store = offer_service.get_store(store_id)
        if not store:
            await message.answer("Магазин не найден" if lang == "ru" else "Do'kon topilmadi")
            return

        # Show category selection directly
        text = f"🏪 <b>{store.name}</b>\n\n📂 {get_text(lang, 'select_category_in_store')}"

        keyboard = offers_category_filter(
            lang,
            store_id=store_id,
            include_back=True,
            back_callback=f"store_card_back_{store_id}",
        )

        await message.answer(text, parse_mode="HTML", reply_markup=keyboard)

    @dp.callback_query(F.data.startswith("filter_store_"))
    async def filter_offers_by_store(callback: types.CallbackQuery, state: FSMContext) -> None:
        if not callback.from_user or not callback.data:
            await callback.answer()
            return
        msg = _callback_message(callback)
        if not msg:
            await callback.answer()
            return
        lang = db.get_user_language(callback.from_user.id)

        try:
            store_id = int(callback.data.split("_")[-1])
        except (ValueError, IndexError) as e:
            logger.error(f"Invalid store_id in callback data: {callback.data}, error: {e}")
            await callback.answer(get_text(lang, "error"), show_alert=True)
            return

        store = offer_service.get_store(store_id)
        if not store:
            await callback.answer("× Магазин не найден", show_alert=True)
            return

        # Save store_id to state so we can filter by category later
        await state.update_data(viewing_store_id=store_id)

        # The user flow: Store -> Category -> Offers
        header = (
            f"<b>{store.name}</b>\n"
            f"{store.address or ''}\n\n"
            f"{get_text(lang, 'select_category_in_store')}"
        )

        await msg.edit_text(
            header,
            parse_mode="HTML",
            reply_markup=offers_category_filter(
                lang,
                store_id=store_id,
                include_back=True,
                back_callback=f"store_card_back_{store_id}",
            ),
        )
        # Do NOT show offers list immediately

    @dp.callback_query(F.data.startswith("store_info_"))
    async def show_store_info(callback: types.CallbackQuery) -> None:
        """Show full store information card with photo."""
        if not callback.from_user or not callback.data:
            await callback.answer()
            return
        msg = _callback_message(callback)
        if not msg:
            await callback.answer()
            return
        lang = db.get_user_language(callback.from_user.id)

        try:
            store_id = int(callback.data.split("_")[-1])
        except (ValueError, IndexError) as e:
            logger.error(f"Invalid store_id in callback data: {callback.data}, error: {e}")
            await callback.answer(get_text(lang, "error"), show_alert=True)
            return

        # Use offer_service for structured store details
        store = offer_service.get_store(store_id)
        if not store:
            await callback.answer(
                "Магазин не найден" if lang == "ru" else "Do'kon topilmadi",
                show_alert=True,
            )
            return

        # Render full store card with all details
        text = offer_templates.render_store_card(lang, store)
        keyboard = offer_keyboards.store_card_keyboard(
            lang,
            store_id,
            store.offers_count,
            store.ratings_count,
            back_callback="back_to_store_list",
        )

        # Try to get photo from raw store data
        photo = None
        try:
            raw_store = db.get_store(store_id) if db else None
            if isinstance(raw_store, dict):
                photo = raw_store.get("photo") or raw_store.get("photo_id")
        except Exception:
            photo = None

        # Send with photo if available
        if photo:
            try:
                await msg.answer_photo(
                    photo=photo, caption=text, parse_mode="HTML", reply_markup=keyboard
                )
                await safe_delete_message(msg)
                await callback.answer()
                return
            except Exception:
                # Fall back to text if photo fails
                pass

        if not await safe_edit_message(msg, text, reply_markup=keyboard):
            await safe_delete_message(msg)
            await msg.answer(text, parse_mode="HTML", reply_markup=keyboard)
        await callback.answer()

    @dp.callback_query(F.data.startswith("store_card_back_"))
    async def store_card_back(callback: types.CallbackQuery) -> None:
        """Return to store card from category selection."""
        if not callback.from_user or not callback.data:
            await callback.answer()
            return
        msg = _callback_message(callback)
        if not msg:
            await callback.answer()
            return
        lang = db.get_user_language(callback.from_user.id)

        try:
            store_id = int(callback.data.split("_")[-1])
        except (ValueError, IndexError) as e:
            logger.error(f"Invalid store_id in callback data: {callback.data}, error: {e}")
            await callback.answer(get_text(lang, "error"), show_alert=True)
            return

        store = offer_service.get_store(store_id)
        if not store:
            await callback.answer(get_text(lang, "error"), show_alert=True)
            return

        text = offer_templates.render_store_card(lang, store)
        keyboard = offer_keyboards.store_card_keyboard(
            lang,
            store_id,
            store.offers_count,
            store.ratings_count,
            back_callback="back_to_store_list",
        )
        photo = None
        try:
            raw_store = db.get_store(store_id) if db else None
            if isinstance(raw_store, dict):
                photo = raw_store.get("photo") or raw_store.get("photo_id")
        except Exception:
            photo = None

        if photo:
            try:
                await msg.answer_photo(
                    photo=photo, caption=text, parse_mode="HTML", reply_markup=keyboard
                )
                await safe_delete_message(msg)
                await callback.answer()
                return
            except Exception:
                pass

        if not await safe_edit_message(msg, text, reply_markup=keyboard):
            await safe_delete_message(msg)
            await msg.answer(text, parse_mode="HTML", reply_markup=keyboard)
        await callback.answer()

    @dp.callback_query(F.data.regexp(r"^store_offers_\d+$"))
    async def show_store_offers(callback: types.CallbackQuery, state: FSMContext) -> None:
        if not callback.from_user or not callback.data:
            await callback.answer()
            return
        msg = _callback_message(callback)
        if not msg:
            await callback.answer()
            return
        lang = db.get_user_language(callback.from_user.id)

        try:
            store_id = int(callback.data.split("_")[-1])
        except (ValueError, IndexError) as e:
            logger.error(f"Invalid store_id in callback data: {callback.data}, error: {e}")
            await callback.answer(get_text(lang, "error"), show_alert=True)
            return

        store = offer_service.get_store(store_id)
        if not store:
            await callback.answer(
                "Магазин не найден" if lang == "ru" else "Do'kon topilmadi",
                show_alert=True,
            )
            return

        # Show category selection for store
        text = f"🏪 <b>{store.name}</b>\n\n📂 {get_text(lang, 'select_category_in_store')}"

        keyboard = offers_category_filter(
            lang,
            store_id=store_id,
            include_back=True,
            back_callback=f"store_card_back_{store_id}",
        )

        if getattr(msg, "photo", None):
            await safe_delete_message(msg)
            await msg.answer(text, parse_mode="HTML", reply_markup=keyboard)
            await callback.answer()
            return

        if not await safe_edit_message(msg, text, reply_markup=keyboard):
            await safe_delete_message(msg)
            await msg.answer(text, parse_mode="HTML", reply_markup=keyboard)
        await callback.answer()

    @dp.callback_query(F.data.startswith("store_cat_"))
    async def show_store_offers_by_category(
        callback: types.CallbackQuery,
        state: FSMContext,
    ) -> None:
        """Show store offers filtered by category."""
        if not callback.from_user or not callback.data:
            await callback.answer()
            return
        msg = _callback_message(callback)
        if not msg:
            await callback.answer()
            return
        lang = db.get_user_language(callback.from_user.id)

        try:
            # Parse: store_cat_{store_id}_{category}
            parts = callback.data.split("_", 3)  # Split into max 4 parts
            store_id = int(parts[2])
            category = parts[3] if len(parts) > 3 else "all"
        except (ValueError, IndexError) as e:
            logger.error(f"Invalid callback data: {callback.data}, error: {e}")
            await callback.answer(get_text(lang, "error"), show_alert=True)
            return

        store = offer_service.get_store(store_id)
        if not store:
            await callback.answer(
                "Магазин не найден" if lang == "ru" else "Do'kon topilmadi",
                show_alert=True,
            )
            return

        # Get all offers for the store
        all_offers = offer_service.list_store_offers(store_id)

        # Filter by category if not "all"
        if category != "all":
            # Map display category to database category value
            category_map = {
                "bakery": "bakery",
                "dairy": "dairy",
                "meat": "meat",
                "fruits": "fruits",
                "vegetables": "vegetables",
                "drinks": "drinks",
                "snacks": "snacks",
                "frozen": "frozen",
            }
            db_category = category_map.get(category, category)

            # Filter offers by their category field
            offers = []
            for offer in all_offers:
                if offer.category == db_category:
                    offers.append(offer)
        else:
            offers = all_offers

        if not offers:
            await callback.answer(
                "В этой категории пока нет товаров"
                if lang == "ru"
                else "Bu toifada hali mahsulotlar yo'q",
                show_alert=True,
            )
            return

        await _send_store_offers_list(
            msg,
            state,
            lang,
            store,
            offers,
            page=0,
            edit_message=True,
            category=category,
        )
        await callback.answer()

    @dp.callback_query(F.data.startswith("store_offers_page_"))
    async def store_offers_page_handler(callback: types.CallbackQuery, state: FSMContext) -> None:
        """Handle store offers pagination with compact view."""
        if not callback.from_user or not callback.data:
            await callback.answer()
            return
        msg = _callback_message(callback)
        if not msg:
            await callback.answer()
            return
        lang = db.get_user_language(callback.from_user.id)

        try:
            # Parse: store_offers_page_{store_id}_{page}
            parts = callback.data.split("_")
            store_id = int(parts[3])
            page = int(parts[4])
        except (ValueError, IndexError) as e:
            logger.error(f"Invalid pagination data: {callback.data}, error: {e}")
            await callback.answer(get_text(lang, "error"), show_alert=True)
            return

        store = offer_service.get_store(store_id)
        if not store:
            await callback.answer("Магазин не найден", show_alert=True)
            return

        # Get stored category from state
        data = await state.get_data()
        category = data.get("store_category", "all")

        # Get all offers for the store
        all_offers = offer_service.list_store_offers(store_id)

        # Filter by category if not "all"
        if category != "all":
            category_map = {
                "bakery": "bakery",
                "dairy": "dairy",
                "meat": "meat",
                "fruits": "fruits",
                "vegetables": "vegetables",
                "drinks": "drinks",
                "snacks": "snacks",
                "frozen": "frozen",
            }
            db_category = category_map.get(category, category)
            offers = [offer for offer in all_offers if offer.category == db_category]
        else:
            offers = all_offers

        await _send_store_offers_list(
            msg,
            state,
            lang,
            store,
            offers,
            page=page,
            edit_message=True,
            category=category,
        )
        await callback.answer()

    @dp.callback_query(F.data.startswith("store_offer_"))
    async def store_offer_select_handler(callback: types.CallbackQuery, state: FSMContext) -> None:
        """Handle store offer selection - show offer card with cart controls."""
        if not callback.from_user or not callback.message:
            await callback.answer()
            return

        lang = db.get_user_language(callback.from_user.id)
        user_id = callback.from_user.id

        try:
            # Parse: store_offer_{store_id}_{offer_id}
            parts = callback.data.split("_")
            store_id = int(parts[2])
            offer_id = int(parts[3])
        except (ValueError, IndexError) as e:
            logger.error(f"Invalid offer data: {callback.data}, error: {e}")
            await callback.answer(get_text(lang, "error"), show_alert=True)
            return

        # Get offer details
        offer = offer_service.get_offer_details(offer_id)
        if not offer:
            not_found = "Mahsulot topilmadi" if lang == "uz" else "Товар не найден"
            await callback.answer(not_found, show_alert=True)
            return

        # Save store context for returning
        data = await state.get_data()
        await state.update_data(
            last_store_id=store_id,
            last_store_page=data.get("store_offers_page", 0),
            last_store_category=data.get("store_category", "all"),
            source="store",
            store_id=store_id,
        )

        # Get store info
        store = offer_service.get_store(offer.store_id) if offer.store_id else None

        max_quantity = offer.quantity or 0
        if max_quantity <= 0:
            sold_out = "Mahsulot tugadi" if lang == "uz" else "Товар закончился"
            await callback.answer(sold_out, show_alert=True)
            return

        delivery_enabled = store.delivery_enabled if store else False
        text = offer_templates.render_offer_details(lang, offer, store)

        # Use cart keyboard
        kb = offer_keyboards.offer_details_with_back_keyboard(
            lang,
            offer_id,
            offer.store_id,
            delivery_enabled,
            back_callback=f"back_to_store_offers_{store_id}",
        )

        # Get message to respond to
        msg = _callback_message(callback)
        if not msg:
            await callback.answer()
            return

        # Send offer card - keep one active message
        if getattr(offer, "photo", None):
            try:
                await msg.answer_photo(
                    photo=offer.photo,
                    caption=text,
                    parse_mode="HTML",
                    reply_markup=kb,
                )
                await safe_delete_message(msg)
                await callback.answer()
                return
            except Exception:
                pass

        if not await safe_edit_message(msg, text, reply_markup=kb):
            await safe_delete_message(msg)
            await msg.answer(text, parse_mode="HTML", reply_markup=kb)
        await callback.answer()

    @dp.callback_query(F.data.startswith("back_to_store_offers_"))
    async def back_to_store_offers(callback: types.CallbackQuery, state: FSMContext) -> None:
        if not callback.from_user or not callback.data:
            await callback.answer()
            return
        msg = _callback_message(callback)
        if not msg:
            await callback.answer()
            return
        lang = db.get_user_language(callback.from_user.id)

        try:
            store_id = int(callback.data.split("_")[-1])
        except (ValueError, IndexError) as e:
            logger.error(f"Invalid store_id in callback data: {callback.data}, error: {e}")
            await callback.answer(get_text(lang, "error"), show_alert=True)
            return

        store = offer_service.get_store(store_id)
        if not store:
            await callback.answer("РњР°РіР°Р·РёРЅ РЅРµ РЅР°Р№РґРµРЅ", show_alert=True)
            return

        data = await state.get_data()
        category = data.get("store_category", "all")
        page = data.get("store_offers_page", 0)

        all_offers = offer_service.list_store_offers(store_id)
        if category != "all":
            category_map = {
                "bakery": "bakery",
                "dairy": "dairy",
                "meat": "meat",
                "fruits": "fruits",
                "vegetables": "vegetables",
                "drinks": "drinks",
                "snacks": "snacks",
                "frozen": "frozen",
            }
            db_category = category_map.get(category, category)
            offers = [offer for offer in all_offers if offer.category == db_category]
        else:
            offers = all_offers

        if getattr(msg, "photo", None):
            await safe_delete_message(msg)
            await _send_store_offers_list(
                msg,
                state,
                lang,
                store,
                offers,
                page=page,
                edit_message=False,
                category=category,
            )
        else:
            await _send_store_offers_list(
                msg,
                state,
                lang,
                store,
                offers,
                page=page,
                edit_message=True,
                category=category,
            )
        await callback.answer()

    @dp.callback_query(F.data.startswith("store_offers_next_"))
    async def store_offers_pagination(callback: types.CallbackQuery, state: FSMContext) -> None:
        if not callback.from_user or not callback.data:
            await callback.answer()
            return
        msg = _callback_message(callback)
        if not msg:
            await callback.answer()
            return
        lang = db.get_user_language(callback.from_user.id)

        try:
            parts = callback.data.split("_")
            store_id = int(parts[3])
            offset = int(parts[4])
        except (ValueError, IndexError) as e:
            logger.error(f"Invalid pagination data in callback: {callback.data}, error: {e}")
            await callback.answer(get_text(lang, "error"), show_alert=True)
            return

        store = offer_service.get_store(store_id)
        if not store:
            await callback.answer("Магазин не найден", show_alert=True)
            return
        data = await state.get_data()
        category = data.get("store_category", "all")
        all_offers = offer_service.list_store_offers(store_id)

        if category != "all":
            category_map = {
                "bakery": "bakery",
                "dairy": "dairy",
                "meat": "meat",
                "fruits": "fruits",
                "vegetables": "vegetables",
                "drinks": "drinks",
                "snacks": "snacks",
                "frozen": "frozen",
            }
            db_category = category_map.get(category, category)
            offers = [offer for offer in all_offers if offer.category == db_category]
        else:
            offers = all_offers

        if offset >= len(offers):
            await callback.answer(
                "Больше товаров нет" if lang == "ru" else "Boshqa mahsulotlar yo'q",
                show_alert=True,
            )
            return

        items_per_page = 10
        page = max(0, offset // items_per_page)
        await _send_store_offers_list(
            msg,
            state,
            lang,
            store,
            offers,
            page=page,
            edit_message=True,
            category=category,
        )
        await callback.answer()

    @dp.callback_query(F.data.startswith("store_reviews_"))
    async def show_store_reviews(callback: types.CallbackQuery) -> None:
        if not callback.from_user or not callback.data:
            await callback.answer()
            return
        msg = _callback_message(callback)
        if not msg:
            await callback.answer()
            return
        lang = db.get_user_language(callback.from_user.id)

        try:
            store_id = int(callback.data.split("_")[-1])
        except (ValueError, IndexError) as e:
            logger.error(f"Invalid store_id in callback data: {callback.data}, error: {e}")
            await callback.answer(get_text(lang, "error"), show_alert=True)
            return

        store = offer_service.get_store(store_id)
        if not store:
            await callback.answer("Магазин не найден", show_alert=True)
            return
        avg_rating, reviews = offer_service.get_store_reviews(store_id)
        text = offer_templates.render_store_reviews(lang, store.name, avg_rating, reviews)
        keyboard = offer_keyboards.store_reviews_keyboard(lang, store_id)
        if not await safe_edit_message(msg, text, reply_markup=keyboard):
            await safe_delete_message(msg)
            await msg.answer(text, parse_mode="HTML", reply_markup=keyboard)
        await callback.answer()

    @dp.callback_query(F.data.regexp(r"^back_to_store_\d+$"))
    async def back_to_store_card(callback: types.CallbackQuery) -> None:
        """Return to store - show categories instead of card."""
        if not callback.from_user or not callback.data:
            await callback.answer()
            return
        msg = _callback_message(callback)
        if not msg:
            await callback.answer()
            return
        lang = db.get_user_language(callback.from_user.id)

        try:
            store_id = int(callback.data.split("_")[-1])
        except (ValueError, IndexError) as e:
            logger.error(f"Invalid store_id in callback data: {callback.data}, error: {e}")
            await callback.answer(get_text(lang, "error"), show_alert=True)
            return

        # Get store and show categories
        store = offer_service.get_store(store_id)
        if not store:
            logger.warning(f"Store {store_id} not found in back_to_store_card")
            await callback.answer(
                "Магазин не найден" if lang == "ru" else "Do'kon topilmadi", show_alert=True
            )
            return

        # Show category selection
        text = f"🏪 <b>{store.name}</b>\n\n📂 {get_text(lang, 'select_category_in_store')}"

        keyboard = offers_category_filter(
            lang,
            store_id=store_id,
            include_back=True,
            back_callback=f"store_card_back_{store_id}",
        )

        if getattr(msg, "photo", None):
            await safe_delete_message(msg)
            await msg.answer(text, parse_mode="HTML", reply_markup=keyboard)
            await callback.answer()
            return

        if not await safe_edit_message(msg, text, reply_markup=keyboard):
            await safe_delete_message(msg)
            await msg.answer(text, parse_mode="HTML", reply_markup=keyboard)
        await callback.answer()

    @dp.callback_query(F.data == "back_to_store_list")
    async def back_to_store_list(callback: types.CallbackQuery, state: FSMContext) -> None:
        if not callback.from_user:
            await callback.answer()
            return
        msg = _callback_message(callback)
        if not msg:
            await callback.answer()
            return
        lang = db.get_user_language(callback.from_user.id)
        data = await state.get_data()

        store_ids = data.get("store_list", [])
        business_type = data.get("current_business_type", "")
        page = int(data.get("store_list_page", 0) or 0)

        user = db.get_user_model(callback.from_user.id)
        city = user.city if user else "Ташкент"

        stores = []
        for sid in store_ids:
            store = offer_service.get_store(sid)
            if store:
                stores.append(store)

        if not stores:
            text = get_text(lang, "browse_by_business_type")
            keyboard = business_type_keyboard(
                lang, include_back=True, back_callback="hot_entry_back"
            )
            if getattr(msg, "photo", None):
                await safe_delete_message(msg)
                await msg.answer(text, parse_mode="HTML", reply_markup=keyboard)
            else:
                if not await safe_edit_message(msg, text, reply_markup=keyboard):
                    await safe_delete_message(msg)
                    await msg.answer(text, parse_mode="HTML", reply_markup=keyboard)
            await callback.answer()
            return

        text = offer_templates.render_business_type_store_list(lang, business_type, city, stores, page=page, per_page=STORES_PER_PAGE)
        keyboard = offer_keyboards.store_list_keyboard(lang, stores, page=page)

        if getattr(msg, "photo", None):
            await safe_delete_message(msg)
            await msg.answer(text, parse_mode="HTML", reply_markup=keyboard)
        else:
            if not await safe_edit_message(msg, text, reply_markup=keyboard):
                await safe_delete_message(msg)
                await msg.answer(text, parse_mode="HTML", reply_markup=keyboard)
        await callback.answer()

    @dp.callback_query(F.data == "back_to_places")
    async def back_to_places_menu(callback: types.CallbackQuery) -> None:
        if not callback.from_user:
            await callback.answer()
            return
        lang = db.get_user_language(callback.from_user.id)
        msg = _callback_message(callback)
        if not msg:
            await callback.answer()
            return
        text = get_text(lang, "browse_by_business_type")
        keyboard = business_type_keyboard(
            lang, include_back=True, back_callback="hot_entry_back"
        )
        if not await safe_edit_message(msg, text, reply_markup=keyboard):
            await safe_delete_message(msg)
            await msg.answer(text, parse_mode="HTML", reply_markup=keyboard)
        await callback.answer()

    @dp.callback_query(F.data.startswith("stores_page_"))
    async def stores_page_handler(callback: types.CallbackQuery, state: FSMContext) -> None:
        """Handle store list pagination."""
        if not callback.from_user or not callback.data:
            await callback.answer()
            return
        msg = _callback_message(callback)
        if not msg:
            await callback.answer()
            return

        lang = db.get_user_language(callback.from_user.id)

        try:
            page = int(callback.data.split("_")[-1])
        except (ValueError, IndexError):
            await callback.answer()
            return

        # Get stored data
        data = await state.get_data()
        store_ids = data.get("store_list", [])
        business_type = data.get("current_business_type", "")

        if not store_ids:
            await callback.answer()
            return

        user = db.get_user_model(callback.from_user.id)
        city = user.city if user else "Ташкент"

        # Get stores
        stores = []
        for sid in store_ids:
            store = offer_service.get_store(sid)
            if store:
                stores.append(store)

        if not stores:
            await callback.answer()
            return

        # Render with new page
        text = offer_templates.render_business_type_store_list(lang, business_type, city, stores, page=page, per_page=STORES_PER_PAGE)
        keyboard = offer_keyboards.store_list_keyboard(lang, stores, page=page)
        await state.update_data(store_list_page=page)

        if not await safe_edit_message(msg, text, reply_markup=keyboard):
            await safe_delete_message(msg)
            await msg.answer(text, parse_mode="HTML", reply_markup=keyboard)

        await callback.answer()

    @dp.callback_query(F.data == "stores_noop")
    async def stores_noop_handler(callback: types.CallbackQuery) -> None:
        """Handle noop button (page indicator)."""
        await callback.answer()

    # ------------------------------------------------------------------
    # Helper closures (store-only)
    # ------------------------------------------------------------------

    async def _send_store_offers_list(
        target: types.Message,
        state: FSMContext,
        lang: str,
        store: Any,
        offers: list[OfferDetails] | list[OfferListItem] | list[Any],
        page: int = 0,
        edit_message: bool = False,
        category: str = "all",
    ) -> None:
        """Send store offers with compact list and inline buttons (like hot offers)."""
        ITEMS_PER_PAGE = 10
        try:
            store_id = store.id
            total_offers = len(offers)

            if total_offers == 0:
                await target.answer(
                    "В этом магазине пока нет товаров"
                    if lang == "ru"
                    else "Bu do'konda hali mahsulotlar yo'q",
                    parse_mode="HTML",
                )
                return

            offset = page * ITEMS_PER_PAGE
            page_offers = offers[offset : offset + ITEMS_PER_PAGE]

            await state.set_state(BrowseOffers.offer_list)
            await state.update_data(
                offer_list=[offer.id for offer in page_offers],
                store_offers_page=page,
                store_offers_offset=offset,
                current_store_id=store_id,
                store_category=category,
            )
            total_pages = max(1, (total_offers + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE)
            page_label = "Стр." if lang == "ru" else "Sah."
            category_title = _category_label(lang, category)

            total_label = "Всего" if lang == "ru" else "Jami"
            lines = [
                f"🏪 <b>{store.name}</b>",
                f"{category_title} | {page_label} {page + 1}/{total_pages} | {total_label} {total_offers}",
            ]

            for idx, offer in enumerate(page_offers, start=1):
                title = _short_title(offer.title, limit=28)
                price_line = _offer_price_line(offer, lang)
                lines.append(f"{idx}. <b>{title}</b> - {price_line}")

            text = "\n".join(lines).rstrip()

            # Build keyboard with offer buttons
            keyboard = offer_keyboards.store_offers_compact_keyboard(
                lang, page_offers, store_id, page, total_pages
            )

            if edit_message:
                if not await safe_edit_message(target, text, reply_markup=keyboard):
                    await safe_delete_message(target)
                    await target.answer(text, parse_mode="HTML", reply_markup=keyboard)
            else:
                await target.answer(text, parse_mode="HTML", reply_markup=keyboard)

        except Exception as exc:  # pragma: no cover
            logger.error("Failed to send store offers: %s", exc)
            await target.answer(f"😔 {get_text(lang, 'error')}")

    async def _set_offer_state(state: FSMContext, offers: list[OfferListItem]) -> None:
        offer_ids = [offer.id for offer in offers]
        logger.info(
            f"📝 Setting FSM state BrowseOffers.offer_list with {len(offer_ids)} offers: {offer_ids[:5]}..."
        )
        await state.set_state(BrowseOffers.offer_list)
        await state.update_data(offer_list=offer_ids)
        # Verify state was set
        current_state = await state.get_state()
        current_data = await state.get_data()
        logger.info(
            f"📝 FSM state after set: state={current_state}, data_keys={list(current_data.keys())}"
        )

