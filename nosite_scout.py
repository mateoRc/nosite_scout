#!/usr/bin/env python3
"""NoSite Scout: find local leads from Google Places and export them."""

from __future__ import annotations

import argparse
import html
import os
import re
import sqlite3
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from xml.etree import ElementTree as ET

import requests

try:
    import pandas as pd
except ModuleNotFoundError:  # Dependencies are declared in requirements.txt.
    pd = None

try:
    from dotenv import load_dotenv
except ModuleNotFoundError:
    load_dotenv = None


DEFAULT_KEYWORDS = [
    "restaurants",
    "cafes",
    "apartments",
    "plumbers",
    "electricians",
    "beauty_salon",
    "massage",
    "wellness_spa",
    "physiotherapy",
    "mechanics",
    "dentists",
    "private_clinics",
    "small_shops",
    "local_services",
]

LEAD_COLUMNS = [
    "place_id",
    "name",
    "category",
    "address",
    "city",
    "phone",
    "formatted_phone_number",
    "international_phone_number",
    "phone_preferred",
    "mobile_phone",
    "has_phone",
    "website",
    "google_maps_url",
    "rating",
    "review_count",
    "no_website",
    "likely_small_business",
    "source",
    "status",
    "assigned_to",
    "next_follow_up_at",
    "last_contacted_at",
    "do_not_contact",
    "estimated_value",
    "notes",
    "email",
    "contact_page_url",
    "facebook_url",
    "instagram_url",
    "whatsapp_url",
    "created_at",
    "updated_at",
]

PROFILE_DOMAINS = (
    "facebook.com",
    "instagram.com",
    "linktr.ee",
    "booking.com",
    "tripadvisor.",
    "whatsapp.com",
    "wa.me",
    "google.com/maps",
    "business.site",
)

CHAIN_WORDS = (
    "mcdonald",
    "burger king",
    "kfc",
    "lidl",
    "kaufland",
    "spar",
    "dm",
    "bipa",
    "zara",
    "h&m",
    "tommy",
    "konzum",
    "plodine",
)

LOCAL_CITIES = (
    "istria",
    "istra",
    "croatia",
    "hrvatska",
    "pula",
    "rovinj",
    "porec",
    "poreč",
    "umag",
    "novigrad",
    "labin",
    "pazin",
    "buzet",
    "motovun",
    "medulin",
    "vodnjan",
    "fažana",
    "fazana",
)

LOCAL_CATEGORIES = (
    "restaurant",
    "cafe",
    "lodging",
    "apartment",
    "plumber",
    "electrician",
    "beauty",
    "massage",
    "spa",
    "physiotherapist",
    "fitness_centre",
    "mechanic",
    "dentist",
    "clinic",
    "doctors",
    "veterinary",
    "photographer",
    "store",
    "shop",
    "local_service",
)

TEXT_SEARCH_URL = "https://maps.googleapis.com/maps/api/place/textsearch/json"
DETAILS_URL = "https://maps.googleapis.com/maps/api/place/details/json"
NOMINATIM_SEARCH_URL = "https://nominatim.openstreetmap.org/search"
OVERPASS_URL = "https://overpass-api.de/api/interpreter"
OSM_RETRY_STATUSES = {429, 502, 503, 504}
DEFAULT_OSM_RADIUS_KM = 25.0
DETAIL_FIELDS = ",".join(
    [
        "place_id",
        "name",
        "formatted_address",
        "formatted_phone_number",
        "international_phone_number",
        "website",
        "url",
        "rating",
        "user_ratings_total",
        "types",
    ]
)


def normalize_phone(phone: str | None) -> str | None:
    if not phone:
        return None
    phone = phone.strip()
    if not phone:
        return None
    leading_plus = phone.startswith("+")
    digits = re.sub(r"\D", "", phone)
    if not digits:
        return None
    return f"+{digits}" if leading_plus else digits


def is_likely_croatian_mobile(phone: str | None) -> bool:
    normalized = normalize_phone(phone)
    if not normalized:
        return False
    digits = normalized.lstrip("+")
    return digits.startswith("3859") or digits.startswith("09")


def is_real_website(url: str | None) -> bool:
    if not url or not url.strip():
        return False
    candidate = url.strip().lower()
    parsed = urlparse(candidate if "://" in candidate else f"https://{candidate}")
    host = (parsed.netloc or parsed.path).removeprefix("www.")
    whole_url = f"{host}{parsed.path}"
    return not any(domain in whole_url for domain in PROFILE_DOMAINS)


