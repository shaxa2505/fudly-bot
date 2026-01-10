"""
Offer-related database operations.
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

# Маппинг городов: латиница <-> кириллица
CITY_TRANSLITERATION = {
    "toshkent": ["Ташкент", "Tashkent"],
    "tashkent": ["Ташкент", "Toshkent"],
    "samarqand": ["Самарканд", "Samarkand"],
    "samarkand": ["Самарканд", "Samarqand"],
    "buxoro": ["Бухара", "Bukhara"],
    "bukhara": ["Бухара", "Buxoro"],
    "farg'ona": ["Фергана", "Fergana"],
    "fergana": ["Фергана", "Farg'ona"],
    "andijon": ["Андижан", "Andijan"],
    "andijan": ["Андижан", "Andijon"],
    "namangan": ["Наманган"],
    "navoiy": ["Навои", "Navoi"],
    "navoi": ["Навои", "Navoiy"],
    "qarshi": ["Карши", "Karshi"],
    "karshi": ["Карши", "Qarshi"],
    "nukus": ["Нукус"],
    "urganch": ["Ургенч", "Urgench"],
    "urgench": ["Ургенч", "Urganch"],
    "jizzax": ["Джизак", "Jizzakh"],
    "jizzakh": ["Джизак", "Jizzax"],
    "termiz": ["Термез", "Termez"],
    "termez": ["Термез", "Termiz"],
    "guliston": ["Гулистан", "Gulistan"],
    "gulistan": ["Гулистан", "Guliston"],
    "chirchiq": ["Чирчик", "Chirchik"],
    "chirchik": ["Чирчик", "Chirchiq"],
    "kattaqo'rg'on": ["Каттакурган", "Kattakurgan", "Kattaqurgan"],
    "kattakurgan": ["Каттакурган", "Kattaqo'rg'on", "Kattaqurgan"],
    "kattaqurgan": ["Каттакурган", "Kattaqo'rg'on", "Kattakurgan"],
    "olmaliq": ["Алмалык", "Olmaliq"],
    "angren": ["Ангрен"],
    "bekobod": ["Бекабад", "Bekabad"],
    "shahrisabz": ["Шахрисабз"],
    "marg'ilon": ["Маргилан", "Margilan"],
    "margilan": ["Маргилан", "Marg'ilon"],
    "qo'qon": ["Коканд", "Kokand"],
    "kokand": ["Коканд", "Qo'qon"],
    "xiva": ["Хива", "Khiva"],
    "khiva": ["Хива", "Xiva"],
    "ташкент": ["Toshkent", "Tashkent"],
    "самарканд": ["Samarqand", "Samarkand"],
    "бухара": ["Buxoro", "Bukhara"],
    "фергана": ["Farg'ona", "Fergana"],
    "андижан": ["Andijon", "Andijan"],
    "наманган": ["Namangan"],
    "навои": ["Navoiy", "Navoi"],
    "карши": ["Qarshi", "Karshi"],
    "нукус": ["Nukus"],
    "ургенч": ["Urganch", "Urgench"],
    "джизак": ["Jizzax", "Jizzakh"],
    "термез": ["Termiz", "Termez"],
    "гулистан": ["Guliston", "Gulistan"],
    "чирчик": ["Chirchiq", "Chirchik"],
    "каттакурган": ["Kattaqo'rg'on", "Kattakurgan", "Kattaqurgan"],
    "алмалык": ["Olmaliq"],
    "ангрен": ["Angren"],
    "бекабад": ["Bekobod", "Bekabad"],
    "шахрисабз": ["Shahrisabz"],
    "маргилан": ["Marg'ilon", "Margilan"],
    "коканд": ["Qo'qon", "Kokand"],
    "хива": ["Xiva", "Khiva"],
}

_CITY_SUFFIX_RE = re.compile(
    r"\s+(?:shahri|shahar|shahr|tumani|tuman|viloyati|viloyat|region|district|province|oblast|oblasti"
    r"|город|район|область|шахри|шахар|тумани|туман|вилояти)\b",
    re.IGNORECASE,
)


class OfferMixin:
    """Mixin for offer-related database operations."""

    def _normalize_city_label(self, city: str) -> str:
        city_clean = " ".join(city.strip().split())
        city_clean = city_clean.split(",")[0]
        city_clean = re.sub(r"\s*\([^)]*\)", "", city_clean)
        city_clean = _CITY_SUFFIX_RE.sub("", city_clean).strip(" ,")
        return city_clean.lower()

    def _get_city_variants(self, city: str) -> list[str]:
        """Get all variants of city name (transliteration)."""
        city_lower = self._normalize_city_label(city)
        variants = {city_lower}

        # Добавляем варианты из маппинга
        if city_lower in CITY_TRANSLITERATION:
            variants.update(CITY_TRANSLITERATION[city_lower])

        # Проверяем обратный маппинг
        for key, values in CITY_TRANSLITERATION.items():
            if city_lower in [v.lower() for v in values]:
                variants.add(key)
                variants.update(values)

        return list(variants)

    def _get_location_variants(self, value: str) -> list[str]:
        """Return normalized variants for region/district matching."""
        return self._get_city_variants(value)

    def add_offer(
        self,
        store_id: int,
        title: str,
        description: str = None,
        original_price: int = None,  # Now in kopeks (INTEGER)
        discount_price: int = None,  # Now in kopeks (INTEGER)
        quantity: int = 1,
        stock_quantity: int | None = None,
        available_from: str = None,  # Will be converted to TIME by Pydantic
        available_until: str = None,  # Will be converted to TIME by Pydantic
        photo_id: str = None,  # Unified parameter name
        expiry_date: str = None,  # Will be converted to DATE by Pydantic
        unit: str = "шт",
        category: str = "other",
    ):
        """
        Add new offer with unified schema.

        Note: Prices should be in kopeks (INTEGER), not rubles.
        Times and dates will be validated by Pydantic models before reaching here.

        Legacy 'photo' parameter removed - use 'photo_id' instead.
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            # Support legacy/new partner panel which may send `stock_quantity`.
            final_quantity = stock_quantity if stock_quantity is not None else quantity

            cursor.execute(
                """
                INSERT INTO offers (store_id, title, description, original_price, discount_price,
                                  quantity, stock_quantity, available_from, available_until,
                                  expiry_date, photo_id, unit, category)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING offer_id
            """,
                (
                    store_id,
                    title,
                    description,
                    original_price,
                    discount_price,
                    final_quantity,
                    final_quantity,
                    available_from,
                    available_until,
                    expiry_date,
                    photo_id,  # No more hack - direct parameter
                    unit,
                    category,
                ),
            )
            result = cursor.fetchone()
            if not result:
                raise ValueError("Failed to create offer")
            offer_id = result[0]
            logger.info(f"Offer {offer_id} added to store {store_id}")
            return offer_id

    def get_offer(self, offer_id: int):
        """Get offer by ID."""
        with self.get_connection() as conn:
            cursor = conn.cursor(row_factory=dict_row)
            cursor.execute("SELECT * FROM offers WHERE offer_id = %s", (offer_id,))
            result = cursor.fetchone()
            return dict(result) if result else None

    def get_offer_model(self, offer_id: int) -> Any | None:
        """Get offer as Pydantic model."""
        try:
            from app.domain import Offer
        except ImportError:
            logger.error("Domain models not available. Install pydantic.")
            return None

        offer_tuple = self.get_offer(offer_id)
        if not offer_tuple:
            return None

        try:
            return Offer.from_db_row(offer_tuple)
        except Exception as e:
            logger.error(f"Failed to convert offer {offer_id} to model: {e}")
            return None

    def get_store_offers(
        self,
        store_id: int,
        status: str = "active",
        limit: int | None = None,
        offset: int = 0,
        sort_by: str | None = None,
        min_price: float | None = None,
        max_price: float | None = None,
        min_discount: float | None = None,
    ):
        """Get offers for a store (excluding expired)."""
        with self.get_connection() as conn:
            cursor = conn.cursor(row_factory=dict_row)

            query = """
                SELECT o.*,
                       CASE WHEN o.original_price > 0 THEN CAST((1.0 - o.discount_price::numeric / o.original_price::numeric) * 100 AS INTEGER) ELSE 0 END as discount_percent
                FROM offers o
                WHERE o.store_id = %s
                  AND o.status = %s
                  AND (o.expiry_date IS NULL OR o.expiry_date >= CURRENT_DATE)
            """
            params: list[Any] = [store_id, status]

            if min_price is not None:
                query += " AND o.discount_price >= %s"
                params.append(min_price)
            if max_price is not None:
                query += " AND o.discount_price <= %s"
                params.append(max_price)
            if min_discount is not None:
                query += (
                    " AND o.original_price > 0"
                    " AND (1.0 - o.discount_price::numeric / o.original_price::numeric) * 100 >= %s"
                )
                params.append(min_discount)

            order_by = "o.created_at DESC"
            if sort_by:
                sort_key = sort_by.lower()
                if sort_key == "discount":
                    order_by = "discount_percent DESC, o.created_at DESC"
                elif sort_key == "price_asc":
                    order_by = "o.discount_price ASC, o.created_at DESC"
                elif sort_key == "price_desc":
                    order_by = "o.discount_price DESC, o.created_at DESC"
                elif sort_key == "new":
                    order_by = "o.offer_id DESC"

            query += f" ORDER BY {order_by}"

            if limit is not None:
                query += " LIMIT %s OFFSET %s"
                params.extend([limit, offset])
            elif offset:
                query += " OFFSET %s"
                params.append(offset)

            cursor.execute(query, params)
            return [dict(row) for row in cursor.fetchall()]

    def get_active_offers(
        self, city: str | None = None, store_id: int | None = None
    ) -> list[dict[str, Any]]:
        """Return active offers, optionally filtered by city or store."""
        with self.get_connection() as conn:
            cursor = conn.cursor(row_factory=dict_row)
            base = [
                "SELECT o.*, s.city FROM offers o JOIN stores s ON o.store_id = s.store_id WHERE o.status = 'active'",
                "AND COALESCE(o.stock_quantity, o.quantity) > 0",
            ]
            params = []
            if city:
                city_variants = self._get_city_variants(city)
                city_conditions = " OR ".join(["s.city ILIKE %s" for _ in city_variants])
                base.append(f"AND ({city_conditions})")
                params.extend([f"%{v}%" for v in city_variants])
            if store_id:
                base.append("AND o.store_id = %s")
                params.append(store_id)
            base.append("ORDER BY o.created_at DESC")
            query = " ".join(base)
            cursor.execute(query, tuple(params))
            return list(cursor.fetchall())

    def get_hot_offers(
        self,
        city: str | None = None,
        limit: int = 20,
        offset: int = 0,
        business_type: str | None = None,
        region: str | None = None,
        district: str | None = None,
        sort_by: str | None = None,
        min_price: float | None = None,
        max_price: float | None = None,
        min_discount: float | None = None,
    ):
        """Get hot offers (top by discount and expiry date)."""
        with self.get_connection() as conn:
            cursor = conn.cursor(row_factory=dict_row)

            query = """
                SELECT o.*, s.name as store_name, s.address, s.city, s.category as store_category,
                       s.delivery_enabled, s.delivery_price, s.min_order_amount,
                       CASE WHEN o.original_price > 0 THEN CAST((1.0 - o.discount_price::numeric / o.original_price::numeric) * 100 AS INTEGER) ELSE 0 END as discount_percent
                FROM offers o
                JOIN stores s ON o.store_id = s.store_id
                WHERE o.status = 'active'
                AND COALESCE(o.stock_quantity, o.quantity) > 0
                AND (s.status = 'approved' OR s.status = 'active')
                AND (o.expiry_date IS NULL OR o.expiry_date >= CURRENT_DATE)
            """

            params = []
            if city:
                # Поддержка транслитерации: ищем и латиницу и кириллицу
                city_variants = self._get_city_variants(city)
                city_conditions = " OR ".join(["s.city ILIKE %s" for _ in city_variants])
                query += f" AND ({city_conditions})"
                params.extend([f"%{v}%" for v in city_variants])

            if region:
                region_variants = self._get_location_variants(region)
                region_conditions = " OR ".join(["s.region ILIKE %s" for _ in region_variants])
                query += f" AND ({region_conditions})"
                params.extend([f"%{v}%" for v in region_variants])

            if district:
                district_variants = self._get_location_variants(district)
                district_conditions = " OR ".join(
                    ["s.district ILIKE %s" for _ in district_variants]
                )
                query += f" AND ({district_conditions})"
                params.extend([f"%{v}%" for v in district_variants])

            if business_type:
                query += " AND s.category = %s"
                params.append(business_type)

            if min_price is not None:
                query += " AND o.discount_price >= %s"
                params.append(min_price)
            if max_price is not None:
                query += " AND o.discount_price <= %s"
                params.append(max_price)
            if min_discount is not None:
                query += (
                    " AND o.original_price > 0"
                    " AND (1.0 - o.discount_price::numeric / o.original_price::numeric) * 100 >= %s"
                )
                params.append(min_discount)

            order_by = (
                "discount_percent DESC, COALESCE(o.expiry_date, '9999-12-31') ASC, o.created_at DESC"
            )
            if sort_by:
                sort_key = sort_by.lower()
                if sort_key == "price_asc":
                    order_by = "o.discount_price ASC, o.created_at DESC"
                elif sort_key == "price_desc":
                    order_by = "o.discount_price DESC, o.created_at DESC"
                elif sort_key == "new":
                    order_by = "o.offer_id DESC"
                elif sort_key == "discount":
                    order_by = (
                        "discount_percent DESC, COALESCE(o.expiry_date, '9999-12-31') ASC, o.created_at DESC"
                    )

            query += f"""
                ORDER BY {order_by}
                LIMIT %s OFFSET %s
            """
            params.extend([limit, offset])

            cursor.execute(query, params)
            return [dict(row) for row in cursor.fetchall()]

    def count_hot_offers(
        self,
        city: str | None = None,
        business_type: str | None = None,
        region: str | None = None,
        district: str | None = None,
    ) -> int:
        """Count hot offers without loading data."""
        with self.get_connection() as conn:
            cursor = conn.cursor()

            query = """
                SELECT COUNT(*)
                FROM offers o
                JOIN stores s ON o.store_id = s.store_id
                WHERE o.status = 'active'
                  AND COALESCE(o.stock_quantity, o.quantity) > 0
                  AND s.status = 'active'
            """
            params = []

            if city:
                city_variants = self._get_city_variants(city)
                city_conditions = " OR ".join(["s.city ILIKE %s" for _ in city_variants])
                query += f" AND ({city_conditions})"
                params.extend([f"%{v}%" for v in city_variants])

            if region:
                region_variants = self._get_location_variants(region)
                region_conditions = " OR ".join(["s.region ILIKE %s" for _ in region_variants])
                query += f" AND ({region_conditions})"
                params.extend([f"%{v}%" for v in region_variants])

            if district:
                district_variants = self._get_location_variants(district)
                district_conditions = " OR ".join(
                    ["s.district ILIKE %s" for _ in district_variants]
                )
                query += f" AND ({district_conditions})"
                params.extend([f"%{v}%" for v in district_variants])

            if business_type:
                query += " AND s.business_type = %s"
                params.append(business_type)

            cursor.execute(query, params)
            return cursor.fetchone()[0]

    def get_nearby_offers(
        self,
        latitude: float,
        longitude: float,
        limit: int = 20,
        offset: int = 0,
        category: str | None = None,
        business_type: str | None = None,
        max_distance_km: float | None = None,
        sort_by: str | None = None,
        min_price: float | None = None,
        max_price: float | None = None,
        min_discount: float | None = None,
    ) -> list[dict]:
        """Get offers nearest to the provided coordinates."""
        with self.get_connection() as conn:
            cursor = conn.cursor(row_factory=dict_row)
            distance_expr = (
                "6371 * 2 * ASIN(SQRT("
                "POWER(SIN(RADIANS(%s - s.latitude) / 2), 2) + "
                "COS(RADIANS(s.latitude)) * COS(RADIANS(%s)) * "
                "POWER(SIN(RADIANS(%s - s.longitude) / 2), 2)"
                "))"
            )
            query = f"""
                SELECT * FROM (
                    SELECT o.*, s.name as store_name, s.address, s.city, s.category as store_category,
                           s.delivery_enabled, s.delivery_price, s.min_order_amount,
                           CASE WHEN o.original_price > 0 THEN CAST((1.0 - o.discount_price::numeric / o.original_price::numeric) * 100 AS INTEGER) ELSE 0 END as discount_percent,
                           {distance_expr} as distance_km
                    FROM offers o
                    JOIN stores s ON o.store_id = s.store_id
                    WHERE o.status = 'active'
                      AND COALESCE(o.stock_quantity, o.quantity) > 0
                      AND (s.status = 'approved' OR s.status = 'active')
                      AND (o.expiry_date IS NULL OR o.expiry_date >= CURRENT_DATE)
                      AND s.latitude IS NOT NULL
                      AND s.longitude IS NOT NULL
                ) as t
            """
            params: list[Any] = [latitude, latitude, longitude]
            where_parts: list[str] = []

            if max_distance_km is not None:
                where_parts.append("t.distance_km <= %s")
                params.append(max_distance_km)
            if category:
                where_parts.append("t.category = %s")
                params.append(category)
            if business_type:
                where_parts.append("t.store_category = %s")
                params.append(business_type)
            if min_price is not None:
                where_parts.append("t.discount_price >= %s")
                params.append(min_price)
            if max_price is not None:
                where_parts.append("t.discount_price <= %s")
                params.append(max_price)
            if min_discount is not None:
                where_parts.append(
                    "t.original_price > 0"
                    " AND (1.0 - t.discount_price::numeric / t.original_price::numeric) * 100 >= %s"
                )
                params.append(min_discount)

            if where_parts:
                query += " WHERE " + " AND ".join(where_parts)

            order_by = "t.distance_km ASC, t.discount_percent DESC, t.created_at DESC"
            if sort_by:
                sort_key = sort_by.lower()
                if sort_key == "price_asc":
                    order_by = "t.distance_km ASC, t.discount_price ASC, t.created_at DESC"
                elif sort_key == "price_desc":
                    order_by = "t.distance_km ASC, t.discount_price DESC, t.created_at DESC"
                elif sort_key == "new":
                    order_by = "t.distance_km ASC, t.offer_id DESC"
                elif sort_key == "discount":
                    order_by = "t.distance_km ASC, t.discount_percent DESC, t.created_at DESC"

            query += f" ORDER BY {order_by} LIMIT %s OFFSET %s"
            params.extend([limit, offset])

            cursor.execute(query, params)
            return [dict(row) for row in cursor.fetchall()]

    def get_offers_by_store(self, store_id: int, include_all: bool = False):
        """
        Get offers for store with store info.

        Args:
            store_id: The store ID
            include_all: If True, includes out-of-stock and expired products (for partner panel).
                        If False, only active products with stock (for customers).
        """
        with self.get_connection() as conn:
            cursor = conn.cursor(row_factory=dict_row)

            if include_all:
                # Partner panel: show ALL products except deleted (inactive)
                cursor.execute(
                    """
                    SELECT o.*, s.name, s.address, s.city, s.category as store_category, o.category as category
                    FROM offers o
                    JOIN stores s ON o.store_id = s.store_id
                    WHERE o.store_id = %s AND o.status != 'inactive'
                    ORDER BY o.created_at DESC
                """,
                    (store_id,),
                )
            else:
                # Customer view: only active products with stock and not expired
                cursor.execute(
                    """
                    SELECT o.*, s.name, s.address, s.city, s.category as store_category, o.category as category
                    FROM offers o
                    JOIN stores s ON o.store_id = s.store_id
                    WHERE o.store_id = %s AND COALESCE(o.stock_quantity, o.quantity) > 0 AND o.status = 'active'
                    AND (o.expiry_date IS NULL OR o.expiry_date >= CURRENT_DATE)
                    ORDER BY o.created_at DESC
                """,
                    (store_id,),
                )
            return [dict(row) for row in cursor.fetchall()]

    def get_top_offers_by_city(self, city: str, limit: int = 10):
        """Get top offers in city (by discount)."""
        with self.get_connection() as conn:
            cursor = conn.cursor(row_factory=dict_row)
            city_variants = self._get_city_variants(city)
            city_conditions = " OR ".join(["s.city ILIKE %s" for _ in city_variants])
            params = [f"%{v}%" for v in city_variants]
            params.append(limit)
            cursor.execute(
                f"""
                SELECT o.*, s.name, s.address, s.city, s.category,
                       CAST((o.original_price - o.discount_price) * 100.0 / o.original_price AS INTEGER) as discount_percent
                FROM offers o
                JOIN stores s ON o.store_id = s.store_id
                WHERE ({city_conditions}) AND s.status = 'active'
                      AND o.status = 'active' AND COALESCE(o.stock_quantity, o.quantity) > 0
                      AND (o.expiry_date IS NULL OR o.expiry_date >= CURRENT_DATE)
                ORDER BY discount_percent DESC, o.created_at DESC
                LIMIT %s
            """,
                tuple(params),
            )
            return [dict(row) for row in cursor.fetchall()]

    def get_offers_by_city_and_category(
        self,
        city: str | None,
        category: str,
        limit: int = 20,
        offset: int = 0,
        region: str | None = None,
        district: str | None = None,
        sort_by: str | None = None,
        min_price: float | None = None,
        max_price: float | None = None,
        min_discount: float | None = None,
    ) -> list[dict]:
        """Get offers by city and category."""
        with self.get_connection() as conn:
            cursor = conn.cursor(row_factory=dict_row)
            query = """
                SELECT o.*, s.name as store_name, s.address, s.city,
                       CASE WHEN o.original_price > 0 THEN CAST((1.0 - o.discount_price::numeric / o.original_price::numeric) * 100 AS INTEGER) ELSE 0 END as discount_percent
                FROM offers o
                JOIN stores s ON o.store_id = s.store_id
                WHERE o.category = %s
                  AND o.status = 'active'
                  AND COALESCE(o.stock_quantity, o.quantity) > 0
                  AND (o.expiry_date IS NULL OR o.expiry_date >= CURRENT_DATE)
                  AND (s.status = 'approved' OR s.status = 'active')
            """
            params = [category]

            if city:
                city_variants = self._get_city_variants(city)
                city_conditions = " OR ".join(["s.city ILIKE %s" for _ in city_variants])
                query += f" AND ({city_conditions})"
                params.extend([f"%{v}%" for v in city_variants])

            if region:
                region_variants = self._get_location_variants(region)
                region_conditions = " OR ".join(["s.region ILIKE %s" for _ in region_variants])
                query += f" AND ({region_conditions})"
                params.extend([f"%{v}%" for v in region_variants])

            if district:
                district_variants = self._get_location_variants(district)
                district_conditions = " OR ".join(
                    ["s.district ILIKE %s" for _ in district_variants]
                )
                query += f" AND ({district_conditions})"
                params.extend([f"%{v}%" for v in district_variants])

            if min_price is not None:
                query += " AND o.discount_price >= %s"
                params.append(min_price)
            if max_price is not None:
                query += " AND o.discount_price <= %s"
                params.append(max_price)
            if min_discount is not None:
                query += (
                    " AND o.original_price > 0"
                    " AND (1.0 - o.discount_price::numeric / o.original_price::numeric) * 100 >= %s"
                )
                params.append(min_discount)

            order_by = "o.created_at DESC"
            if sort_by:
                sort_key = sort_by.lower()
                if sort_key == "discount":
                    order_by = "discount_percent DESC, o.created_at DESC"
                elif sort_key == "price_asc":
                    order_by = "o.discount_price ASC, o.created_at DESC"
                elif sort_key == "price_desc":
                    order_by = "o.discount_price DESC, o.created_at DESC"
                elif sort_key == "new":
                    order_by = "o.offer_id DESC"

            query += f"""
                ORDER BY {order_by}
                LIMIT %s OFFSET %s
            """
            params.extend([limit, offset])

            cursor.execute(query, params)
            return [dict(row) for row in cursor.fetchall()]

    def update_offer_quantity(self, offer_id: int, quantity: int):
        """Update offer quantity."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE offers
                SET quantity = %s,
                    stock_quantity = %s,
                    status = CASE
                        WHEN %s <= 0 AND status IN ('active','out_of_stock') THEN 'out_of_stock'
                        WHEN %s > 0 AND status = 'out_of_stock' THEN 'active'
                        ELSE status
                    END
                WHERE offer_id = %s
                """,
                (quantity, quantity, quantity, quantity, offer_id),
            )

    def increment_offer_quantity(self, offer_id: int, amount: int = 1):
        """Increment offer quantity."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE offers
                SET quantity = quantity + %s,
                    stock_quantity = COALESCE(stock_quantity, quantity, 0) + %s,
                    status = CASE
                        WHEN COALESCE(stock_quantity, quantity, 0) + %s <= 0
                             AND status IN ('active','out_of_stock') THEN 'out_of_stock'
                        WHEN COALESCE(stock_quantity, quantity, 0) + %s > 0
                             AND status = 'out_of_stock' THEN 'active'
                        ELSE status
                    END
                WHERE offer_id = %s
            """,
                (amount, amount, amount, amount, offer_id),
            )
            logger.info(f"Offer {offer_id} quantity increased by {amount}")

    def increment_offer_quantity_atomic(self, offer_id: int, amount: int = 1) -> int:
        """Atomically increment and return new quantity."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE offers
                SET quantity = quantity + %s,
                    stock_quantity = COALESCE(stock_quantity, quantity, 0) + %s,
                    status = CASE
                        WHEN COALESCE(stock_quantity, quantity, 0) + %s <= 0
                             AND status IN ('active','out_of_stock') THEN 'out_of_stock'
                        WHEN COALESCE(stock_quantity, quantity, 0) + %s > 0
                             AND status = 'out_of_stock' THEN 'active'
                        ELSE status
                    END
                WHERE offer_id = %s
                RETURNING quantity
            """,
                (amount, amount, amount, amount, offer_id),
            )
            result = cursor.fetchone()
            new_qty = result[0] if result else 0
            logger.info(f"Offer {offer_id} quantity atomically increased to {new_qty}")
            return new_qty

    def activate_offer(self, offer_id: int):
        """Activate offer."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE offers SET status = 'active' WHERE offer_id = %s", (offer_id,))

    def deactivate_offer(self, offer_id: int):
        """Deactivate offer."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE offers SET status = 'inactive' WHERE offer_id = %s", (offer_id,))

    def delete_offer(self, offer_id: int):
        """Delete offer and all related records."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            # Delete from all tables that reference this offer (in correct order)
            # First get all booking_ids for this offer to delete their ratings
            cursor.execute("SELECT booking_id FROM bookings WHERE offer_id = %s", (offer_id,))
            booking_ids = [row[0] for row in cursor.fetchall()]
            if booking_ids:
                # Delete ratings that reference these bookings
                cursor.execute("DELETE FROM ratings WHERE booking_id = ANY(%s)", (booking_ids,))
            # Now delete in correct FK order
            cursor.execute("DELETE FROM recently_viewed WHERE offer_id = %s", (offer_id,))
            cursor.execute("DELETE FROM orders WHERE offer_id = %s", (offer_id,))
            cursor.execute("DELETE FROM bookings WHERE offer_id = %s", (offer_id,))
            cursor.execute("DELETE FROM favorites WHERE offer_id = %s", (offer_id,))
            cursor.execute("DELETE FROM offers WHERE offer_id = %s", (offer_id,))
            logger.info(f"Offer {offer_id} and related records deleted")

    def update_offer_expiry(self, offer_id: int, new_expiry: str):
        """Update offer expiry date."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE offers SET expiry_date = %s WHERE offer_id = %s", (new_expiry, offer_id)
            )

    def delete_expired_offers(self):
        """Delete expired offers."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE offers
                SET status = 'expired'
                WHERE status = 'active'
                AND expiry_date IS NOT NULL
                AND expiry_date < CURRENT_DATE
                RETURNING offer_id
            """
            )
            expired = cursor.fetchall()
            if expired:
                logger.info(f"Marked {len(expired)} offers as expired")
            return len(expired)
