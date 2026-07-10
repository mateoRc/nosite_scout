"""Focused accommodation campaign definitions for NoSite Scout."""

from __future__ import annotations

from dataclasses import dataclass


GOOGLE_ACCOMMODATION_KEYWORDS = (
    "apartments",
    "apartmani",
    "holiday home",
    "kuća za odmor",
    "villa rental",
    "guest house",
    "rooms",
    "sobe",
    "agrotourism",
)

# OSM uses structured tourism tags. Repeating text synonyms would execute the
# same Overpass query, so one broad keyword is both faster and more respectful
# of the public service.
OSM_ACCOMMODATION_KEYWORDS = ("apartments",)


@dataclass(frozen=True)
class CampaignConfig:
    keywords: tuple[str, ...]
    radius_km: float | None


def get_campaign(name: str, provider: str) -> CampaignConfig:
    """Return provider-aware defaults for a named search campaign."""
    if name != "accommodation":
        raise ValueError(f"Unknown campaign: {name}")
    keywords = GOOGLE_ACCOMMODATION_KEYWORDS if provider == "google" else OSM_ACCOMMODATION_KEYWORDS
    return CampaignConfig(
        keywords=keywords,
        # A radius is useful for OSM's structured around query. Google text
        # search already uses each town name and requires coordinates when a
        # radius is supplied, so leave it unset there.
        radius_km=12.0 if provider == "osm" else None,
    )
