from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Optional, List, Dict, Any


@dataclass
class Period:
    start: datetime
    end: datetime
    tz: str


@dataclass
class PartnerTotals:
    revenue: Decimal = Decimal(0)
    orders: int = 0
    items_sold: int = 0
    active_products: int = 0
    avg_ticket: Optional[Decimal] = None
    refunds_amount: Decimal = Decimal(0)
    refunds_count: int = 0


@dataclass
class PartnerStats:
    period: Period
    totals: PartnerTotals


@dataclass
class ChannelBreakdown:
    channel: str
    revenue: Decimal
    orders: int


@dataclass
class TopProduct:
    product_id: int
    name: str
    revenue: Decimal
    qty: int


@dataclass
class TopSeller:
    seller_id: int
    name: str
    revenue: Decimal
    orders: int


@dataclass
class AdminTotals:
    revenue: Decimal = Decimal(0)
    orders: int = 0
    buyers: int = 0
    active_sellers: int = 0
    items_sold: int = 0
    avg_ticket: Optional[Decimal] = None
    refunds_amount: Decimal = Decimal(0)
    refunds_count: int = 0


@dataclass
class AdminBreakdowns:
    by_channel: Optional[List[ChannelBreakdown]] = None
    top_products: Optional[List[TopProduct]] = None
    top_sellers: Optional[List[TopSeller]] = None


@dataclass
class AdminStats:
    period: Period
    totals: AdminTotals
    breakdowns: AdminBreakdowns


@dataclass
class AdminStatsFilters:
    period: Period
    store_id: Optional[int] = None
    city: Optional[str] = None
    category_id: Optional[int] = None
    seller_id: Optional[int] = None


def get_partner_stats(db, partner_id: int, period: Period, tz: str, store_id: Optional[int] = None) -> PartnerStats:
    """
    Aggregate partner statistics for the given period.

    Args:
        db: Database instance.
        partner_id: Current partner ID.
        period: Period with start/end in partner TZ.
        tz: IANA timezone string.
        store_id: Optional store filter (useful for admin-access stores).

    Returns:
        PartnerStats dataclass with totals.
    """
    # Query bookings + orders for revenue, orders, items_sold
    with db.get_connection() as conn:
        cursor = conn.cursor()
        if store_id is not None:
            booking_store_filter = "o.store_id = %s"
            order_store_filter = "ord.store_id = %s"
            offer_store_filter = "o.store_id = %s"
            store_param = store_id
        else:
            booking_store_filter = "o.store_id IN (SELECT store_id FROM stores WHERE owner_id = %s)"
            order_store_filter = "ord.store_id IN (SELECT store_id FROM stores WHERE owner_id = %s)"
            offer_store_filter = "o.store_id IN (SELECT store_id FROM stores WHERE owner_id = %s)"
            store_param = partner_id

        # Revenue and orders: sum of completed bookings (status='completed' or 'confirmed')
        # Items sold: sum(quantity) from bookings
        # Price is from offers.discount_price
        cursor.execute(
            f"""
            SELECT
                COALESCE(SUM(o.discount_price * b.quantity), 0) AS revenue,
                COUNT(DISTINCT b.booking_id) AS orders,
                COALESCE(SUM(b.quantity), 0) AS items_sold
            FROM bookings b
            JOIN offers o ON b.offer_id = o.offer_id
            WHERE {booking_store_filter}
            AND b.status IN ('completed', 'confirmed')
            AND b.created_at >= %s AND b.created_at < %s
            """,
            (store_param, period.start, period.end),
        )
        row = cursor.fetchone() or (0, 0, 0)
        bookings_revenue = Decimal(row[0] or 0)
        bookings_orders = int(row[1] or 0)
        bookings_items_sold = int(row[2] or 0)

        # Revenue and orders from delivery/pickup orders table (completed only)
        cursor.execute(
            f"""
            SELECT
                COALESCE(SUM(ord.total_price), 0) AS revenue,
                COUNT(DISTINCT ord.order_id) AS orders,
                COALESCE(SUM(ord.quantity), 0) AS items_sold
            FROM orders ord
            WHERE {order_store_filter}
            AND ord.order_status = 'completed'
            AND ord.created_at >= %s AND ord.created_at < %s
            """,
            (store_param, period.start, period.end),
        )
        row = cursor.fetchone() or (0, 0, 0)
        orders_revenue = Decimal(row[0] or 0)
        orders_orders = int(row[1] or 0)
        orders_items_sold = int(row[2] or 0)

        revenue = bookings_revenue + orders_revenue
        orders = bookings_orders + orders_orders
        items_sold = bookings_items_sold + orders_items_sold

        # Active products: count active offers from partner's stores
        cursor.execute(
            f"""
            SELECT COUNT(*) FROM offers o
            WHERE {offer_store_filter}
            AND o.status = 'active'
            AND (COALESCE(o.stock_quantity, o.quantity) IS NULL OR COALESCE(o.stock_quantity, o.quantity) > 0)
            """,
            (store_param,),
        )
        active_products = cursor.fetchone()[0] or 0

    avg_ticket = (revenue / orders) if orders > 0 else None
    totals = PartnerTotals(
        revenue=revenue,
        orders=orders,
        items_sold=items_sold,
        active_products=active_products,
        avg_ticket=avg_ticket,
        refunds_amount=Decimal(0),  # TODO: track refunds if needed
        refunds_count=0
    )
    return PartnerStats(period=period, totals=totals)


def get_admin_stats(db, filters: AdminStatsFilters) -> AdminStats:
    """
    Aggregate admin statistics for the given filters.

    Args:
        db: Database instance.
        filters: AdminStatsFilters with period and optional store/city/category/seller filters.

    Returns:
        AdminStats dataclass with totals and breakdowns.
    """
    with db.get_connection() as conn:
        cursor = conn.cursor()
        # Revenue, orders, buyers (distinct users), items_sold from bookings
        # Price is from offers.discount_price
        cursor.execute(
            """
            SELECT
                COALESCE(SUM(o.discount_price * b.quantity), 0) AS revenue,
                COUNT(DISTINCT b.booking_id) AS orders,
                COUNT(DISTINCT b.user_id) AS buyers,
                COALESCE(SUM(b.quantity), 0) AS items_sold
            FROM bookings b
            JOIN offers o ON b.offer_id = o.offer_id
            WHERE b.status IN ('completed', 'confirmed')
            AND b.created_at >= %s AND b.created_at < %s
            """,
            (filters.period.start, filters.period.end)
        )
        row = cursor.fetchone()
        revenue = Decimal(row[0]) if row else Decimal(0)
        orders = int(row[1]) if row else 0
        buyers = int(row[2]) if row else 0
        items_sold = int(row[3]) if row else 0

        # Active sellers: count stores with active offers
        cursor.execute(
            """
            SELECT COUNT(DISTINCT s.owner_id)
            FROM stores s
            JOIN offers o ON s.store_id = o.store_id
            WHERE o.status = 'active' AND s.status = 'approved'
            """
        )
        active_sellers = cursor.fetchone()[0] or 0

    avg_ticket = (revenue / orders) if orders > 0 else None
    totals = AdminTotals(
        revenue=revenue,
        orders=orders,
        buyers=buyers,
        active_sellers=active_sellers,
        items_sold=items_sold,
        avg_ticket=avg_ticket,
        refunds_amount=Decimal(0),
        refunds_count=0
    )
    breakdowns = AdminBreakdowns(by_channel=None, top_products=None, top_sellers=None)
    return AdminStats(period=filters.period, totals=totals, breakdowns=breakdowns)
