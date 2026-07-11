import sqlite3
import unittest

from scout.scoring import category_score, initialize_scoring, rescore_leads, set_category_score


class ProspectScoringTests(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.execute(
            "CREATE TABLE leads (place_id TEXT PRIMARY KEY, category TEXT, prospect_probability REAL, prospect_tier TEXT)"
        )
        initialize_scoring(self.conn)

    def tearDown(self):
        self.conn.close()

    def test_accommodation_is_high_and_cafe_is_last(self):
        apartment, apartment_tier = category_score(self.conn, "tourism:apartment")
        cafe, cafe_tier = category_score(self.conn, "amenity:cafe")
        self.assertGreater(apartment, cafe)
        self.assertEqual(apartment_tier, "high")
        self.assertEqual(cafe_tier, "last_priority")

    def test_exact_rule_beats_wildcard(self):
        restaurant, _ = category_score(self.conn, "amenity:restaurant")
        unknown, _ = category_score(self.conn, "amenity:parking")
        self.assertEqual(restaurant, 2.5)
        self.assertEqual(unknown, 4.0)

    def test_rule_change_rescores_matching_leads(self):
        self.conn.executemany(
            "INSERT INTO leads(place_id, category) VALUES (?, ?)",
            [("a", "amenity:cafe"), ("b", "tourism:apartment")],
        )
        rescore_leads(self.conn)
        changed = set_category_score(self.conn, "amenity:cafe", 1.2, "Observed improvement")
        self.assertEqual(changed, 1)
        probability, tier = self.conn.execute(
            "SELECT prospect_probability, prospect_tier FROM leads WHERE place_id='a'"
        ).fetchone()
        self.assertEqual(probability, 1.2)
        self.assertEqual(tier, "last_priority")

    def test_custom_rule_survives_default_initialization(self):
        set_category_score(self.conn, "amenity:cafe", 1.7, "Observed result")
        initialize_scoring(self.conn)
        probability, _ = category_score(self.conn, "amenity:cafe")
        self.assertEqual(probability, 1.7)


if __name__ == "__main__":
    unittest.main()
