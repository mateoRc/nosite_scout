"""Configurable category-only prospect scoring."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone


DEFAULT_CATEGORY_SCORES = (
    ("tourism:guest_house", 14.0, "Direct-booking value and platform commission savings"),
    ("tourism:apartment", 13.0, "Direct bookings, multilingual presentation, and repeat guests"),
    ("tourism:chalet", 12.0, "High-value stays benefit from an independent booking presence"),
    ("amenity:dentist", 10.0, "High-value services where trust and appointment information matter"),
    ("amenity:clinic", 9.0, "Trust, service information, and appointment enquiries"),
    ("amenity:doctors", 8.0, "Trust and appointment information, subject to private-practice verification"),
    ("shop:beauty", 8.0, "Portfolio, prices, local discovery, and booking potential"),
    ("shop:massage", 8.0, "Service menu and booking potential"),
    ("shop:hairdresser", 7.0, "Portfolio, prices, and booking potential"),
    ("craft:%", 7.0, "Customers commonly research local services before calling"),
    ("office:%", 6.0, "Professional services benefit from credibility and lead capture"),
    ("tourism:hotel", 6.0, "Direct bookings help, but many hotels already have established channels"),
    ("shop:%", 3.0, "Mixed need; many local shops depend on foot traffic"),
    ("amenity:restaurant", 2.5, "Menus and reservations help, but Maps and social profiles often suffice"),
    ("amenity:fuel", 1.0, "Usually a chain or location-driven purchase"),
    ("amenity:cafe", 0.5, "Lowest priority: typically driven by location, Maps, and social media"),
    ("%", 4.0, "Unclassified category; neutral starting estimate"),
)


def probability_tier(probability: float) -> str:
    if probability >= 10:
        return "high"
    if probability >= 6:
        return "medium"
    if probability >= 2:
        return "low"
    return "last_priority"


def initialize_scoring(conn: sqlite3.Connection) -> None:
    """Create score configuration and seed missing defaults."""
    conn.execute(
        """CREATE TABLE IF NOT EXISTS category_prospect_scores (
            category_pattern TEXT PRIMARY KEY,
            probability REAL NOT NULL CHECK(probability BETWEEN 0 AND 100),
            rationale TEXT DEFAULT '',
            is_custom INTEGER NOT NULL DEFAULT 0,
            updated_at TEXT NOT NULL
        )"""
    )
    score_columns = {row[1] for row in conn.execute("PRAGMA table_info(category_prospect_scores)")}
    if "is_custom" not in score_columns:
        conn.execute(
            "ALTER TABLE category_prospect_scores ADD COLUMN is_custom INTEGER NOT NULL DEFAULT 0"
        )
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    conn.executemany(
        """INSERT INTO category_prospect_scores
           (category_pattern, probability, rationale, updated_at) VALUES (?, ?, ?, ?)
           ON CONFLICT(category_pattern) DO UPDATE SET
             probability = excluded.probability,
             rationale = excluded.rationale,
             updated_at = excluded.updated_at
           WHERE category_prospect_scores.is_custom = 0""",
        [(pattern, probability, rationale, now) for pattern, probability, rationale in DEFAULT_CATEGORY_SCORES],
    )


def category_score(conn: sqlite3.Connection, category: str | None) -> tuple[float, str]:
    """Return the most-specific configured score matching a category."""
    row = conn.execute(
        """SELECT probability FROM category_prospect_scores
           WHERE COALESCE(?, '') LIKE category_pattern
           ORDER BY CASE WHEN category_pattern = ? THEN 0 ELSE 1 END,
                    LENGTH(REPLACE(category_pattern, '%', '')) DESC
           LIMIT 1""",
        (category, category),
    ).fetchone()
    probability = float(row[0]) if row else 40.0
    return probability, probability_tier(probability)


def rescore_leads(conn: sqlite3.Connection, category_like: str = "%") -> int:
    rows = conn.execute(
        "SELECT place_id, category FROM leads WHERE COALESCE(category, '') LIKE ?",
        (category_like,),
    ).fetchall()
    for place_id, category in rows:
        probability, tier = category_score(conn, category)
        conn.execute(
            "UPDATE leads SET prospect_probability = ?, prospect_tier = ? WHERE place_id = ?",
            (probability, tier, place_id),
        )
    return len(rows)


def set_category_score(
    conn: sqlite3.Connection,
    category_pattern: str,
    probability: float,
    rationale: str = "",
) -> int:
    if not category_pattern.strip():
        raise ValueError("category pattern cannot be blank")
    if not 0 <= probability <= 100:
        raise ValueError("probability must be between 0 and 100")
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    conn.execute(
        """INSERT INTO category_prospect_scores
           (category_pattern, probability, rationale, updated_at) VALUES (?, ?, ?, ?)
           ON CONFLICT(category_pattern) DO UPDATE SET
             probability = excluded.probability,
             rationale = excluded.rationale,
             is_custom = 1,
             updated_at = excluded.updated_at""",
        (category_pattern, probability, rationale, now),
    )
    conn.execute(
        "UPDATE category_prospect_scores SET is_custom = 1 WHERE category_pattern = ?",
        (category_pattern,),
    )
    return rescore_leads(conn, category_pattern)
