"""
Backfill store latitude/longitude and region/district using Nominatim.

Usage examples:
  python scripts/backfill_store_locations.py --dry-run --limit 20
  python scripts/backfill_store_locations.py --city "Tashkent" --sleep 1.2
  python scripts/backfill_store_locations.py --store-id 12 --store-id 42
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from dataclasses import dataclass
from typing import Any, Dict, Optional

import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import Database
from database_pg_module.mixins.offers import canonicalize_geo_slug

NOMINATIM_SEARCH_URL = "https://nominatim.openstreetmap.org/search"
NOMINATIM_REVERSE_URL = "https://nominatim.openstreetmap.org/reverse"


def _normalize(text: Optional[str]) -> str:
    if not text:
        return ""
    return " ".join(text.strip().lower().split())


def _blank_to_none(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    value = value.strip()
    return value if value else None


def _is_missing_text(value: Optional[str]) -> bool:
    return _blank_to_none(value) is None


def _is_missing_coord(value: Optional[float]) -> bool:
    if value is None:
        return True
    try:
        return float(value) == 0.0
    except (TypeError, ValueError):
        return True


def _pick_first(address: Dict[str, Any], keys: tuple[str, ...]) -> Optional[str]:
    for key in keys:
        value = address.get(key)
        value = _blank_to_none(value)
        if value:
            return value
    return None


def _extract_region_district(address: Dict[str, Any]) -> tuple[Optional[str], Optional[str]]:
    region_keys = ("state", "region", "province", "state_district")
    district_keys = ("county", "district", "city_district", "municipality", "suburb")
    region = _pick_first(address, region_keys)
    district = _pick_first(address, district_keys)
    return region, district


@dataclass
class GeoResult:
    lat: float
    lon: float
    address: Dict[str, Any]
    display_name: str


class GeoClient:
    def __init__(
        self,
        user_agent: str,
        sleep_seconds: float = 1.1,
        language: Optional[str] = None,
        country_code: Optional[str] = None,
        timeout: float = 15.0,
    ) -> None:
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": user_agent})
        self.sleep_seconds = max(sleep_seconds, 0.0)
        self.language = _blank_to_none(language)
        self.country_code = _blank_to_none(country_code)
        self.timeout = timeout
        self._last_request_ts = 0.0
        self._search_cache: dict[str, Optional[GeoResult]] = {}
        self._reverse_cache: dict[str, Optional[GeoResult]] = {}

    def _wait(self) -> None:
        if self.sleep_seconds <= 0:
            return
        elapsed = time.time() - self._last_request_ts
        if elapsed < self.sleep_seconds:
            time.sleep(self.sleep_seconds - elapsed)

    def _request(self, url: str, params: Dict[str, Any]) -> Optional[dict[str, Any]]:
        self._wait()
        if self.language:
            params["accept-language"] = self.language
        if self.country_code and "countrycodes" not in params:
            params["countrycodes"] = self.country_code
        try:
            resp = self.session.get(url, params=params, timeout=self.timeout)
        except requests.RequestException:
            self._last_request_ts = time.time()
            return None
        self._last_request_ts = time.time()
        if resp.status_code != 200:
            return None
        try:
            return resp.json()
        except ValueError:
            return None

    def geocode(self, query: str) -> Optional[GeoResult]:
        cache_key = query
        if cache_key in self._search_cache:
            return self._search_cache[cache_key]
        payload = {
            "q": query,
            "format": "json",
            "limit": 1,
            "addressdetails": 1,
        }
        data = self._request(NOMINATIM_SEARCH_URL, payload)
        if not data:
            self._search_cache[cache_key] = None
            return None
        item = data[0]
        try:
            result = GeoResult(
                lat=float(item["lat"]),
                lon=float(item["lon"]),
                address=item.get("address", {}) or {},
                display_name=item.get("display_name", ""),
            )
        except (KeyError, TypeError, ValueError):
            result = None
        self._search_cache[cache_key] = result
        return result

    def reverse(self, lat: float, lon: float) -> Optional[GeoResult]:
        cache_key = f"{lat:.6f},{lon:.6f}"
        if cache_key in self._reverse_cache:
            return self._reverse_cache[cache_key]
        payload = {
            "lat": lat,
            "lon": lon,
            "format": "json",
            "zoom": 18,
            "addressdetails": 1,
        }
        data = self._request(NOMINATIM_REVERSE_URL, payload)
        if not data:
            self._reverse_cache[cache_key] = None
            return None
        try:
            result = GeoResult(
                lat=float(data["lat"]),
                lon=float(data["lon"]),
                address=data.get("address", {}) or {},
                display_name=data.get("display_name", ""),
            )
        except (KeyError, TypeError, ValueError):
            result = None
        self._reverse_cache[cache_key] = result
        return result


def _build_query(address: Optional[str], city: Optional[str], country: Optional[str]) -> str:
    parts = []
    if address and address.strip():
        parts.append(address.strip())
    if city and city.strip():
        parts.append(city.strip())
    if country and country.strip():
        parts.append(country.strip())
    return ", ".join(parts)


def _row_value(row: Any, key: str, index: int) -> Any:
    if hasattr(row, "get"):
        return row.get(key)
    try:
        return row[index]
    except Exception:
        return None


def _city_matches(store_city: Optional[str], address: Dict[str, Any]) -> bool:
    store_norm = _normalize(store_city)
    if not store_norm:
        return True
    candidate_keys = ("city", "town", "village", "municipality", "county")
    for key in candidate_keys:
        value = _normalize(address.get(key))
        if value and (value == store_norm or store_norm in value or value in store_norm):
            return True
    return False


def fetch_candidates(db: Database) -> list[Any]:
    query = """
        SELECT store_id, name, city, address, region, district, latitude, longitude
        FROM stores
        WHERE (
            latitude IS NULL OR longitude IS NULL OR latitude = 0 OR longitude = 0
            OR region IS NULL OR btrim(region) = ''
            OR district IS NULL OR btrim(district) = ''
        )
        ORDER BY store_id
    """
    with db.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(query)
        return list(cursor.fetchall())


def update_store(
    conn,
    store_id: int,
    lat: Optional[float],
    lon: Optional[float],
    region: Optional[str],
    district: Optional[str],
    dry_run: bool,
) -> None:
    updates = []
    params: list[Any] = []
    if lat is not None:
        updates.append("latitude = %s")
        params.append(lat)
    if lon is not None:
        updates.append("longitude = %s")
        params.append(lon)
    if region is not None:
        updates.append("region = %s")
        params.append(region)
        updates.append("region_slug = %s")
        params.append(canonicalize_geo_slug(region))
    if district is not None:
        updates.append("district = %s")
        params.append(district)
        updates.append("district_slug = %s")
        params.append(canonicalize_geo_slug(district))
    if not updates:
        return
    params.append(store_id)
    sql = f"UPDATE stores SET {', '.join(updates)} WHERE store_id = %s"
    if dry_run:
        print(f"[dry-run] store_id={store_id} -> {', '.join(updates)}")
        return
    cursor = conn.cursor()
    cursor.execute(sql, params)
    conn.commit()


def main() -> int:
    parser = argparse.ArgumentParser(description="Backfill stores with geocoding data.")
    parser.add_argument("--limit", type=int, default=None, help="Max stores to update.")
    parser.add_argument("--sleep", type=float, default=1.1, help="Delay between requests.")
    parser.add_argument("--dry-run", action="store_true", help="Print updates without saving.")
    parser.add_argument("--city", type=str, default=None, help="Only process this city.")
    parser.add_argument(
        "--store-id", type=int, action="append", default=None, help="Process specific store id."
    )
    parser.add_argument("--force", action="store_true", help="Overwrite existing data.")
    parser.add_argument(
        "--allow-city-only",
        action="store_true",
        help="Allow geocoding with city only when address is missing.",
    )
    parser.add_argument(
        "--country",
        type=str,
        default=os.getenv("FUDLY_GEOCODE_COUNTRY", ""),
        help="Append country to geocode query.",
    )
    parser.add_argument(
        "--country-code",
        type=str,
        default=os.getenv("FUDLY_GEOCODE_COUNTRY_CODE", ""),
        help="Nominatim countrycodes param (e.g. 'uz').",
    )
    parser.add_argument(
        "--language",
        type=str,
        default=os.getenv("FUDLY_GEOCODE_LANG", "ru"),
        help="Preferred response language (accept-language).",
    )
    parser.add_argument(
        "--user-agent",
        type=str,
        default=os.getenv("FUDLY_GEOCODE_USER_AGENT", "fudly-bot-backfill/1.0"),
        help="User-Agent for Nominatim requests.",
    )
    args = parser.parse_args()

    db = Database()
    client = GeoClient(
        user_agent=args.user_agent,
        sleep_seconds=args.sleep,
        language=args.language,
        country_code=args.country_code,
    )

    rows = fetch_candidates(db)
    if not rows:
        print("No stores with missing location data.")
        return 0

    if args.city:
        rows = [row for row in rows if _normalize(_row_value(row, "city", 2)) == _normalize(args.city)]
    if args.store_id:
        store_ids = set(args.store_id)
        rows = [row for row in rows if _row_value(row, "store_id", 0) in store_ids]
    if args.limit is not None:
        rows = rows[: args.limit]

    processed = 0
    updated = 0
    skipped = 0

    with db.get_connection() as conn:
        for row in rows:
            store_id = _row_value(row, "store_id", 0)
            name = _row_value(row, "name", 1)
            city = _row_value(row, "city", 2)
            address = _row_value(row, "address", 3)
            region = _row_value(row, "region", 4)
            district = _row_value(row, "district", 5)
            latitude = _row_value(row, "latitude", 6)
            longitude = _row_value(row, "longitude", 7)

            needs_coords = args.force or _is_missing_coord(latitude) or _is_missing_coord(longitude)
            needs_region = args.force or _is_missing_text(region)
            needs_district = args.force or _is_missing_text(district)
            if not (needs_coords or needs_region or needs_district):
                skipped += 1
                continue

            processed += 1
            new_lat = None
            new_lon = None
            new_region = None
            new_district = None

            geo_source = None
            geocode = None

            if needs_coords:
                query = _build_query(address, city, args.country)
                if not query and not args.allow_city_only:
                    print(f"[skip] store_id={store_id} name={name!r}: missing address")
                    skipped += 1
                    continue
                if not query and args.allow_city_only:
                    query = _build_query(None, city, args.country)
                if query:
                    geocode = client.geocode(query)
                    geo_source = "search"

            if geocode is None and (needs_region or needs_district):
                if not _is_missing_coord(latitude) and not _is_missing_coord(longitude):
                    geocode = client.reverse(float(latitude), float(longitude))
                    geo_source = "reverse"

            if geocode is None:
                print(f"[skip] store_id={store_id} name={name!r}: geocode failed")
                skipped += 1
                continue

            if needs_coords:
                new_lat = geocode.lat
                new_lon = geocode.lon

            region_guess, district_guess = _extract_region_district(geocode.address)
            if needs_region and region_guess:
                new_region = region_guess
            if needs_district and district_guess:
                new_district = district_guess

            if new_region is None and needs_region:
                new_region = None
            if new_district is None and needs_district:
                new_district = None

            if not _city_matches(city, geocode.address):
                print(
                    f"[warn] store_id={store_id} name={name!r}: city mismatch via {geo_source} -> {geocode.display_name}"
                )

            if any(value is not None for value in (new_lat, new_lon, new_region, new_district)):
                update_store(
                    conn,
                    store_id,
                    new_lat if needs_coords else None,
                    new_lon if needs_coords else None,
                    new_region if needs_region else None,
                    new_district if needs_district else None,
                    args.dry_run,
                )
                updated += 1
                print(
                    f"[ok] store_id={store_id} name={name!r} -> "
                    f"lat={new_lat} lon={new_lon} region={new_region!r} district={new_district!r}"
                )
            else:
                skipped += 1
                print(f"[skip] store_id={store_id} name={name!r}: no new data")

    print(f"Processed={processed} Updated={updated} Skipped={skipped}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
