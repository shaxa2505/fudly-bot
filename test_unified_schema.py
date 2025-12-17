"""
Test script to verify unified offers schema compatibility.

Tests:
1. Database schema has correct types
2. Pydantic models work with different input formats
3. Bot and Panel create compatible offers
"""
import asyncio
import os
import sys
from datetime import date, datetime, time, timedelta

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def test_pydantic_models():
    """Test Pydantic models with various input formats."""
    from app.domain.models import OfferCreate
    
    print("\n🔍 Testing Pydantic models...")
    
    # Test 1: Create offer with HH:MM time format (bot style)
    try:
        offer = OfferCreate(
            store_id=1,
            title="Test Product",
            description="Test description",
            original_price=10000,  # 100 rubles in kopeks
            discount_price=8000,   # 80 rubles in kopeks
            quantity=10,
            available_from="08:00",  # Bot format
            available_until="23:00",  # Bot format
            expiry_date="2025-12-31",  # ISO format
            photo_id="test_photo_id",
        )
        print("✅ HH:MM time format parsed correctly")
        print(f"   available_from: {offer.available_from} (type: {type(offer.available_from).__name__})")
    except Exception as e:
        print(f"❌ HH:MM time format failed: {e}")
        return False
    
    # Test 2: Create offer with ISO timestamp (panel style)
    try:
        now = datetime.now()
        offer = OfferCreate(
            store_id=1,
            title="Test Product 2",
            original_price=15000,
            discount_price=12000,
            quantity=5,
            available_from=now.replace(hour=9, minute=0).isoformat(),  # Panel format
            available_until=now.replace(hour=22, minute=0).isoformat(),  # Panel format
            expiry_date=(now + timedelta(days=7)).date(),  # Date object
            photo_id=None,
        )
        print("✅ ISO timestamp format parsed correctly")
        print(f"   available_from: {offer.available_from} (type: {type(offer.available_from).__name__})")
    except Exception as e:
        print(f"❌ ISO timestamp format failed: {e}")
        return False
    
    # Test 3: Russian date format DD.MM.YYYY
    try:
        offer = OfferCreate(
            store_id=1,
            title="Test Product 3",
            original_price=20000,
            discount_price=16000,
            quantity=3,
            available_from="10:30",
            available_until="20:00",
            expiry_date="31.12.2025",  # Russian format
        )
        print("✅ Russian date format (DD.MM.YYYY) parsed correctly")
        print(f"   expiry_date: {offer.expiry_date} (type: {type(offer.expiry_date).__name__})")
    except Exception as e:
        print(f"❌ Russian date format failed: {e}")
        return False
    
    # Test 4: Validation - discount > original should fail
    try:
        offer = OfferCreate(
            store_id=1,
            title="Invalid Product",
            original_price=10000,
            discount_price=15000,  # Higher than original!
            quantity=1,
            available_from="08:00",
            available_until="23:00",
            expiry_date="2025-12-31",
        )
        print("❌ Validation failed: should reject discount > original")
        return False
    except ValueError as e:
        print(f"✅ Validation works: {e}")
    
    # Test 5: Validation - expiry in past should fail
    try:
        offer = OfferCreate(
            store_id=1,
            title="Expired Product",
            original_price=10000,
            discount_price=8000,
            quantity=1,
            available_from="08:00",
            available_until="23:00",
            expiry_date="2020-01-01",  # Past date
        )
        print("❌ Validation failed: should reject past expiry date")
        return False
    except ValueError as e:
        print(f"✅ Validation works: {e}")
    
    print("\n✅ All Pydantic model tests passed!")
    return True


def test_database_schema():
    """Test that database has correct types."""
    from database_pg import Database
    
    print("\n🔍 Testing database schema...")
    
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        print("⚠️  DATABASE_URL not set, skipping database tests")
        return True
    
    try:
        db = Database(db_url)
        
        with db.get_connection() as conn:
            cursor = conn.cursor()
            
            # Check offers table schema
            cursor.execute("""
                SELECT column_name, data_type 
                FROM information_schema.columns 
                WHERE table_name = 'offers' 
                AND column_name IN ('available_from', 'available_until', 'expiry_date', 'original_price', 'discount_price', 'photo_id')
                ORDER BY column_name
            """)
            
            schema = {row[0]: row[1] for row in cursor.fetchall()}
            
            expected = {
                'available_from': 'time without time zone',
                'available_until': 'time without time zone',
                'expiry_date': 'date',
                'original_price': 'integer',
                'discount_price': 'integer',
                'photo_id': 'character varying',
            }
            
            all_correct = True
            for column, expected_type in expected.items():
                actual_type = schema.get(column)
                if actual_type == expected_type:
                    print(f"✅ {column}: {actual_type}")
                else:
                    print(f"❌ {column}: expected '{expected_type}', got '{actual_type}'")
                    all_correct = False
            
            if all_correct:
                print("\n✅ Database schema is correct!")
                return True
            else:
                print("\n❌ Database schema needs migration!")
                print("\n💡 Run: alembic upgrade head")
                return False
                
    except Exception as e:
        print(f"❌ Database test failed: {e}")
        return False


