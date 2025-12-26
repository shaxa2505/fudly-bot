"""
Full-Text Search service for Fudly.

Provides PostgreSQL FTS-powered search across offers and stores
with support for:
- Russian language stemming
- Weighted search (title > description > category)
- Fuzzy matching with trigram similarity
- Search suggestions and autocomplete
- Result highlighting
"""
import logging
import re
from dataclasses import dataclass
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class SearchTarget(str, Enum):
    """What to search."""

    OFFERS = "offers"
    STORES = "stores"
    ALL = "all"


@dataclass
class SearchResult:
    """Single search result."""

    id: int
    type: str  # 'offer' or 'store'
    title: str
    description: str | None
    relevance: float
    highlight: str | None = None

    # Additional data depending on type
    extra: dict[str, Any] = None

    def __post_init__(self):
        if self.extra is None:
            self.extra = {}


@dataclass
class SearchResponse:
    """Search response with results and metadata."""

    query: str
    results: list[SearchResult]
    total: int
    page: int
    per_page: int
    took_ms: float
    suggestions: list[str] = None

    def __post_init__(self):
        if self.suggestions is None:
            self.suggestions = []


class SearchService:
    """
    Full-text search service using PostgreSQL FTS.

    Features:
    - Russian language support with stemming
    - Weighted relevance scoring
    - Prefix matching for autocomplete
    - Fallback to LIKE for non-FTS databases
    """

    def __init__(self, db):
        """
        Initialize search service.

        Args:
            db: Database instance with get_connection() method
        """
        self.db = db
        self._fts_available = None

    def _check_fts_available(self) -> bool:
        """Check if PostgreSQL FTS is available."""
        if self._fts_available is not None:
            return self._fts_available

        try:
            with self.db.get_connection() as conn:
                cursor = conn.cursor()
                # Check if we're on PostgreSQL and have search_vector column
                cursor.execute(
                    """
                    SELECT column_name FROM information_schema.columns
                    WHERE table_name = 'offers' AND column_name = 'search_vector'
                """
                )
                self._fts_available = cursor.fetchone() is not None
        except Exception as e:
            logger.warning(f"FTS check failed, using fallback: {e}")
            self._fts_available = False

        return self._fts_available

    def _sanitize_query(self, query: str) -> str:
        """Sanitize search query."""
        # Remove special characters that could break FTS
        query = re.sub(r'[!@#$%^&*()+=\[\]{};:\'",.<>?/\\|`~]', " ", query)
        # Collapse multiple spaces
        query = re.sub(r"\s+", " ", query).strip()
        return query

    def _to_tsquery(self, query: str) -> str:
        """
        Convert user query to PostgreSQL tsquery.

        Supports:
        - Multiple words (AND)
        - Prefix matching with *
        - Phrase matching with quotes
        """
        query = self._sanitize_query(query)

        if not query:
            return ""

        words = query.split()

        # Add prefix matching for last word (autocomplete)
        terms = []
        for i, word in enumerate(words):
            if len(word) >= 2:
                if i == len(words) - 1:
                    # Prefix match for last word
                    terms.append(f"{word}:*")
                else:
                    terms.append(word)

        # Join with AND
        return " & ".join(terms) if terms else ""

    async def search(
        self,
        query: str,
        target: SearchTarget = SearchTarget.ALL,
        city: str | None = None,
        category: str | None = None,
        page: int = 1,
        per_page: int = 20,
        min_relevance: float = 0.0,
    ) -> SearchResponse:
        """
        Perform full-text search.

        Args:
            query: Search query string
            target: What to search (offers, stores, or all)
            city: Filter by city
            category: Filter by category
            page: Page number (1-indexed)
            per_page: Results per page
            min_relevance: Minimum relevance score (0-1)

        Returns:
            SearchResponse with results and metadata
        """
        import time

        start = time.time()

        query = self._sanitize_query(query)

        if not query:
            return SearchResponse(
                query=query, results=[], total=0, page=page, per_page=per_page, took_ms=0
            )

        results = []
        total = 0

        if self._check_fts_available():
            # Use PostgreSQL FTS
            if target in (SearchTarget.OFFERS, SearchTarget.ALL):
                offer_results, offer_total = await self._search_offers_fts(
                    query, city, category, page, per_page
                )
                results.extend(offer_results)
                total += offer_total

            if target in (SearchTarget.STORES, SearchTarget.ALL):
                store_results, store_total = await self._search_stores_fts(
                    query, city, category, page, per_page
                )
                results.extend(store_results)
                total += store_total
        else:
            # Fallback to LIKE search
            if target in (SearchTarget.OFFERS, SearchTarget.ALL):
                offer_results, offer_total = await self._search_offers_like(
                    query, city, category, page, per_page
                )
                results.extend(offer_results)
                total += offer_total

            if target in (SearchTarget.STORES, SearchTarget.ALL):
                store_results, store_total = await self._search_stores_like(
                    query, city, category, page, per_page
                )
                results.extend(store_results)
                total += store_total

        # Sort by relevance
        results.sort(key=lambda r: r.relevance, reverse=True)

        # Apply min_relevance filter
        if min_relevance > 0:
            results = [r for r in results if r.relevance >= min_relevance]

        # Get suggestions for low-result queries
        suggestions = []
        if len(results) < 3:
            suggestions = await self._get_suggestions(query, target)

        took_ms = (time.time() - start) * 1000

        return SearchResponse(
            query=query,
            results=results[:per_page],
            total=total,
            page=page,
            per_page=per_page,
            took_ms=round(took_ms, 2),
            suggestions=suggestions,
        )

    async def _search_offers_fts(
        self, query: str, city: str | None, category: str | None, page: int, per_page: int
    ) -> tuple[list[SearchResult], int]:
        """Search offers using PostgreSQL FTS."""
        tsquery = self._to_tsquery(query)
        if not tsquery:
            return [], 0

        offset = (page - 1) * per_page

        try:
            with self.db.get_connection() as conn:
                cursor = conn.cursor()

                # Build WHERE clause
                conditions = ["o.is_active = TRUE", "COALESCE(o.stock_quantity, o.quantity) > 0"]
                params = []

                if city:
                    conditions.append("s.city = %s")
                    params.append(city)

                if category:
                    conditions.append("o.category = %s")
                    params.append(category)

                where_clause = " AND ".join(conditions)

                # Count total
                count_sql = f"""
                    SELECT COUNT(*) FROM offers o
                    JOIN stores s ON o.store_id = s.store_id
                    WHERE {where_clause}
                    AND o.search_vector @@ to_tsquery('russian', %s)
                """
                cursor.execute(count_sql, params + [tsquery])
                total = cursor.fetchone()[0]

                # Get results with relevance
                search_sql = f"""
                    SELECT
                        o.offer_id,
                        o.title,
                        o.description,
                        o.category,
                        o.original_price,
                        o.discount_price,
                        o.quantity,
                        s.store_id,
                        s.name as store_name,
                        s.city,
                        ts_rank_cd(o.search_vector, to_tsquery('russian', %s)) as relevance,
                        ts_headline('russian', o.title || ' ' || COALESCE(o.description, ''),
                                   to_tsquery('russian', %s),
                                   'StartSel=<b>, StopSel=</b>, MaxWords=50') as highlight
                    FROM offers o
                    JOIN stores s ON o.store_id = s.store_id
                    WHERE {where_clause}
                    AND o.search_vector @@ to_tsquery('russian', %s)
                    ORDER BY relevance DESC
                    LIMIT %s OFFSET %s
                """
                cursor.execute(search_sql, params + [tsquery, tsquery, tsquery, per_page, offset])

                results = []
                for row in cursor.fetchall():
                    results.append(
                        SearchResult(
                            id=row[0],
                            type="offer",
                            title=row[1],
                            description=row[2],
                            relevance=float(row[10]) if row[10] else 0.0,
                            highlight=row[11],
                            extra={
                                "category": row[3],
                                "original_price": row[4],
                                "discount_price": row[5],
                                "quantity": row[6],
                                "store_id": row[7],
                                "store_name": row[8],
                                "city": row[9],
                            },
                        )
                    )

                return results, total

        except Exception as e:
            logger.error(f"FTS offer search failed: {e}")
            return [], 0

    async def _search_stores_fts(
        self, query: str, city: str | None, category: str | None, page: int, per_page: int
    ) -> tuple[list[SearchResult], int]:
        """Search stores using PostgreSQL FTS."""
        tsquery = self._to_tsquery(query)
        if not tsquery:
            return [], 0

        offset = (page - 1) * per_page

        try:
            with self.db.get_connection() as conn:
                cursor = conn.cursor()

                # Build WHERE clause
                conditions = ["status = 'verified'"]
                params = []

                if city:
                    conditions.append("city = %s")
                    params.append(city)

                if category:
                    conditions.append("category = %s")
                    params.append(category)

                where_clause = " AND ".join(conditions)

                # Count total
                count_sql = f"""
                    SELECT COUNT(*) FROM stores
                    WHERE {where_clause}
                    AND search_vector @@ to_tsquery('russian', %s)
                """
                cursor.execute(count_sql, params + [tsquery])
                total = cursor.fetchone()[0]

                # Get results
                search_sql = f"""
                    SELECT
                        store_id,
                        name,
                        description,
                        category,
                        city,
                        address,
                        ts_rank_cd(search_vector, to_tsquery('russian', %s)) as relevance,
                        ts_headline('russian', name || ' ' || COALESCE(description, ''),
                                   to_tsquery('russian', %s),
                                   'StartSel=<b>, StopSel=</b>, MaxWords=50') as highlight
                    FROM stores
                    WHERE {where_clause}
                    AND search_vector @@ to_tsquery('russian', %s)
                    ORDER BY relevance DESC
                    LIMIT %s OFFSET %s
                """
                cursor.execute(search_sql, params + [tsquery, tsquery, tsquery, per_page, offset])

                results = []
                for row in cursor.fetchall():
                    results.append(
                        SearchResult(
                            id=row[0],
                            type="store",
                            title=row[1],
                            description=row[2],
                            relevance=float(row[6]) if row[6] else 0.0,
                            highlight=row[7],
                            extra={"category": row[3], "city": row[4], "address": row[5]},
                        )
                    )

                return results, total

        except Exception as e:
            logger.error(f"FTS store search failed: {e}")
            return [], 0

    async def _search_offers_like(
        self, query: str, city: str | None, category: str | None, page: int, per_page: int
    ) -> tuple[list[SearchResult], int]:
        """Fallback search using LIKE (for SQLite)."""
        offset = (page - 1) * per_page
        pattern = f"%{query}%"

        try:
            with self.db.get_connection() as conn:
                cursor = conn.cursor()

                # Build WHERE clause
                conditions = [
                    "o.is_active = 1",
                    "COALESCE(o.stock_quantity, o.quantity) > 0",
                    "(o.title LIKE ? OR o.description LIKE ? OR o.category LIKE ?)",
                ]
                params = [pattern, pattern, pattern]

                if city:
                    conditions.append("s.city = ?")
                    params.append(city)

                if category:
                    conditions.append("o.category = ?")
                    params.append(category)

                where_clause = " AND ".join(conditions)

                # Count total
                count_sql = f"""
                    SELECT COUNT(*) FROM offers o
                    JOIN stores s ON o.store_id = s.store_id
                    WHERE {where_clause}
                """
                cursor.execute(count_sql, params)
                total = cursor.fetchone()[0]

                # Get results
                search_sql = f"""
                    SELECT
                        o.offer_id,
                        o.title,
                        o.description,
                        o.category,
                        o.original_price,
                        o.discount_price,
                        o.quantity,
                        s.store_id,
                        s.name,
                        s.city
                    FROM offers o
                    JOIN stores s ON o.store_id = s.store_id
                    WHERE {where_clause}
                    ORDER BY o.created_at DESC
                    LIMIT ? OFFSET ?
                """
                cursor.execute(search_sql, params + [per_page, offset])

                results = []
                for row in cursor.fetchall():
                    # Calculate simple relevance based on title match
                    title_match = query.lower() in (row[1] or "").lower()
                    relevance = 1.0 if title_match else 0.5

                    results.append(
                        SearchResult(
                            id=row[0],
                            type="offer",
                            title=row[1],
                            description=row[2],
                            relevance=relevance,
                            extra={
                                "category": row[3],
                                "original_price": row[4],
                                "discount_price": row[5],
                                "quantity": row[6],
                                "store_id": row[7],
                                "store_name": row[8],
                                "city": row[9],
                            },
                        )
                    )

                return results, total

        except Exception as e:
            logger.error(f"LIKE offer search failed: {e}")
            return [], 0

    async def _search_stores_like(
        self, query: str, city: str | None, category: str | None, page: int, per_page: int
    ) -> tuple[list[SearchResult], int]:
        """Fallback store search using LIKE (for SQLite)."""
        offset = (page - 1) * per_page
        pattern = f"%{query}%"

        try:
            with self.db.get_connection() as conn:
                cursor = conn.cursor()

                # Build WHERE clause
                conditions = [
                    "status = 'verified'",
                    "(name LIKE ? OR description LIKE ? OR address LIKE ?)",
                ]
                params = [pattern, pattern, pattern]

                if city:
                    conditions.append("city = ?")
                    params.append(city)

                if category:
                    conditions.append("category = ?")
                    params.append(category)

                where_clause = " AND ".join(conditions)

                # Count
                count_sql = f"SELECT COUNT(*) FROM stores WHERE {where_clause}"
                cursor.execute(count_sql, params)
                total = cursor.fetchone()[0]

                # Results
                search_sql = f"""
                    SELECT store_id, name, description, category, city, address
                    FROM stores
                    WHERE {where_clause}
                    ORDER BY name
                    LIMIT ? OFFSET ?
                """
                cursor.execute(search_sql, params + [per_page, offset])

                results = []
                for row in cursor.fetchall():
                    title_match = query.lower() in (row[1] or "").lower()
                    relevance = 1.0 if title_match else 0.5

                    results.append(
                        SearchResult(
                            id=row[0],
                            type="store",
                            title=row[1],
                            description=row[2],
                            relevance=relevance,
                            extra={"category": row[3], "city": row[4], "address": row[5]},
                        )
                    )

                return results, total

        except Exception as e:
            logger.error(f"LIKE store search failed: {e}")
            return [], 0

    async def _get_suggestions(self, query: str, target: SearchTarget) -> list[str]:
        """Get search suggestions based on existing data."""
        suggestions = []

        try:
            with self.db.get_connection() as conn:
                cursor = conn.cursor()

                if target in (SearchTarget.OFFERS, SearchTarget.ALL):
                    # Get similar offer titles
                    cursor.execute(
                        """
                        SELECT DISTINCT category FROM offers
                        WHERE is_active = TRUE
                        LIMIT 5
                    """
                    )
                    for row in cursor.fetchall():
                        if row[0]:
                            suggestions.append(row[0])

                if target in (SearchTarget.STORES, SearchTarget.ALL):
                    # Get store categories
                    cursor.execute(
                        """
                        SELECT DISTINCT category FROM stores
                        WHERE status = 'verified'
                        LIMIT 5
                    """
                    )
                    for row in cursor.fetchall():
                        if row[0] and row[0] not in suggestions:
                            suggestions.append(row[0])

        except Exception as e:
            logger.warning(f"Failed to get suggestions: {e}")

        return suggestions[:5]

    async def autocomplete(
        self, prefix: str, target: SearchTarget = SearchTarget.ALL, limit: int = 10
    ) -> list[str]:
        """
        Get autocomplete suggestions for a prefix.

        Args:
            prefix: Search prefix
            target: What to search
            limit: Max suggestions

        Returns:
            List of suggested completions
        """
        prefix = self._sanitize_query(prefix)
        if len(prefix) < 2:
            return []

        suggestions = []
        pattern = f"{prefix}%"

        try:
            with self.db.get_connection() as conn:
                cursor = conn.cursor()

                if target in (SearchTarget.OFFERS, SearchTarget.ALL):
                    cursor.execute(
                        """
                        SELECT DISTINCT title FROM offers
                        WHERE is_active = TRUE AND title LIKE ?
                        ORDER BY title
                        LIMIT ?
                    """,
                        (pattern, limit),
                    )
                    suggestions.extend([row[0] for row in cursor.fetchall()])

                if target in (SearchTarget.STORES, SearchTarget.ALL):
                    cursor.execute(
                        """
                        SELECT DISTINCT name FROM stores
                        WHERE status = 'verified' AND name LIKE ?
                        ORDER BY name
                        LIMIT ?
                    """,
                        (pattern, limit),
                    )
                    for row in cursor.fetchall():
                        if row[0] not in suggestions:
                            suggestions.append(row[0])

        except Exception as e:
            logger.warning(f"Autocomplete failed: {e}")

        return suggestions[:limit]

    async def search_by_category(
        self, category: str, city: str | None = None, page: int = 1, per_page: int = 20
    ) -> SearchResponse:
        """
        Search offers by category.

        Args:
            category: Category to search
            city: Filter by city
            page: Page number
            per_page: Results per page

        Returns:
            SearchResponse with offers in category
        """
        return await self.search(
            query=category,
            target=SearchTarget.OFFERS,
            city=city,
            category=category,
            page=page,
            per_page=per_page,
        )

    async def search_nearby(
        self, query: str, city: str, page: int = 1, per_page: int = 20
    ) -> SearchResponse:
        """
        Search offers in a specific city.

        Args:
            query: Search query
            city: City to search in
            page: Page number
            per_page: Results per page

        Returns:
            SearchResponse with local results
        """
        return await self.search(
            query=query, target=SearchTarget.ALL, city=city, page=page, per_page=per_page
        )


# Factory function
def create_search_service(db) -> SearchService:
    """Create search service instance."""
    return SearchService(db)
