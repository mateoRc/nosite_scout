import argparse
import unittest

from scout.cli import validate_args
from scout.domain import extract_city, is_real_website, normalize_phone
from scout.providers import osm_keyword_filters
from scout.storage import connect_db, upsert_lead


class DomainTests(unittest.TestCase):
    def test_phone_and_website_normalization(self):
        self.assertEqual(normalize_phone("+385 (91) 123-4567"), "+385911234567")
        self.assertFalse(is_real_website("https://instagram.com/example"))
        self.assertTrue(is_real_website("https://example.hr"))

    def test_city_extraction_supports_croatian_characters(self):
        self.assertEqual(extract_city("Ulica 1, 52440 Poreč, Croatia"), "Poreč")


class ProviderMappingTests(unittest.TestCase):
    def test_accommodation_query_uses_structured_osm_tags(self):
        filters = osm_keyword_filters("apartments")
        self.assertIn('["tourism"="apartment"]', filters)
        self.assertIn('["tourism"="guest_house"]', filters)


class StorageTests(unittest.TestCase):
    def setUp(self):
        self.conn = connect_db(":memory:")

    def tearDown(self):
        self.conn.close()

    def test_upsert_refreshes_business_data_but_preserves_workflow(self):
        lead = {
            "place_id": "osm:node:1", "name": "Before", "category": "tourism:apartment",
            "has_phone": True, "no_website": True, "likely_small_business": True,
            "status": "new", "notes": "",
        }
        self.assertEqual(upsert_lead(self.conn, lead), "new")
        self.conn.execute(
            "UPDATE leads SET status='contacted', notes='Keep me', assigned_to='Mateo' WHERE place_id=?",
            (lead["place_id"],),
        )
        lead["name"] = "After"
        self.assertEqual(upsert_lead(self.conn, lead), "updated")
        row = self.conn.execute(
            "SELECT name, status, notes, assigned_to, prospect_probability FROM leads WHERE place_id=?",
            (lead["place_id"],),
        ).fetchone()
        self.assertEqual(tuple(row[:4]), ("After", "contacted", "Keep me", "Mateo"))
        self.assertEqual(row[4], 13.0)


class ValidationTests(unittest.TestCase):
    def test_rejects_half_of_coordinate_pair(self):
        args = argparse.Namespace(
            manual_add=False, manual_name=None, center_lat=45.0, center_lng=None,
            radius_km=None, provider="osm", request_delay=0, osm_retries=0,
            max_results=10, min_rating=None, max_rating=None,
            min_reviews=None, max_reviews=None,
        )
        with self.assertRaisesRegex(ValueError, "provided together"):
            validate_args(args)


if __name__ == "__main__":
    unittest.main()
