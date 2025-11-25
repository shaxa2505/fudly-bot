"""Tests for app/services/ - business logic layer."""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.services.admin_service import AdminService
from app.services.offer_service import OfferListItem, OfferService, StoreDetails

# =============================================================================
# Tests for OfferService
# =============================================================================


class TestOfferService:
    """Tests for OfferService."""

    @pytest.fixture
    def mock_db(self) -> MagicMock:
        """Create mock database."""
        db = MagicMock()
        # Full tuple structure matching database schema (22 fields):
        # 0:id, 1:store_id, 2:title, 3:description, 4:original_price, 5:discount_price,
        # 6:quantity, 7:unit, 8:photo, 9:expiry_date, 10:available_from, 11:available_until,
        # 12:category, 13:unit(dup), 14:store_name, 15:store_address, 16:store_city,
        # 17:store_category, 18:discount_percent, 19:delivery_enabled, 20:delivery_price, 21:min_order_amount
        db.get_hot_offers.return_value = [
            (
                1,
                10,
                "Test Offer",
                "Description",
                10000.0,
                5000.0,
                10,
                "шт",
                None,
                "2025-12-31",
                None,
                None,
                "bakery",
                "шт",
                "Test Store",
                "Address 1",
                "Ташкент",
                "bakery",
                50.0,
                1,
                5000.0,
                20000.0,
            ),
        ]
        db.count_hot_offers.return_value = 1
        return db

    @pytest.fixture
    def service(self, mock_db: MagicMock) -> OfferService:
        """Create OfferService instance."""
        return OfferService(db=mock_db)

    def test_list_hot_offers_returns_result(
        self, service: OfferService, mock_db: MagicMock
    ) -> None:
        """Test list_hot_offers returns OfferListResult."""
        result = service.list_hot_offers(city="Ташкент", limit=20, offset=0)

        assert result.total == 1
        assert len(result.items) == 1
        assert isinstance(result.items[0], OfferListItem)
        assert result.items[0].title == "Test Offer"
        assert result.items[0].original_price == 10000.0
        assert result.items[0].discount_price == 5000.0

    def test_list_hot_offers_calls_db(self, service: OfferService, mock_db: MagicMock) -> None:
        """Test list_hot_offers calls database methods."""
        service.list_hot_offers(city="Ташкент", limit=10, offset=0)

        mock_db.get_hot_offers.assert_called_once_with("Ташкент", limit=10, offset=0)
        mock_db.count_hot_offers.assert_called_once_with("Ташкент")

    def test_get_store_returns_details(self, mock_db: MagicMock) -> None:
        """Test get_store returns StoreDetails."""
        # Store tuple structure (matching database schema):
        # 0:store_id, 1:owner_id, 2:name, 3:city, 4:address, 5:description,
        # 6:category, 7:phone, 8:status, 9:created_at, 10:photo, 11:business_type,
        # 12:delivery_enabled, 13:delivery_price, 14:min_order_amount, 15:offers_count
        mock_db.get_store.return_value = (
            10,
            100,
            "Test Store",
            "Ташкент",
            "Address 1",
            "Description",
            "food",
            "+998901234567",
            "active",
            "2025-01-01",
            None,
            "supermarket",
            1,
            10000.0,
            50000.0,
            15,
        )
        mock_db.get_store_average_rating.return_value = 4.5
        mock_db.get_store_ratings.return_value = [1, 2, 3]  # 3 ratings

        from app.repositories import StoreRepository

        store_repo = StoreRepository(mock_db)
        service = OfferService(db=mock_db, store_repo=store_repo)

        result = service.get_store(10)

        assert result is not None
        assert isinstance(result, StoreDetails)
        assert result.name == "Test Store"
        assert result.city == "Ташкент"
        assert result.delivery_enabled is True

    def test_get_store_not_found(self, mock_db: MagicMock) -> None:
        """Test get_store returns None for non-existent store."""
        mock_db.get_store.return_value = None

        from app.repositories import StoreRepository

        store_repo = StoreRepository(mock_db)
        service = OfferService(db=mock_db, store_repo=store_repo)

        result = service.get_store(999)
        assert result is None


# =============================================================================
# Tests for AdminService
# =============================================================================


