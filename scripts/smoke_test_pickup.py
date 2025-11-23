"""Smoke test for pickup booking flow using local SQLite DB.

This script will:
- create a test store and offer
- create a booking via `create_booking_atomic` with a pickup_time
- check that a booking row was created and the pickup_slots.reserved increased
"""
from __future__ import annotations

import time
from datetime import datetime, timedelta
from pprint import pprint

import sys
from pathlib import Path

# Ensure project root is on sys.path so imports like `database` work when script runs from scripts/
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from database import Database


def iso_future(minutes: int = 30) -> str:
    dt = datetime.now() + timedelta(minutes=minutes)
    return dt.strftime('%Y-%m-%d %H:%M')


def main():
    db = Database()

    # create test user
    user_id = 999999
    db.add_user(user_id, username='smoke_tester', first_name='Smoke')

    # create store
    owner_id = 888888
    db.add_user(owner_id, username='owner', first_name='Owner')
    store_id = db.add_store(owner_id, 'Smoke Store', 'Tashkent', 'Test address')

    # create offer with quantity 5
    offer_id = db.add_offer(store_id, 'Smoke Offer', 'Test', 10000.0, 5000.0, quantity=5, available_from='00:00', available_until='23:59')

    pickup_time = iso_future(20)
    print('Using pickup_time:', pickup_time)

    # Debug: show current offer row
    offer_row = db.get_offer(offer_id)
    print('Offer row before booking:')
    pprint(offer_row)

    # Debug: show any existing pickup_slots for this store
    conn = db.get_connection()
    cur = conn.cursor()
    cur.execute('SELECT slot_id, store_id, slot_ts, capacity, reserved FROM pickup_slots WHERE store_id = ?', (store_id,))
    print('Existing pickup_slots for store:')
    for r in cur.fetchall():
        print(r)
    conn.close()

    ok, booking_id, code = db.create_booking_atomic(offer_id, user_id, quantity=1, pickup_time=pickup_time, pickup_address='Test address')

    print('create_booking_atomic ->', ok, booking_id, code)

    if ok and booking_id:
        booking = db.get_booking(booking_id)
        print('Booking row:')
        pprint(booking)

        # check pickup_slots
        conn = db.get_connection()
        cur = conn.cursor()
        cur.execute('SELECT slot_id, store_id, slot_ts, capacity, reserved FROM pickup_slots WHERE store_id = ? AND slot_ts = ?', (store_id, pickup_time))
        slot = cur.fetchone()
        conn.close()
        print('Slot row:', slot)
    else:
        print('Booking failed; inspect DB or logs for details')


if __name__ == '__main__':
    main()
