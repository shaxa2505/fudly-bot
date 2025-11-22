"""
Help and FAQ handler - explains how Fudly works
"""
from aiogram import Router, F, types
from aiogram.filters import Command
from database_protocol import DatabaseProtocol
from localization import get_text
from handlers.common import user_view_mode

router = Router()


def setup(dp_or_router, db, get_text):
    """Setup help handler with dependencies"""
    pass


@router.message(F.text.in_(["❓ Как это работает", "❓ Qanday ishlaydi"]))
@router.message(Command("help"))
async def show_help(message: types.Message, db: DatabaseProtocol):
    """Show help information based on current user mode"""
    user_id = message.from_user.id
    lang = db.get_user_language(user_id)
    user = db.get_user_model(user_id)
    
    # Check current view mode (partner can switch to customer mode)
    current_mode = user_view_mode.get(user_id, 'customer')
    
    # Show help based on current mode, not just role
    if user and user.role == 'seller' and current_mode == 'seller':
        help_text = get_text(lang, 'help_partner')
    else:
        help_text = get_text(lang, 'help_customer')
    
    await message.answer(help_text, parse_mode='HTML')
