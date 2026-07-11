"""External search-provider clients and OSM tag mapping."""

from __future__ import annotations

import re
import sys
import time
from functools import lru_cache
from typing import Any

import requests

from .constants import (
    DEFAULT_OSM_RADIUS_KM, DETAILS_URL, DETAIL_FIELDS, NOMINATIM_SEARCH_URL,
    OSM_RETRY_STATUSES, OVERPASS_URL, TEXT_SEARCH_URL,
)


def request_headers() -> dict[str, str]:
    return {"User-Agent": "NoSiteScout/0.1 (internal lead research; contact: local)"}


def google_get(url: str, params: dict[str, Any]) -> dict[str, Any]:
    response = requests.get(url, params=params, timeout=20)
    response.raise_for_status()
    payload = response.json()
    status = payload.get("status")
    if status not in {"OK", "ZERO_RESULTS"}:
        raise RuntimeError(payload.get("error_message") or status or "Unknown Google Places error")
    return payload


@lru_cache(maxsize=256)
def geocode_location(location: str) -> tuple[float, float]:
    """Resolve a location once per process, avoiding duplicate Nominatim calls."""
    response = requests.get(
        NOMINATIM_SEARCH_URL,
        params={"q": location, "format": "jsonv2", "limit": 1},
        headers=request_headers(), timeout=20,
    )
    response.raise_for_status()
    payload = response.json()
    if not payload:
        raise RuntimeError(f"Could not geocode location with OpenStreetMap/Nominatim: {location}")
    return float(payload[0]["lat"]), float(payload[0]["lon"])


OSM_KEYWORD_TAGS: dict[str, list[tuple[str, str | None]]] = {
    "restaurants": [("amenity", "restaurant")], "restaurant": [("amenity", "restaurant")],
    "cafes": [("amenity", "cafe")], "cafe": [("amenity", "cafe")],
    "apartments": [("tourism", "apartment"), ("tourism", "chalet"), ("tourism", "guest_house"), ("tourism", "hotel")],
    "holiday homes": [("tourism", "apartment"), ("tourism", "chalet"), ("tourism", "guest_house")],
    "vacation rentals": [("tourism", "apartment"), ("tourism", "chalet"), ("tourism", "guest_house")],
    "plumbers": [("craft", "plumber")], "plumber": [("craft", "plumber")],
    "electricians": [("craft", "electrician")], "electrician": [("craft", "electrician")],
    "beauty salon": [("shop", "beauty"), ("shop", "hairdresser")],
    "massage": [("shop", "massage")], "massages": [("shop", "massage")],
    "wellness spa": [("leisure", "spa")], "spa": [("leisure", "spa")],
    "physiotherapy": [("healthcare", "physiotherapist")], "physiotherapists": [("healthcare", "physiotherapist")],
    "fitness centres": [("leisure", "fitness_centre")], "gyms": [("leisure", "fitness_centre")],
    "mechanics": [("shop", "car_repair"), ("craft", "mechanic")], "mechanic": [("shop", "car_repair"), ("craft", "mechanic")],
    "dentists": [("amenity", "dentist")], "dentist": [("amenity", "dentist")],
    "private clinics": [("amenity", "clinic"), ("amenity", "doctors")], "clinics": [("amenity", "clinic"), ("amenity", "doctors")],
    "veterinarians": [("amenity", "veterinary")], "vets": [("amenity", "veterinary")],
    "photographers": [("craft", "photographer")], "photography": [("craft", "photographer")],
    "small shops": [("shop", None)], "local services": [("craft", None), ("office", None)],
}


def osm_keyword_filters(keyword: str) -> list[str]:
    normalized = keyword.lower().replace("_", " ")
    pairs = OSM_KEYWORD_TAGS.get(normalized, [("name", keyword)])
    filters = []
    for key, value in pairs:
        if value is None:
            filters.append(f'["{key}"]')
        elif key == "name":
            filters.append(f'["name"~"{re.escape(value)}",i]')
        else:
            filters.append(f'["{key}"="{value}"]')
    return filters


def search_osm_places(keyword: str, location: str, max_results: int,
                      center_lat: float | None = None, center_lng: float | None = None,
                      radius_km: float | None = None, retries: int = 2) -> list[dict[str, Any]]:
    lat, lng = ((center_lat, center_lng) if center_lat is not None and center_lng is not None
                else geocode_location(location))
    radius_m = int((radius_km or DEFAULT_OSM_RADIUS_KM) * 1000)
    selectors = "\n".join(
        f"      {element_type}{tag_filter}(around:{radius_m},{lat},{lng});"
        for tag_filter in osm_keyword_filters(keyword)
        for element_type in ("node", "way", "relation")
    )
    query = f"""[out:json][timeout:30];
    (
{selectors}
    );
    out center tags {max_results};"""
    for attempt in range(retries + 1):
        response = requests.post(OVERPASS_URL, data={"data": query}, headers=request_headers(), timeout=45)
        if response.status_code not in OSM_RETRY_STATUSES:
            response.raise_for_status()
            return response.json().get("elements", [])[:max_results]
        if attempt >= retries:
            response.raise_for_status()
        wait_seconds = 15 * (attempt + 1)
        print(f"OSM request got HTTP {response.status_code}; retrying in {wait_seconds}s...", file=sys.stderr)
        time.sleep(wait_seconds)
    return []


def search_google_places(api_key: str, keyword: str, location: str, max_results: int,
                         center_lat: float | None = None, center_lng: float | None = None,
                         radius_km: float | None = None) -> list[dict[str, Any]]:
    params: dict[str, Any] = {"query": f"{keyword} in {location}", "key": api_key}
    if center_lat is not None and center_lng is not None and radius_km is not None:
        params.update(location=f"{center_lat},{center_lng}", radius=int(radius_km * 1000))
    results: list[dict[str, Any]] = []
    page = 0
    while len(results) < max_results:
        if page:
            time.sleep(2.2)
        payload = google_get(TEXT_SEARCH_URL, params)
        results.extend(payload.get("results", []))
        token = payload.get("next_page_token")
        if not token or len(results) >= max_results:
            break
        params = {"pagetoken": token, "key": api_key}
        page += 1
        time.sleep(0.3)
    return results[:max_results]


def fetch_place_details(api_key: str, place_id: str) -> dict[str, Any] | None:
    payload = google_get(DETAILS_URL, {"place_id": place_id, "fields": DETAIL_FIELDS, "key": api_key})
    return payload.get("result")


def first_tag(tags: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        if tags.get(key):
            return str(tags[key]).strip()
    return None


def osm_address(tags: dict[str, Any]) -> str | None:
    parts = [first_tag(tags, "addr:street"), first_tag(tags, "addr:housenumber"),
             first_tag(tags, "addr:postcode"), first_tag(tags, "addr:city", "addr:town", "addr:village"),
             first_tag(tags, "addr:country")]
    return ", ".join(part for part in parts if part) or None


def osm_category(tags: dict[str, Any], fallback: str) -> str:
    for key in ("amenity", "shop", "tourism", "craft", "office", "leisure"):
        if tags.get(key):
            return f"{key}:{tags[key]}"
    return fallback
