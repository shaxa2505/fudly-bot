"""Tests for app.core modules."""
from __future__ import annotations

from app.core.exceptions import (
    BookingNotFoundException,
    DatabaseException,
    FudlyException,
    OfferNotFoundException,
    RateLimitException,
    StoreNotFoundException,
    UserNotFoundException,
    ValidationException,
)
from app.core.utils import (
    get_offer_field,
    get_store_field,
    get_user_field,
    normalize_city,
)


class TestExceptions:
    """Test custom exception classes."""

    def test_base_exception(self):
        """Test FudlyException base class."""
        exc = FudlyException("test message")
        assert str(exc) == "test message"
        assert exc.message == "test message"

    def test_user_not_found_exception(self):
        """Test UserNotFoundException."""
        exc = UserNotFoundException(12345)
        assert exc.user_id == 12345
        assert "12345" in str(exc)

    def test_store_not_found_exception(self):
        """Test StoreNotFoundException."""
        exc = StoreNotFoundException(999)
        assert exc.store_id == 999
        assert "999" in str(exc)

    def test_offer_not_found_exception(self):
        """Test OfferNotFoundException."""
        exc = OfferNotFoundException(777)
        assert exc.offer_id == 777
        assert "777" in str(exc)

    def test_booking_not_found_exception(self):
        """Test BookingNotFoundException."""
        exc = BookingNotFoundException(111)
        assert exc.booking_id == 111
        assert "111" in str(exc)

    def test_rate_limit_exception(self):
        """Test RateLimitException."""
        exc = RateLimitException(12345, "test_action", 60)
        assert exc.user_id == 12345
        assert exc.action == "test_action"
        assert exc.retry_after == 60
        assert "12345" in str(exc)
        assert "test_action" in str(exc)

    def test_validation_exception(self):
        """Test ValidationException."""
        exc = ValidationException("Invalid input")
        assert "Invalid input" in str(exc)

    def test_database_exception(self):
        """Test DatabaseException."""
        exc = DatabaseException("Connection failed")
        assert "Connection failed" in str(exc)


class TestUtils:
    """Test utility functions."""

    def test_get_user_field_dict(self):
        """Test get_user_field with dict input."""
        user = {
            "user_id": 123,
            "first_name": "Test",
            "language": "ru",
            "city": "Ташкент",
        }
        assert get_user_field(user, "user_id") == 123
        assert get_user_field(user, "first_name") == "Test"
        assert get_user_field(user, "language") == "ru"
        assert get_user_field(user, "nonexistent", "default") == "default"

    def test_get_user_field_tuple(self):
        """Test get_user_field with tuple input (SQLite format)."""
        # Tuple: (id, lang, name, phone, city, created_at, role, store_id, notif)
        user = (123, "ru", "Test", "+998901234567", "Ташкент", "2025-01-01", "customer", None, 1)
        assert get_user_field(user, "id") == 123
        assert get_user_field(user, "language") == "ru"
        assert get_user_field(user, "name") == "Test"
        assert get_user_field(user, "phone") == "+998901234567"
        assert get_user_field(user, "city") == "Ташкент"

    def test_get_user_field_none(self):
        """Test get_user_field with None input."""
        assert get_user_field(None, "any_field") is None
        assert get_user_field(None, "any_field", "default") == "default"

    def test_get_store_field_dict(self):
        """Test get_store_field with dict input."""
        store = {
            "store_id": 1,
            "name": "Test Store",
            "city": "Ташкент",
            "status": "active",
        }
        assert get_store_field(store, "store_id") == 1
        assert get_store_field(store, "name") == "Test Store"
        assert get_store_field(store, "city") == "Ташкент"
        assert get_store_field(store, "status") == "active"

    def test_get_store_field_tuple(self):
        """Test get_store_field with tuple input."""
        # Tuple format from database
        store = (
            1,
            123,
            "Test Store",
            "Ташкент",
            "Address",
            "Desc",
            "Ресторан",
            "+998",
            "active",
            None,
            "2025-01-01",
            "restaurant",
            1,
            15000,
            30000,
        )
        assert get_store_field(store, "store_id") == 1
        assert get_store_field(store, "owner_id") == 123
        assert get_store_field(store, "name") == "Test Store"
        assert get_store_field(store, "city") == "Ташкент"

    def test_get_store_field_none(self):
        """Test get_store_field with None input."""
        assert get_store_field(None, "any_field") is None
        assert get_store_field(None, "any_field", "default") == "default"

    def test_get_offer_field_dict(self):
        """Test get_offer_field with dict input."""
        offer = {
            "offer_id": 1,
            "title": "Test Offer",
            "discount_price": 10000,
        }
        assert get_offer_field(offer, "offer_id") == 1
        assert get_offer_field(offer, "title") == "Test Offer"
        assert get_offer_field(offer, "discount_price") == 10000

    def test_get_offer_field_none(self):
        """Test get_offer_field with None input."""
        assert get_offer_field(None, "any_field") is None
        assert get_offer_field(None, "any_field", "default") == "default"

    def test_normalize_city_russian(self):
        """Test normalize_city with Russian names."""
        assert normalize_city("Ташкент") == "Ташкент"
        assert normalize_city("Самарканд") == "Самарканд"
        assert normalize_city("Бухара") == "Бухара"

    def test_normalize_city_uzbek(self):
        """Test normalize_city with Uzbek names."""
        assert normalize_city("Toshkent") == "Ташкент"
        assert normalize_city("Samarqand") == "Самарканд"
        assert normalize_city("Buxoro") == "Бухара"
        assert normalize_city("Andijon") == "Андижан"
        assert normalize_city("Namangan") == "Наманган"
        assert normalize_city("Farg'ona") == "Фергана"
        assert normalize_city("Xiva") == "Хива"
        assert normalize_city("Nukus") == "Нукус"

    def test_normalize_city_english(self):
        """Test normalize_city with English names (normalized to Russian)."""
        assert normalize_city("Tashkent") == "Ташкент"
        assert normalize_city("Samarkand") == "Самарканд"
        assert normalize_city("Bukhara") == "Бухара"

    def test_normalize_city_unknown(self):
        """Test normalize_city with unknown city."""
        assert normalize_city("Unknown City") == "Unknown City"
        assert normalize_city("") == ""  # Empty string returns empty

    def test_normalize_city_case_sensitive(self):
        """Test that normalize_city is case-insensitive for known cities."""
        assert normalize_city("TOSHKENT") == "Ташкент"
        assert normalize_city("ToShKeNt") == "Ташкент"
        assert normalize_city("samarqand") == "Самарканд"