def extract_city(address: str | None) -> str | None:
    if not address:
        return None
    parts = [part.strip() for part in address.split(",") if part.strip()]
    if not parts:
        return None

    for part in parts:
        match = re.search(r"\b\d{5}\b\s*(.+)", part)
        if match and re.search(r"[A-Za-zÀ-ž]", match.group(1)):
            return match.group(1).strip()

    lowered_parts = [(part, part.lower()) for part in parts]
    for part, lowered in lowered_parts:
        for city in LOCAL_CITIES:
            if city in {"istria", "istra", "croatia", "hrvatska"}:
                continue
            if city in lowered:
                return part

    non_country_parts = [
        part
        for part in parts
        if not any(country in part.lower() for country in ("croatia", "hrvatska"))
    ]
    if len(non_country_parts) >= 2:
        return re.sub(r"\b\d{5}\b", "", non_country_parts[-1]).strip() or non_country_parts[-1]

    for part in parts:
        cleaned = re.sub(r"\b\d{5}\b", "", part).strip()
        if cleaned and not any(country in cleaned.lower() for country in ("croatia", "hrvatska")):
            if re.search(r"[A-Za-zÀ-ž]", cleaned):
                return cleaned
    return parts[-1]


def score_likely_small_business(row: dict[str, Any], review_threshold: int) -> bool:
    name = str(row.get("name") or "").lower()
    if any(word in name for word in CHAIN_WORDS):
        return False

    review_count = int(row.get("review_count") or 0)
    if review_count >= review_threshold:
        return False

    address = str(row.get("address") or "").lower()
    category = str(row.get("category") or "").lower()
    has_local_address = any(token in address for token in LOCAL_CITIES)
    has_local_category = any(token in category for token in LOCAL_CATEGORIES)
    return has_local_address and has_local_category


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Find local businesses that likely lack a real website.")
    parser.add_argument("--manual-add", action="store_true", help="Add one lead manually, then export.")
    parser.add_argument("--manual-name", help="Manual lead business name.")
    parser.add_argument("--manual-phone", help="Manual lead phone number.")
    parser.add_argument("--manual-website", help="Manual lead website URL.")
    parser.add_argument("--manual-address", help="Manual lead address.")
    parser.add_argument("--manual-city", help="Manual lead city.")
    parser.add_argument("--manual-category", default="manual_review", help="Manual lead category.")
    parser.add_argument("--manual-notes", help="Manual lead notes.")
    parser.add_argument("--manual-status", default="review_website_age", help="Manual lead status.")
    parser.add_argument("--provider", choices=["osm", "google"], default="osm", help="Data provider. Default: osm.")
    parser.add_argument("--location", default="Istria, Croatia")
    parser.add_argument("--locations", nargs="+", help="One or more areas to search. Overrides --location.")
    parser.add_argument("--countries", nargs="+", help="One or more countries to combine with each location.")
    parser.add_argument("--radius-km", "--range-km", dest="radius_km", type=float, help="Radius bias in kilometers.")
    parser.add_argument("--center-lat", type=float, help="Latitude used with --radius-km.")
    parser.add_argument("--center-lng", type=float, help="Longitude used with --radius-km.")
    parser.add_argument("--keywords", nargs="+", default=DEFAULT_KEYWORDS)
    parser.add_argument("--max-results", type=int, default=50, help="Maximum Places results per keyword.")
    parser.add_argument("--request-delay", type=float, default=2.0, help="Delay between provider requests in seconds.")
    parser.add_argument("--osm-retries", type=int, default=2, help="Retries for rate-limited or timed-out OSM requests.")
    parser.add_argument("--review-threshold", type=int, default=300)
    parser.add_argument("--min-rating", type=float)
    parser.add_argument("--max-rating", type=float)
    parser.add_argument("--min-reviews", type=int)
    parser.add_argument("--max-reviews", type=int)
    parser.add_argument("--include-terms", nargs="+", help="Export only leads matching any term in name/category/address/city.")
    parser.add_argument("--exclude-terms", nargs="+", help="Exclude exported leads matching any term in name/category/address/city.")
    parser.add_argument(
        "--lead-preset",
        choices=["no_website_phone", "no_website", "mobile_no_website", "all"],
        default="no_website_phone",
        help="Export preset. Default: no_website_phone.",
    )
    parser.add_argument(
        "--secondary-scrape",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Optional enrichment for records that do have a real website. Default: disabled.",
    )
    parser.add_argument(
        "--formats",
        "--output-format",
        dest="formats",
        default="csv,json,xlsx",
        help="Comma-separated exports: csv,json,xlsx,xml,all",
    )
    parser.add_argument("--only-no-website", action="store_true")
    parser.add_argument("--has-phone", action="store_true")
    parser.add_argument("--mobile-only", action="store_true")
    parser.add_argument(
        "--include-do-not-contact",
        action="store_true",
        help="Include suppressed leads in exports. Default: excluded.",
    )
    parser.add_argument("--db-path", default="nosite_scout.sqlite")
    parser.add_argument("--out-dir", default="exports")
    return parser.parse_args()