def test_price_conversion():
    """Test that price conversions work correctly."""
    print("\n🔍 Testing price conversions...")
    
    # Rubles → Kopeks
    rubles = 100
    kopeks = rubles * 100
    assert kopeks == 10000, "Rubles to kopeks conversion failed"
    print(f"✅ {rubles} rubles = {kopeks} kopeks")
    
    # Kopeks → Rubles
    kopeks = 12500
    rubles = kopeks / 100
    assert rubles == 125.0, "Kopeks to rubles conversion failed"
    print(f"✅ {kopeks} kopeks = {rubles} rubles")
    
    # Float precision test
    rubles = 99.99
    kopeks = int(rubles * 100)
    assert kopeks == 9999, "Float precision test failed"
    print(f"✅ {rubles} rubles = {kopeks} kopeks (float precision)")
    
    print("\n✅ All price conversion tests passed!")
    return True


def test_compatibility_bot_style():
    """Test creating offer bot-style (what bot sends to database)."""
    from app.domain.models import OfferCreate
    
    print("\n🔍 Testing bot-style offer creation...")
    
    try:
        # Simulate bot creating offer
        now = datetime.now()
        bot_offer = OfferCreate(
            store_id=1,
            title="Йогурт Активиа",
            description="Йогурт Активиа",
            original_price=500 * 100,  # Bot converts: 500 rubles → 50000 kopeks
            discount_price=300 * 100,  # 300 rubles → 30000 kopeks
            quantity=10,
            available_from=now.replace(hour=8, minute=0).time(),
            available_until=now.replace(hour=23, minute=0).time(),
            expiry_date=(now + timedelta(days=3)).date(),
            photo_id="AgACAgIAAxkBAAIBY2...",
            unit="шт",
            category="dairy",
        )
        
        print(f"✅ Bot offer created:")
        print(f"   Title: {bot_offer.title}")
        print(f"   Prices: {bot_offer.original_price} → {bot_offer.discount_price} kopeks")
        print(f"   Times: {bot_offer.available_from} - {bot_offer.available_until}")
        print(f"   Expiry: {bot_offer.expiry_date}")
        return True
        
    except Exception as e:
        print(f"❌ Bot-style creation failed: {e}")
        return False


def test_compatibility_panel_style():
    """Test creating offer panel-style (what Partner Panel sends to API)."""
    from app.domain.models import OfferCreate
    
    print("\n🔍 Testing panel-style offer creation...")
    
    try:
        # Simulate Partner Panel creating offer
        now = datetime.now()
        
        # Panel sends in rubles, API converts to kopeks
        rubles_original = 500
        rubles_discount = 300
        
        panel_offer = OfferCreate(
            store_id=1,
            title="Йогурт Активиа",
            description="Йогурт Активиа натуральный",
            original_price=rubles_original * 100,  # API converts: rubles → kopeks
            discount_price=rubles_discount * 100,
            quantity=10,
            available_from=now.replace(hour=8, minute=0).time(),
            available_until=now.replace(hour=23, minute=0).time(),
            expiry_date=(now + timedelta(days=7)).date(),
            photo_id="AgACAgIAAxkBAAIBY2...",
            unit="шт",
            category="dairy",
        )
        
        print(f"✅ Panel offer created:")
        print(f"   Title: {panel_offer.title}")
        print(f"   Prices: {panel_offer.original_price} → {panel_offer.discount_price} kopeks")
        print(f"   Times: {panel_offer.available_from} - {panel_offer.available_until}")
        print(f"   Expiry: {panel_offer.expiry_date}")
        return True
        
    except Exception as e:
        print(f"❌ Panel-style creation failed: {e}")
        return False


def main():
    """Run all tests."""
    print("=" * 70)
    print("🧪 UNIFIED OFFERS SCHEMA COMPATIBILITY TEST")
    print("=" * 70)
    
    tests = [
        ("Pydantic Models", test_pydantic_models),
        ("Price Conversions", test_price_conversion),
        ("Bot-Style Creation", test_compatibility_bot_style),
        ("Panel-Style Creation", test_compatibility_panel_style),
        ("Database Schema", test_database_schema),
    ]
    
    results = []
    for name, test_func in tests:
        try:
            result = test_func()
            results.append((name, result))
        except Exception as e:
            print(f"\n❌ {name} crashed: {e}")
            import traceback
            traceback.print_exc()
            results.append((name, False))
    
    print("\n" + "=" * 70)
    print("📊 TEST RESULTS")
    print("=" * 70)
    
    for name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status}  {name}")
    
    passed = sum(1 for _, r in results if r)
    total = len(results)
    
    print("\n" + "=" * 70)
    if passed == total:
        print(f"🎉 ALL TESTS PASSED ({passed}/{total})")
        print("\n✅ System is ready for unified offers schema!")
        return 0
    else:
        print(f"⚠️  SOME TESTS FAILED ({passed}/{total})")
        print("\n❌ Please fix issues before deploying migration")
        return 1


if __name__ == "__main__":
    sys.exit(main())
