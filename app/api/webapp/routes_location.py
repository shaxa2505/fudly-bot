from __future__ import annotations

from typing import Any

import aiohttp
from cachetools import TTLCache
from fastapi import APIRouter, HTTPException, Query

from .common import logger

router = APIRouter()

_geocode_cache: TTLCache[str, dict[str, Any]] = TTLCache(maxsize=5000, ttl=3600)


def _make_cache_key(lat: float, lon: float, lang: str) -> str:
    return f"{round(lat, 5)}:{round(lon, 5)}:{lang.strip().lower()}"


async def _fetch_reverse_geocode(lat: float, lon: float, lang: str) -> dict[str, Any]:
    url = "https://nominatim.openstreetmap.org/reverse"
    params = {
        "format": "jsonv2",
        "lat": lat,
        "lon": lon,
        "accept-language": lang,
    }
    headers = {
        "User-Agent": "FudlyApp/1.0 (webapp reverse geocode)",
    }
    timeout = aiohttp.ClientTimeout(total=8)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.get(url, params=params, headers=headers) as response:
            if response.status != 200:
                raise HTTPException(status_code=502, detail="Geo lookup failed")
            return await response.json()


@router.get("/location/reverse")
async def reverse_geocode(
    lat: float = Query(..., description="Latitude"),
    lon: float = Query(..., description="Longitude"),
    lang: str = Query("uz", description="Response language"),
) -> dict[str, Any]:
    cache_key = _make_cache_key(lat, lon, lang)
    cached = _geocode_cache.get(cache_key)
    if cached is not None:
        return cached

    try:
        data = await _fetch_reverse_geocode(lat, lon, lang)
    except HTTPException:
        raise
    except Exception as exc:  # pragma: no cover - defensive
        logger.error("Reverse geocode failed: %s", exc)
        raise HTTPException(status_code=502, detail="Geo lookup failed") from exc

    _geocode_cache[cache_key] = data
    return data
