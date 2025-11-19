"""Search handlers."""
from __future__ import annotations

from aiogram import F, Router, types
from aiogram.fsm.context import FSMContext

from app.keyboards import main_menu_customer, search_cancel_keyboard, offer_quick_keyboard
from app.services.offer_service import OfferService
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
            # We need to send offer card. 
            # Since we don't have access to _send_offer_card from here easily without importing,
            # let's use a simplified version or import it if possible.
            # Better to use the same format as in offers.py
            
            # Construct caption
            price_line = (
                f"<s>{offer.original_price:,.0f}</s> ➡️ <b>{offer.discount_price:,.0f} UZS</b>"
                if offer.original_price > offer.discount_price
                else f"<b>{offer.discount_price:,.0f} UZS</b>"
            )
            
            caption = (
                f"<b>{offer.title}</b>\n"
                f"🏪 {offer.store_name}\n"
                f"{price_line}\n"
                f"📦 {offer.quantity} {offer.unit}\n"
                f"🕒 {offer.expiry_date}"
            )
            
            keyboard = offer_quick_keyboard(
                lang, 
                offer.id, 
                offer.store_id, 
                offer.delivery_enabled
            )
            
            await message.answer(caption, parse_mode="HTML", reply_markup=keyboard)

