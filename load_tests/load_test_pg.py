"""Load test against PostgreSQL using the project's `database_pg.Database`.

Usage: set `DATABASE_URL` env var (or pass in via command line) and run with project's venv Python.

This script will:
- connect to Postgres via `database_pg.Database`
- create a store, activate it, create an offer with a given initial quantity
- spawn concurrent workers that call `increment_offer_quantity_atomic` with +1 or -1
- report final quantity, expected quantity, duration, and any errors

WARNING: This writes to the provided database. Only run against staging/test DB.
"""
import os
import random
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

# Ensure repository root is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from database_pg import Database

DB_URL = os.environ.get("DATABASE_URL")
if not DB_URL:
    print("ERROR: set DATABASE_URL env var to the target Postgres connection string")
    sys.exit(1)


def worker(db_url: str, offer_id: int, amount: int):
    try:
        db = Database(database_url=db_url)
        new_qty = db.increment_offer_quantity_atomic(offer_id, amount)
        return ("ok", new_qty)
    except Exception as e:
        return ("err", str(e))


def run_load_test(
    database_url: str, concurrent_workers=50, decrements=200, increments=50, initial_qty=100
):
    db = Database(database_url=database_url)

    # Ensure a user exists for owner_id (add_user upserts)
    db.add_user(1, username="loadtest", first_name="LoadTest")

    # Create store and activate it
    store_id = db.add_store(owner_id=1, name="LoadTestStore", city="Ташкент", address="Load test")
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

    ops = []
    for _ in range(decrements):
        ops.append(-1)
    for _ in range(increments):
        ops.append(1)

    random.shuffle(ops)

    results = []
    start = time.time()
    with ThreadPoolExecutor(max_workers=concurrent_workers) as ex:
        futures = [ex.submit(worker, database_url, offer_id, amt) for amt in ops]
        for f in as_completed(futures):
            results.append(f.result())

    duration = time.time() - start
    ok_count = sum(1 for r in results if r[0] == "ok")
    err_list = [r for r in results if r[0] == "err"]

    # Read final qty
    db_final = Database(database_url=database_url)
    # Use raw connection to ensure numeric result
    with db_final.get_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT quantity FROM offers WHERE offer_id = %s", (offer_id,))
        row = cur.fetchone()
        final_qty = row[0] if row else None

    expected = initial_qty - decrements + increments

    print("\n--- Result ---")
    print("operations:", len(ops))
    print("duration:", f"{duration:.2f}s")
    print("successful ops:", ok_count)
    print("errors:", len(err_list))
    if len(err_list) > 0:
        print("first errors (up to 10):", err_list[:10])
    print("final_qty:", final_qty)
    print("expected:", expected)

    return {
        "operations": len(ops),
        "duration": duration,
        "success": ok_count,
        "errors": [e for e in err_list],
        "final_qty": final_qty,
        "expected": expected,
    }


if __name__ == "__main__":
    # params
    workers = int(os.environ.get("LOAD_WORKERS", "50"))
    decrements = int(os.environ.get("LOAD_DECREMENTS", "300"))
    increments = int(os.environ.get("LOAD_INCREMENTS", "100"))
    initial_qty = int(os.environ.get("LOAD_INITIAL_QTY", "500"))

    summary = run_load_test(
        DB_URL,
        concurrent_workers=workers,
        decrements=decrements,
        increments=increments,
        initial_qty=initial_qty,
    )
    print("\nSummary:")
    for k, v in summary.items():
        print(f"{k}: {v}")
