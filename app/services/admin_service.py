"""Admin services encapsulating statistics queries and DTOs."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, List, Tuple

from app.repositories import BookingRepository, OfferRepository, StoreRepository, UserRepository


@dataclass(slots=True)
class UserStats:
    total: int
    sellers: int
    customers: int
    week_users: int
    today_users: int


@dataclass(slots=True)
class StoreStats:
    active: int
    pending: int
    rejected: int


@dataclass(slots=True)
class OfferStats:
    active: int
    inactive: int
    deleted: int
    top_categories: List[Tuple[str, int]]


@dataclass(slots=True)
class BookingStats:
    total: int
    pending: int
    completed: int
    cancelled: int
    today_bookings: int
    today_revenue: float


class AdminService:
    """Provide aggregated information for admin dashboards."""

    def __init__(
        self, 
        db: Any, 
        use_postgres: bool,
        user_repo: UserRepository | None = None,
        store_repo: StoreRepository | None = None,
        offer_repo: OfferRepository | None = None,
        booking_repo: BookingRepository | None = None,
    ):
        self._db: Any = db
        self._use_postgres = use_postgres
        # Initialize repositories if not provided
        self._user_repo = user_repo or UserRepository(db)
        self._store_repo = store_repo or StoreRepository(db)
        self._offer_repo = offer_repo or OfferRepository(db)
        self._booking_repo = booking_repo or BookingRepository(db)

    @property
    def placeholder(self) -> str:
        return "%s" if self._use_postgres else "?"

    def is_admin(self, user_id: int) -> bool:
        return self._db.is_admin(user_id)

    @staticmethod
    def _fetch_value(row: Tuple[Any, ...] | None) -> int:
        if not row:
            return 0
        value = row[0]
        return int(value) if value is not None else 0

    def get_user_stats(self) -> UserStats:
        from datetime import datetime

        today = datetime.now().strftime("%Y-%m-%d")
        with self._db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM users")
            total = self._fetch_value(cursor.fetchone())

            cursor.execute("SELECT COUNT(*) FROM users WHERE role = 'seller'")
            sellers = self._fetch_value(cursor.fetchone())

            cursor.execute("SELECT COUNT(*) FROM users WHERE role = 'customer'")
            customers = self._fetch_value(cursor.fetchone())

            if self._use_postgres:
                cursor.execute("SELECT COUNT(*) FROM users WHERE created_at >= CURRENT_DATE - INTERVAL '7 days'")
                week_users = self._fetch_value(cursor.fetchone())
                cursor.execute("SELECT COUNT(*) FROM users WHERE DATE(created_at) = %s", (today,))
                today_users = self._fetch_value(cursor.fetchone())
            else:
                cursor.execute(
                    """
                    SELECT COUNT(*) FROM users
                    WHERE DATE(created_at) >= DATE('now', '-7 days')
                    """
                )
                week_users = self._fetch_value(cursor.fetchone())
                cursor.execute("SELECT COUNT(*) FROM users WHERE DATE(created_at) = ?", (today,))
                today_users = self._fetch_value(cursor.fetchone())

        return UserStats(
            total=total,
            sellers=sellers,
            customers=customers,
            week_users=week_users,
            today_users=today_users,
        )

    def get_store_stats(self) -> StoreStats:
        query = f"SELECT COUNT(*) FROM stores WHERE status = {self.placeholder}"
        with self._db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, ("active",))
            active = self._fetch_value(cursor.fetchone())
            cursor.execute(query, ("pending",))
            pending = self._fetch_value(cursor.fetchone())
            cursor.execute(query, ("rejected",))
            rejected = self._fetch_value(cursor.fetchone())
        return StoreStats(active=active, pending=pending, rejected=rejected)

    def get_offer_stats(self) -> OfferStats:
        query = f"SELECT COUNT(*) FROM offers WHERE status = {self.placeholder}"
        with self._db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, ("active",))
            active = self._fetch_value(cursor.fetchone())
            cursor.execute(query, ("inactive",))
            inactive = self._fetch_value(cursor.fetchone())
            cursor.execute(query, ("deleted",))
            deleted = self._fetch_value(cursor.fetchone())
            cursor.execute(
                """
                SELECT category, COUNT(*) as cnt
                FROM offers
                WHERE status = 'active' AND category IS NOT NULL
                GROUP BY category
                ORDER BY cnt DESC
                LIMIT 5
                """
            )
            rows: List[Tuple[Any, Any]] = cursor.fetchall() or []
            top_categories: List[Tuple[str, int]] = [
                (str(row[0]), int(row[1])) for row in rows if row and row[0] is not None and row[1] is not None
            ]
        return OfferStats(active=active, inactive=inactive, deleted=deleted, top_categories=top_categories)

    def get_booking_stats(self) -> BookingStats:
        from datetime import datetime

        today = datetime.now().strftime("%Y-%m-%d")
        status_query = f"SELECT COUNT(*) FROM bookings WHERE status = {self.placeholder}"
        with self._db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM bookings")
            total = self._fetch_value(cursor.fetchone())

            cursor.execute(status_query, ("pending",))
            pending = self._fetch_value(cursor.fetchone())
            cursor.execute(status_query, ("completed",))
            completed = self._fetch_value(cursor.fetchone())
            cursor.execute(status_query, ("cancelled",))
            cancelled = self._fetch_value(cursor.fetchone())

            date_query = "SELECT COUNT(*) FROM bookings WHERE DATE(created_at) = %s" if self._use_postgres else "SELECT COUNT(*) FROM bookings WHERE DATE(created_at) = ?"
            cursor.execute(date_query, (today,))
            today_bookings = self._fetch_value(cursor.fetchone())

            revenue_query = (
                """
                SELECT SUM(o.discount_price * b.quantity)
                FROM bookings b
                JOIN offers o ON b.offer_id = o.offer_id
                WHERE DATE(b.created_at) = %s AND b.status != 'cancelled'
                """
                if self._use_postgres
                else
                """
                SELECT SUM(o.discount_price * b.quantity)
                FROM bookings b
                JOIN offers o ON b.offer_id = o.offer_id
                WHERE DATE(b.created_at) = ? AND b.status != 'cancelled'
                """
            )
            cursor.execute(revenue_query, (today,))
            row = cursor.fetchone()
            today_revenue = float(row[0]) if row and row[0] is not None else 0.0

        return BookingStats(
            total=total,
            pending=pending,
            completed=completed,
            cancelled=cancelled,
            today_bookings=today_bookings,
            today_revenue=today_revenue,
        )
