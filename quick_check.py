#!/usr/bin/env python3
"""Quick check bookings for user 7969096859"""
import os
import sys
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from database_pg_module import Database

db = Database()
user_id = 7969096859

print(f"Checking bookings for user {user_id}...")
bookings: list[dict[str, Any]] = db.get_user_bookings(user_id)
print(f"Found {len(bookings)} bookings")

for b in bookings:
    bid: Any = b.get("booking_id")
    status: Any = b.get("status")
    title: Any = b.get("title", "N/A")
    print(f"  #{bid} | {status} | {title}")

# Count active
active: list[dict[str, Any]] = [
    b for b in bookings if b.get("status") in ("pending", "confirmed", "active")
]
print(f"\nActive bookings: {len(active)}")

# Cancel all active if requested
if len(sys.argv) > 1 and sys.argv[1] == "--cancel":
    print("\nCancelling all active bookings...")
    for b in active:
        bid = b.get("booking_id")
        if bid is not None:
            try:
                db.cancel_booking(int(bid))
                print(f"  Cancelled #{bid}")
            except Exception as e:
                print(f"  Error cancelling #{bid}: {e}")
