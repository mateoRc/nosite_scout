import argparse
import unittest

from accommodation_search import (
    GOOGLE_ACCOMMODATION_KEYWORDS,
    get_campaign,
)
from nosite_scout import DEFAULT_KEYWORDS, apply_campaign_defaults, build_search_targets


def args_for(**overrides):
    values = {
        "campaign": None,
        "provider": "osm",
        "location": "Istria, Croatia",
        "locations": None,
        "countries": None,
        "keywords": None,
        "radius_km": None,
    }
    values.update(overrides)
    return argparse.Namespace(**values)


class AccommodationCampaignTests(unittest.TestCase):
    def test_osm_campaign_keeps_geography_and_uses_structured_query(self):
        args = apply_campaign_defaults(args_for(campaign="accommodation"))
        self.assertIsNone(args.locations)
        self.assertEqual(args.keywords, ["apartments"])
        self.assertEqual(args.radius_km, 12.0)
        self.assertEqual(build_search_targets(args), ["Istria, Croatia"])

    def test_google_campaign_uses_richer_text_queries(self):
        args = apply_campaign_defaults(args_for(campaign="accommodation", provider="google"))
        self.assertEqual(args.keywords, list(GOOGLE_ACCOMMODATION_KEYWORDS))
        self.assertIn("apartmani", args.keywords)
        self.assertIsNone(args.radius_km)

    def test_explicit_values_override_campaign(self):
        args = apply_campaign_defaults(
            args_for(
                campaign="accommodation",
                locations=["Rovinj"],
                countries=["Croatia"],
                keywords=["villas"],
                radius_km=7,
            )
        )
        self.assertEqual(args.locations, ["Rovinj"])
        self.assertEqual(args.keywords, ["villas"])
        self.assertEqual(args.radius_km, 7)

    def test_no_campaign_keeps_original_keywords(self):
        args = apply_campaign_defaults(args_for())
        self.assertEqual(args.keywords, DEFAULT_KEYWORDS)

    def test_unknown_campaign_is_rejected(self):
        with self.assertRaises(ValueError):
            get_campaign("unknown", "osm")


if __name__ == "__main__":
    unittest.main()
