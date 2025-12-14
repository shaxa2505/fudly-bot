"""
Quick script to set user as seller/partner in database
Run this to fix the "Not a partner" error
"""
import os
import sys

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database_pg import Database

# Your Telegram ID from the error
TELEGRAM_ID = 253445521

def fix_seller_role():
    """Set user as seller in database"""
    db = Database()
    
    # Check if user exists
    user = db.get_user(TELEGRAM_ID)
    
    if not user:
        print(f"❌ User {TELEGRAM_ID} not found in database")
        print("💡 Send /start to the bot first to create your user account")
        return
    
    print(f"✅ Found user: {user.get('first_name')} (@{user.get('username')})")
    print(f"📋 Current role: {user.get('role')}")
    
    # Update role to seller
    if user.get('role') == 'seller':
        print("✅ User is already a seller!")
    else:
        print(f"🔄 Updating role from '{user.get('role')}' to 'seller'...")
        db.update_user_role(TELEGRAM_ID, 'seller')
        print("✅ Role updated to 'seller'!")
    
    # Verify update
    updated_user = db.get_user(TELEGRAM_ID)
    print(f"\n✅ Verified: {updated_user.get('first_name')} is now a {updated_user.get('role')}")
    print("\n🎉 You can now refresh the Mini App at http://localhost:8080")

if __name__ == "__main__":
    try:
        fix_seller_role()
    except Exception as e:
        print(f"❌ Error: {e}")
        print("\n💡 Alternative: Run this SQL query:")
        print(f"   UPDATE users SET role = 'seller' WHERE telegram_id = {TELEGRAM_ID};")
