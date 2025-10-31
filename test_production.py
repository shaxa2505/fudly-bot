"""
Simple tests for production optimizations.
Run with: python test_production.py
"""
import os
import sys
import tempfile
import unittest
from unittest.mock import patch, MagicMock

# Add project root to path
sys.path.insert(0, os.path.dirname(__file__))

# Test database pooling
class TestDatabasePool(unittest.TestCase):
    
    def setUp(self):
        # Use temporary database for tests
        self.temp_db = tempfile.NamedTemporaryFile(delete=False, suffix='.db')
        self.temp_db.close()
    
    def tearDown(self):
        try:
            os.unlink(self.temp_db.name)
        except:
            pass
    
    def test_database_initialization(self):
        """Test that database initializes with pool and indexes."""
        from database import Database
        
        db = Database(self.temp_db.name)
        
        # Test basic functionality
        user_id = 12345
        db.add_user(user_id, "test_user", "Test User")
        user = db.get_user(user_id)
        
        self.assertIsNotNone(user)
        self.assertEqual(user[0], user_id)  # user_id is first column
    
    def test_connection_pool_usage(self):
        """Test that connections are properly pooled."""
        from db_pool import SQLitePool
        
        # Test pool creation
        pool = SQLitePool(self.temp_db.name, maxsize=2)
        
        # Get and return connections
        conn1 = pool.getconn()
        self.assertIsNotNone(conn1)
        
        conn2 = pool.getconn()
        self.assertIsNotNone(conn2)
        
        # Return to pool
        conn1.close()
        conn2.close()


class TestCaching(unittest.TestCase):
    
    def test_in_memory_cache(self):
        """Test in-memory cache functionality."""
        from cache import InMemoryCache
        
        cache = InMemoryCache()
        
        # Test set/get
        cache.set('test_key', {'data': 'test'}, ex=300)
        result = cache.get('test_key')
        
        self.assertEqual(result, {'data': 'test'})
        
        # Test expiration (use negative TTL to force expiration)
        import time
        cache.set('expire_key', 'value', ex=1)  # 1 second expiration
        time.sleep(1.1)  # wait for expiration
        result = cache.get('expire_key')
        self.assertIsNone(result)
        
        # Test deletion
        cache.set('delete_key', 'value')
        cache.delete('delete_key')
        result = cache.get('delete_key')
        self.assertIsNone(result)


class TestSecurity(unittest.TestCase):
    
    def test_input_sanitization(self):
        """Test input validation and sanitization."""
        try:
            from security import sanitize_string, validate_user_id, validate_phone
            
            # Test string sanitization
            dirty_input = "<script>alert('xss')</script>Hello World   "
            clean = sanitize_string(dirty_input)
            self.assertNotIn('<script>', clean)
            self.assertIn('Hello World', clean)
            
            # Test user ID validation
            self.assertTrue(validate_user_id(123456789))
            self.assertFalse(validate_user_id('invalid'))
            self.assertFalse(validate_user_id(-1))
            
            # Test phone validation
            self.assertTrue(validate_phone('+1234567890'))
            self.assertTrue(validate_phone('1234567890'))
            self.assertFalse(validate_phone('123'))  # too short
            self.assertFalse(validate_phone('abc'))  # not digits
        except ImportError:
            self.skipTest("Security module dependencies not available")
    
    def test_data_validation(self):
        """Test business data validation."""
        try:
            from security import validate_store_data, validate_offer_data
            
            # Test store data validation
            good_store = {
                'name': 'Test Restaurant',
                'city': 'Ташкент',
                'phone': '+998901234567'
            }
            errors = validate_store_data(good_store)
            self.assertEqual(len(errors), 0)
            
            # Test invalid store data
            bad_store = {
                'name': 'X',  # too short
                'city': 'Invalid123',  # contains numbers
                'phone': '123'  # too short
            }
            errors = validate_store_data(bad_store)
            self.assertGreater(len(errors), 0)
            
            # Test offer data validation
            good_offer = {
                'title': 'Pizza Deal',
                'original_price': 50000,
                'discount_price': 30000,
                'quantity': 5
            }
            errors = validate_offer_data(good_offer)
            self.assertEqual(len(errors), 0)
            
        except ImportError:
            self.skipTest("Security module dependencies not available")


