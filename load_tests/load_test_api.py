"""Simple async load test for Mini App API endpoints.

Usage (PowerShell):
  $env:BASE_URL = "http://localhost:8080"
  $env:LOAD_CONCURRENCY = "50"
  $env:LOAD_DURATION = "60"
  python .\load_tests\load_test_api.py

Optional:
  $env:LOAD_CITIES = "Tashkent,Samarkand"
  $env:TG_INIT_DATA = "<telegram initData>"  # to hit auth endpoints
  $env:LOAD_WRITE = "1"  # include write endpoints (disabled by default)
  $env:LOAD_SKIP_REVERSE = "1"  # skip reverse geocode (hits external service)
"""
from __future__ import annotations

import asyncio
import os
import random
import statistics
import time
from typing import Any

import aiohttp

BASE_URL = os.getenv("BASE_URL", "http://localhost:8080").rstrip("/")
CONCURRENCY = int(os.getenv("LOAD_CONCURRENCY", "25"))
DURATION = int(os.getenv("LOAD_DURATION", "60"))
TIMEOUT = float(os.getenv("LOAD_TIMEOUT", "10"))
LOAD_WRITE = os.getenv("LOAD_WRITE", "0") == "1"
TG_INIT_DATA = os.getenv("TG_INIT_DATA", "")
SKIP_REVERSE = os.getenv("LOAD_SKIP_REVERSE", "0") == "1"

CITIES = [c.strip() for c in os.getenv("LOAD_CITIES", "Tashkent").split(",") if c.strip()]
SEARCH_QUERIES = ["bread", "milk", "meat", "coffee", "pizza", "cake"]
DEFAULT_LAT = os.getenv("LOAD_LAT", "41.2995")
DEFAULT_LON = os.getenv("LOAD_LON", "69.2401")
DEFAULT_LANG = os.getenv("LOAD_LANG", "ru")


class Stats:
    def __init__(self) -> None:
        self.total = 0
        self.errors = 0
        self.latencies: list[float] = []
        self.statuses: dict[int, int] = {}

    def add(self, status: int | None, latency: float, ok: bool) -> None:
        self.total += 1
        self.latencies.append(latency)
        if status is not None:
            self.statuses[status] = self.statuses.get(status, 0) + 1
        if not ok:
            self.errors += 1


def percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    values_sorted = sorted(values)
    k = int((len(values_sorted) - 1) * p)
    return values_sorted[k]


async def fetch(
    session: aiohttp.ClientSession, method: str, url: str, headers=None, payload=None
):
    start = time.perf_counter()
    status = None
    ok = False
    try:
        async with session.request(method, url, headers=headers, json=payload) as resp:
            status = resp.status
            _ = await resp.text()
            ok = 200 <= resp.status < 300
    except Exception:
        ok = False
    return status, time.perf_counter() - start, ok


async def prepare_samples(session: aiohttp.ClientSession) -> dict[str, list[int]]:
    samples = {"offer_ids": [], "store_ids": []}
    try:
        url = f"{BASE_URL}/api/v1/offers?limit=50"
        async with session.get(url, timeout=TIMEOUT) as resp:
            data = await resp.json()
            if isinstance(data, list):
                for item in data:
                    offer_id = item.get("id") or item.get("offer_id")
                    store_id = item.get("store_id")
                    if offer_id:
                        samples["offer_ids"].append(int(offer_id))
                    if store_id:
                        samples["store_ids"].append(int(store_id))
    except Exception:
        pass
    return samples


