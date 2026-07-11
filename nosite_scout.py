#!/usr/bin/env python3
"""NoSite Scout CLI and backward-compatible public API facade."""

from scout.app import main
from scout.cli import (
    apply_campaign_defaults,
    build_search_targets,
    manual_lead_from_args,
    parse_args,
    validate_args,
)
from scout.constants import DEFAULT_KEYWORDS, LEAD_COLUMNS
from scout.domain import (
    extract_city,
    is_likely_croatian_mobile,
    is_real_website,
    normalize_phone,
    score_likely_small_business,
)
from scout.exporting import export_rows, parse_formats
from scout.lead_factory import google_detail_to_lead as detail_to_lead
from scout.lead_factory import osm_to_lead
from scout.providers import (
    fetch_place_details,
    geocode_location,
    osm_keyword_filters,
    search_google_places as search_places,
    search_osm_places,
)
from scout.storage import connect_db, load_export_rows, upsert_lead

__all__ = [
    "DEFAULT_KEYWORDS", "LEAD_COLUMNS", "apply_campaign_defaults", "build_search_targets",
    "connect_db", "detail_to_lead", "export_rows", "extract_city", "fetch_place_details",
    "geocode_location", "is_likely_croatian_mobile", "is_real_website", "load_export_rows",
    "main", "manual_lead_from_args", "normalize_phone", "osm_keyword_filters", "osm_to_lead",
    "parse_args", "parse_formats", "score_likely_small_business", "search_osm_places",
    "search_places", "upsert_lead", "validate_args",
]


if __name__ == "__main__":
    raise SystemExit(main())
