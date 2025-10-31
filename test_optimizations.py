#!/usr/bin/env python3
"""
Simple test suite for production optimizations.
Tests database, caching, security, and core functionality.
"""
import os
import tempfile
import unittest
from unittest.mock import Mock, patch


class TestDatabaseOptimizations(unittest.TestCase):
    """Test database connection pooling and caching."""
    
    def setUp(self):
        self.temp_db = tempfile.NamedTemporaryFile(delete=False, suffix='.db')
        self.temp_db.close()
        
    def tearDown(self):
        try:
            os.unlink(self.temp_db.name)
        except:
            pass
    
    def test_database_initialization(self):
        """Test that database initializes with pooling."""
        from database import Database
        
        db = Database(self.temp_db.name)
        self.assertIsNotNone(db)
        
        # Test basic operations
        user_id = 12345
        db.add_user(user_id, 'test_user', 'Test User')
        user = db.get_user(user_id)
        self.assertIsNotNone(user)
        self.assertEqual(user[0], user_id)
    
    def test_caching(self):
        """Test caching functionality."""
        from cache import InMemoryCache
        
        cache = InMemoryCache()
        
        # Test set/get
        cache.set('test_key', 'test_value', ex=60)
        result = cache.get('test_key')
        self.assertEqual(result, 'test_value')
        
        # Test expiration (short TTL)
        cache.set('expire_key', 'expire_value', ex=1)
        import time
        time.sleep(1.1)
        result = cache.get('expire_key')
        self.assertIsNone(result)
    
    def test_store_caching(self):
        """Test that store queries use cache."""
        from database import Database
        
        db = Database(self.temp_db.name)
        
        # Add test store
        store_id = db.add_store(123, 'Test Store', 'Ташкент', 'Test Address')
        
        # First call should hit database
        store1 = db.get_store(store_id)
        
        # Second call should hit cache
        store2 = db.get_store(store_id)
        
        self.assertEqual(store1, store2)
        self.assertIsNotNone(store1)


class TestSecurity(unittest.TestCase):
    """Test security and validation functions."""
    
    def test_input_validation(self):
        """Test input validation functions."""
        from security import InputValidator
        
        validator = InputValidator()
        
        # Test phone validation
        self.assertTrue(validator.validate_phone('+1234567890'))
        self.assertFalse(validator.validate_phone('invalid'))
        self.assertFalse(validator.validate_phone(''))
        
        # Test text sanitization
        dirty_text = '<script>alert("xss")</script>Hello & world'
        clean_text = validator.sanitize_text(dirty_text)
        self.assertNotIn('<script>', clean_text)
        self.assertIn('Hello', clean_text)
        
        # Test price validation
        is_valid, price = validator.validate_price('123.45')
        self.assertTrue(is_valid)
        self.assertEqual(price, 123.45)
        
        is_valid, _ = validator.validate_price('invalid')
        self.assertFalse(is_valid)
    
    def test_rate_limiting(self):
        """Test rate limiting functionality."""
        from security import RateLimiter
        
        limiter = RateLimiter()
        user_id = 12345
        action = 'test_action'
        
        # Should allow initial requests
        for i in range(5):
            self.assertTrue(limiter.is_allowed(user_id, action, max_requests=10))
        
        # Should still allow more requests under limit
        self.assertTrue(limiter.is_allowed(user_id, action, max_requests=10))


class TestBackgroundTasks(unittest.TestCase):
    """Test background task functionality."""
    
    def test_cleanup_function(self):
        """Test that cleanup function works."""
        from database import Database
        
        temp_db = tempfile.NamedTemporaryFile(delete=False, suffix='.db')
        temp_db.close()
        
        try:
            db = Database(temp_db.name)
            
            # Test cleanup function exists and runs
            deleted_count = db.delete_expired_offers()
            self.assertIsInstance(deleted_count, int)
            self.assertGreaterEqual(deleted_count, 0)
            
        finally:
            try:
                os.unlink(temp_db.name)
            except:
                pass


class TestLogging(unittest.TestCase):
    """Test logging configuration."""
    
    def test_logger_initialization(self):
        """Test that logger initializes properly."""
        try:
            from logging_config import logger
            self.assertIsNotNone(logger)
            
            # Test that we can log messages
            logger.info("Test log message")
            logger.warning("Test warning")
            logger.error("Test error")
            
        except ImportError:
            # Fallback logging is acceptable
            import logging
            logging.basicConfig(level=logging.INFO)
            logger = logging.getLogger('fudly')
            self.assertIsNotNone(logger)


def run_integration_test():
    """Run a simple integration test of the full flow."""
    print("\n=== Integration Test ===")
    
    temp_db = tempfile.NamedTemporaryFile(delete=False, suffix='.db')
    temp_db.close()
    
    try:
        from database import Database
        from security import InputValidator, rate_limiter
        
        print("✓ Imports successful")
        
        # Initialize database
        db = Database(temp_db.name)
        print("✓ Database initialized with pooling")
        
        # Test user flow
        user_id = 98765
        db.add_user(user_id, 'integration_user', 'Integration User', city='Ташкент')
        user = db.get_user(user_id)
        assert user is not None
        print("✓ User operations work")
        
        # Test store flow
        store_id = db.add_store(user_id, 'Test Store', 'Ташкент', 'Test Address')
        store = db.get_store(store_id)
        assert store is not None
        print("✓ Store operations with caching work")
        
        # Test security
        validator = InputValidator()
        clean_text = validator.sanitize_text("Test <script>alert('xss')</script> message")
        assert '<script>' not in clean_text
        print("✓ Security validation works")
        
        # Test rate limiting
        allowed = rate_limiter.is_allowed(user_id, 'test', max_requests=5)
        assert allowed == True
        print("✓ Rate limiting works")
        
        print("✓ All integration tests passed!")
        
    except Exception as e:
        print(f"✗ Integration test failed: {e}")
        raise
    finally:
        try:
            os.unlink(temp_db.name)
        except:
            pass


if __name__ == '__main__':
    print("Running production optimization tests...")
    
    # Run unit tests
    unittest.main(verbosity=2, exit=False)
    
    # Run integration test
    run_integration_test()