def validate_args(args: argparse.Namespace) -> None:
    if args.manual_add and not args.manual_name:
        raise ValueError("--manual-add requires --manual-name")
    has_center = args.center_lat is not None and args.center_lng is not None
    if args.radius_km is not None and not has_center and args.provider == "google":
        raise ValueError("--radius-km requires both --center-lat and --center-lng with --provider google")
    if args.radius_km is not None and args.radius_km <= 0:
        raise ValueError("--radius-km must be greater than 0")
    if args.request_delay < 0:
        raise ValueError("--request-delay must be 0 or greater")
    if args.osm_retries < 0:
        raise ValueError("--osm-retries must be 0 or greater")
    if args.min_rating is not None and not 0 <= args.min_rating <= 5:
        raise ValueError("--min-rating must be between 0 and 5")
    if args.max_rating is not None and not 0 <= args.max_rating <= 5:
        raise ValueError("--max-rating must be between 0 and 5")
    if args.min_rating is not None and args.max_rating is not None and args.min_rating > args.max_rating:
        raise ValueError("--min-rating cannot be greater than --max-rating")
    if args.min_reviews is not None and args.min_reviews < 0:
        raise ValueError("--min-reviews must be 0 or greater")
    if args.max_reviews is not None and args.max_reviews < 0:
        raise ValueError("--max-reviews must be 0 or greater")
    if args.min_reviews is not None and args.max_reviews is not None and args.min_reviews > args.max_reviews:
        raise ValueError("--min-reviews cannot be greater than --max-reviews")


