"""Quick bot health check - validates configuration and imports."""
import sys
from app.core.config import load_settings
from app.core.bootstrap import build_application

def main():
    print("🔍 Fudly Bot - Quick Health Check\n")
    
    # 1. Check configuration
    print("1️⃣ Checking configuration...")
    try:
        settings = load_settings()
        print(f"   ✓ Bot token: {'SET' if settings.bot_token else 'MISSING'}")
        print(f"   ✓ Admin ID: {settings.admin_id}")
        print(f"   ✓ Database: {'PostgreSQL' if settings.database_url else 'SQLite'}")
        print(f"   ✓ Webhook: {settings.webhook.enabled}")
    except Exception as e:
        print(f"   ✗ Configuration error: {e}")
        return False
    
    # 2. Check database
    print("\n2️⃣ Checking database connection...")
    try:
        bot, dp, db, cache = build_application(settings)
        print(f"   ✓ Database initialized")
        
        # Test basic query
        stats = db.get_statistics()
        print(f"   ✓ Database query works")
        print(f"   📊 Users: {stats.get('total_users', 0)}")
        print(f"   📊 Stores: {stats.get('total_stores', 0)}")
        print(f"   📊 Offers: {stats.get('total_offers', 0)}")
    except Exception as e:
        print(f"   ✗ Database error: {e}")
        return False
    
    # 3. Check handlers
    print("\n3️⃣ Checking handlers registration...")
    try:
        # Just verify the import works
        import bot
        print(f"   ✓ All handlers imported successfully")
    except Exception as e:
        print(f"   ✗ Handlers error: {e}")
        return False
    
    print("\n✅ All checks passed! Bot is ready to run.")
    print("\n💡 To start the bot, run: python bot.py")
    return True

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
