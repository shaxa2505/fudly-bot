"""
Help and FAQ handler - explains how Fudly works
"""
from aiogram import Router, F, types
from aiogram.filters import Command
from database_protocol import DatabaseProtocol
from localization import get_text

router = Router()


def setup(dp_or_router, db, get_text):
    """Setup help handler with dependencies"""
    pass


@router.message(F.text.in_(["❓ Как это работает", "❓ Qanday ishlaydi"]))
@router.message(Command("help"))
async def show_help(message: types.Message, db: DatabaseProtocol):
    """Show help information based on user role"""
    user_id = message.from_user.id
    lang = db.get_user_language(user_id)
    user = db.get_user_model(user_id)
    
    # Determine if user is a partner
    is_partner = False
    if user and user.role == 'seller':
        stores = db.get_stores_by_owner(user_id)
        is_partner = len(stores) > 0
    
    if is_partner:
        # Partner help
        help_text = get_text(lang, 'help_partner')
    else:
        # Customer help
        help_text = get_text(lang, 'help_customer')
    
    await message.answer(help_text, parse_mode='HTML')
