"""
Unit tests for security module (validator and rate limiter)
"""
from security import InputValidator, RateLimiter


class TestInputValidator:
    """Tests for InputValidator class"""

    def setup_method(self):
        """Initialize validator before each test"""
        self.validator = InputValidator()

    def test_validate_phone_valid_international(self):
        """Test validation of valid international phone numbers"""
        assert self.validator.validate_phone("+1234567890") is True
        assert self.validator.validate_phone("+79991234567") is True
        assert self.validator.validate_phone("+380123456789") is True

    def test_validate_phone_valid_local(self):
        """Test validation of valid local phone numbers"""
        assert self.validator.validate_phone("1234567890") is True
        assert self.validator.validate_phone("9991234567") is True

    def test_validate_phone_too_short(self):
        """Test rejection of too short phone numbers"""
        # Based on PHONE_PATTERN = r'^\+?[1-9]\d{1,14}$' min length is 2 digits after initial [1-9]
        # So "12" is valid (1 + 1 digit), but single digit without + is invalid
        assert self.validator.validate_phone("1") is False  # Only 1 digit
        assert self.validator.validate_phone("+1") is False  # + with 1 digit

    def test_validate_phone_too_long(self):
        """Test rejection of too long phone numbers"""
        assert self.validator.validate_phone("12345678901234567") is False
        assert self.validator.validate_phone("+123456789012345678") is False

    def test_validate_phone_invalid_characters(self):
        """Test rejection of phone numbers with invalid characters"""
        assert self.validator.validate_phone("123abc4567") is False
        assert self.validator.validate_phone("phone!@#$%") is False
        assert self.validator.validate_phone("++1234567890") is False

    def test_validate_phone_with_formatting(self):
        """Test that phone numbers with common formatting are accepted"""
        # Dashes, spaces, parentheses are stripped before validation
        assert self.validator.validate_phone("+123-456-7890") is True
        assert self.validator.validate_phone("123 456 7890") is True
        assert self.validator.validate_phone("(123)4567890") is True

    def test_validate_phone_empty(self):
        """Test rejection of empty phone numbers"""
        assert self.validator.validate_phone("") is False
        assert self.validator.validate_phone("   ") is False


class TestRateLimiter:
    """Tests for RateLimiter class"""

    def setup_method(self):
        """Initialize rate limiter before each test"""
        self.limiter = RateLimiter()

    def test_is_allowed_permits_requests(self):
        """Test that rate limiter allows requests under the limit"""
        user_id = 12345
        action = "test_action"
        assert self.limiter.is_allowed(user_id, action, max_requests=3, window_seconds=60) is True
        assert self.limiter.is_allowed(user_id, action, max_requests=3, window_seconds=60) is True
        assert self.limiter.is_allowed(user_id, action, max_requests=3, window_seconds=60) is True

    def test_is_allowed_blocks_excess_requests(self):
        """Test that rate limiter blocks requests over the limit"""
        user_id = 67890
        action = "limited_action"
        # Allow 3 requests
        for _ in range(3):
            assert (
                self.limiter.is_allowed(user_id, action, max_requests=3, window_seconds=60) is True
            )
        # Block 4th request
        assert self.limiter.is_allowed(user_id, action, max_requests=3, window_seconds=60) is False

    def test_is_allowed_different_users(self):
        """Test that rate limiter tracks users independently"""
        user1 = 11111
        user2 = 22222
        action = "shared_action"

        # Both users get their own limits
        assert self.limiter.is_allowed(user1, action, max_requests=5, window_seconds=60) is True
        assert self.limiter.is_allowed(user2, action, max_requests=5, window_seconds=60) is True
        assert self.limiter.is_allowed(user1, action, max_requests=5, window_seconds=60) is True
        assert self.limiter.is_allowed(user2, action, max_requests=5, window_seconds=60) is True

    def test_is_allowed_different_actions(self):
        """Test that rate limiter tracks actions separately for same user"""
        user_id = 99999
        action1 = "action_one"
        action2 = "action_two"

        # Different actions should have independent limits
        for _ in range(3):
            assert (
                self.limiter.is_allowed(user_id, action1, max_requests=3, window_seconds=60) is True
            )

        # action1 exhausted, but action2 should still work
        assert self.limiter.is_allowed(user_id, action1, max_requests=3, window_seconds=60) is False
        assert self.limiter.is_allowed(user_id, action2, max_requests=3, window_seconds=60) is True
