"""
Search-related database operations.
"""
from __future__ import annotations

from typing import Any
import re

from psycopg.rows import dict_row

try:
    from logging_config import logger
except ImportError:
    import logging

    logger = logging.getLogger(__name__)

# Импортируем маппинг транслитерации из offers
from database_pg_module.mixins.offers import CITY_TRANSLITERATION

_CITY_SUFFIX_RE = re.compile(
    r"\s+(?:shahri|shahar|shahr|tumani|tuman|viloyati|viloyat|region|district|province|oblast|oblasti"
    r"|город|район|область|шахри|шахар|тумани|туман|вилояти)\b",
    re.IGNORECASE,
)


class SearchMixin:
    """Mixin for search-related database operations."""

    def _is_fts_available(self, table_name: str) -> bool:
        cache = getattr(self, "_fts_available_cache", {})
        if table_name in cache:
            return cache[table_name]

        available = False
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    SELECT 1
                    FROM information_schema.columns
                    WHERE table_name = %s AND column_name = 'search_vector'
                """,
                    (table_name,),
                )
                available = cursor.fetchone() is not None
        except Exception as e:
            logger.warning(f"FTS availability check failed for {table_name}: {e}")
            available = False

        cache[table_name] = available
        self._fts_available_cache = cache
        return available

    def _sanitize_search_query(self, query: str) -> str:
        query = re.sub(r"[!@#$%^&*()+=\[\]{};:'\",.<>?/\\|`~]", " ", query)
        query = re.sub(r"\s+", " ", query).strip()
        return query

    def _build_tsquery(self, query: str) -> str:
        cleaned = self._sanitize_search_query(query)
        if not cleaned:
            return ""
        words = cleaned.split()
        terms: list[str] = []
        for idx, word in enumerate(words):
            safe = re.sub(r"[^\w]+", "", word, flags=re.UNICODE).strip("_")
            if len(safe) < 2:
                continue
            if idx == len(words) - 1:
                terms.append(f"{safe}:*")
            else:
                terms.append(safe)
        return " & ".join(terms)

    def _get_city_variants_search(self, city: str) -> list[str]:
        """Get all variants of city name (transliteration)."""
        city_clean = " ".join(city.strip().split())
        city_clean = city_clean.split(",")[0]
        city_clean = re.sub(r"\s*\([^)]*\)", "", city_clean)
        city_clean = _CITY_SUFFIX_RE.sub("", city_clean).strip(" ,")
        city_lower = city_clean.lower()
        variants = {city_lower}

        if city_lower in CITY_TRANSLITERATION:
            variants.update(CITY_TRANSLITERATION[city_lower])

        for key, values in CITY_TRANSLITERATION.items():
            if city_lower in [v.lower() for v in values]:
                variants.add(key)
                variants.update(values)

        return list(variants)

    def _collect_location_filters(
        self,
        city: str | None,
        region: str | None,
        district: str | None,
        alias: str = "s",
    ) -> tuple[list[str], list[Any]]:
        conditions: list[str] = []
        params: list[Any] = []
        if city:
            condition, condition_params = self._build_location_filter(
                city, "city", alias, self._get_city_variants_search
            )
            if condition:
                conditions.append(condition)
                params.extend(condition_params)
        if region:
            condition, condition_params = self._build_location_filter(
                region, "region", alias, self._get_city_variants_search
            )
            if condition:
                conditions.append(condition)
                params.extend(condition_params)
        if district:
            condition, condition_params = self._build_location_filter(
                district, "district", alias, self._get_city_variants_search
            )
            if condition:
                conditions.append(condition)
                params.extend(condition_params)
        return conditions, params

    def search_offers(
        self,
        query: str,
        city: str | None = None,
        limit: int = 50,
        offset: int = 0,
        region: str | None = None,
        district: str | None = None,
        min_price: float | None = None,
        max_price: float | None = None,
        min_discount: float | None = None,
        category: str | list[str] | None = None,
    ) -> list[Any]:
        """Search offers by title or store name using advanced PostgreSQL full-text search."""
        tsquery = self._build_tsquery(query)
        if tsquery and self._is_fts_available("offers"):
            where_parts = [
                "o.status = 'active'",
                "COALESCE(o.stock_quantity, o.quantity) > 0",
                "(s.status = 'approved' OR s.status = 'active')",
                "(o.expiry_date IS NULL OR o.expiry_date >= CURRENT_DATE)",
            ]
            params: list[Any] = []

            location_conditions, location_params = self._collect_location_filters(
                city, region, district, alias="s"
            )
            where_parts.extend(location_conditions)
            params.extend(location_params)

            if min_price is not None:
                where_parts.append("o.discount_price >= %s")
                params.append(min_price)

            if max_price is not None:
                where_parts.append("o.discount_price <= %s")
                params.append(max_price)

            if min_discount is not None:
                where_parts.append(
                    "o.original_price > 0"
                    " AND (1.0 - o.discount_price::numeric / o.original_price::numeric) * 100 >= %s"
                )
                params.append(min_discount)

            categories: list[str] | None = None
            if category:
                if isinstance(category, (list, tuple, set)):
                    categories = [str(item).strip().lower() for item in category if item]
                else:
                    categories = [str(category).strip().lower()]
                categories = [item for item in categories if item]

            if categories:
                if len(categories) == 1:
                    where_parts.append("o.category = %s")
                    params.append(categories[0])
                else:
                    where_parts.append("o.category = ANY(%s)")
                    params.append(categories)

            where_parts.append("o.search_vector @@ to_tsquery('russian', %s)")
            params.append(tsquery)

            where_clause = " AND ".join(where_parts)
            base_sql = f"""
                SELECT
                    o.offer_id, o.store_id, o.title, o.description,
                    o.original_price, o.discount_price, o.quantity,
                    o.available_from, o.available_until, o.expiry_date,
                    o.status, o.photo_id as photo, o.created_at, o.unit,
                    s.name as store_name, s.address, s.category as store_category,
                    CASE WHEN o.original_price > 0 THEN CAST((1.0 - o.discount_price::numeric / o.original_price::numeric) * 100 AS INTEGER) ELSE 0 END as discount_percent,
                    s.delivery_enabled, s.delivery_price, s.min_order_amount,
                    ts_rank_cd(o.search_vector, to_tsquery('russian', %s)) as relevance
                FROM offers o
                JOIN stores s ON o.store_id = s.store_id
                WHERE {where_clause}
                ORDER BY relevance DESC, o.created_at DESC
                LIMIT %s OFFSET %s
            """
            select_params = [tsquery] + params + [limit, offset]

            with self.get_connection() as conn:
                cursor = conn.cursor(row_factory=dict_row)
                cursor.execute(base_sql, tuple(select_params))
                results = [dict(row) for row in cursor.fetchall()]
                if results:
                    return results

        base_sql = """
            SELECT
                o.offer_id, o.store_id, o.title, o.description,
                o.original_price, o.discount_price, o.quantity,
                o.available_from, o.available_until, o.expiry_date,
                o.status, o.photo_id as photo, o.created_at, o.unit,
                s.name as store_name, s.address, s.category as store_category,
                CASE WHEN o.original_price > 0 THEN CAST((1.0 - o.discount_price::numeric / o.original_price::numeric) * 100 AS INTEGER) ELSE 0 END as discount_percent,
                s.delivery_enabled, s.delivery_price, s.min_order_amount,
                (
                    CASE WHEN LOWER(o.title) = LOWER(%s) THEN 100 ELSE 0 END +
                    CASE WHEN LOWER(o.title) LIKE LOWER(%s) || '%%' THEN 50 ELSE 0 END +
                    CASE WHEN LOWER(o.title) LIKE '%%' || LOWER(%s) || '%%' THEN 10 ELSE 0 END +
                    CASE WHEN
                        TRANSLATE(LOWER(o.title), 'абвгдеёжзийклмнопрстуфхцчшщъыьэюя', 'abvgdeejziiklmnoprstufxcchshshhyyyeua') LIKE '%%' || LOWER(%s) || '%%'
                        OR LOWER(o.title) LIKE '%%' || REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(LOWER(%s), 'a', 'а'), 'e', 'е'), 'o', 'о'), 'p', 'р'), 'c', 'с') || '%%'
                    THEN 5 ELSE 0 END
                ) as relevance
            FROM offers o
            JOIN stores s ON o.store_id = s.store_id
            WHERE o.status = 'active'
            AND COALESCE(o.stock_quantity, o.quantity) > 0
            AND (s.status = 'approved' OR s.status = 'active')
        """

        params = [query, query, query, query, query]

        # Добавляем фильтр по городу с транслитерацией
        location_conditions, location_params = self._collect_location_filters(
            city, region, district, alias="s"
        )
        if location_conditions:
            base_sql += " AND " + " AND ".join(location_conditions)
            params.extend(location_params)

        if min_price is not None:
            base_sql += " AND o.discount_price >= %s"
            params.append(min_price)

        if max_price is not None:
            base_sql += " AND o.discount_price <= %s"
            params.append(max_price)

        if min_discount is not None:
            base_sql += (
                " AND o.original_price > 0"
                " AND (1.0 - o.discount_price::numeric / o.original_price::numeric) * 100 >= %s"
            )
            params.append(min_discount)

        categories: list[str] | None = None
        if category:
            if isinstance(category, (list, tuple, set)):
                categories = [str(item).strip().lower() for item in category if item]
            else:
                categories = [str(category).strip().lower()]
            categories = [item for item in categories if item]

        if categories:
            if len(categories) == 1:
                base_sql += " AND o.category = %s"
                params.append(categories[0])
            else:
                base_sql += " AND o.category = ANY(%s)"
                params.append(categories)

        base_sql += """
            AND (o.expiry_date IS NULL OR o.expiry_date >= CURRENT_DATE)
            AND (
                LOWER(o.title) LIKE '%%' || LOWER(%s) || '%%' OR
                LOWER(s.name) LIKE '%%' || LOWER(%s) || '%%' OR
                LOWER(s.category) LIKE '%%' || LOWER(%s) || '%%' OR
                TRANSLATE(LOWER(o.title), 'абвгдеёжзийклмнопрстуфхцчшщъыьэюя', 'abvgdeejziiklmnoprstufxcchshshhyyyeua') LIKE '%%' || LOWER(%s) || '%%'
            )
            ORDER BY relevance DESC, o.created_at DESC
            LIMIT %s OFFSET %s
        """
        params.extend([query, query, query, query])
        params.extend([limit, offset])

        with self.get_connection() as conn:
            cursor = conn.cursor(row_factory=dict_row)
            cursor.execute(base_sql, tuple(params))
            return [dict(row) for row in cursor.fetchall()]

    def get_offer_suggestions(
        self,
        query: str,
        limit: int = 5,
        city: str | None = None,
        region: str | None = None,
        district: str | None = None,
    ) -> list[str]:
        """Get offer title suggestions using FTS when available."""
        cleaned = (query or "").strip()
        if not cleaned:
            return []

        tsquery = self._build_tsquery(cleaned)
        suggestions: list[str] = []

        if tsquery and self._is_fts_available("offers"):
            where_parts = [
                "o.status = 'active'",
                "COALESCE(o.stock_quantity, o.quantity) > 0",
                "(o.expiry_date IS NULL OR o.expiry_date >= CURRENT_DATE)",
                "(s.status = 'approved' OR s.status = 'active')",
            ]
            where_params: list[Any] = []

            location_conditions, location_params = self._collect_location_filters(
                city, region, district, alias="s"
            )
            where_parts.extend(location_conditions)
            where_params.extend(location_params)

            where_parts.append("o.search_vector @@ to_tsquery('russian', %s)")
            where_clause = " AND ".join(where_parts)
            sql = f"""
                SELECT o.title,
                       ts_rank_cd(o.search_vector, to_tsquery('russian', %s)) as relevance
                FROM offers o
                JOIN stores s ON o.store_id = s.store_id
                WHERE {where_clause}
                ORDER BY relevance DESC, o.created_at DESC
                LIMIT %s
            """
            params = [tsquery] + where_params + [tsquery, limit * 3]
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(sql, params)
                for row in cursor.fetchall():
                    title = row[0]
                    if title and title not in suggestions:
                        suggestions.append(title)
                        if len(suggestions) >= limit:
                            break
            if suggestions:
                return suggestions

        pattern = f"%{cleaned}%"
        where_parts = [
            "o.status = 'active'",
            "COALESCE(o.stock_quantity, o.quantity) > 0",
            "(o.expiry_date IS NULL OR o.expiry_date >= CURRENT_DATE)",
            "(s.status = 'approved' OR s.status = 'active')",
            "LOWER(o.title) LIKE LOWER(%s)",
        ]
        params: list[Any] = [pattern]

        location_conditions, location_params = self._collect_location_filters(
            city, region, district, alias="s"
        )
        where_parts.extend(location_conditions)
        params.extend(location_params)

        where_clause = " AND ".join(where_parts)
        sql = f"""
            SELECT DISTINCT o.title
            FROM offers o
            JOIN stores s ON o.store_id = s.store_id
            WHERE {where_clause}
            ORDER BY o.created_at DESC
            LIMIT %s
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(sql, params + [limit])
            for row in cursor.fetchall():
                title = row[0]
                if title:
                    suggestions.append(title)
        return suggestions

    def get_store_suggestions(
        self,
        query: str,
        limit: int = 5,
        city: str | None = None,
        region: str | None = None,
        district: str | None = None,
    ) -> list[str]:
        """Get store name suggestions using FTS when available."""
        cleaned = (query or "").strip()
        if not cleaned:
            return []

        tsquery = self._build_tsquery(cleaned)
        suggestions: list[str] = []

        if tsquery and self._is_fts_available("stores"):
            where_parts = ["(status = 'approved' OR status = 'active')"]
            where_params: list[Any] = []

            location_conditions, location_params = self._collect_location_filters(
                city, region, district, alias=""
            )
            where_parts.extend(location_conditions)
            where_params.extend(location_params)

            where_parts.append("search_vector @@ to_tsquery('russian', %s)")
            where_clause = " AND ".join(where_parts)
            sql = f"""
                SELECT name,
                       ts_rank_cd(search_vector, to_tsquery('russian', %s)) as relevance
                FROM stores
                WHERE {where_clause}
                ORDER BY relevance DESC
                LIMIT %s
            """
            params = [tsquery] + where_params + [tsquery, limit * 3]
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(sql, params)
                for row in cursor.fetchall():
                    name = row[0]
                    if name and name not in suggestions:
                        suggestions.append(name)
                        if len(suggestions) >= limit:
                            break
            if suggestions:
                return suggestions

        pattern = f"%{cleaned}%"
        where_parts = [
            "(status = 'approved' OR status = 'active')",
            "LOWER(name) LIKE LOWER(%s)",
        ]
        params: list[Any] = [pattern]

        location_conditions, location_params = self._collect_location_filters(
            city, region, district, alias=""
        )
        where_parts.extend(location_conditions)
        params.extend(location_params)

        where_clause = " AND ".join(where_parts)
        sql = f"""
            SELECT DISTINCT name
            FROM stores
            WHERE {where_clause}
            ORDER BY name
            LIMIT %s
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(sql, params + [limit])
            for row in cursor.fetchall():
                name = row[0]
                if name:
                    suggestions.append(name)
        return suggestions

    def get_search_suggestions(
        self,
        query: str,
        limit: int = 5,
        city: str | None = None,
        region: str | None = None,
        district: str | None = None,
    ) -> list[str]:
        """Get combined offer + store suggestions."""
        suggestions: list[str] = []

        for title in self.get_offer_suggestions(
            query, limit=limit * 2, city=city, region=region, district=district
        ):
            if title and title not in suggestions:
                suggestions.append(title)
                if len(suggestions) >= limit:
                    return suggestions[:limit]

        for name in self.get_store_suggestions(
            query, limit=limit * 2, city=city, region=region, district=district
        ):
            if name and name not in suggestions:
                suggestions.append(name)
                if len(suggestions) >= limit:
                    break

        return suggestions[:limit]

    def search_stores(self, query: str, city: str = None) -> list[Any]:
        """Search stores by name with transliteration support."""
        tsquery = self._build_tsquery(query)
        if tsquery and self._is_fts_available("stores"):
            where_parts = ["(status = 'approved' OR status = 'active')"]
            params: list[Any] = []

            location_conditions, location_params = self._collect_location_filters(
                city, None, None, alias=""
            )
            where_parts.extend(location_conditions)
            params.extend(location_params)

            where_parts.append("search_vector @@ to_tsquery('russian', %s)")
            params.append(tsquery)

            where_clause = " AND ".join(where_parts)
            base_sql = f"""
                SELECT
                    store_id, name, address, category, description, city, phone,
                    delivery_enabled, delivery_price, min_order_amount,
                    ts_rank_cd(search_vector, to_tsquery('russian', %s)) as relevance
                FROM stores
                WHERE {where_clause}
                ORDER BY relevance DESC
                LIMIT 20
            """
            select_params = [tsquery] + params
            with self.get_connection() as conn:
                cursor = conn.cursor(row_factory=dict_row)
                cursor.execute(base_sql, tuple(select_params))
                return [dict(row) for row in cursor.fetchall()]

        base_sql = """
            SELECT
                store_id, name, address, category, description, city, phone,
                delivery_enabled, delivery_price, min_order_amount,
                (
                    CASE WHEN LOWER(name) = LOWER(%s) THEN 100 ELSE 0 END +
                    CASE WHEN LOWER(name) LIKE LOWER(%s) || '%%' THEN 50 ELSE 0 END +
                    CASE WHEN LOWER(name) LIKE '%%' || LOWER(%s) || '%%' THEN 10 ELSE 0 END +
                    CASE WHEN LOWER(category) LIKE '%%' || LOWER(%s) || '%%' THEN 15 ELSE 0 END +
                    CASE WHEN
                        TRANSLATE(LOWER(name), 'абвгдеёжзийклмнопрстуфхцчшщъыьэюя', 'abvgdeejziiklmnoprstufxcchshshhyyyeua') LIKE '%%' || LOWER(%s) || '%%'
                        OR LOWER(name) LIKE '%%' || REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(LOWER(%s), 'a', 'а'), 'e', 'е'), 'o', 'о'), 'p', 'р'), 'c', 'с') || '%%'
                    THEN 5 ELSE 0 END
                ) as relevance
            FROM stores
            WHERE (status = 'approved' OR status = 'active')
        """

        params = [query, query, query, query, query, query]

        # Добавляем фильтр по городу с транслитерацией
        location_conditions, location_params = self._collect_location_filters(
            city, None, None, alias=""
        )
        if location_conditions:
            base_sql += " AND " + " AND ".join(location_conditions)
            params.extend(location_params)

        base_sql += """
            AND (
                LOWER(name) LIKE '%%' || LOWER(%s) || '%%' OR
                LOWER(category) LIKE '%%' || LOWER(%s) || '%%' OR
                LOWER(description) LIKE '%%' || LOWER(%s) || '%%' OR
                TRANSLATE(LOWER(name), 'абвгдеёжзийклмнопрстуфхцчшщъыьэюя', 'abvgdeejziiklmnoprstufxcchshshhyyyeua') LIKE '%%' || LOWER(%s) || '%%'
            )
            ORDER BY relevance DESC
            LIMIT 20
        """
        params.extend([query, query, query, query])

        with self.get_connection() as conn:
            cursor = conn.cursor(row_factory=dict_row)
            cursor.execute(base_sql, tuple(params))
            return [dict(row) for row in cursor.fetchall()]
