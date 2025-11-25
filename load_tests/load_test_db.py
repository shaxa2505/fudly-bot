"""Simple load test for Database.increment_offer_quantity_atomic.

This script:
- Creates a temporary SQLite DB `load_test.db`.
- Adds a store and an offer with an initial quantity.
- Spins up many concurrent workers that decrement the offer quantity (simulate bookings)
  and also some workers that increment (simulate cancellations).
- Verifies that quantity never goes negative and that final quantity matches expected value.

Run with the project's venv Python.
"""
import os
import random

# Ensure project root is on sys.path when running from load_tests/
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from database import Database

DB_PATH = "load_test.db"


def setup_db(path: str):
    if os.path.exists(path):
        os.remove(path)
    db = Database(db_name=path)
    return db


def worker_decrement(db_path: str, offer_id: int, amount: int = 1):
    # Each worker creates its own Database instance/connection
    db = Database(db_name=db_path)
    # Use atomic increment with negative amount to decrement
    try:
        new_qty = db.increment_offer_quantity_atomic(offer_id, -amount)
        return new_qty
    except Exception as e:
        return f"err:{e}"


def worker_increment(db_path: str, offer_id: int, amount: int = 1):
    db = Database(db_name=db_path)
    try:
        new_qty = db.increment_offer_quantity_atomic(offer_id, amount)
        return new_qty
    except Exception as e:
        return f"err:{e}"


def run_load_test(concurrent_workers=50, decrements=200, increments=50, initial_qty=100):
    db = setup_db(DB_PATH)

    # Create store and activate it
    store_id = db.add_store(owner_id=1, name="LoadTestStore", city="Ташкент", address="Addr")
    db.update_store_status(store_id, "active")

    # Create offer
    offer_id = db.add_offer(
        store_id=store_id,
        title="LoadTestOffer",
        description="Load test",
        original_price=100.0,
        discount_price=50.0,
        quantity=initial_qty,
        available_from="",
        available_until="",
        photo=None,
        expiry_date=None,
    )

    print(f"Created store={store_id}, offer={offer_id} with qty={initial_qty}")

    tasks = []
    results = []

    start = time.time()

    with ThreadPoolExecutor(max_workers=concurrent_workers) as ex:
        # schedule decrements (bookings)
        futures = [ex.submit(worker_decrement, DB_PATH, offer_id, 1) for _ in range(decrements)]
        # schedule increments (cancellations) interleaved
        futures += [ex.submit(worker_increment, DB_PATH, offer_id, 1) for _ in range(increments)]

        # shuffle to create contention
        random.shuffle(futures)

        for f in as_completed(futures):
            results.append(f.result())

    duration = time.time() - start
    print(f"Completed {len(results)} operations in {duration:.2f}s")

    # Inspect final quantity from DB
    db_final = Database(db_name=DB_PATH)
    conn = db_final.get_connection()
    cur = conn.cursor()
    cur.execute("SELECT quantity FROM offers WHERE offer_id = ?", (offer_id,))
    row = cur.fetchone()
    final_qty = row[0] if row else None
    conn.close()

    print("Final quantity:", final_qty)

    # Compute expected final quantity
    expected = initial_qty - decrements + increments
    print("Expected final quantity:", expected)

    # Check for negative quantities produced as intermediate results
    negatives = [r for r in results if isinstance(r, int) and r < 0]
    errs = [r for r in results if isinstance(r, str) and r.startswith("err:")]
    print("Errors:", len(errs))
    print("Negative intermediate qtys:", len(negatives))

    ok = (final_qty == expected) and (len(negatives) == 0) and (len(errs) == 0)
    return {
        "final_qty": final_qty,
        "expected": expected,
        "duration": duration,
        "errors": errs,
        "negatives": negatives,
        "ok": ok,
    }


if __name__ == "__main__":
    summary = run_load_test(concurrent_workers=50, decrements=300, increments=100, initial_qty=500)
    print("\nSummary:")
    for k, v in summary.items():
        print(f"{k}: {v}")
