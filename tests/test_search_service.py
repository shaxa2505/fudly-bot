"""
Tests for Full-Text Search service.
"""
from unittest.mock import MagicMock

import pytest

from app.services.search_service import (
    SearchResponse,
    SearchResult,
    SearchService,
    SearchTarget,
    create_search_service,
)


class TestSearchTarget:
    """Test SearchTarget enum."""

    def test_values(self):
        """Test enum values."""
        assert SearchTarget.OFFERS == "offers"
        assert SearchTarget.STORES == "stores"
        assert SearchTarget.ALL == "all"


class TestSearchResult:
    """Test SearchResult dataclass."""

    def test_create_result(self):
        """Test creating a search result."""
        result = SearchResult(
            id=1, type="offer", title="Test Offer", description="Description", relevance=0.8
        )

        assert result.id == 1
        assert result.type == "offer"
        assert result.title == "Test Offer"
        assert result.relevance == 0.8
        assert result.extra == {}

    def test_result_with_extra(self):
        """Test result with extra data."""
        extra = {"price": 100, "category": "food"}
        result = SearchResult(
            id=2, type="offer", title="Test", description=None, relevance=0.5, extra=extra
        )

        assert result.extra == extra


class TestSearchResponse:
    """Test SearchResponse dataclass."""

    def test_create_response(self):
        """Test creating a search response."""
        results = [
            SearchResult(id=1, type="offer", title="A", description="", relevance=0.9),
            SearchResult(id=2, type="store", title="B", description="", relevance=0.7),
        ]

        response = SearchResponse(
            query="test", results=results, total=2, page=1, per_page=20, took_ms=15.5
        )

        assert response.query == "test"
        assert len(response.results) == 2
        assert response.total == 2
        assert response.took_ms == 15.5
        assert response.suggestions == []

    def test_response_with_suggestions(self):
        """Test response with suggestions."""
        response = SearchResponse(
            query="pizz",
            results=[],
            total=0,
            page=1,
            per_page=20,
            took_ms=5.0,
            suggestions=["pizza", "pizzeria"],
        )

        assert response.suggestions == ["pizza", "pizzeria"]


