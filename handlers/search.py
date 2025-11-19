"""Search handlers."""
from __future__ import annotations

from aiogram import F, Router, types
from aiogram.fsm.context import FSMContext

from app.keyboards import main_menu_customer, search_cancel_keyboard, offer_quick_keyboard
from app.services.offer_service import OfferService
from app.templates.offers import render_offer_card
from database_protocol import DatabaseProtocol
from handlers.common_states.states import Search
from localization import get_text

router = Router()

def setup(
    dp: Router,
    db: DatabaseProtocol,
    offer_service: OfferService,
) -> None:
    """Register search handlers."""
    
    @dp.message(F.text.in_(["🔍 Поиск", "🔍 Qidirish"]))
    async def start_search(message: types.Message, state: FSMContext):
        """Start search flow."""
        lang = db.get_user_language(message.from_user.id)
        
        await state.set_state(Search.query)
        await message.answer(
            get_text(lang, "enter_search_query"),
            reply_markup=search_cancel_keyboard(lang)
        )

    @dp.message(Search.query)
    async def process_search_query(message: types.Message, state: FSMContext):
        """Process search query."""
        lang = db.get_user_language(message.from_user.id)
        
        # Handle cancellation
        if message.text in ["Отмена", "Bekor qilish", "❌ Отмена", "❌ Bekor qilish"]:
            await state.clear()
            await message.answer(
                get_text(lang, "action_cancelled"),
                reply_markup=main_menu_customer(lang)
            )
            return
            
        query = message.text
        if len(query) < 2:
            await message.answer(
                "Введите минимум 2 символа" if lang == "ru" else "Kamida 2 ta belgi kiriting"
            )
            return
            
        # Perform search
        user = db.get_user_model(message.from_user.id)
        city = user.city if user else None
        
        results = offer_service.search_offers(query, city)
        
        if not results:
            await message.answer(get_text(lang, "no_results"))
            return
            
        await message.answer(
            f"{get_text(lang, 'search_results')} {len(results)}",
            reply_markup=main_menu_customer(lang)
        )
        await state.clear()
        
        # Show results (limit to 10)
        for offer in results[:10]:
            # Construct caption using template
            caption = render_offer_card(lang, offer)
            
            keyboard = offer_quick_keyboard(
                lang, 
                offer.id, 
                offer.store_id, 
                offer.delivery_enabled
            )
            
            if offer.photo:
                try:
                    await message.answer_photo(
                        photo=offer.photo,
                        caption=caption,
                        parse_mode="HTML",
                        reply_markup=keyboard
                    )
                except Exception:
                    # Fallback if photo is invalid
                    await message.answer(caption, parse_mode="HTML", reply_markup=keyboard)
            else:
                await message.answer(caption, parse_mode="HTML", reply_markup=keyboard)

