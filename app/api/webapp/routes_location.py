from __future__ import annotations

import math
from typing import Any

import aiohttp
from cachetools import TTLCache
from fastapi import APIRouter, HTTPException, Query, Request

from .common import logger
from app.api.rate_limit import limiter

router = APIRouter()

_geocode_cache: TTLCache[str, dict[str, Any]] = TTLCache(maxsize=5000, ttl=3600)
_search_cache: TTLCache[str, dict[str, Any]] = TTLCache(maxsize=5000, ttl=3600)
_OVERPASS_ADDRESS_RADIUS_M = 140
_OVERPASS_TIMEOUT_S = 8


def _make_cache_key(lat: float, lon: float, lang: str, enrich: bool) -> str:
    enrich_key = "1" if enrich else "0"
    return f"{round(lat, 5)}:{round(lon, 5)}:{lang.strip().lower()}:{enrich_key}"


def _make_search_key(
    query: str,
    lang: str,
    limit: int,
    lat: float | None,
    lon: float | None,
    countrycodes: str | None,
    radius_km: float | None,
) -> str:
    lat_key = f"{round(lat, 4)}" if lat is not None else ""
    lon_key = f"{round(lon, 4)}" if lon is not None else ""
    country_key = (countrycodes or "").strip().lower()
    radius_key = f"{round(radius_km or 0, 1)}"
    return f"{query.strip().lower()}|{lang.strip().lower()}|{limit}|{lat_key}:{lon_key}|{country_key}|{radius_key}"


def _normalize_query(value: str) -> str:
    return " ".join((value or "").strip().split())


def _build_viewbox(lat: float, lon: float, radius_km: float) -> str:
    lat_delta = radius_km / 111.0
    lon_delta = radius_km / max(0.1, 111.0 * math.cos(lat * math.pi / 180.0))
    left = lon - lon_delta
    right = lon + lon_delta
    top = lat + lat_delta
    bottom = lat - lat_delta
    return f"{left},{top},{right},{bottom}"


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


def _get_element_coords(element: dict[str, Any]) -> tuple[float, float] | None:
    el_lat = element.get("lat")
    el_lon = element.get("lon")
    if el_lat is None or el_lon is None:
        center = element.get("center") or {}
        el_lat = center.get("lat")
        el_lon = center.get("lon")
    if el_lat is None or el_lon is None:
        return None
    return float(el_lat), float(el_lon)


def _extract_overpass_road(tags: dict[str, Any]) -> str | None:
    return tags.get("addr:street") or tags.get("addr:road") or tags.get("addr:place")


def _score_overpass_candidate(tags: dict[str, Any]) -> int:
    if tags.get("addr:street"):
        road_score = 300
    elif tags.get("addr:road"):
        road_score = 220
    elif tags.get("addr:place"):
        road_score = 120
    else:
        road_score = 0

    house_score = 80 if tags.get("addr:housenumber") else 0
    return road_score + house_score


