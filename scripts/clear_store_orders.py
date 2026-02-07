"""
Clear all orders/bookings/ratings for a store while keeping offers.

Usage:
  python scripts/clear_store_orders.py <store_id>

Requires DATABASE_URL env var.
"""
from __future__ import annotations

import os
import sys

from database_pg import Database


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: python scripts/clear_store_orders.py <store_id>")
        return 1

    try:
        store_id = int(sys.argv[1])
    except ValueError:
        print("store_id must be an integer")
        return 1

    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        print("DATABASE_URL is required")
        return 1

    db = Database(db_url)
    try:
        ok = db.clear_store_orders(store_id)
    finally:
        db.close()

    if ok:
        print(f"Cleared orders/bookings for store {store_id}")
        return 0

    print(f"Failed to clear orders/bookings for store {store_id}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
