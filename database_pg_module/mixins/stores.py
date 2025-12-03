"""
Store-related database operations.
"""
from __future__ import annotations

from typing import Any

from psycopg.rows import dict_row

try:
    from logging_config import logger
except ImportError:
    import logging

    logger = logging.getLogger(__name__)


class StoreMixin:
    """Mixin for store-related database operations."""

    def add_store(
        self,
        owner_id: int,
        name: str,
        city: str,
        address: str | None = None,
        description: str | None = None,
        category: str = "Ресторан",
        phone: str | None = None,
        business_type: str = "supermarket",
        photo: str | None = None,
    ) -> int:
        """Add new store."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO stores (owner_id, name, city, address, description, category, phone, business_type, photo)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING store_id
            """,
                (owner_id, name, city, address, description, category, phone, business_type, photo),
            )
            store_id = cursor.fetchone()[0]
            logger.info(
                f"Store {store_id} added by user {owner_id}" + (" with photo" if photo else "")
            )
            return store_id

    def get_store(self, store_id: int):
        """Get store by ID."""
        with self.get_connection() as conn:
            cursor = conn.cursor(row_factory=dict_row)
            cursor.execute("SELECT * FROM stores WHERE store_id = %s", (store_id,))
            result = cursor.fetchone()
            return dict(result) if result else None

    def get_store_by_owner(self, owner_id: int):
        """Get store by owner ID."""
        with self.get_connection() as conn:
            cursor = conn.cursor(row_factory=dict_row)
            cursor.execute("SELECT * FROM stores WHERE owner_id = %s", (owner_id,))
            result = cursor.fetchone()
            return dict(result) if result else None

    def get_store_model(self, store_id: int) -> Any | None:
        """Get store as Pydantic model."""
        try:
            from app.domain import Store
        except ImportError:
            logger.error("Domain models not available. Install pydantic.")
            return None

        store_dict = self.get_store(store_id)
        if not store_dict:
            return None

        try:
            return Store.from_db_row(store_dict)
        except Exception as e:
            logger.error(f"Failed to convert store {store_id} to model: {e}")
            return None

    def get_user_stores(self, owner_id: int):
        """Get ALL stores for user (any status)."""
        with self.get_connection() as conn:
            cursor = conn.cursor(row_factory=dict_row)
            cursor.execute(
                """
                SELECT s.*, u.first_name, u.username
                FROM stores s
                LEFT JOIN users u ON s.owner_id = u.user_id
                WHERE s.owner_id = %s
                ORDER BY s.created_at DESC
            """,
                (owner_id,),
            )
            return [dict(row) for row in cursor.fetchall()]

    def get_user_accessible_stores(self, user_id: int):
        """Get ALL stores accessible to user (owned + admin access)."""
        with self.get_connection() as conn:
            cursor = conn.cursor(row_factory=dict_row)
            cursor.execute(
                """
                SELECT s.*, u.first_name, u.username,
                       CASE WHEN s.owner_id = %s THEN 'owner' ELSE 'admin' END as user_role
                FROM stores s
                LEFT JOIN users u ON s.owner_id = u.user_id
                WHERE s.owner_id = %s
                   OR s.store_id IN (SELECT store_id FROM store_admins WHERE user_id = %s)
                ORDER BY s.created_at DESC
            """,
                (user_id, user_id, user_id),
            )
            return [dict(row) for row in cursor.fetchall()]

    def get_stores_by_city(self, city: str):
        """Return active stores for a given city."""
        with self.get_connection() as conn:
            cursor = conn.cursor(row_factory=dict_row)
            cursor.execute(
                """
                SELECT store_id, name, address, category, city
                FROM stores
                WHERE city = %s AND status = 'active'
                ORDER BY created_at DESC
            """,
                (city,),
            )
            return list(cursor.fetchall())

    def get_approved_stores(self, city: str = None):
        """Get approved stores, optionally filtered by city."""
        with self.get_connection() as conn:
            cursor = conn.cursor(row_factory=dict_row)
            if city:
                cursor.execute(
                    "SELECT * FROM stores WHERE status = %s AND city = %s", ("approved", city)
                )
            else:
                cursor.execute("SELECT * FROM stores WHERE status = %s", ("approved",))
            return [dict(row) for row in cursor.fetchall()]

    def get_pending_stores(self):
        """Get stores awaiting approval."""
        with self.get_connection() as conn:
            cursor = conn.cursor(row_factory=dict_row)
            cursor.execute(
                """
                SELECT s.*, u.first_name, u.username, u.phone as user_phone
                FROM stores s
                LEFT JOIN users u ON s.owner_id = u.user_id
                WHERE s.status = 'pending'
                ORDER BY s.created_at DESC
            """
            )
            return [dict(row) for row in cursor.fetchall()]

    def get_stores_by_business_type(self, business_type: str, city: str = None):
        """Get stores by business type with offers count."""
        with self.get_connection() as conn:
            cursor = conn.cursor(row_factory=dict_row)
            if city:
                cursor.execute(
                    """
                    SELECT s.*,
                           COALESCE(AVG(r.rating), 0) as avg_rating,
                           COUNT(DISTINCT r.rating_id) as ratings_count,
                           (SELECT COUNT(*) FROM offers o
                            WHERE o.store_id = s.store_id
                            AND o.status = 'active') as offers_count
                    FROM stores s
                    LEFT JOIN ratings r ON s.store_id = r.store_id
                    WHERE s.business_type = %s
                    AND s.city = %s
                    AND (s.status = 'active' OR s.status = 'approved')
                    GROUP BY s.store_id
                    ORDER BY avg_rating DESC, s.created_at DESC
                """,
                    (business_type, city),
                )
            else:
                cursor.execute(
                    """
                    SELECT s.*,
                           COALESCE(AVG(r.rating), 0) as avg_rating,
                           COUNT(DISTINCT r.rating_id) as ratings_count,
                           (SELECT COUNT(*) FROM offers o
                            WHERE o.store_id = s.store_id
                            AND o.status = 'active') as offers_count
                    FROM stores s
                    LEFT JOIN ratings r ON s.store_id = r.store_id
                    WHERE s.business_type = %s
                    AND (s.status = 'active' OR s.status = 'approved')
                    GROUP BY s.store_id
                    ORDER BY avg_rating DESC, s.created_at DESC
                """,
                    (business_type,),
                )
            return [dict(row) for row in cursor.fetchall()]

    def get_stores_by_category(self, category: str, city: str = None) -> list[dict]:
        """Get stores by category."""
        with self.get_connection() as conn:
            cursor = conn.cursor(row_factory=dict_row)
            if city:
                cursor.execute(
                    """
                    SELECT * FROM stores
                    WHERE category = %s AND city = %s
                    AND (status = 'active' OR status = 'approved')
                    ORDER BY created_at DESC
                """,
                    (category, city),
                )
            else:
                cursor.execute(
                    """
                    SELECT * FROM stores
                    WHERE category = %s
                    AND (status = 'active' OR status = 'approved')
                    ORDER BY created_at DESC
                """,
                    (category,),
                )
            return [dict(row) for row in cursor.fetchall()]

    def get_stores_count_by_category(self, city: str) -> dict:
        """Get store counts grouped by category."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT category, COUNT(*) as count
                FROM stores
                WHERE city = %s AND (status = 'active' OR status = 'approved')
                GROUP BY category
            """,
                (city,),
            )
            return dict(cursor.fetchall())

    def get_top_stores_by_city(self, city: str, limit: int = 10) -> list[dict]:
        """Get top rated stores in city."""
        with self.get_connection() as conn:
            cursor = conn.cursor(row_factory=dict_row)
            cursor.execute(
                """
                SELECT s.*,
                       COALESCE(AVG(r.rating), 0) as avg_rating,
                       COUNT(r.rating_id) as ratings_count
                FROM stores s
                LEFT JOIN ratings r ON s.store_id = r.store_id
                WHERE s.city = %s AND s.status = 'active'
                GROUP BY s.store_id
                ORDER BY avg_rating DESC, ratings_count DESC
                LIMIT %s
            """,
                (city, limit),
            )
            return cursor.fetchall()

    def update_store_status(self, store_id: int, status: str, rejection_reason: str = None):
        """Update store status."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE stores SET status = %s, rejection_reason = %s
                WHERE store_id = %s
            """,
                (status, rejection_reason, store_id),
            )

    def approve_store(self, store_id: int):
        """Approve a store."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE stores SET status = 'active' WHERE store_id = %s", (store_id,))
            # Get store owner for notification
            cursor.execute("SELECT owner_id FROM stores WHERE store_id = %s", (store_id,))
            result = cursor.fetchone()
            owner_id = result[0] if result else None

            if owner_id:
                # Update user role
                cursor.execute("UPDATE users SET role = 'seller' WHERE user_id = %s", (owner_id,))

            logger.info(f"Store {store_id} approved")
            return owner_id

    def reject_store(self, store_id: int, reason: str):
        """Reject a store with reason."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE stores SET status = 'rejected', rejection_reason = %s
                WHERE store_id = %s
            """,
                (reason, store_id),
            )
            logger.info(f"Store {store_id} rejected: {reason}")

    def delete_store(self, store_id: int):
        """Delete store and ALL related data (respecting FK constraints)."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Get all offer_ids for this store
            cursor.execute("SELECT offer_id FROM offers WHERE store_id = %s", (store_id,))
            offer_ids = [row[0] for row in cursor.fetchall()]
            
            if offer_ids:
                # Delete ratings that reference bookings of these offers
                cursor.execute(
                    """DELETE FROM ratings WHERE booking_id IN 
                       (SELECT booking_id FROM bookings WHERE offer_id = ANY(%s))""",
                    (offer_ids,)
                )
                # Delete orders referencing these offers
                cursor.execute("DELETE FROM orders WHERE offer_id = ANY(%s)", (offer_ids,))
                # Delete bookings referencing these offers
                cursor.execute("DELETE FROM bookings WHERE offer_id = ANY(%s)", (offer_ids,))
                # Delete recently_viewed referencing these offers
                cursor.execute("DELETE FROM recently_viewed WHERE offer_id = ANY(%s)", (offer_ids,))
            
            # Delete ratings for this store
            cursor.execute("DELETE FROM ratings WHERE store_id = %s", (store_id,))
            # Delete orders for this store
            cursor.execute("DELETE FROM orders WHERE store_id = %s", (store_id,))
            # Delete bookings for this store
            cursor.execute("DELETE FROM bookings WHERE store_id = %s", (store_id,))
            # Delete favorites for this store
            cursor.execute("DELETE FROM favorites WHERE store_id = %s", (store_id,))
            # Delete pickup_slots for this store
            cursor.execute("DELETE FROM pickup_slots WHERE store_id = %s", (store_id,))
            # Delete store_admins for this store
            cursor.execute("DELETE FROM store_admins WHERE store_id = %s", (store_id,))
            # Delete store_payment_integrations for this store
            cursor.execute("DELETE FROM store_payment_integrations WHERE store_id = %s", (store_id,))
            # Delete payment_settings for this store
            cursor.execute("DELETE FROM payment_settings WHERE store_id = %s", (store_id,))
            # Now safe to delete offers
            cursor.execute("DELETE FROM offers WHERE store_id = %s", (store_id,))
            # Finally delete the store
            cursor.execute("DELETE FROM stores WHERE store_id = %s", (store_id,))
            
            logger.info(f"Store {store_id} and ALL related data deleted")

    def get_store_owner(self, store_id: int):
        """Get store owner user_id."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT owner_id FROM stores WHERE store_id = %s", (store_id,))
            result = cursor.fetchone()
            return result[0] if result else None

    def update_store_photo(self, store_id: int, photo: str | None) -> bool:
        """Update store photo."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE stores SET photo = %s WHERE store_id = %s",
                (photo, store_id),
            )
            logger.info(f"Store {store_id} photo updated")
            return True

    def update_store_location(self, store_id: int, latitude: float, longitude: float) -> bool:
        """Update store geolocation coordinates."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE stores SET latitude = %s, longitude = %s WHERE store_id = %s",
                (latitude, longitude, store_id),
            )
            logger.info(f"Store {store_id} location updated to ({latitude}, {longitude})")
            return True

    def get_store_analytics(self, store_id: int) -> dict:
        """Get store analytics."""
        with self.get_connection() as conn:
            cursor = conn.cursor()

            # Total stats
            cursor.execute(
                """
                SELECT
                    COUNT(*) as total_bookings,
                    SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) as completed,
                    SUM(CASE WHEN status = 'cancelled' THEN 1 ELSE 0 END) as cancelled
                FROM bookings b
                JOIN offers o ON b.offer_id = o.offer_id
                WHERE o.store_id = %s
            """,
                (store_id,),
            )
            stats = cursor.fetchone()

            # Sales by day of week
            cursor.execute(
                """
                SELECT
                    EXTRACT(DOW FROM b.created_at)::INTEGER as day_of_week,
                    COUNT(*) as count
                FROM bookings b
                JOIN offers o ON b.offer_id = o.offer_id
                WHERE o.store_id = %s AND b.status = 'completed'
                GROUP BY day_of_week
            """,
                (store_id,),
            )
            days = cursor.fetchall()

            # Popular categories
            cursor.execute(
                """
                SELECT
                    o.category,
                    COUNT(*) as count
                FROM bookings b
                JOIN offers o ON b.offer_id = o.offer_id
                WHERE o.store_id = %s AND b.status = 'completed'
                GROUP BY o.category
                ORDER BY count DESC
                LIMIT 5
            """,
                (store_id,),
            )
            categories = cursor.fetchall()

            # Average rating
            cursor.execute(
                """
                SELECT AVG(rating) as avg_rating, COUNT(*) as rating_count
                FROM ratings
                WHERE store_id = %s
            """,
                (store_id,),
            )
            rating = cursor.fetchone()

            return {
                "total_bookings": stats[0] or 0,
                "completed": stats[1] or 0,
                "cancelled": stats[2] or 0,
                "conversion_rate": (stats[1] / stats[0] * 100) if stats[0] > 0 else 0,
                "days_of_week": dict(days) if days else {},
                "popular_categories": categories or [],
                "avg_rating": rating[0] or 0,
                "rating_count": rating[1] or 0,
            }

    # Payment integration methods
    def get_store_payment_integrations(self, store_id: int) -> list[dict]:
        """Get all payment integrations for a store."""
        with self.get_connection() as conn:
            cursor = conn.cursor(row_factory=dict_row)
            cursor.execute(
                """
                SELECT * FROM store_payment_integrations
                WHERE store_id = %s AND is_active = 1
                ORDER BY provider
            """,
                (store_id,),
            )
            return [dict(row) for row in cursor.fetchall()]

    def get_store_payment_integration(self, store_id: int, provider: str) -> dict | None:
        """Get specific payment integration for a store."""
        with self.get_connection() as conn:
            cursor = conn.cursor(row_factory=dict_row)
            cursor.execute(
                """
                SELECT * FROM store_payment_integrations
                WHERE store_id = %s AND provider = %s AND is_active = 1
            """,
                (store_id, provider),
            )
            result = cursor.fetchone()
            return dict(result) if result else None

    def set_store_payment_integration(
        self,
        store_id: int,
        provider: str,
        merchant_id: str,
        secret_key: str,
        service_id: str | None = None,
    ) -> bool:
        """Set or update payment integration for a store."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO store_payment_integrations
                    (store_id, provider, merchant_id, service_id, secret_key, is_active, updated_at)
                VALUES (%s, %s, %s, %s, %s, 1, CURRENT_TIMESTAMP)
                ON CONFLICT (store_id, provider)
                DO UPDATE SET
                    merchant_id = EXCLUDED.merchant_id,
                    service_id = EXCLUDED.service_id,
                    secret_key = EXCLUDED.secret_key,
                    is_active = 1,
                    updated_at = CURRENT_TIMESTAMP
            """,
                (store_id, provider, merchant_id, service_id, secret_key),
            )
            logger.info(f"Payment integration {provider} set for store {store_id}")
            return True

    def disable_store_payment_integration(self, store_id: int, provider: str) -> bool:
        """Disable payment integration for a store."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE store_payment_integrations
                SET is_active = 0, updated_at = CURRENT_TIMESTAMP
                WHERE store_id = %s AND provider = %s
            """,
                (store_id, provider),
            )
            logger.info(f"Payment integration {provider} disabled for store {store_id}")
            return True

    def get_stores_with_payment_provider(self, provider: str) -> list[dict]:
        """Get all stores that have a specific payment provider enabled."""
        with self.get_connection() as conn:
            cursor = conn.cursor(row_factory=dict_row)
            cursor.execute(
                """
                SELECT s.*, spi.merchant_id, spi.service_id
                FROM stores s
                JOIN store_payment_integrations spi ON s.store_id = spi.store_id
                WHERE spi.provider = %s AND spi.is_active = 1
                AND (s.status = 'active' OR s.status = 'approved')
            """,
                (provider,),
            )
            return [dict(row) for row in cursor.fetchall()]

    # ===================== STORE ADMINS =====================

    def add_store_admin(
        self, store_id: int, user_id: int, added_by: int, role: str = "admin"
    ) -> bool:
        """Add an admin to a store."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute(
                    """
                    INSERT INTO store_admins (store_id, user_id, added_by, role)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (store_id, user_id) DO NOTHING
                    """,
                    (store_id, user_id, added_by, role),
                )
                logger.info(f"Admin {user_id} added to store {store_id} by {added_by}")
                return True
            except Exception as e:
                logger.error(f"Failed to add store admin: {e}")
                return False

    def remove_store_admin(self, store_id: int, user_id: int) -> bool:
        """Remove an admin from a store."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "DELETE FROM store_admins WHERE store_id = %s AND user_id = %s",
                (store_id, user_id),
            )
            logger.info(f"Admin {user_id} removed from store {store_id}")
            return True

    def get_store_admins(self, store_id: int) -> list[dict]:
        """Get all admins for a store."""
        with self.get_connection() as conn:
            cursor = conn.cursor(row_factory=dict_row)
            cursor.execute(
                """
                SELECT sa.*, u.username, u.first_name, u.phone
                FROM store_admins sa
                JOIN users u ON sa.user_id = u.user_id
                WHERE sa.store_id = %s
                ORDER BY sa.created_at
                """,
                (store_id,),
            )
            return [dict(row) for row in cursor.fetchall()]

    def is_store_admin(self, store_id: int, user_id: int) -> bool:
        """Check if user is an admin of the store (owner or added admin)."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            # Check if user is owner
            cursor.execute(
                "SELECT owner_id FROM stores WHERE store_id = %s",
                (store_id,),
            )
            result = cursor.fetchone()
            if result and result[0] == user_id:
                return True

            # Check if user is added admin
            cursor.execute(
                "SELECT 1 FROM store_admins WHERE store_id = %s AND user_id = %s",
                (store_id, user_id),
            )
            return cursor.fetchone() is not None

    def get_user_admin_stores(self, user_id: int) -> list[dict]:
        """Get all stores where user is owner OR admin."""
        with self.get_connection() as conn:
            cursor = conn.cursor(row_factory=dict_row)
            cursor.execute(
                """
                SELECT DISTINCT s.*,
                    CASE WHEN s.owner_id = %s THEN 'owner' ELSE 'admin' END as user_role
                FROM stores s
                LEFT JOIN store_admins sa ON s.store_id = sa.store_id
                WHERE (s.owner_id = %s OR sa.user_id = %s)
                AND (s.status = 'active' OR s.status = 'approved' OR s.status = 'pending')
                ORDER BY s.created_at DESC
                """,
                (user_id, user_id, user_id),
            )
            return [dict(row) for row in cursor.fetchall()]
