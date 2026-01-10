"""
Lightweight geocoding helpers (Nominatim).

Used for store address -> coordinates/region/district and reverse geocoding.
"""
from __future__ import annotations

import asyncio
import os
import time
from dataclasses import dataclass
from typing import Any, Optional

import aiohttp

NOMINATIM_SEARCH_URL = "https://nominatim.openstreetmap.org/search"
NOMINATIM_REVERSE_URL = "https://nominatim.openstreetmap.org/reverse"

_DEFAULT_USER_AGENT = os.getenv("FUDLY_GEOCODE_USER_AGENT", "fudly-bot-geocode/1.0")
_DEFAULT_LANGUAGE = os.getenv("FUDLY_GEOCODE_LANG", "ru")
_DEFAULT_COUNTRY = os.getenv("FUDLY_GEOCODE_COUNTRY", "")
_DEFAULT_COUNTRY_CODE = os.getenv("FUDLY_GEOCODE_COUNTRY_CODE", "")
_DEFAULT_MIN_DELAY = float(os.getenv("FUDLY_GEOCODE_MIN_DELAY", "1.0"))
_DEFAULT_TIMEOUT = float(os.getenv("FUDLY_GEOCODE_TIMEOUT", "10.0"))
_DEFAULT_ENABLED = os.getenv("FUDLY_GEOCODE_ENABLED", "1").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}


def _normalize(text: Optional[str]) -> str:
    if not text:
        return ""
    return " ".join(text.strip().split())


def _blank_to_none(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    value = value.strip()
    return value if value else None


def _pick_first(address: dict[str, Any], keys: tuple[str, ...]) -> Optional[str]:
    for key in keys:
        value = address.get(key)
        value = _blank_to_none(value)
        if value:
            return value
    return None


def _extract_region_district(address: dict[str, Any]) -> tuple[Optional[str], Optional[str]]:
    region_keys = ("state", "region", "province", "state_district")
    district_keys = ("county", "district", "city_district", "municipality", "suburb")
    region = _pick_first(address, region_keys)
    district = _pick_first(address, district_keys)
    return region, district


def _build_query(address: Optional[str], city: Optional[str], country: Optional[str]) -> str:
    parts = []
    if address:
        parts.append(address)
    if city:
        parts.append(city)
    if country:
        parts.append(country)
    return ", ".join(parts)


@dataclass(slots=True)
class GeoResult:
    lat: float
    lon: float
    address: dict[str, Any]
    display_name: str


class GeoClient:
    def __init__(
        self,
        user_agent: str,
        language: Optional[str],
        country_code: Optional[str],
        min_delay: float,
        timeout: float,
    ) -> None:
        self._user_agent = user_agent
        self._language = _blank_to_none(language)
        self._country_code = _blank_to_none(country_code)
        self._min_delay = max(min_delay, 0.0)
        self._timeout = timeout
        self._lock = asyncio.Lock()
        self._last_request_ts = 0.0
        self._search_cache: dict[str, Optional[GeoResult]] = {}
        self._reverse_cache: dict[str, Optional[GeoResult]] = {}

    async def _throttle(self) -> None:
        if self._min_delay <= 0:
            return
        async with self._lock:
            now = time.monotonic()
            wait_for = self._min_delay - (now - self._last_request_ts)
            if wait_for > 0:
                await asyncio.sleep(wait_for)
            self._last_request_ts = time.monotonic()

    async def _request_json(self, url: str, params: dict[str, Any]) -> Optional[Any]:
        await self._throttle()
        if self._language:
            params["accept-language"] = self._language
        if self._country_code and "countrycodes" not in params:
            params["countrycodes"] = self._country_code
        headers = {"User-Agent": self._user_agent}
        try:
            async with aiohttp.ClientSession(headers=headers) as session:
                async with session.get(url, params=params, timeout=self._timeout) as resp:
                    if resp.status != 200:
                        return None
                    return await resp.json()
        except (aiohttp.ClientError, asyncio.TimeoutError):
            return None

    async def geocode(self, query: str) -> Optional[GeoResult]:
        query = _normalize(query)
        if not query:
            return None
        if query in self._search_cache:
            return self._search_cache[query]
        payload = {
            "q": query,
            "format": "jsonv2",
            "limit": 1,
            "addressdetails": 1,
        }
        data = await self._request_json(NOMINATIM_SEARCH_URL, payload)
        if not data:
            self._search_cache[query] = None
            return None
        item = data[0]
        try:
            result = GeoResult(
                lat=float(item["lat"]),
                lon=float(item["lon"]),
                address=item.get("address", {}) or {},
                display_name=item.get("display_name", "") or "",
            )
        except (KeyError, TypeError, ValueError):
            result = None
        self._search_cache[query] = result
        return result

    async def reverse(self, lat: float, lon: float) -> Optional[GeoResult]:
        cache_key = f"{lat:.6f},{lon:.6f}"
        if cache_key in self._reverse_cache:
            return self._reverse_cache[cache_key]
        payload = {
            "lat": lat,
            "lon": lon,
            "format": "jsonv2",
            "zoom": 18,
            "addressdetails": 1,
        }
        data = await self._request_json(NOMINATIM_REVERSE_URL, payload)
        if not data:
            self._reverse_cache[cache_key] = None
            return None
        try:
            result = GeoResult(
                lat=float(data["lat"]),
                lon=float(data["lon"]),
                address=data.get("address", {}) or {},
                display_name=data.get("display_name", "") or "",
            )
        except (KeyError, TypeError, ValueError):
            result = None
        self._reverse_cache[cache_key] = result
        return result


_client: GeoClient | None = None


def geocoding_enabled() -> bool:
    return _DEFAULT_ENABLED


def _get_client() -> GeoClient:
    global _client
    if _client is None:
        _client = GeoClient(
            user_agent=_DEFAULT_USER_AGENT,
            language=_DEFAULT_LANGUAGE,
            country_code=_DEFAULT_COUNTRY_CODE,
            min_delay=_DEFAULT_MIN_DELAY,
            timeout=_DEFAULT_TIMEOUT,
        )
    return _client


async def geocode_store_address(
    address: Optional[str], city: Optional[str], country: Optional[str] = None
) -> Optional[dict[str, Any]]:
    if not geocoding_enabled():
        return None
    query = _build_query(_normalize(address), _normalize(city), _normalize(country or _DEFAULT_COUNTRY))
    if not query:
        return None
    client = _get_client()
    result = await client.geocode(query)
    if not result:
        return None
    region, district = _extract_region_district(result.address)
    return {
        "latitude": result.lat,
        "longitude": result.lon,
        "region": region,
        "district": district,
        "display_name": result.display_name,
    }


async def reverse_geocode_store(lat: float, lon: float) -> Optional[dict[str, Any]]:
    if not geocoding_enabled():
        return None
    client = _get_client()
    result = await client.reverse(lat, lon)
    if not result:
        return None
    region, district = _extract_region_district(result.address)
    return {
        "latitude": result.lat,
        "longitude": result.lon,
        "region": region,
        "district": district,
        "display_name": result.display_name,
    }
