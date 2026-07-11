"""Translate provider payloads into the canonical lead record."""

from __future__ import annotations

from typing import Any

from .domain import (
    extract_city, is_likely_croatian_mobile, is_real_website, normalize_phone,
    score_likely_small_business,
)
from .enrichment import scrape_website
from .providers import first_tag, osm_address, osm_category


def osm_to_lead(element: dict[str, Any], keyword: str, location: str,
                review_threshold: int, secondary_scrape: bool = False) -> dict[str, Any]:
    tags = element.get("tags") or {}
    phone = first_tag(tags, "contact:phone", "phone", "contact:mobile", "mobile")
    phone_preferred = normalize_phone(phone)
    website = first_tag(tags, "contact:website", "website", "url")
    address = osm_address(tags) or location
    city = first_tag(tags, "addr:city", "addr:town", "addr:village") or extract_city(address)
    name = first_tag(tags, "name", "official_name", "brand") or f"Unnamed {keyword}"
    lead = {
        "place_id": f"osm:{element.get('type')}:{element.get('id')}",
        "name": name, "category": osm_category(tags, keyword), "address": address, "city": city,
        "phone": phone_preferred, "formatted_phone_number": phone_preferred,
        "international_phone_number": phone_preferred if phone_preferred and phone_preferred.startswith("+") else None,
        "phone_preferred": phone_preferred,
        "mobile_phone": phone_preferred if is_likely_croatian_mobile(phone_preferred) else None,
        "has_phone": bool(phone_preferred), "website": website, "google_maps_url": None,
        "rating": None, "review_count": 0, "no_website": not is_real_website(website),
        "likely_small_business": False, "source": "openstreetmap", "status": "new", "notes": "",
        "email": first_tag(tags, "contact:email", "email"),
        "contact_page_url": first_tag(tags, "contact:url"),
        "facebook_url": first_tag(tags, "contact:facebook", "facebook"),
        "instagram_url": first_tag(tags, "contact:instagram", "instagram"),
        "whatsapp_url": first_tag(tags, "contact:whatsapp", "whatsapp"),
    }
    lead["likely_small_business"] = score_likely_small_business(lead, review_threshold)
    if secondary_scrape and is_real_website(website):
        for key, value in scrape_website(website).items():
            if value and not lead.get(key):
                lead[key] = value
    return lead


def google_detail_to_lead(detail: dict[str, Any], keyword: str, review_threshold: int,
                          secondary_scrape: bool = False) -> dict[str, Any]:
    address = detail.get("formatted_address")
    formatted_phone = normalize_phone(detail.get("formatted_phone_number"))
    international_phone = normalize_phone(detail.get("international_phone_number"))
    phone_preferred = international_phone or formatted_phone
    website = detail.get("website")
    category = ",".join(detail.get("types") or []) or keyword
    lead = {
        "place_id": detail.get("place_id"), "name": detail.get("name"), "category": category,
        "address": address, "city": extract_city(address), "phone": phone_preferred,
        "formatted_phone_number": formatted_phone, "international_phone_number": international_phone,
        "phone_preferred": phone_preferred,
        "mobile_phone": phone_preferred if is_likely_croatian_mobile(phone_preferred) else None,
        "has_phone": bool(phone_preferred), "website": website, "google_maps_url": detail.get("url"),
        "rating": detail.get("rating"), "review_count": int(detail.get("user_ratings_total") or 0),
        "no_website": not is_real_website(website), "likely_small_business": False,
        "source": "google_places", "status": "new", "notes": "", "email": None,
        "contact_page_url": None, "facebook_url": None, "instagram_url": None, "whatsapp_url": None,
    }
    lead["likely_small_business"] = score_likely_small_business(lead, review_threshold)
    if secondary_scrape and is_real_website(website):
        lead.update(scrape_website(website))
    return lead