class TestAdminService:
    """Tests for AdminService."""

    @pytest.fixture
    def mock_db(self) -> MagicMock:
        """Create mock database."""
        return MagicMock()

    @pytest.fixture
    def service(self, mock_db: MagicMock) -> AdminService:
        """Create AdminService instance."""
        return AdminService(db=mock_db, use_postgres=True)

    def test_is_admin_returns_boolean(self, service: AdminService, mock_db: MagicMock) -> None:
        """Test is_admin returns boolean."""
        mock_db.is_admin.return_value = True
        assert service.is_admin(123) is True

        mock_db.is_admin.return_value = False
        assert service.is_admin(456) is False

    def test_placeholder_postgres(self, mock_db: MagicMock) -> None:
        """Test placeholder returns %s for PostgreSQL."""
        service = AdminService(db=mock_db, use_postgres=True)
        assert service.placeholder == "%s"

    def test_placeholder_sqlite(self, mock_db: MagicMock) -> None:
        """Test placeholder returns ? for SQLite."""
        service = AdminService(db=mock_db, use_postgres=False)
        assert service.placeholder == "?"

    def test_admin_service_initialization(self, mock_db: MagicMock) -> None:
        """Test AdminService can be initialized."""
        service = AdminService(db=mock_db, use_postgres=True)
        assert service is not None
        assert service.placeholder == "%s"


# =============================================================================
# Tests for BookingService
# =============================================================================


class TestBookingService:
    """Tests for BookingService (basic structure tests)."""

    def test_booking_service_can_be_imported(self) -> None:
        """Test BookingService can be imported."""
        from app.services.booking_service import BookingService

        assert BookingService is not None

    def test_booking_service_initialization(self) -> None:
        """Test BookingService can be initialized."""
        from app.services.booking_service import BookingService

        mock_db = MagicMock()
        service = BookingService(db=mock_db)
        assert service is not None


# =============================================================================
# Integration Tests
# =============================================================================


class TestServiceIntegration:
    """Integration tests for service layer."""

    def test_offer_service_with_cache(self) -> None:
        """Test OfferService works with cache manager."""
        mock_db = MagicMock()
        mock_cache = MagicMock()
        # Full tuple (22 fields)
        mock_cache.get_hot_offers.return_value = [
            (
                1,
                10,
                "Cached Offer",
                "Desc",
                10000.0,
                5000.0,
                5,
                "шт",
                None,
                "2025-12-31",
                None,
                None,
                "bakery",
                "шт",
                "Store",
                "Addr",
                "City",
                "bakery",
                50.0,
                0,
                0.0,
                0.0,
            ),
        ]
        mock_db.count_hot_offers.return_value = 1

        service = OfferService(db=mock_db, cache=mock_cache)
        result = service.list_hot_offers(city="Ташкент", limit=10, offset=0)

        # Should use cache for offset=0
        mock_cache.get_hot_offers.assert_called_once()
        assert len(result.items) == 1
        assert result.items[0].title == "Cached Offer"

    def test_offer_service_without_cache_uses_db(self) -> None:
        """Test OfferService uses DB when no cache."""
        mock_db = MagicMock()
        # Full tuple (22 fields)
        mock_db.get_hot_offers.return_value = [
            (
                1,
                10,
                "DB Offer",
                "Desc",
                10000.0,
                5000.0,
                5,
                "шт",
                None,
                "2025-12-31",
                None,
                None,
                "bakery",
                "шт",
                "Store",
                "Addr",
                "City",
                "bakery",
                50.0,
                0,
                0.0,
                0.0,
            ),
        ]
        mock_db.count_hot_offers.return_value = 1

        service = OfferService(db=mock_db, cache=None)
        result = service.list_hot_offers(city="Ташкент", limit=10, offset=0)

        # Should use DB
        mock_db.get_hot_offers.assert_called_once()
        assert len(result.items) == 1
        assert result.items[0].title == "DB Offer"

    def test_admin_service_can_check_admin(self) -> None:
        """Test AdminService can check if user is admin."""
        mock_db = MagicMock()
        mock_db.is_admin.return_value = True

        service = AdminService(db=mock_db, use_postgres=True)

        assert service.is_admin(123) is True
