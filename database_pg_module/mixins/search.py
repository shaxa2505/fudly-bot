"""
Search-related database operations.
"""
from __future__ import annotations

from typing import Any

from psycopg.rows import dict_row

try:
    from logging_config import logger
except ImportError:
    import logging

    logger = logging.getLogger(__name__)

# Импортируем маппинг транслитерации из offers
from database_pg_module.mixins.offers import CITY_TRANSLITERATION


class SearchMixin:
    """Mixin for search-related database operations."""

    def _get_city_variants_search(self, city: str) -> list[str]:
        """Get all variants of city name (transliteration)."""
        city_lower = city.lower().strip()
        variants = {city_lower}

        if city_lower in CITY_TRANSLITERATION:
            variants.update(CITY_TRANSLITERATION[city_lower])

        for key, values in CITY_TRANSLITERATION.items():
            if city_lower in [v.lower() for v in values]:
                variants.add(key)
                variants.update(values)

        return list(variants)

    def search_offers(self, query: str, city: str = None) -> list[Any]:
        """Search offers by title or store name using advanced PostgreSQL full-text search."""
        base_sql = """
            SELECT
                o.offer_id, o.store_id, o.title, o.description,
                o.original_price, o.discount_price, o.quantity,
                o.available_from, o.available_until, o.expiry_date,
                o.status, o.photo_id as photo, o.created_at, o.unit,
                s.name as store_name, s.address, s.category as store_category,
                CAST((1.0 - o.discount_price::float / o.original_price::float) * 100 AS INTEGER) as discount_percent,
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
            AND o.quantity > 0
            AND (s.status = 'approved' OR s.status = 'active')
        """

        params = [query, query, query, query, query]

        # Добавляем фильтр по городу с транслитерацией
        if city:
            city_variants = self._get_city_variants_search(city)
            city_conditions = " OR ".join(["s.city ILIKE %s" for _ in city_variants])
            base_sql += f" AND ({city_conditions})"
            params.extend([f"%{v}%" for v in city_variants])

        base_sql += """
            AND (o.expiry_date IS NULL OR o.expiry_date >= CURRENT_DATE)
            AND (
                LOWER(o.title) LIKE '%%' || LOWER(%s) || '%%' OR
                LOWER(s.name) LIKE '%%' || LOWER(%s) || '%%' OR
                LOWER(s.category) LIKE '%%' || LOWER(%s) || '%%' OR
                TRANSLATE(LOWER(o.title), 'абвгдеёжзийклмнопрстуфхцчшщъыьэюя', 'abvgdeejziiklmnoprstufxcchshshhyyyeua') LIKE '%%' || LOWER(%s) || '%%'
            )
            ORDER BY relevance DESC, o.created_at DESC
            LIMIT 50
        """
        params.extend([query, query, query, query])

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