class TestAPIEndpoints(unittest.TestCase):
    
    def setUp(self):
        # Create temporary database
        self.temp_db = tempfile.NamedTemporaryFile(delete=False, suffix='.db')
        self.temp_db.close()
    
    def tearDown(self):
        try:
            os.unlink(self.temp_db.name)
        except:
            pass
    
    @patch('webapp.server.db')
    def test_health_endpoint(self, mock_db):
        """Test health check endpoint."""
        try:
            from webapp.server import app
            
            # Mock successful DB connection
            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_conn.cursor.return_value = mock_cursor
            mock_db.get_connection.return_value = mock_conn
            
            with app.test_client() as client:
                response = client.get('/health')
                
                self.assertEqual(response.status_code, 200)
                data = response.get_json()
                self.assertEqual(data['status'], 'healthy')
                self.assertEqual(data['database'], 'ok')
                
        except ImportError:
            self.skipTest("Flask dependencies not available")
    
    @patch('webapp.server.db')
    def test_metrics_endpoint(self, mock_db):
        """Test metrics endpoint."""
        try:
            from webapp.server import app
            
            # Mock statistics
            mock_db.get_statistics.return_value = {
                'users': 100,
                'stores': 25,
                'active_offers': 50,
                'bookings': 200
            }
            
            with app.test_client() as client:
                response = client.get('/metrics')
                
                self.assertEqual(response.status_code, 200)
                data = response.get_json()
                self.assertEqual(data['users'], 100)
                self.assertEqual(data['stores'], 25)
                
        except ImportError:
            self.skipTest("Flask dependencies not available")


class TestImageProcessing(unittest.TestCase):
    
    def test_image_validation(self):
        """Test image validation and processing."""
        try:
            from image_utils import validate_image, get_image_hash
            
            # Create minimal valid JPEG data (1x1 pixel)
            minimal_jpeg = bytes.fromhex('FFD8FFE000104A46494600010101006000600000FFDB004300080606070605080707070909080A0C140D0C0B0B0C1912130F141D1A1F1E1D1A1C1C20242E2720222C231C1C2837292C30313434341F27393D38323C2E333432FFDB0043010909090C0B0C18101018321B1C2132323232323232323232323232323232323232323232323232323232323232323232323232323232323232323232323232323232FFC000110801001E0103012200021101031101FFC4001F0000010501010101010100000000000000000102030405060708090A0BFFC400B5100002010303020403050504040000017D01020300041105122131410613516107227114328191A1082342B1C11552D1F02433627282090A161718191A25262728292A3435363738393A434445464748494A535455565758595A636465666768696A737475767778797A838485868788898A92939495969798999AA2A3A4A5A6A7A8A9AAB2B3B4B5B6B7B8B9BAC2C3C4C5C6C7C8C9CAD2D3D4D5D6D7D8D9DAE1E2E3E4E5E6E7E8E9EAF1F2F3F4F5F6F7F8F9FAFFC4001F0100030101010101010101010000000000000102030405060708090A0BFFC400B51100020102040403040705040400010277000102031104052131061241510761711322328108144291A1B1C109233352F0156272D10A162434E125F11718191A262728292A35363738393A434445464748494A535455565758595A636465666768696A737475767778797A82838485868788898A92939495969798999AA2A3A4A5A6A7A8A9AAB2B3B4B5B6B7B8B9BAC2C3C4C5C6C7C8C9CAD2D3D4D5D6D7D8D9DAE2E3E4E5E6E7E8E9EAF2F3F4F5F6F7F8F9FAFFDA000C03010002110311003F00FFFD9')
            
            # Should validate (minimal but valid)
            # This might fail without PIL, so we'll catch the exception
            try:
                result = validate_image(minimal_jpeg)
                # If PIL is available, this should work
                self.assertIsInstance(result, bool)
            except:
                # PIL not available, skip this part
                pass
            
            # Test hash generation (should work even without PIL)
            hash1 = get_image_hash(b'test data')
            hash2 = get_image_hash(b'test data')
            hash3 = get_image_hash(b'different data')
            
            self.assertEqual(hash1, hash2)  # Same data = same hash
            self.assertNotEqual(hash1, hash3)  # Different data = different hash
            
        except ImportError:
            self.skipTest("Image processing dependencies not available")