class TestSearchService:
    """Test SearchService."""

    @pytest.fixture
    def mock_db(self):
        """Create mock database."""
        db = MagicMock()
        conn = MagicMock()
        cursor = MagicMock()

        db.get_connection.return_value.__enter__ = MagicMock(return_value=conn)
        db.get_connection.return_value.__exit__ = MagicMock(return_value=None)
        conn.cursor.return_value = cursor

        return db, conn, cursor

    @pytest.fixture
    def service(self, mock_db):
        """Create service with mock db."""
        db, _, _ = mock_db
        svc = SearchService(db)
        svc._fts_available = False  # Use LIKE fallback for tests
        return svc

    def test_sanitize_query(self, service):
        """Test query sanitization."""
        assert service._sanitize_query("hello world") == "hello world"
        assert service._sanitize_query("hello@world!") == "hello world"
        assert service._sanitize_query("  multiple   spaces  ") == "multiple spaces"
        assert service._sanitize_query("") == ""

    def test_to_tsquery_single_word(self, service):
        """Test tsquery conversion with single word."""
        result = service._to_tsquery("pizza")
        assert "pizza:*" in result

    def test_to_tsquery_multiple_words(self, service):
        """Test tsquery conversion with multiple words."""
        result = service._to_tsquery("fresh pizza")
        assert "fresh" in result
        assert "pizza:*" in result
        assert "&" in result

    def test_to_tsquery_short_words_filtered(self, service):
        """Test that very short words are filtered."""
        result = service._to_tsquery("a b pizza")
        assert "pizza:*" in result

    def test_to_tsquery_empty(self, service):
        """Test empty query."""
        assert service._to_tsquery("") == ""
        assert service._to_tsquery("   ") == ""

    @pytest.mark.asyncio
    async def test_search_empty_query(self, service):
        """Test search with empty query."""
        response = await service.search("")

        assert response.query == ""
        assert response.results == []
        assert response.total == 0

    @pytest.mark.asyncio
    async def test_search_basic(self, mock_db):
        """Test basic search."""
        db, conn, cursor = mock_db

        # Setup cursor responses
        cursor.fetchone.side_effect = [
            (2,),  # count query
        ]
        cursor.fetchall.side_effect = [
            [  # search results
                (1, "Pizza", "Delicious pizza", "food", 100, 70, 5, 1, "Pizza Place", "Tashkent"),
                (2, "Pasta", "Italian pasta", "food", 80, 50, 3, 1, "Pizza Place", "Tashkent"),
            ],
            [],  # suggestions
            [],  # store suggestions
        ]

        service = SearchService(db)
        service._fts_available = False

        response = await service.search("pizza", target=SearchTarget.OFFERS)

        assert response.query == "pizza"
        assert len(response.results) == 2
        assert response.results[0].type == "offer"

    @pytest.mark.asyncio
    async def test_search_with_city_filter(self, mock_db):
        """Test search with city filter."""
        db, conn, cursor = mock_db

        cursor.fetchone.side_effect = [(1,)]
        cursor.fetchall.side_effect = [
            [(1, "Coffee", "Fresh", "drinks", 50, 30, 10, 1, "Cafe", "Samarkand")],
            [],
            [],
        ]

        service = SearchService(db)
        service._fts_available = False

        response = await service.search("coffee", target=SearchTarget.OFFERS, city="Samarkand")

        assert response.query == "coffee"
        # Verify city was used in query
        call_args = cursor.execute.call_args_list
        assert any("city" in str(call).lower() for call in call_args)

    @pytest.mark.asyncio
    async def test_search_with_pagination(self, mock_db):
        """Test search pagination."""
        db, conn, cursor = mock_db

        cursor.fetchone.side_effect = [(50,)]  # Total of 50 results
        cursor.fetchall.side_effect = [
            [(i, f"Item {i}", "", "cat", 100, 70, 5, 1, "Store", "City") for i in range(10)],
            [],
            [],
        ]

        service = SearchService(db)
        service._fts_available = False

        response = await service.search("item", target=SearchTarget.OFFERS, page=2, per_page=10)

        assert response.page == 2
        assert response.per_page == 10
        assert response.total == 50

    @pytest.mark.asyncio
    async def test_search_stores(self, mock_db):
        """Test store search."""
        db, conn, cursor = mock_db

        cursor.fetchone.side_effect = [(1,)]
        cursor.fetchall.side_effect = [
            [(1, "Best Bakery", "Fresh bread daily", "bakery", "Tashkent", "123 Main St")],
            [],
        ]

        service = SearchService(db)
        service._fts_available = False

        response = await service.search("bakery", target=SearchTarget.STORES)

        assert len(response.results) == 1
        assert response.results[0].type == "store"
        assert response.results[0].title == "Best Bakery"

    @pytest.mark.asyncio
    async def test_search_all(self, mock_db):
        """Test searching both offers and stores."""
        db, conn, cursor = mock_db

        cursor.fetchone.side_effect = [(1,), (1,)]  # counts for offers and stores
        cursor.fetchall.side_effect = [
            [(1, "Pizza", "Desc", "food", 100, 70, 5, 1, "Store", "City")],  # offers
            [(1, "Pizzeria", "Best pizza", "restaurant", "City", "Addr")],  # stores
            [],  # suggestions
            [],
        ]

        service = SearchService(db)
        service._fts_available = False

        response = await service.search("pizza", target=SearchTarget.ALL)

        assert len(response.results) == 2
        types = {r.type for r in response.results}
        assert "offer" in types
        assert "store" in types

    @pytest.mark.asyncio
    async def test_autocomplete(self, mock_db):
        """Test autocomplete suggestions."""
        db, conn, cursor = mock_db

        cursor.fetchall.side_effect = [
            [("Pizza Margherita",), ("Pizza Pepperoni",)],
            [("Pizzeria Italia",)],
        ]

        service = SearchService(db)

        suggestions = await service.autocomplete("piz", limit=5)

        assert len(suggestions) == 3
        assert "Pizza Margherita" in suggestions
        assert "Pizza Pepperoni" in suggestions
        assert "Pizzeria Italia" in suggestions

    @pytest.mark.asyncio
    async def test_autocomplete_short_prefix(self, mock_db):
        """Test autocomplete with very short prefix."""
        db, _, _ = mock_db
        service = SearchService(db)

        suggestions = await service.autocomplete("p")

        assert suggestions == []  # Too short

    @pytest.mark.asyncio
    async def test_search_by_category(self, mock_db):
        """Test search by category."""
        db, conn, cursor = mock_db

        cursor.fetchone.side_effect = [(2,)]
        cursor.fetchall.side_effect = [
            [
                (1, "Bread", "Fresh", "bakery", 30, 20, 10, 1, "Bakery", "City"),
                (2, "Croissant", "Buttery", "bakery", 25, 15, 5, 1, "Bakery", "City"),
            ],
            [],
            [],
        ]

        service = SearchService(db)
        service._fts_available = False

        response = await service.search_by_category("bakery")

        assert response.query == "bakery"
        assert len(response.results) == 2

    @pytest.mark.asyncio
    async def test_search_nearby(self, mock_db):
        """Test location-based search."""
        db, conn, cursor = mock_db

        cursor.fetchone.side_effect = [(1,), (0,)]
        cursor.fetchall.side_effect = [
            [(1, "Local Pizza", "Nearby", "food", 100, 70, 5, 1, "Local Store", "Tashkent")],
            [],
            [],
            [],
        ]

        service = SearchService(db)
        service._fts_available = False

        response = await service.search_nearby("pizza", city="Tashkent")

        assert response.query == "pizza"
        # Should filter by city
        call_args_str = str(cursor.execute.call_args_list)
        assert "Tashkent" in call_args_str

    def test_check_fts_available_true(self, mock_db):
        """Test FTS availability check - available."""
        db, conn, cursor = mock_db
        cursor.fetchone.return_value = ("search_vector",)

        service = SearchService(db)

        assert service._check_fts_available() is True

    def test_check_fts_available_false(self, mock_db):
        """Test FTS availability check - not available."""
        db, conn, cursor = mock_db
        cursor.fetchone.return_value = None

        service = SearchService(db)

        assert service._check_fts_available() is False

    def test_check_fts_available_error(self, mock_db):
        """Test FTS check with error."""
        db, conn, cursor = mock_db
        db.get_connection.return_value.__enter__.side_effect = Exception("DB error")

        service = SearchService(db)

        assert service._check_fts_available() is False


class TestCreateSearchService:
    """Test factory function."""

    def test_create_service(self):
        """Test creating service via factory."""
        mock_db = MagicMock()

        service = create_search_service(mock_db)

        assert isinstance(service, SearchService)
        assert service.db is mock_db