async def _fetch_overpass_address(lat: float, lon: float) -> dict[str, Any] | None:
    query = f"""
    [out:json][timeout:{_OVERPASS_TIMEOUT_S}];
    (
      node(around:{_OVERPASS_ADDRESS_RADIUS_M},{lat},{lon})["addr:housenumber"];
      way(around:{_OVERPASS_ADDRESS_RADIUS_M},{lat},{lon})["addr:housenumber"];
      relation(around:{_OVERPASS_ADDRESS_RADIUS_M},{lat},{lon})["addr:housenumber"];
      node(around:{_OVERPASS_ADDRESS_RADIUS_M},{lat},{lon})["addr:street"];
      way(around:{_OVERPASS_ADDRESS_RADIUS_M},{lat},{lon})["addr:street"];
      relation(around:{_OVERPASS_ADDRESS_RADIUS_M},{lat},{lon})["addr:street"];
      node(around:{_OVERPASS_ADDRESS_RADIUS_M},{lat},{lon})["addr:road"];
      way(around:{_OVERPASS_ADDRESS_RADIUS_M},{lat},{lon})["addr:road"];
      relation(around:{_OVERPASS_ADDRESS_RADIUS_M},{lat},{lon})["addr:road"];
    );
    out center 1;
    """
    url = "https://overpass-api.de/api/interpreter"
    headers = {
        "User-Agent": "FudlyApp/1.0 (webapp overpass reverse)",
    }
    timeout = aiohttp.ClientTimeout(total=_OVERPASS_TIMEOUT_S)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.get(url, params={"data": query}, headers=headers) as response:
            if response.status != 200:
                return None
            payload = await response.json()

    elements = payload.get("elements") or []
    best_tags: dict[str, Any] | None = None
    best_score = -1
    best_distance = float("inf")
    for element in elements:
        coords = _get_element_coords(element)
        if coords is None:
            continue
        tags = element.get("tags") or {}
        score = _score_overpass_candidate(tags)
        if score <= 0:
            continue
        distance = _distance_m(lat, lon, coords[0], coords[1])
        if score > best_score or (score == best_score and distance < best_distance):
            best_score = score
            best_distance = distance
            best_tags = tags

    if not best_tags:
        return None

    return {
        "road": _extract_overpass_road(best_tags),
        "house_number": best_tags.get("addr:housenumber"),
        "city": best_tags.get("addr:city") or best_tags.get("addr:town") or best_tags.get("addr:village"),
        "suburb": best_tags.get("addr:suburb") or best_tags.get("addr:district") or best_tags.get("addr:neighbourhood"),
        "state": best_tags.get("addr:region") or best_tags.get("addr:state") or best_tags.get("addr:province"),
        "postcode": best_tags.get("addr:postcode"),
        "name": best_tags.get("name"),
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


async def _fetch_search_geocode(
    query: str,
    lang: str,
    limit: int,
    lat: float | None,
    lon: float | None,
    radius_km: float,
    countrycodes: str | None,
) -> list[dict[str, Any]]:
    url = "https://nominatim.openstreetmap.org/search"
    params: dict[str, Any] = {
        "format": "jsonv2",
        "q": query,
        "limit": limit,
        "accept-language": lang,
        "addressdetails": 1,
        "namedetails": 1,
        "extratags": 1,
    }
    if countrycodes:
        params["countrycodes"] = countrycodes
    if lat is not None and lon is not None:
        params["viewbox"] = _build_viewbox(lat, lon, radius_km)
        params["bounded"] = 0

    headers = {
        "User-Agent": "FudlyApp/1.0 (webapp search geocode)",
    }
    timeout = aiohttp.ClientTimeout(total=8)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.get(url, params=params, headers=headers) as response:
            if response.status != 200:
                raise HTTPException(status_code=502, detail="Geo lookup failed")
            data = await response.json()

    if not isinstance(data, list):
        return []

    if lat is None or lon is None:
        return data

    for item in data:
        try:
            item_lat = float(item.get("lat"))
            item_lon = float(item.get("lon"))
        except (TypeError, ValueError):
            continue
        item["distance_m"] = _distance_m(lat, lon, item_lat, item_lon)
    return data


@router.get("/location/reverse")
@limiter.limit("30/minute")
async def reverse_geocode(
    request: Request,
    lat: float = Query(..., description="Latitude"),
    lon: float = Query(..., description="Longitude"),
    lang: str = Query("uz", description="Response language"),
    enrich: bool = Query(True, description="Include optional address enrichment"),
    fresh: bool = Query(False, description="Bypass reverse cache for this request"),
) -> dict[str, Any]:
    cache_key = _make_cache_key(lat, lon, lang, enrich)
    if not fresh:
        cached = _geocode_cache.get(cache_key)
        if cached is not None:
            return cached

    try:
        data = await _fetch_reverse_geocode(lat, lon, lang)
        if enrich and _needs_overpass_details(data):
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


@router.get("/location/search")
@limiter.limit("30/minute")
async def search_location(
    request: Request,
    query: str = Query(..., min_length=2, description="Address query"),
    lang: str = Query("uz", description="Response language"),
    limit: int = Query(8, ge=1, le=20, description="Max results"),
    lat: float | None = Query(None, description="User latitude"),
    lon: float | None = Query(None, description="User longitude"),
    radius_km: float = Query(40, ge=5, le=200, description="Bias radius around user"),
    countrycodes: str | None = Query("uz", description="Country codes for search"),
) -> dict[str, Any]:
    normalized = _normalize_query(query)
    if len(normalized) < 2:
        return {"items": []}

    if lat is not None and not math.isfinite(lat):
        lat = None
    if lon is not None and not math.isfinite(lon):
        lon = None

    cache_key = _make_search_key(normalized, lang, limit, lat, lon, countrycodes, radius_km)
    cached = _search_cache.get(cache_key)
    if cached is not None:
        return cached

    try:
        items = await _fetch_search_geocode(
            normalized,
            lang,
            limit,
            lat,
            lon,
            radius_km,
            countrycodes,
        )
    except HTTPException:
        raise
    except Exception as exc:  # pragma: no cover - defensive
        logger.error("Forward geocode failed: %s", exc)
        raise HTTPException(status_code=502, detail="Geo lookup failed") from exc

    response = {"items": items}
    _search_cache[cache_key] = response
    return response
