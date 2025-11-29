"""
Offer-related database operations.
"""
from __future__ import annotations

from typing import Any

from psycopg.rows import dict_row

try:
    from logging_config import logger
except ImportError:
    import logging

    logger = logging.getLogger(__name__)

# Маппинг городов: латиница <-> кириллица
CITY_TRANSLITERATION = {
    # Основные города
    'toshkent': ['ташкент', 'tashkent'],
    'samarqand': ['самарканд', 'samarkand'],
    'buxoro': ['бухара', 'bukhara'],
    "farg'ona": ['фергана', 'fergana'],
    'andijon': ['андижан', 'andijan'],
    'namangan': ['наманган'],
    'navoiy': ['навои', 'navoi'],
    'qarshi': ['карши', 'karshi'],
    'nukus': ['нукус'],
    'urganch': ['ургенч', 'urgench'],
    'jizzax': ['джизак', 'jizzakh'],
    'termiz': ['термез', 'termez'],
    'guliston': ['гулистан', 'gulistan'],
    "chirchiq": ['чирчик', 'chirchik'],
    "kattaqo'rg'on": ['каттакурган', 'kattakurgan', 'kattaqurgan'],
    'olmaliq': ['алмалык', 'almalyk'],
    'angren': ['ангрен'],
    'bekobod': ['бекабад', 'bekabad'],
    'shahrisabz': ['шахрисабз'],
    "marg'ilon": ['маргилан', 'margilan'],
    "qo'qon": ['коканд', 'kokand'],
    'xiva': ['хива', 'khiva'],
    # Кириллица -> латиница
    'ташкент': ['toshkent', 'tashkent'],
    'самарканд': ['samarqand', 'samarkand'],
    'бухара': ['buxoro', 'bukhara'],
    'фергана': ["farg'ona", 'fergana'],
    'андижан': ['andijon', 'andijan'],
    'наманган': ['namangan'],
    'навои': ['navoiy', 'navoi'],
    'карши': ['qarshi', 'karshi'],
    'нукус': ['nukus'],
    'ургенч': ['urganch', 'urgench'],
    'джизак': ['jizzax', 'jizzakh'],
    'термез': ['termiz', 'termez'],
    'гулистан': ['guliston', 'gulistan'],
    'чирчик': ['chirchiq', 'chirchik'],
    'каттакурган': ["kattaqo'rg'on", 'kattakurgan', 'kattaqurgan'],
}


