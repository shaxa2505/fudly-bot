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
        if city:
            city_variants = self._get_city_variants_search(city)
            city_conditions = " OR ".join(["s.city ILIKE %s" for _ in city_variants])
            base_sql += f" AND ({city_conditions})"
            params.extend([f"%{v}%" for v in city_variants])

        if region:
            region_variants = self._get_city_variants_search(region)
            region_conditions = " OR ".join(["s.region ILIKE %s" for _ in region_variants])
            base_sql += f" AND ({region_conditions})"
            params.extend([f"%{v}%" for v in region_variants])

        if district:
            district_variants = self._get_city_variants_search(district)
            district_conditions = " OR ".join(
                ["s.district ILIKE %s" for _ in district_variants]
            )
            base_sql += f" AND ({district_conditions})"
            params.extend([f"%{v}%" for v in district_variants])

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

    def search_stores(self, query: str, city: str = None) -> list[Any]:
        """Search stores by name with transliteration support."""
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
        if city:
            city_variants = self._get_city_variants_search(city)
            city_conditions = " OR ".join(["city ILIKE %s" for _ in city_variants])
            base_sql += f" AND ({city_conditions})"
            params.extend([f"%{v}%" for v in city_variants])

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
