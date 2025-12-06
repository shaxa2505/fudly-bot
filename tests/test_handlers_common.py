"""Tests for handlers/common/ - utilities, states, middleware."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from handlers.common.states import (
    BookOffer,
    Browse,
    ChangeCity,
    CreateOffer,
    RegisterStore,
    Registration,
    Search,
)
from handlers.common.utils import (
    CITY_UZ_TO_RU,
    UZB_TZ,
    get_appropriate_menu,
    get_uzb_time,
    has_approved_store,
    normalize_city,
    user_view_mode,
)

# =============================================================================
# Tests for normalize_city
# =============================================================================


class TestNormalizeCity:
    """Tests for normalize_city function."""

    def test_tashkent_uz_to_ru(self) -> None:
        """Test Tashkent conversion from Uzbek to Russian."""
        assert normalize_city("Toshkent") == "Ташкент"

    def test_samarkand_uz_to_ru(self) -> None:
        """Test Samarkand conversion from Uzbek to Russian."""
        assert normalize_city("Samarqand") == "Самарканд"

    def test_bukhara_uz_to_ru(self) -> None:
        """Test Bukhara conversion from Uzbek to Russian."""
        assert normalize_city("Buxoro") == "Бухара"

    def test_andijan_uz_to_ru(self) -> None:
        """Test Andijan conversion from Uzbek to Russian."""
        assert normalize_city("Andijon") == "Андижан"

    def test_already_russian(self) -> None:
        """Test that Russian city names pass through."""
        assert normalize_city("Ташкент") == "Ташкент"
        assert normalize_city("Москва") == "Москва"

    def test_unknown_city(self) -> None:
        """Test unknown city passes through unchanged."""
        assert normalize_city("UnknownCity") == "UnknownCity"


# =============================================================================
# Tests for get_uzb_time
# =============================================================================


class TestGetUzbTime:
    """Tests for get_uzb_time function."""

    def test_returns_datetime(self) -> None:
        """Test that function returns datetime."""
        result = get_uzb_time()
        assert isinstance(result, datetime)

    def test_has_correct_timezone(self) -> None:
        """Test that returned time has UTC+5 timezone."""
        result = get_uzb_time()
        assert result.tzinfo is not None
        # UTC+5 offset
        assert result.utcoffset() == timedelta(hours=5)


# =============================================================================
# Tests for has_approved_store
# =============================================================================


class TestHasApprovedStore:
    """Tests for has_approved_store function."""

    def test_user_with_active_store(self) -> None:
        """Test user with active store returns True."""
        mock_db = MagicMock()
        mock_db.get_user_accessible_stores.return_value = [
            {"id": 1, "name": "Test Store", "status": "active"},
        ]

        assert has_approved_store(123, mock_db) is True

    def test_user_with_pending_store(self) -> None:
        """Test user with only pending store returns False."""
        mock_db = MagicMock()
        mock_db.get_user_accessible_stores.return_value = [
            {"id": 1, "name": "Test Store", "status": "pending"},
        ]

        assert has_approved_store(123, mock_db) is False

    def test_user_without_stores(self) -> None:
        """Test user without stores returns False."""
        mock_db = MagicMock()
        mock_db.get_user_accessible_stores.return_value = []

        assert has_approved_store(123, mock_db) is False

    def test_user_with_multiple_stores_one_active(self) -> None:
        """Test user with multiple stores, one active."""
        mock_db = MagicMock()
        mock_db.get_user_accessible_stores.return_value = [
            {"id": 1, "name": "Store 1", "status": "pending"},
            {"id": 2, "name": "Store 2", "status": "active"},
            {"id": 3, "name": "Store 3", "status": "rejected"},
        ]

        assert has_approved_store(123, mock_db) is True


# =============================================================================
# Tests for get_appropriate_menu
# =============================================================================


class TestGetAppropriateMenu:
    """Tests for get_appropriate_menu function."""

    def test_no_user_returns_customer_menu(self) -> None:
        """Test that non-existent user gets customer menu."""
        mock_db = MagicMock()
        mock_db.get_user_model.return_value = None
        mock_customer_menu = MagicMock(return_value="customer_menu")
        mock_seller_menu = MagicMock(return_value="seller_menu")

        result = get_appropriate_menu(
            user_id=123,
            lang="ru",
            db=mock_db,
            main_menu_seller=mock_seller_menu,
            main_menu_customer=mock_customer_menu,
        )

        assert result == "customer_menu"

    def test_customer_gets_customer_menu(self) -> None:
        """Test that customer role gets customer menu."""
        mock_user = MagicMock()
        mock_user.role = "customer"

        mock_db = MagicMock()
        mock_db.get_user_model.return_value = mock_user

        mock_customer_menu = MagicMock(return_value="customer_menu")
        mock_seller_menu = MagicMock(return_value="seller_menu")

        result = get_appropriate_menu(
            user_id=123,
            lang="ru",
            db=mock_db,
            main_menu_seller=mock_seller_menu,
            main_menu_customer=mock_customer_menu,
        )

        assert result == "customer_menu"

    def test_seller_with_approved_store_in_seller_mode(self) -> None:
        """Test seller with approved store in seller mode gets seller menu."""
        mock_user = MagicMock()
        mock_user.role = "seller"

        mock_db = MagicMock()
        mock_db.get_user_model.return_value = mock_user
        mock_db.get_user_stores.return_value = [{"status": "active"}]
        mock_db.get_user_accessible_stores.return_value = [{"status": "active"}]
        mock_db.get_user_view_mode.return_value = "seller"

        mock_customer_menu = MagicMock(return_value="customer_menu")
        mock_seller_menu = MagicMock(return_value="seller_menu")

        result = get_appropriate_menu(
            user_id=123,
            lang="ru",
            db=mock_db,
            main_menu_seller=mock_seller_menu,
            main_menu_customer=mock_customer_menu,
        )

        assert result == "seller_menu"

    def test_seller_with_approved_store_in_customer_mode(self) -> None:
        """Test seller with approved store in customer mode gets customer menu."""
        mock_user = MagicMock()
        mock_user.role = "seller"

        mock_db = MagicMock()
        mock_db.get_user_model.return_value = mock_user
        mock_db.get_user_stores.return_value = [{"status": "active"}]
        mock_db.get_user_accessible_stores.return_value = [{"status": "active"}]
        mock_db.get_user_view_mode.return_value = "customer"

        mock_customer_menu = MagicMock(return_value="customer_menu")
        mock_seller_menu = MagicMock(return_value="seller_menu")

        result = get_appropriate_menu(
            user_id=123,
            lang="ru",
            db=mock_db,
            main_menu_seller=mock_seller_menu,
            main_menu_customer=mock_customer_menu,
        )

        assert result == "customer_menu"

    def test_seller_without_approved_store(self) -> None:
        """Test seller without approved store gets customer menu."""
        mock_user = MagicMock()
        mock_user.role = "seller"

        mock_db = MagicMock()
        mock_db.get_user_model.return_value = mock_user
        mock_db.get_user_stores.return_value = [{"status": "pending"}]
        mock_db.get_user_accessible_stores.return_value = [{"status": "pending"}]
        mock_db.get_user_view_mode.return_value = "customer"

        mock_customer_menu = MagicMock(return_value="customer_menu")
        mock_seller_menu = MagicMock(return_value="seller_menu")

        result = get_appropriate_menu(
            user_id=123,
            lang="ru",
            db=mock_db,
            main_menu_seller=mock_seller_menu,
            main_menu_customer=mock_customer_menu,
        )

        assert result == "customer_menu"

    def test_store_owner_treated_as_seller(self) -> None:
        """Test store_owner role is treated as seller."""
        mock_user = MagicMock()
        mock_user.role = "store_owner"

        mock_db = MagicMock()
        mock_db.get_user_model.return_value = mock_user
        mock_db.get_user_stores.return_value = [{"status": "active"}]
        mock_db.get_user_accessible_stores.return_value = [{"status": "active"}]
        mock_db.get_user_view_mode.return_value = "seller"

        mock_customer_menu = MagicMock(return_value="customer_menu")
        mock_seller_menu = MagicMock(return_value="seller_menu")

        result = get_appropriate_menu(
            user_id=123,
            lang="ru",
            db=mock_db,
            main_menu_seller=mock_seller_menu,
            main_menu_customer=mock_customer_menu,
        )

        assert result == "seller_menu"


# =============================================================================
# Tests for States
# =============================================================================


class TestStates:
    """Tests for FSM states."""

    def test_registration_states_exist(self) -> None:
        """Test Registration states are defined."""
        assert hasattr(Registration, "phone")
        assert hasattr(Registration, "city")

    def test_register_store_states_exist(self) -> None:
        """Test RegisterStore states are defined."""
        assert hasattr(RegisterStore, "name")
        assert hasattr(RegisterStore, "category")
        assert hasattr(RegisterStore, "city")
        assert hasattr(RegisterStore, "address")

    def test_create_offer_states_exist(self) -> None:
        """Test CreateOffer states are defined."""
        assert hasattr(CreateOffer, "title")
        assert hasattr(CreateOffer, "original_price")
        assert hasattr(CreateOffer, "discount_price")

    def test_change_city_states_exist(self) -> None:
        """Test ChangeCity states are defined."""
        assert hasattr(ChangeCity, "city")

    def test_book_offer_states_exist(self) -> None:
        """Test BookOffer states are defined."""
        assert hasattr(BookOffer, "quantity")
        assert hasattr(BookOffer, "delivery_choice")
        assert hasattr(BookOffer, "delivery_address")

    def test_search_states_exist(self) -> None:
        """Test Search states are defined."""
        assert hasattr(Search, "query")

    def test_browse_states_exist(self) -> None:
        """Test Browse states are defined."""
        assert hasattr(Browse, "viewing_store")
        assert hasattr(Browse, "viewing_category")


# =============================================================================
# Tests for Constants
# =============================================================================


class TestConstants:
    """Tests for constants and configurations."""

    def test_uzb_tz_is_utc_plus_5(self) -> None:
        """Test UZB_TZ is UTC+5."""
        assert UZB_TZ == timezone(timedelta(hours=5))

    def test_city_mapping_completeness(self) -> None:
        """Test city mapping contains major cities."""
        required_cities = ["Toshkent", "Samarqand", "Buxoro", "Andijon", "Namangan"]
        for city in required_cities:
            assert city in CITY_UZ_TO_RU

    def test_user_view_mode_is_dict(self) -> None:
        """Test user_view_mode is a dictionary."""
        assert isinstance(user_view_mode, dict)


# =============================================================================
# Tests for RegistrationCheckMiddleware
# =============================================================================


class TestRegistrationCheckMiddleware:
    """Tests for RegistrationCheckMiddleware."""

    @pytest.fixture
    def middleware(self) -> Any:
        """Create middleware instance with mocks."""
        from handlers.common.utils import RegistrationCheckMiddleware

        mock_db = MagicMock()
        mock_get_text = MagicMock(return_value="Please register")
        mock_phone_keyboard = MagicMock(return_value="phone_keyboard")

        middleware = RegistrationCheckMiddleware(
            db=mock_db,
            get_text_func=mock_get_text,
            phone_request_keyboard_func=mock_phone_keyboard,
        )
        middleware._mock_db = mock_db
        middleware._mock_get_text = mock_get_text
        return middleware

    @pytest.mark.asyncio
    async def test_allows_start_command(self, middleware: Any) -> None:
        """Test /start command is allowed without registration."""
        mock_handler = AsyncMock()
        mock_message = MagicMock()
        mock_message.text = "/start"
        mock_message.from_user.id = 123
        mock_message.contact = None
        mock_message.photo = None

        mock_event = MagicMock()
        mock_event.message = mock_message
        mock_event.callback_query = None

        await middleware(mock_handler, mock_event, {})

        mock_handler.assert_called_once()

    @pytest.mark.asyncio
    async def test_allows_contact_sharing(self, middleware: Any) -> None:
        """Test contact sharing is allowed without registration."""
        mock_handler = AsyncMock()
        mock_message = MagicMock()
        mock_message.text = None
        mock_message.from_user.id = 123
        mock_message.contact = MagicMock()  # Has contact
        mock_message.photo = None

        mock_event = MagicMock()
        mock_event.message = mock_message
        mock_event.callback_query = None

        await middleware(mock_handler, mock_event, {})

        mock_handler.assert_called_once()

    @pytest.mark.asyncio
    async def test_registered_user_passes(self, middleware: Any) -> None:
        """Test registered user can proceed."""
        mock_user = MagicMock()
        mock_user.phone = "+998901234567"
        middleware._mock_db.get_user_model.return_value = mock_user

        mock_handler = AsyncMock()
        mock_message = MagicMock()
        mock_message.text = "Some message"
        mock_message.from_user.id = 123
        mock_message.contact = None
        mock_message.photo = None

        mock_event = MagicMock()
        mock_event.message = mock_message
        mock_event.callback_query = None

        await middleware(mock_handler, mock_event, {"state": None})

        mock_handler.assert_called_once()

    @pytest.mark.asyncio
    async def test_unregistered_user_blocked(self, middleware: Any) -> None:
        """Test unregistered user is blocked and asked to register."""
        middleware.db.get_user_model.return_value = None
        middleware.db.get_user_language.return_value = "ru"

        mock_handler = AsyncMock()
        mock_message = MagicMock()
        mock_message.text = "Some message"
        mock_message.from_user.id = 123
        mock_message.contact = None
        mock_message.photo = None
        mock_message.answer = AsyncMock()  # Make answer async

        mock_event = MagicMock()
        mock_event.message = mock_message
        mock_event.callback_query = None

        await middleware(mock_handler, mock_event, {"state": None})

        # Handler should NOT be called
        mock_handler.assert_not_called()
        # Message answer should be called
        mock_message.answer.assert_called_once()

    @pytest.mark.asyncio
    async def test_allows_language_callbacks(self, middleware: Any) -> None:
        """Test language selection callbacks are allowed."""
        mock_handler = AsyncMock()
        mock_callback = MagicMock()
        mock_callback.data = "lang_ru"
        mock_callback.from_user.id = 123

        mock_event = MagicMock()
        mock_event.message = None
        mock_event.callback_query = mock_callback

        await middleware(mock_handler, mock_event, {})

        mock_handler.assert_called_once()

    @pytest.mark.asyncio
    async def test_allows_booking_callbacks(self, middleware: Any) -> None:
        """Test booking callbacks are allowed."""
        mock_handler = AsyncMock()
        mock_callback = MagicMock()
        mock_callback.data = "book_123"
        mock_callback.from_user.id = 123

        mock_event = MagicMock()
        mock_event.message = None
        mock_event.callback_query = mock_callback

        await middleware(mock_handler, mock_event, {})

        mock_handler.assert_called_once()

    @pytest.mark.asyncio
    async def test_allows_user_in_fsm_state(self, middleware: Any) -> None:
        """Test user in FSM state can proceed without registration check."""
        mock_handler = AsyncMock()
        mock_message = MagicMock()
        mock_message.text = "Some input"
        mock_message.from_user.id = 123
        mock_message.contact = None
        mock_message.photo = None

        mock_event = MagicMock()
        mock_event.message = mock_message
        mock_event.callback_query = None

        mock_state = AsyncMock()
        mock_state.get_state.return_value = "Registration:waiting_for_phone"

        await middleware(mock_handler, mock_event, {"state": mock_state})

        mock_handler.assert_called_once()