class OfferMixin:
    """Mixin for offer-related database operations."""

    def _get_city_variants(self, city: str) -> list[str]:
        """Get all variants of city name (transliteration)."""
        city_lower = city.lower().strip()
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

    def add_offer(
        self,
        store_id: int,
        title: str,
        description: str = None,
        original_price: float = None,
        discount_price: float = None,
        quantity: int = 1,
        available_from: str = None,
        available_until: str = None,
        photo_id: str = None,
        expiry_date: str = None,
        unit: str = "шт",
        category: str = "other",
        photo: str = None,
    ):
        """Add new offer."""
        actual_photo_id = photo if photo is not None else photo_id

        # Normalize expiry_date format
        if expiry_date and "." in expiry_date:
            try:
                from datetime import datetime

                dt = datetime.strptime(expiry_date, "%d.%m.%Y")
                expiry_date = dt.strftime("%Y-%m-%d")
            except ValueError:
                pass

        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO offers (store_id, title, description, original_price, discount_price,
                                  quantity, available_from, available_until, expiry_date, photo_id, unit, category)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING offer_id
            """,
                (
                    store_id,
                    title,
                    description,
                    original_price,
                    discount_price,
                    quantity,
                    available_from,
                    available_until,
                    expiry_date,
                    actual_photo_id,
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

    def get_store_offers(self, store_id: int, status: str = "active"):
        """Get all offers for a store (excluding expired)."""
        with self.get_connection() as conn:
            cursor = conn.cursor(row_factory=dict_row)
            cursor.execute(
                """
                SELECT * FROM offers
                WHERE store_id = %s
                AND status = %s
                AND (expiry_date IS NULL
                     OR expiry_date !~ '[.]'
                     OR (expiry_date ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}' AND expiry_date::date >= CURRENT_DATE))
                ORDER BY created_at DESC
            """,
                (store_id, status),
            )
            return [dict(row) for row in cursor.fetchall()]

    def get_active_offers(
        self, city: str | None = None, store_id: int | None = None
    ) -> list[dict[str, Any]]:
        """Return active offers, optionally filtered by city or store."""
        with self.get_connection() as conn:
            cursor = conn.cursor(row_factory=dict_row)
            base = [
                "SELECT o.*, s.city FROM offers o JOIN stores s ON o.store_id = s.store_id WHERE o.status = 'active'"
            ]
            params = []
            if city:
                base.append("AND s.city = %s")
                params.append(city)
            if store_id:
                base.append("AND o.store_id = %s")
                params.append(store_id)
            base.append("ORDER BY o.created_at DESC")
            query = " ".join(base)
            cursor.execute(query, tuple(params))
            return list(cursor.fetchall())

    def get_hot_offers(
        self, city: str = None, limit: int = 20, offset: int = 0, business_type: str = None
    ):
        """Get hot offers (top by discount and expiry date)."""
        with self.get_connection() as conn:
            cursor = conn.cursor(row_factory=dict_row)

            query = """
                SELECT o.*, s.name as store_name, s.address, s.city, s.category as store_category,
                       s.delivery_enabled, s.delivery_price, s.min_order_amount,
                       CAST((1.0 - o.discount_price::float / o.original_price::float) * 100 AS INTEGER) as discount_percent
                FROM offers o
                JOIN stores s ON o.store_id = s.store_id
                WHERE o.status = 'active'
                AND o.quantity > 0
                AND (s.status = 'approved' OR s.status = 'active')
                AND (o.available_until IS NULL OR LENGTH(o.available_until) < 6 OR
                     (LENGTH(o.available_until) > 10 AND o.available_until::timestamp >= NOW()))
                AND (o.expiry_date IS NULL
                     OR o.expiry_date !~ '[.]'
                     OR (o.expiry_date ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}' AND o.expiry_date::date >= CURRENT_DATE))
            """

            params = []
            if city:
                # Поддержка транслитерации: ищем и латиницу и кириллицу
                city_variants = self._get_city_variants(city)
                city_conditions = " OR ".join(["s.city ILIKE %s" for _ in city_variants])
                query += f" AND ({city_conditions})"
                params.extend([f"%{v}%" for v in city_variants])

            if business_type:
                query += " AND s.category = %s"
                params.append(business_type)

            query += """
                ORDER BY discount_percent DESC,
                         COALESCE(o.expiry_date, '9999-12-31') ASC,
                         o.created_at DESC
                LIMIT %s OFFSET %s
            """
            params.extend([limit, offset])

            cursor.execute(query, params)
            return [dict(row) for row in cursor.fetchall()]

    def count_hot_offers(self, city: str = None, business_type: str = None) -> int:
        """Count hot offers without loading data."""
        with self.get_connection() as conn:
            cursor = conn.cursor()

            query = """
                SELECT COUNT(*)
                FROM offers o
                JOIN stores s ON o.store_id = s.store_id
                WHERE o.status = 'active'
                  AND o.quantity > 0
                  AND s.status = 'active'
                  AND (o.available_until IS NULL OR LENGTH(o.available_until) < 6 OR
                       (LENGTH(o.available_until) > 10 AND o.available_until::timestamp >= NOW()))
            """
            params = []

            if city:
                city_variants = self._get_city_variants(city)
                city_conditions = " OR ".join(["s.city ILIKE %s" for _ in city_variants])
                query += f" AND ({city_conditions})"
                params.extend([f"%{v}%" for v in city_variants])

            if business_type:
                query += " AND s.business_type = %s"
                params.append(business_type)

            cursor.execute(query, params)
            return cursor.fetchone()[0]

    def get_offers_by_store(self, store_id: int):
        """Get active offers for store with store info."""
        with self.get_connection() as conn:
            cursor = conn.cursor(row_factory=dict_row)
            cursor.execute(
                """
                SELECT o.*, s.name, s.address, s.city, s.category as store_category, o.category as category
                FROM offers o
                JOIN stores s ON o.store_id = s.store_id
                WHERE o.store_id = %s AND o.quantity > 0
                AND (o.expiry_date IS NULL
                     OR o.expiry_date !~ '[.]'
                     OR (o.expiry_date ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}' AND o.expiry_date::date >= CURRENT_DATE))
                ORDER BY o.created_at DESC
            """,
                (store_id,),
            )
            return [dict(row) for row in cursor.fetchall()]

    def get_top_offers_by_city(self, city: str, limit: int = 10):
        """Get top offers in city (by discount)."""
        with self.get_connection() as conn:
            cursor = conn.cursor(row_factory=dict_row)
            cursor.execute(
                """
                SELECT o.*, s.name, s.address, s.city, s.category,
                       CAST((o.original_price - o.discount_price)::float / o.original_price * 100 AS INTEGER) as discount_percent
                FROM offers o
                JOIN stores s ON o.store_id = s.store_id
                WHERE s.city = %s AND s.status = 'active'
                      AND o.status = 'active' AND o.quantity > 0
                      AND (o.expiry_date IS NULL
                           OR o.expiry_date !~ '[.]'
                           OR (o.expiry_date ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}' AND o.expiry_date::date >= CURRENT_DATE))
                ORDER BY discount_percent DESC, o.created_at DESC
                LIMIT %s
            """,
                (city, limit),
            )
            return [dict(row) for row in cursor.fetchall()]

    def get_offers_by_city_and_category(
        self, city: str, category: str, limit: int = 20
    ) -> list[dict]:
        """Get offers by city and category."""
        with self.get_connection() as conn:
            cursor = conn.cursor(row_factory=dict_row)
            if city:
                cursor.execute(
                    """
                    SELECT o.*, s.name as store_name, s.address
                    FROM offers o
                    JOIN stores s ON o.store_id = s.store_id
                    WHERE s.city = %s AND o.category = %s AND o.status = 'active'
                    ORDER BY o.created_at DESC
                    LIMIT %s
                """,
                    (city, category, limit),
                )
            else:
                # No city filter - return all categories
                cursor.execute(
                    """
                    SELECT o.*, s.name as store_name, s.address
                    FROM offers o
                    JOIN stores s ON o.store_id = s.store_id
                    WHERE o.category = %s AND o.status = 'active'
                    ORDER BY o.created_at DESC
                    LIMIT %s
                """,
                    (category, limit),
                )
            return [dict(row) for row in cursor.fetchall()]

    def update_offer_quantity(self, offer_id: int, quantity: int):
        """Update offer quantity."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE offers SET quantity = %s WHERE offer_id = %s", (quantity, offer_id)
            )

    def increment_offer_quantity(self, offer_id: int, amount: int = 1):
        """Increment offer quantity."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE offers
                SET quantity = quantity + %s
                WHERE offer_id = %s
            """,
                (amount, offer_id),
            )
            logger.info(f"Offer {offer_id} quantity increased by {amount}")

    def increment_offer_quantity_atomic(self, offer_id: int, amount: int = 1) -> int:
        """Atomically increment and return new quantity."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE offers
                SET quantity = quantity + %s
                WHERE offer_id = %s
                RETURNING quantity
            """,
                (amount, offer_id),
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
        """Delete offer."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM bookings WHERE offer_id = %s", (offer_id,))
            cursor.execute("DELETE FROM offers WHERE offer_id = %s", (offer_id,))
            logger.info(f"Offer {offer_id} deleted")

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
                AND expiry_date ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}'
                AND expiry_date::date < CURRENT_DATE
                RETURNING offer_id
            """
            )
            expired = cursor.fetchall()
            if expired:
                logger.info(f"Marked {len(expired)} offers as expired")
            return len(expired)
