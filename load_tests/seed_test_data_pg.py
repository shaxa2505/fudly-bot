"""Seed PostgreSQL with load test data (stores + offers).

Usage (PowerShell):
  $env:DATABASE_URL = "postgresql://user:pass@host:5432/db"
  $env:SEED_STORES = "50"
  $env:SEED_OFFERS_PER_STORE = "20"
  python .\load_tests\seed_test_data_pg.py

Optional:
  $env:SEED_RESET = "1"          # delete previous LoadTest Store entries
  $env:SEED_USER_BASE = "9000000000"
  $env:SEED_CITIES = "Tashkent,Samarkand"
"""
from __future__ import annotations

import os
import random
import sys
from datetime import date, timedelta
from pathlib import Path

# Ensure repository root is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from database_pg import Database

DB_URL = os.getenv("DATABASE_URL")
if not DB_URL:
    raise SystemExit("DATABASE_URL env var is required.")

TARGET_STORES = int(os.getenv("SEED_STORES", "50"))
OFFERS_PER_STORE = int(os.getenv("SEED_OFFERS_PER_STORE", "20"))
RESET = os.getenv("SEED_RESET", "0").strip().lower() in {"1", "true", "yes"}
USER_BASE = int(os.getenv("SEED_USER_BASE", "9000000000"))

CITIES = [c.strip() for c in os.getenv("SEED_CITIES", "Tashkent").split(",") if c.strip()]
CATEGORIES = ["dairy", "bakery", "meat", "fruits", "vegetables", "drinks", "sweets", "frozen", "other"]


def _get_loadtest_store_ids(db: Database) -> list[int]:
    with db.get_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT store_id FROM stores WHERE name LIKE %s", ("LoadTest Store %",))
        return [row[0] for row in cur.fetchall()]


def _get_loadtest_store_count(db: Database) -> int:
    with db.get_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM stores WHERE name LIKE %s", ("LoadTest Store %",))
        return int(cur.fetchone()[0] or 0)


def main() -> None:
    db = Database(database_url=DB_URL)

    if RESET:
        store_ids = _get_loadtest_store_ids(db)
        for store_id in store_ids:
            db.delete_store(store_id)
        print(f"Deleted {len(store_ids)} LoadTest stores.")

    existing = _get_loadtest_store_count(db)
    if existing >= TARGET_STORES:
        print(f"Existing LoadTest stores: {existing} (target {TARGET_STORES})")
        return

    to_create = TARGET_STORES - existing
    print(f"Creating {to_create} stores with {OFFERS_PER_STORE} offers each...")

    for i in range(existing, TARGET_STORES):
        city = random.choice(CITIES) if CITIES else "Tashkent"
        owner_id = USER_BASE + i
        username = f"loadtest_{i}"
        db.add_user(owner_id, username=username, first_name="LoadTest", city=city)

        store_name = f"LoadTest Store {i}"
        store_id = db.add_store(
            owner_id=owner_id,
            name=store_name,
            city=city,
            address=f"Load test address {i}",
            description="Load test store",
        )
        db.update_store_status(store_id, "active")

        for j in range(OFFERS_PER_STORE):
            original_price = random.randint(20000, 120000)
            discount_price = max(1000, int(original_price * random.uniform(0.3, 0.9)))
            quantity = random.randint(1, 50)
            expiry = (date.today() + timedelta(days=random.randint(7, 60))).isoformat()
            category = random.choice(CATEGORIES)
            db.add_offer(
                store_id=store_id,
                title=f"LoadTest Offer {store_id}-{j}",
                description="Load test offer",
                original_price=original_price,
                discount_price=discount_price,
                quantity=quantity,
                expiry_date=expiry,
                category=category,
            )

        if (i + 1) % 10 == 0:
            print(f"Created store {i + 1}/{TARGET_STORES}")

    print("Seeding complete.")


if __name__ == "__main__":
    main()
