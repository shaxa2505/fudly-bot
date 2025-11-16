"""Quick test for switch_to_customer callback."""
import asyncio
from aiogram import Bot, Dispatcher, types
from aiogram.fsm.storage.memory import MemoryStorage
from unittest.mock import AsyncMock, MagicMock

from app.core.config import load_settings
from handlers.user import profile
from database import Database

async def test_switch_to_customer():
    """Test the switch_to_customer_cb handler."""
    print("🧪 Testing switch_to_customer callback handler\n")
    
    # Setup
    settings = load_settings()
    db = Database()
    bot = Bot(token=settings.bot_token)
    user_view_mode = {}
    
    # Initialize dependencies
    profile.setup_dependencies(db, bot, user_view_mode)
    
    print(f"✓ Dependencies initialized:")
    print(f"  - db: {profile.db is not None}")
    print(f"  - bot: {profile.bot is not None}")
    print(f"  - user_view_mode: {profile.user_view_mode is not None}\n")
    
    # Create a test user
    test_user_id = 253445521
    try:
        db.add_user(test_user_id, "Test User")
        db.update_user_language(test_user_id, "ru")
        print(f"✓ Test user {test_user_id} created\n")
    except Exception as e:
        print(f"⚠️ User might already exist: {e}\n")
    
    # Mock callback
    callback = MagicMock(spec=types.CallbackQuery)
    callback.from_user = MagicMock()
    callback.from_user.id = test_user_id
    callback.data = "switch_to_customer"
    callback.message = MagicMock()
    callback.message.answer = AsyncMock()
    callback.answer = AsyncMock()
    
    # Test handler
    print("🔄 Calling switch_to_customer_cb handler...")
    try:
        await profile.switch_to_customer_cb(callback)
        print("✅ Handler executed successfully!\n")
        
        # Check if user_view_mode was updated
        if test_user_id in user_view_mode:
            print(f"✓ user_view_mode[{test_user_id}] = '{user_view_mode[test_user_id]}'")
        else:
            print(f"✗ user_view_mode was not updated")
        
        # Check if answer was called
        if callback.message.answer.called:
            print(f"✓ message.answer() was called")
            print(f"  Args: {callback.message.answer.call_args}")
        else:
            print(f"✗ message.answer() was NOT called")
        
        if callback.answer.called:
            print(f"✓ callback.answer() was called")
        else:
            print(f"✗ callback.answer() was NOT called")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        await bot.session.close()
    
    print("\n✅ Test completed!")

if __name__ == "__main__":
    asyncio.run(test_switch_to_customer())
