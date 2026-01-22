from __future__ import annotations

import math
from typing import Any

import aiohttp
from cachetools import TTLCache
from fastapi import APIRouter, HTTPException, Query

from .common import logger

router = APIRouter()

_geocode_cache: TTLCache[str, dict[str, Any]] = TTLCache(maxsize=5000, ttl=3600)


def _make_cache_key(lat: float, lon: float, lang: str) -> str:
    return f"{round(lat, 5)}:{round(lon, 5)}:{lang.strip().lower()}"


def _needs_overpass_details(data: dict[str, Any]) -> bool:
    address = (data or {}).get("address") or {}
    road_keys = ("road", "residential", "pedestrian", "footway", "path", "cycleway", "service")
    has_road = any(address.get(key) for key in road_keys)
    has_house = bool(address.get("house_number"))
    return not (has_road and has_house)


def _distance_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    rad = math.pi / 180.0
    x = (lon2 - lon1) * rad * math.cos((lat1 + lat2) * rad / 2.0)
    y = (lat2 - lat1) * rad
    return math.hypot(x, y) * 6371000.0


async def _fetch_overpass_address(lat: float, lon: float) -> dict[str, Any] | None:
    query = f"""
    [out:json][timeout:8];
    (
      node(around:80,{lat},{lon})["addr:housenumber"];
      way(around:80,{lat},{lon})["addr:housenumber"];
      relation(around:80,{lat},{lon})["addr:housenumber"];
    );
    out center 1;
    """
    url = "https://overpass-api.de/api/interpreter"
    headers = {
        "User-Agent": "FudlyApp/1.0 (webapp overpass reverse)",
    }
    timeout = aiohttp.ClientTimeout(total=8)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.get(url, params={"data": query}, headers=headers) as response:
            if response.status != 200:
                return None
            payload = await response.json()

    elements = payload.get("elements") or []
    best = None
    best_distance = None
    for element in elements:
        el_lat = element.get("lat")
        el_lon = element.get("lon")
        if el_lat is None or el_lon is None:
            center = element.get("center") or {}
            el_lat = center.get("lat")
            el_lon = center.get("lon")
        if el_lat is None or el_lon is None:
            continue
        distance = _distance_m(lat, lon, float(el_lat), float(el_lon))
        if best_distance is None or distance < best_distance:
            best_distance = distance
            best = element

    if not best:
        return None

    tags = best.get("tags") or {}
    return {
        "road": tags.get("addr:street") or tags.get("addr:place") or tags.get("addr:road"),
        "house_number": tags.get("addr:housenumber"),
        "city": tags.get("addr:city") or tags.get("addr:town") or tags.get("addr:village"),
        "suburb": tags.get("addr:suburb") or tags.get("addr:district") or tags.get("addr:neighbourhood"),
        "state": tags.get("addr:region") or tags.get("addr:state") or tags.get("addr:province"),
        "postcode": tags.get("addr:postcode"),
        "name": tags.get("name"),
    }


def _merge_overpass_details(data: dict[str, Any], overpass: dict[str, Any]) -> dict[str, Any]:
    address = data.setdefault("address", {})
    if overpass.get("road") and not address.get("road"):
        address["road"] = overpass["road"]
    if overpass.get("house_number") and not address.get("house_number"):
        address["house_number"] = overpass["house_number"]
    if overpass.get("city") and not (address.get("city") or address.get("town") or address.get("village")):
        address["city"] = overpass["city"]
    if overpass.get("suburb") and not (address.get("suburb") or address.get("neighbourhood")):
        address["suburb"] = overpass["suburb"]
    if overpass.get("state") and not address.get("state"):
        address["state"] = overpass["state"]
    if overpass.get("postcode") and not address.get("postcode"):
        address["postcode"] = overpass["postcode"]
    if overpass.get("name") and not data.get("name"):
        data["name"] = overpass["name"]
    data["fudly_overpass"] = True
    return data


async def _fetch_reverse_geocode(lat: float, lon: float, lang: str) -> dict[str, Any]:
    url = "https://nominatim.openstreetmap.org/reverse"
    params = {
        "format": "jsonv2",
        "lat": lat,
        "lon": lon,
        "accept-language": lang,
        "zoom": 18,
        "addressdetails": 1,
        "namedetails": 1,
        "extratags": 1,
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
        if _needs_overpass_details(data):
            try:
                overpass = await _fetch_overpass_address(lat, lon)
                if overpass:
                    data = _merge_overpass_details(data, overpass)
            except Exception as exc:  # pragma: no cover - defensive
                logger.warning("Overpass lookup failed: %s", exc)
    except HTTPException:
        raise
    except Exception as exc:  # pragma: no cover - defensive
        logger.error("Reverse geocode failed: %s", exc)
        raise HTTPException(status_code=502, detail="Geo lookup failed") from exc

    _geocode_cache[cache_key] = data
    return data
