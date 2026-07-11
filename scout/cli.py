"""Command-line parsing, validation, and explicit option expansion."""

from __future__ import annotations

import argparse
from typing import Any

from .campaigns import get_campaign
from .constants import DEFAULT_KEYWORDS
from .domain import extract_city, is_likely_croatian_mobile, is_real_website, normalize_phone, slugify_id


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Find local businesses that likely lack a real website.")
    parser.add_argument("--manual-add", action="store_true", help="Add one lead manually, then export.")
    parser.add_argument("--manual-name")
    parser.add_argument("--manual-phone")
    parser.add_argument("--manual-website")
    parser.add_argument("--manual-address")
    parser.add_argument("--manual-city")
    parser.add_argument("--manual-category", default="manual_review")
    parser.add_argument("--manual-notes")
    parser.add_argument("--manual-status", default="review_website_age")
    parser.add_argument("--provider", choices=["osm", "google"], default="osm")
    parser.add_argument("--campaign", choices=["accommodation"],
                        help="Apply focused search defaults; explicit locations, keywords, and radius override them.")
    parser.add_argument("--location", default="Istria, Croatia")
    parser.add_argument("--locations", nargs="+")
    parser.add_argument("--countries", nargs="+")
    parser.add_argument("--radius-km", "--range-km", dest="radius_km", type=float)
    parser.add_argument("--center-lat", type=float)
    parser.add_argument("--center-lng", type=float)
    parser.add_argument("--keywords", nargs="+")
    parser.add_argument("--max-results", type=int, default=50)
    parser.add_argument("--request-delay", type=float, default=2.0)
    parser.add_argument("--osm-retries", type=int, default=2)
    parser.add_argument("--review-threshold", type=int, default=300)
    parser.add_argument("--min-rating", type=float)
    parser.add_argument("--max-rating", type=float)
    parser.add_argument("--min-reviews", type=int)
    parser.add_argument("--max-reviews", type=int)
    parser.add_argument("--include-terms", nargs="+")
    parser.add_argument("--exclude-terms", nargs="+")
    parser.add_argument("--lead-preset", choices=["no_website_phone", "no_website", "mobile_no_website", "all"],
                        default="no_website_phone")
    parser.add_argument("--secondary-scrape", action=argparse.BooleanOptionalAction, default=False)
    parser.add_argument("--formats", "--output-format", dest="formats", default="csv,json,xlsx")
    parser.add_argument("--only-no-website", action="store_true")
    parser.add_argument("--has-phone", action="store_true")
    parser.add_argument("--mobile-only", action="store_true")
    parser.add_argument("--include-do-not-contact", action="store_true")
    parser.add_argument("--db-path", default="nosite_scout.sqlite")
    parser.add_argument("--out-dir", default="exports")
    return parser.parse_args()


def apply_campaign_defaults(args: argparse.Namespace) -> argparse.Namespace:
    if args.campaign:
        campaign = get_campaign(args.campaign, args.provider)
        if args.keywords is None:
            args.keywords = list(campaign.keywords)
        if args.radius_km is None and campaign.radius_km is not None:
            args.radius_km = campaign.radius_km
    elif args.keywords is None:
        args.keywords = list(DEFAULT_KEYWORDS)
    return args


def validate_args(args: argparse.Namespace) -> None:
    if args.manual_add and not args.manual_name:
        raise ValueError("--manual-add requires --manual-name")
    one_coordinate = (args.center_lat is None) != (args.center_lng is None)
    if one_coordinate:
        raise ValueError("--center-lat and --center-lng must be provided together")
    has_center = args.center_lat is not None and args.center_lng is not None
    if args.radius_km is not None and not has_center and args.provider == "google":
        raise ValueError("--radius-km requires both --center-lat and --center-lng with --provider google")
    if args.radius_km is not None and args.radius_km <= 0:
        raise ValueError("--radius-km must be greater than 0")
    if args.request_delay < 0 or args.osm_retries < 0:
        raise ValueError("request delay and retry count cannot be negative")
    if args.max_results <= 0:
        raise ValueError("--max-results must be greater than 0")
    for field in ("min_rating", "max_rating"):
        value = getattr(args, field)
        if value is not None and not 0 <= value <= 5:
            raise ValueError(f"--{field.replace('_', '-')} must be between 0 and 5")
    for field in ("min_reviews", "max_reviews"):
        value = getattr(args, field)
        if value is not None and value < 0:
            raise ValueError(f"--{field.replace('_', '-')} must be 0 or greater")
    if args.min_rating is not None and args.max_rating is not None and args.min_rating > args.max_rating:
        raise ValueError("--min-rating cannot be greater than --max-rating")
    if args.min_reviews is not None and args.max_reviews is not None and args.min_reviews > args.max_reviews:
        raise ValueError("--min-reviews cannot be greater than --max-reviews")


def build_search_targets(args: argparse.Namespace) -> list[str]:
    targets: list[str] = []
    for location in args.locations or [args.location]:
        candidates = [location]
        if args.countries:
            candidates = [location if country.lower() in location.lower() else f"{location}, {country}"
                          for country in args.countries]
        for target in candidates:
            if target not in targets:
                targets.append(target)
    return targets


def manual_lead_from_args(args: argparse.Namespace) -> dict[str, Any]:
    phone = normalize_phone(args.manual_phone)
    notes = args.manual_notes or (
        f"Has website, check if old/outdated: {args.manual_website}" if args.manual_website else ""
    )
    identifier = args.manual_website or args.manual_name
    return {
        "place_id": f"manual:{slugify_id(identifier)}", "name": args.manual_name,
        "category": args.manual_category, "address": args.manual_address,
        "city": args.manual_city or extract_city(args.manual_address), "phone": phone,
        "formatted_phone_number": phone,
        "international_phone_number": phone if phone and phone.startswith("+") else None,
        "phone_preferred": phone, "mobile_phone": phone if is_likely_croatian_mobile(phone) else None,
        "has_phone": bool(phone), "website": args.manual_website, "google_maps_url": None,
        "rating": None, "review_count": 0, "no_website": not is_real_website(args.manual_website),
        "likely_small_business": True, "source": "manual", "status": args.manual_status,
        "notes": notes, "email": None, "contact_page_url": None, "facebook_url": None,
        "instagram_url": None, "whatsapp_url": None,
    }
