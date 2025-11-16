"""Example: Using typed User model from database."""
import sys
sys.path.insert(0, '.')

from database import Database
from app.domain import User


def example_old_way():
    """Old way: using dict/tuple."""
    print("=== OLD WAY (dict/tuple) ===\n")
    
    db = Database("fudly.db")
    user_dict = db.get_user(123456789)
    
    if user_dict:
        # Need to know structure
        print(f"User ID: {user_dict['user_id']}")
        print(f"Name: {user_dict['first_name']}")
        print(f"City: {user_dict['city']}")
        print(f"Language: {user_dict['language']}")
        
        # No type safety, no autocomplete
        # What if field name changes?
    else:
        print("User not found")


def example_new_way():
    """New way: using Pydantic model."""
    print("\n\n=== NEW WAY (Pydantic Model) ===\n")
    
    db = Database("fudly.db")
    user = db.get_user_model(123456789)
    
    if user:
        # Type-safe! IDE autocomplete works!
        print(f"User ID: {user.user_id}")
        print(f"Name: {user.first_name}")
        print(f"City: {user.city}")
        print(f"Language: {user.language}")
        print(f"Display name: {user.display_name}")
        
        # Properties work!
        print(f"\nIs seller: {user.is_seller}")
        print(f"Is admin: {user.is_admin}")
        
        # Type hints everywhere!
        # user.city - IDE knows it's a string
        # user.is_seller - IDE knows it's a bool
    else:
        print("User not found")


def example_comparison():
    """Side by side comparison."""
    print("\n\n=== COMPARISON ===\n")
    
    db = Database("fudly.db")
    
    # Old way
    print("OLD: user_dict['city']")
    print("- No autocomplete")
    print("- No type checking")
    print("- Runtime errors if field missing\n")
    
    # New way
    print("NEW: user.city")
    print("✅ IDE autocomplete")
    print("✅ Type checking (mypy/pylance)")
    print("✅ Validation on creation")
    print("✅ Properties (user.is_seller)")
    print("✅ Methods (user.to_dict())")


if __name__ == "__main__":
    print("╔══════════════════════════════════════════════════════╗")
    print("║  Database Model Integration Example                  ║")
    print("╚══════════════════════════════════════════════════════╝")
    
    try:
        example_old_way()
        example_new_way()
        example_comparison()
        
        print("\n\n✅ Demo completed!")
        print("\n💡 Recommendation: Use get_user_model() for new code!")
        print("   Old get_user() still available for backward compatibility.")
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        print("\nNote: This demo requires existing database with users.")
        print("The important part is the API difference shown above.")