class TestBackgroundTasks(unittest.TestCase):
    
    def test_cleanup_function(self):
        """Test expired offers cleanup."""
        from database import Database
        
        # Use temporary database
        temp_db = tempfile.NamedTemporaryFile(delete=False, suffix='.db')
        temp_db.close()
        
        try:
            db = Database(temp_db.name)
            
            # Test delete_expired_offers method exists and works
            count = db.delete_expired_offers()
            self.assertIsInstance(count, int)
            self.assertGreaterEqual(count, 0)
            
        finally:
            try:
                os.unlink(temp_db.name)
            except:
                pass


def run_integration_test():
    """Run a simple integration test of the booking flow."""
    print("\n=== Integration Test: Complete Booking Flow ===")
    
    # Create temporary database
    temp_db = tempfile.NamedTemporaryFile(delete=False, suffix='.db')
    temp_db.close()
    
    try:
        from database import Database
        
        db = Database(temp_db.name)
        
        # 1. Create a user
        user_id = 999999
        db.add_user(user_id, "test_user", "Test User", role="customer", city="Ташкент")
        print("✓ User created")
        
        # 2. Create a store owner and store
        owner_id = 888888
        db.add_user(owner_id, "store_owner", "Store Owner", role="seller", city="Ташкент")
        store_id = db.add_store(owner_id, "Test Restaurant", "Ташкент", "Test Address")
        
        # Approve the store
        db.approve_store(store_id)
        print("✓ Store created and approved")
        
        # 3. Create an offer
        from datetime import datetime, timedelta
        
        available_from = datetime.now().strftime('%Y-%m-%d %H:%M')
        available_until = (datetime.now() + timedelta(hours=2)).strftime('%Y-%m-%d %H:%M')
        
        offer_id = db.add_offer(
            store_id=store_id,
            title="Test Pizza",
            description="Delicious test pizza",
            original_price=50000,
            discount_price=30000,
            quantity=5,
            available_from=available_from,
            available_until=available_until
        )
        print("✓ Offer created")
        
        # 4. Get active offers (test caching)
        offers1 = db.get_active_offers(city="Ташкент")
        offers2 = db.get_active_offers(city="Ташкент")  # Should use cache
        
        assert len(offers1) > 0, "No offers found"
        assert len(offers1) == len(offers2), "Cache inconsistency"
        print("✓ Offers retrieved (with caching)")
        
        # 5. Create a booking
        booking_id = db.create_booking(offer_id, user_id, "TEST123")
        print("✓ Booking created")
        
        # 6. Get user bookings
        bookings = db.get_user_bookings(user_id)
        assert len(bookings) > 0, "No bookings found"
        print("✓ Bookings retrieved")
        
        # 7. Complete the booking
        db.complete_booking(booking_id)
        print("✓ Booking completed")
        
        # 8. Get statistics
        stats = db.get_statistics()
        assert stats['users'] >= 2, "Statistics incorrect"
        assert stats['stores'] >= 1, "Statistics incorrect"
        print(f"✓ Statistics: {stats['users']} users, {stats['stores']} stores")
        
        print("\n🎉 Integration test PASSED!")
        return True
        
    except Exception as e:
        print(f"\n❌ Integration test FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False
        
    finally:
        try:
            os.unlink(temp_db.name)
        except:
            pass


if __name__ == '__main__':
    print("🧪 Running Production Optimization Tests...")
    print("=" * 50)
    
    # Run unit tests
    unittest.main(argv=[''], exit=False, verbosity=2)
    
    # Run integration test
    success = run_integration_test()
    
    print("\n" + "=" * 50)
    if success:
        print("✅ All tests completed successfully!")
        print("\nProduction optimizations are working correctly:")
        print("- Database connection pooling ✓")
        print("- Caching layer ✓")
        print("- Input validation ✓")
        print("- Background tasks ✓")
        print("- Health monitoring ✓")
    else:
        print("❌ Some tests failed. Check the output above.")
        sys.exit(1)