def slugify_id(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "manual"


def manual_lead_from_args(args: argparse.Namespace) -> dict[str, Any]:
    phone_preferred = normalize_phone(args.manual_phone)
    website = args.manual_website
    notes = args.manual_notes
    if website and not notes:
        notes = f"Has website, check if old/outdated: {website}"

    identifier_source = website or args.manual_name
    lead = {
        "place_id": f"manual:{slugify_id(identifier_source)}",
        "name": args.manual_name,
        "category": args.manual_category,
        "address": args.manual_address,
        "city": args.manual_city or extract_city(args.manual_address),
        "phone": phone_preferred,
        "formatted_phone_number": phone_preferred,
        "international_phone_number": phone_preferred if phone_preferred and phone_preferred.startswith("+") else None,
        "phone_preferred": phone_preferred,
        "mobile_phone": phone_preferred if is_likely_croatian_mobile(phone_preferred) else None,
        "has_phone": bool(phone_preferred),
        "website": website,
        "google_maps_url": None,
        "rating": None,
        "review_count": 0,
        "no_website": not is_real_website(website),
        "likely_small_business": True,
        "source": "manual",
        "status": args.manual_status,
        "notes": notes or "",
        "email": None,
        "contact_page_url": None,
        "facebook_url": None,
        "instagram_url": None,
        "whatsapp_url": None,
    }
    return lead


def build_search_targets(args: argparse.Namespace) -> list[str]:
    locations = args.locations or [args.location]
    countries = args.countries or []
    targets: list[str] = []

    for location in locations:
        if countries:
            for country in countries:
                target = location if country.lower() in location.lower() else f"{location}, {country}"
                if target not in targets:
                    targets.append(target)
        elif location not in targets:
            targets.append(location)

    return targets


def google_get(url: str, params: dict[str, Any]) -> dict[str, Any]:
    response = requests.get(url, params=params, timeout=20)
    response.raise_for_status()
    payload = response.json()
    status = payload.get("status")
    if status not in {"OK", "ZERO_RESULTS"}:
        message = payload.get("error_message") or status or "Unknown Google Places error"
        raise RuntimeError(message)
    return payload


def request_headers() -> dict[str, str]:
    return {"User-Agent": "NoSiteScout/0.1 (internal lead research; contact: local)"}


def geocode_location(location: str) -> tuple[float, float]:
    response = requests.get(
        NOMINATIM_SEARCH_URL,
        params={"q": location, "format": "jsonv2", "limit": 1},
        headers=request_headers(),
        timeout=20,
    )
    response.raise_for_status()
    payload = response.json()
    if not payload:
        raise RuntimeError(f"Could not geocode location with OpenStreetMap/Nominatim: {location}")
    return float(payload[0]["lat"]), float(payload[0]["lon"])


def osm_keyword_filters(keyword: str) -> list[str]:
    normalized = keyword.lower().replace("_", " ")
    mapping = {
        "restaurants": [('amenity', 'restaurant')],
        "restaurant": [('amenity', 'restaurant')],
        "cafes": [('amenity', 'cafe')],
        "cafe": [('amenity', 'cafe')],
        "apartments": [
            ('tourism', 'apartment'),
            ('tourism', 'chalet'),
            ('tourism', 'guest_house'),
            ('tourism', 'hotel'),
        ],
        "holiday homes": [('tourism', 'apartment'), ('tourism', 'chalet'), ('tourism', 'guest_house')],
        "holiday_homes": [('tourism', 'apartment'), ('tourism', 'chalet'), ('tourism', 'guest_house')],
        "vacation rentals": [('tourism', 'apartment'), ('tourism', 'chalet'), ('tourism', 'guest_house')],
        "vacation_rentals": [('tourism', 'apartment'), ('tourism', 'chalet'), ('tourism', 'guest_house')],
        "plumbers": [('craft', 'plumber')],
        "plumber": [('craft', 'plumber')],
        "electricians": [('craft', 'electrician')],
        "electrician": [('craft', 'electrician')],
        "beauty salon": [('shop', 'beauty'), ('shop', 'hairdresser')],
        "beauty_salon": [('shop', 'beauty'), ('shop', 'hairdresser')],
        "massage": [('shop', 'massage')],
        "massages": [('shop', 'massage')],
        "wellness spa": [('leisure', 'spa')],
        "wellness_spa": [('leisure', 'spa')],
        "spa": [('leisure', 'spa')],
        "physiotherapy": [('healthcare', 'physiotherapist')],
        "physiotherapists": [('healthcare', 'physiotherapist')],
        "fitness centres": [('leisure', 'fitness_centre')],
        "fitness_centres": [('leisure', 'fitness_centre')],
        "gyms": [('leisure', 'fitness_centre')],
        "mechanics": [('shop', 'car_repair'), ('craft', 'mechanic')],
        "mechanic": [('shop', 'car_repair'), ('craft', 'mechanic')],
        "dentists": [('amenity', 'dentist')],
        "dentist": [('amenity', 'dentist')],
        "private clinics": [('amenity', 'clinic'), ('amenity', 'doctors')],
        "private_clinics": [('amenity', 'clinic'), ('amenity', 'doctors')],
        "clinics": [('amenity', 'clinic'), ('amenity', 'doctors')],
        "veterinarians": [('amenity', 'veterinary')],
        "vets": [('amenity', 'veterinary')],
        "photographers": [('craft', 'photographer')],
        "photography": [('craft', 'photographer')],
        "small shops": [('shop', None)],
        "small_shops": [('shop', None)],
        "local services": [('craft', None), ('office', None)],
        "local_services": [('craft', None), ('office', None)],
    }
    pairs = mapping.get(normalized, [('name', keyword)])
    filters: list[str] = []
    for key, value in pairs:
        if value is None:
            filters.append(f'["{key}"]')
        elif key == "name":
            escaped = re.escape(value)
            filters.append(f'["name"~"{escaped}",i]')
        else:
            filters.append(f'["{key}"="{value}"]')
    return filters


def search_osm_places(
    keyword: str,
    location: str,
    max_results: int,
    center_lat: float | None = None,
    center_lng: float | None = None,
    radius_km: float | None = None,
    retries: int = 2,
) -> list[dict[str, Any]]:
    lat, lng = (center_lat, center_lng) if center_lat is not None and center_lng is not None else geocode_location(location)
    radius_m = int((radius_km or DEFAULT_OSM_RADIUS_KM) * 1000)
    tag_filters = osm_keyword_filters(keyword)
    selectors = "\n".join(
        f"      {element_type}{tag_filter}(around:{radius_m},{lat},{lng});"
        for tag_filter in tag_filters
        for element_type in ("node", "way", "relation")
    )
    query = f"""
    [out:json][timeout:30];
    (
{selectors}
    );
    out center tags {max_results};
    """
    for attempt in range(retries + 1):
        response = requests.post(
            OVERPASS_URL,
            data={"data": query},
            headers=request_headers(),
            timeout=45,
        )
        if response.status_code not in OSM_RETRY_STATUSES:
            response.raise_for_status()
            return response.json().get("elements", [])[:max_results]
        if attempt >= retries:
            response.raise_for_status()
        wait_seconds = 15 * (attempt + 1)
        print(
            f"OSM request got HTTP {response.status_code}; retrying in {wait_seconds}s...",
            file=sys.stderr,
        )
        time.sleep(wait_seconds)

    return []


def search_places(
    api_key: str,
    keyword: str,
    location: str,
    max_results: int,
    center_lat: float | None = None,
    center_lng: float | None = None,
    radius_km: float | None = None,
) -> list[dict[str, Any]]:
    query = f"{keyword} in {location}"
    params = {"query": query, "key": api_key}
    if center_lat is not None and center_lng is not None and radius_km is not None:
        params["location"] = f"{center_lat},{center_lng}"
        params["radius"] = int(radius_km * 1000)
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
    params = {"place_id": place_id, "fields": DETAIL_FIELDS, "key": api_key}
    payload = google_get(DETAILS_URL, params)
    return payload.get("result")


def first_match(pattern: str, text: str) -> str | None:
    match = re.search(pattern, text, flags=re.IGNORECASE)
    return html.unescape(match.group(1)).strip() if match else None


def absolutize_link(base_url: str, link: str | None) -> str | None:
    if not link:
        return None
    link = html.unescape(link.strip())
    if link.startswith(("http://", "https://")):
        return link
    if link.startswith("//"):
        return f"https:{link}"
    if link.startswith("/"):
        parsed = urlparse(base_url)
        return f"{parsed.scheme}://{parsed.netloc}{link}"
    return link


def fetch_page(url: str) -> str | None:
    try:
        response = requests.get(
            url,
            timeout=10,
            headers=request_headers(),
            allow_redirects=True,
        )
        response.raise_for_status()
    except requests.RequestException:
        return None

    content_type = response.headers.get("content-type", "").lower()
    if content_type and "html" not in content_type and "text" not in content_type:
        return None
    return response.text[:500_000]


def extract_contact_fields(text: str, base_url: str) -> dict[str, str | None]:
    found = {
        "email": None,
        "contact_page_url": None,
        "facebook_url": None,
        "instagram_url": None,
        "whatsapp_url": None,
    }
    email_match = re.search(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", text, flags=re.IGNORECASE)
    if email_match:
        found["email"] = html.unescape(email_match.group(0))

    patterns = {
        "facebook_url": r'href=["\']([^"\']*facebook\.com[^"\']*)["\']',
        "instagram_url": r'href=["\']([^"\']*instagram\.com[^"\']*)["\']',
        "whatsapp_url": r'href=["\']([^"\']*(?:wa\.me|whatsapp\.com)[^"\']*)["\']',
        "contact_page_url": r'href=["\']([^"\']*(?:kontakt|contact|contatti)[^"\']*)["\']',
    }
    for field, pattern in patterns.items():
        found[field] = absolutize_link(base_url, first_match(pattern, text))

    return found


def candidate_contact_urls(base_url: str, detected_url: str | None) -> list[str]:
    candidates: list[str] = []
    if detected_url:
        candidates.append(detected_url)

    parsed = urlparse(base_url if "://" in base_url else f"https://{base_url}")
    root = f"{parsed.scheme}://{parsed.netloc}"
    for path in ("/contact", "/kontakt", "/contatti", "/contacts", "/kontaktirajte-nas"):
        candidates.append(f"{root}{path}")

    unique: list[str] = []
    for url in candidates:
        if url and url not in unique:
            unique.append(url)
    return unique


def merge_missing(base: dict[str, str | None], extra: dict[str, str | None]) -> dict[str, str | None]:
    for key, value in extra.items():
        if value and not base.get(key):
            base[key] = value
    return base


def scrape_website(url: str | None, scrape_contact_pages: bool = True) -> dict[str, str | None]:
    found = {
        "email": None,
        "contact_page_url": None,
        "facebook_url": None,
        "instagram_url": None,
        "whatsapp_url": None,
    }
    if not is_real_website(url):
        return found

    homepage = fetch_page(url or "")
    if not homepage:
        return found

    found = extract_contact_fields(homepage, url or "")
    if not scrape_contact_pages:
        return found

    for contact_url in candidate_contact_urls(url or "", found.get("contact_page_url"))[:5]:
        contact_page = fetch_page(contact_url)
        if not contact_page:
            continue
        found["contact_page_url"] = found.get("contact_page_url") or contact_url
        merge_missing(found, extract_contact_fields(contact_page, contact_url))
        if found.get("email") and found.get("facebook_url") and found.get("instagram_url"):
            break

    return found


def first_tag(tags: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = tags.get(key)
        if value:
            return str(value).strip()
    return None


def osm_address(tags: dict[str, Any]) -> str | None:
    parts = [
        first_tag(tags, "addr:street"),
        first_tag(tags, "addr:housenumber"),
        first_tag(tags, "addr:postcode"),
        first_tag(tags, "addr:city", "addr:town", "addr:village"),
        first_tag(tags, "addr:country"),
    ]
    address = ", ".join(part for part in parts if part)
    return address or None


def osm_category(tags: dict[str, Any], fallback: str) -> str:
    for key in ("amenity", "shop", "tourism", "craft", "office", "leisure"):
        if tags.get(key):
            return f"{key}:{tags[key]}"
    return fallback


def osm_to_lead(
    element: dict[str, Any],
    keyword: str,
    location: str,
    review_threshold: int,
    secondary_scrape: bool = False,
) -> dict[str, Any]:
    tags = element.get("tags") or {}
    phone_preferred = normalize_phone(first_tag(tags, "contact:phone", "phone", "mobile", "contact:mobile"))
    website = first_tag(tags, "contact:website", "website", "url")
    email = first_tag(tags, "contact:email", "email")
    facebook_url = first_tag(tags, "contact:facebook", "facebook")
    instagram_url = first_tag(tags, "contact:instagram", "instagram")
    whatsapp_url = first_tag(tags, "contact:whatsapp", "whatsapp")
    address = osm_address(tags) or location
    city = first_tag(tags, "addr:city", "addr:town", "addr:village") or extract_city(address)
    name = first_tag(tags, "name", "official_name", "brand") or f"Unnamed {keyword}"

    lead = {
        "place_id": f"osm:{element.get('type')}:{element.get('id')}",
        "name": name,
        "category": osm_category(tags, keyword),
        "address": address,
        "city": city,
        "phone": phone_preferred,
        "formatted_phone_number": phone_preferred,
        "international_phone_number": phone_preferred if phone_preferred and phone_preferred.startswith("+") else None,
        "phone_preferred": phone_preferred,
        "mobile_phone": phone_preferred if is_likely_croatian_mobile(phone_preferred) else None,
        "has_phone": bool(phone_preferred),
        "website": website,
        "google_maps_url": None,
        "rating": None,
        "review_count": 0,
        "no_website": not is_real_website(website),
        "likely_small_business": False,
        "source": "openstreetmap",
        "status": "new",
        "notes": "",
        "email": email,
        "contact_page_url": first_tag(tags, "contact:url"),
        "facebook_url": facebook_url,
        "instagram_url": instagram_url,
        "whatsapp_url": whatsapp_url,
    }
    lead["likely_small_business"] = score_likely_small_business(lead, review_threshold)
    if secondary_scrape and is_real_website(website):
        scraped = scrape_website(website)
        for key, value in scraped.items():
            if value and not lead.get(key):
                lead[key] = value
    return lead


def detail_to_lead(
    detail: dict[str, Any],
    keyword: str,
    review_threshold: int,
    secondary_scrape: bool = False,
) -> dict[str, Any]:
    address = detail.get("formatted_address")
    formatted_phone = normalize_phone(detail.get("formatted_phone_number"))
    international_phone = normalize_phone(detail.get("international_phone_number"))
    phone_preferred = international_phone or formatted_phone
    website = detail.get("website")
    types = detail.get("types") or []
    category = ",".join(types)

    lead = {
        "place_id": detail.get("place_id"),
        "name": detail.get("name"),
        "category": category or keyword,
        "address": address,
        "city": extract_city(address),
        "phone": phone_preferred,
        "formatted_phone_number": formatted_phone,
        "international_phone_number": international_phone,
        "phone_preferred": phone_preferred,
        "mobile_phone": phone_preferred if is_likely_croatian_mobile(phone_preferred) else None,
        "has_phone": bool(phone_preferred),
        "website": website,
        "google_maps_url": detail.get("url"),
        "rating": detail.get("rating"),
        "review_count": int(detail.get("user_ratings_total") or 0),
        "no_website": not is_real_website(website),
        "likely_small_business": False,
        "source": "google_places",
        "status": "new",
        "notes": "",
        "email": None,
        "contact_page_url": None,
        "facebook_url": None,
        "instagram_url": None,
        "whatsapp_url": None,
    }
    lead["likely_small_business"] = score_likely_small_business(lead, review_threshold)
    if secondary_scrape and is_real_website(website):
        lead.update(scrape_website(website))
    return lead


def connect_db(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS leads (
            place_id TEXT PRIMARY KEY,
            name TEXT,
            category TEXT,
            address TEXT,
            city TEXT,
            phone TEXT,
            formatted_phone_number TEXT,
            international_phone_number TEXT,
            phone_preferred TEXT,
            mobile_phone TEXT,
            has_phone INTEGER,
            website TEXT,
            google_maps_url TEXT,
            rating REAL,
            review_count INTEGER,
            no_website INTEGER,
            likely_small_business INTEGER,
            source TEXT,
            status TEXT DEFAULT 'new',
            assigned_to TEXT,
            next_follow_up_at TEXT,
            last_contacted_at TEXT,
            do_not_contact INTEGER DEFAULT 0,
            estimated_value REAL,
            notes TEXT DEFAULT '',
            email TEXT,
            contact_page_url TEXT,
            facebook_url TEXT,
            instagram_url TEXT,
            whatsapp_url TEXT,
            created_at TEXT,
            updated_at TEXT
        )
        """
    )
    existing_columns = {row[1] for row in conn.execute("PRAGMA table_info(leads)")}
    workflow_columns = {
        "assigned_to": "TEXT",
        "next_follow_up_at": "TEXT",
        "last_contacted_at": "TEXT",
        "do_not_contact": "INTEGER DEFAULT 0",
        "estimated_value": "REAL",
    }
    for column, definition in workflow_columns.items():
        if column not in existing_columns:
            conn.execute(f"ALTER TABLE leads ADD COLUMN {column} {definition}")
    conn.commit()
    return conn


def upsert_lead(conn: sqlite3.Connection, lead: dict[str, Any]) -> str:
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    row = {column: lead.get(column) for column in LEAD_COLUMNS}
    row["created_at"] = now
    row["updated_at"] = now
    for key in ("has_phone", "no_website", "likely_small_business", "do_not_contact"):
        row[key] = int(bool(row[key]))

    existing = conn.execute("SELECT place_id FROM leads WHERE place_id = ?", (row["place_id"],)).fetchone()
    placeholders = ",".join("?" for _ in LEAD_COLUMNS)
    protected_workflow_columns = {
        "place_id",
        "created_at",
        "status",
        "assigned_to",
        "next_follow_up_at",
        "last_contacted_at",
        "do_not_contact",
        "estimated_value",
        "notes",
    }
    update_columns = [column for column in LEAD_COLUMNS if column not in protected_workflow_columns]
    update_sql = ", ".join(f"{column} = excluded.{column}" for column in update_columns)
    update_sql += ", status = COALESCE(NULLIF(leads.status, ''), excluded.status)"
    update_sql += ", notes = COALESCE(NULLIF(leads.notes, ''), excluded.notes)"
    update_sql += ", updated_at = excluded.updated_at"
    conn.execute(
        f"""
        INSERT INTO leads ({",".join(LEAD_COLUMNS)})
        VALUES ({placeholders})
        ON CONFLICT(place_id) DO UPDATE SET {update_sql}
        """,
        [row[column] for column in LEAD_COLUMNS],
    )
    return "updated" if existing else "new"


def load_export_rows(conn: sqlite3.Connection, args: argparse.Namespace) -> list[dict[str, Any]]:
    clauses: list[str] = []
    params: list[Any] = []
    if not args.include_do_not_contact:
        clauses.append("COALESCE(do_not_contact, 0) = 0")
    if args.lead_preset in {"no_website_phone", "no_website", "mobile_no_website"}:
        clauses.append("no_website = 1")
    if args.lead_preset == "no_website_phone":
        clauses.append("has_phone = 1")
    if args.lead_preset == "mobile_no_website":
        clauses.append("mobile_phone IS NOT NULL AND mobile_phone != ''")
    if args.only_no_website:
        clauses.append("no_website = 1")
    if args.has_phone:
        clauses.append("has_phone = 1")
    if args.mobile_only:
        clauses.append("mobile_phone IS NOT NULL AND mobile_phone != ''")
    if args.min_rating is not None:
        clauses.append("rating >= ?")
        params.append(args.min_rating)
    if args.max_rating is not None:
        clauses.append("rating <= ?")
        params.append(args.max_rating)
    if args.min_reviews is not None:
        clauses.append("review_count >= ?")
        params.append(args.min_reviews)
    if args.max_reviews is not None:
        clauses.append("review_count <= ?")
        params.append(args.max_reviews)
    if args.include_terms:
        term_clauses = []
        for term in args.include_terms:
            term_clauses.append(
                "(name LIKE ? OR category LIKE ? OR address LIKE ? OR city LIKE ?)"
            )
            params.extend([f"%{term}%"] * 4)
        clauses.append(f"({' OR '.join(term_clauses)})")
    if args.exclude_terms:
        for term in args.exclude_terms:
            clauses.append(
                "NOT (name LIKE ? OR category LIKE ? OR address LIKE ? OR city LIKE ?)"
            )
            params.extend([f"%{term}%"] * 4)

    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    sql = f"""
        SELECT {",".join(LEAD_COLUMNS)}
        FROM leads
        {where}
        ORDER BY no_website DESC, has_phone DESC, likely_small_business DESC, review_count DESC
    """
    return [dict(row) for row in conn.execute(sql, params).fetchall()]


def export_xml(rows: list[dict[str, Any]], path: Path) -> None:
    root = ET.Element("leads")
    for row in rows:
        lead_el = ET.SubElement(root, "lead")
        for key in LEAD_COLUMNS:
            child = ET.SubElement(lead_el, key)
            value = row.get(key)
            child.text = "" if value is None else str(value)
    tree = ET.ElementTree(root)
    ET.indent(tree, space="  ")
    tree.write(path, encoding="utf-8", xml_declaration=True)


def export_rows(rows: list[dict[str, Any]], formats: list[str], out_dir: str) -> list[Path]:
    if pd is None:
        raise RuntimeError("pandas is required for exports. Run: pip install -r requirements.txt")

    output_dir = Path(out_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    df = pd.DataFrame(rows, columns=LEAD_COLUMNS)
    paths: list[Path] = []

    for fmt in formats:
        path = output_dir / f"nosite_scout_{timestamp}.{fmt}"
        if fmt == "csv":
            df.to_csv(path, index=False)
        elif fmt == "json":
            df.to_json(path, orient="records", indent=2, force_ascii=False)
        elif fmt == "xlsx":
            df.to_excel(path, index=False, engine="openpyxl")
        elif fmt == "xml":
            export_xml(rows, path)
        else:
            raise ValueError(f"Unsupported export format: {fmt}")
        paths.append(path)
    return paths


def parse_formats(raw: str) -> list[str]:
    formats = [part.strip().lower() for part in raw.split(",") if part.strip()]
    allowed = {"csv", "json", "xlsx", "xml"}
    if "all" in formats:
        if len(formats) > 1:
            raise ValueError("Use 'all' by itself, not mixed with other formats")
        return ["csv", "json", "xlsx", "xml"]
    invalid = sorted(set(formats) - allowed)
    if invalid:
        raise ValueError(f"Unsupported export format(s): {', '.join(invalid)}")
    return formats or ["csv"]


def main() -> int:
    if load_dotenv is not None:
        load_dotenv()
    args = parse_args()
    try:
        validate_args(args)
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    api_key = os.getenv("GOOGLE_MAPS_API_KEY")
    if args.provider == "google" and not api_key:
        print(
            "Error: GOOGLE_MAPS_API_KEY is required only when using --provider google.",
            file=sys.stderr,
        )
        return 1

    try:
        formats = parse_formats(args.formats)
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    if pd is None:
        print("Error: pandas is missing. Run: pip install -r requirements.txt", file=sys.stderr)
        return 1

    conn = connect_db(args.db_path)
    seen_place_ids: set[str] = set()
    total_places_found = 0
    saved_new = 0
    saved_updated = 0
    skipped_searches = 0
    search_targets = build_search_targets(args)

    if args.manual_add:
        result = upsert_lead(conn, manual_lead_from_args(args))
        conn.commit()
        saved_new = 1 if result == "new" else 0
        saved_updated = 1 if result == "updated" else 0
        rows = load_export_rows(conn, args)
        export_paths = export_rows(rows, formats, args.out_dir)
        print("\nNoSite Scout summary")
        print("- manual lead saved: 1")
        print(f"- new leads saved: {saved_new}")
        print(f"- updated leads saved: {saved_updated}")
        print(f"- exported rows count: {len(rows)}")
        print("- export file paths:")
        for path in export_paths:
            print(f"  {path}")
        return 0

    try:
        for search_target in search_targets:
            for keyword in args.keywords:
                print(f"Searching {args.provider}: {keyword} in {search_target}")
                if args.request_delay:
                    time.sleep(args.request_delay)
                try:
                    if args.provider == "google":
                        places = search_places(
                            api_key or "",
                            keyword,
                            search_target,
                            args.max_results,
                            args.center_lat,
                            args.center_lng,
                            args.radius_km,
                        )
                    else:
                        places = search_osm_places(
                            keyword,
                            search_target,
                            args.max_results,
                            args.center_lat,
                            args.center_lng,
                            args.radius_km,
                            args.osm_retries,
                        )
                except (requests.RequestException, RuntimeError) as exc:
                    if args.provider == "osm":
                        skipped_searches += 1
                        print(f"Warning: skipped OSM search for {keyword} in {search_target}: {exc}", file=sys.stderr)
                        continue
                    raise
                total_places_found += len(places)
                for place in places:
                    place_id = (
                        place.get("place_id")
                        if args.provider == "google"
                        else f"osm:{place.get('type')}:{place.get('id')}"
                    )
                    if not place_id or place_id in seen_place_ids:
                        continue
                    seen_place_ids.add(place_id)
                    time.sleep(0.15)
                    if args.provider == "google":
                        detail = fetch_place_details(api_key or "", place_id)
                        if not detail:
                            continue
                        lead = detail_to_lead(
                            detail,
                            keyword,
                            args.review_threshold,
                            args.secondary_scrape,
                        )
                    else:
                        lead = osm_to_lead(
                            place,
                            keyword,
                            search_target,
                            args.review_threshold,
                            args.secondary_scrape,
                        )
                    result = upsert_lead(conn, lead)
                    if result == "new":
                        saved_new += 1
                    else:
                        saved_updated += 1
                conn.commit()
    except (requests.RequestException, RuntimeError) as exc:
        conn.rollback()
        print(f"Error while calling {args.provider}: {exc}", file=sys.stderr)
        return 1

    rows = load_export_rows(conn, args)
    export_paths = export_rows(rows, formats, args.out_dir)

    no_website_count = sum(1 for row in rows if row.get("no_website"))
    phone_count = sum(1 for row in rows if row.get("has_phone"))
    mobile_count = sum(1 for row in rows if row.get("mobile_phone"))

    print("\nNoSite Scout summary")
    print(f"- searched target count: {len(search_targets)}")
    print(f"- searched keywords count: {len(args.keywords)}")
    print(f"- skipped searches count: {skipped_searches}")
    print(f"- total places found: {total_places_found}")
    print(f"- new leads saved: {saved_new}")
    print(f"- updated leads saved: {saved_updated}")
    print(f"- no-website leads count: {no_website_count}")
    print(f"- leads with phone count: {phone_count}")
    print(f"- mobile-looking phone count: {mobile_count}")
    print("- export file paths:")
    for path in export_paths:
        print(f"  {path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