def build_endpoints(samples: dict[str, list[int]]) -> list[tuple[str, str, str, dict | None]]:
    city = random.choice(CITIES) if CITIES else ""
    query = random.choice(SEARCH_QUERIES)
    offer_id = random.choice(samples.get("offer_ids") or [0])
    store_id = random.choice(samples.get("store_ids") or [0])

    endpoints: list[tuple[str, str, str, dict | None]] = [
        ("health", "GET", f"{BASE_URL}/api/v1/health", None),
        ("categories", "GET", f"{BASE_URL}/api/v1/categories?city={city}", None),
        ("offers", "GET", f"{BASE_URL}/api/v1/offers?city={city}&limit=20", None),
        (
            "search_suggestions",
            "GET",
            f"{BASE_URL}/api/v1/search/suggestions?query={query}&city={city}",
            None,
        ),
        ("flash_deals", "GET", f"{BASE_URL}/api/v1/flash-deals?city={city}&limit=10", None),
        ("stats_hot", "GET", f"{BASE_URL}/api/v1/stats/hot-deals?city={city}", None),
    ]

    if not SKIP_REVERSE:
        endpoints.append(
            (
                "reverse_geo",
                "GET",
                f"{BASE_URL}/api/v1/location/reverse?lat={DEFAULT_LAT}&lon={DEFAULT_LON}&lang={DEFAULT_LANG}",
                None,
            )
        )

    if offer_id:
        endpoints.append(("offer_detail", "GET", f"{BASE_URL}/api/v1/offers/{offer_id}", None))
    if store_id:
        endpoints.append(("store_detail", "GET", f"{BASE_URL}/api/v1/stores/{store_id}", None))

    return endpoints


def build_write_endpoints(samples: dict[str, list[int]]) -> list[tuple[str, str, str, dict | None]]:
    if not LOAD_WRITE or not TG_INIT_DATA:
        return []

    offer_id = random.choice(samples.get("offer_ids") or [0])
    if not offer_id:
        return []

    payload = {
        "items": [{"offer_id": offer_id, "quantity": 1}],
        "order_type": "pickup",
        "payment_method": "cash",
        "phone": "+998000000000",
    }

    return [("create_order", "POST", f"{BASE_URL}/api/v1/orders", payload)]


async def worker(name: int, stats: dict[str, Stats], lock: asyncio.Lock, samples):
    timeout = aiohttp.ClientTimeout(total=TIMEOUT)
    headers = {"X-Telegram-Init-Data": TG_INIT_DATA} if TG_INIT_DATA else None
    async with aiohttp.ClientSession(timeout=timeout) as session:
        end_time = time.perf_counter() + DURATION
        while time.perf_counter() < end_time:
            endpoints = build_endpoints(samples) + build_write_endpoints(samples)
            ep_name, method, url, payload = random.choice(endpoints)
            status, latency, ok = await fetch(session, method, url, headers=headers, payload=payload)
            async with lock:
                if ep_name not in stats:
                    stats[ep_name] = Stats()
                stats[ep_name].add(status, latency, ok)


async def main():
    timeout = aiohttp.ClientTimeout(total=TIMEOUT)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        samples = await prepare_samples(session)

    stats: dict[str, Stats] = {}
    lock = asyncio.Lock()

    tasks = [worker(i, stats, lock, samples) for i in range(CONCURRENCY)]
    start = time.perf_counter()
    await asyncio.gather(*tasks)
    duration = time.perf_counter() - start

    print("\n--- Load Test Summary ---")
    print(f"base_url: {BASE_URL}")
    print(f"concurrency: {CONCURRENCY}")
    print(f"duration_s: {duration:.2f}")

    for name, stat in stats.items():
        p50 = percentile(stat.latencies, 0.50)
        p95 = percentile(stat.latencies, 0.95)
        avg = statistics.mean(stat.latencies) if stat.latencies else 0.0
        err_rate = (stat.errors / stat.total) * 100 if stat.total else 0.0
        print(
            f"{name}: total={stat.total} errors={stat.errors} err%={err_rate:.2f} "
            f"avg={avg*1000:.1f}ms p50={p50*1000:.1f}ms p95={p95*1000:.1f}ms"
        )

    if LOAD_WRITE and not TG_INIT_DATA:
        print("\nNOTE: LOAD_WRITE=1 requires TG_INIT_DATA for authenticated endpoints.")


if __name__ == "__main__":
    asyncio.run(main())
