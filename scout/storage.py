"""SQLite schema, migrations, persistence, and lead querying."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from typing import Any, Protocol

from .constants import LEAD_COLUMNS
from .scoring import category_score, initialize_scoring, rescore_leads


class LeadFilterOptions(Protocol):
    include_do_not_contact: bool
    lead_preset: str
    only_no_website: bool
    has_phone: bool
    mobile_only: bool
    min_rating: float | None
    max_rating: float | None
    min_reviews: int | None
    max_reviews: int | None
    include_terms: list[str] | None
    exclude_terms: list[str] | None


def connect_db(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute(
        """CREATE TABLE IF NOT EXISTS leads (
            place_id TEXT PRIMARY KEY, name TEXT, category TEXT, address TEXT, city TEXT,
            phone TEXT, formatted_phone_number TEXT, international_phone_number TEXT,
            phone_preferred TEXT, mobile_phone TEXT, has_phone INTEGER, website TEXT,
            google_maps_url TEXT, rating REAL, review_count INTEGER, no_website INTEGER,
            likely_small_business INTEGER, prospect_probability REAL, prospect_tier TEXT,
            source TEXT, status TEXT DEFAULT 'new', assigned_to TEXT, next_follow_up_at TEXT,
            last_contacted_at TEXT, do_not_contact INTEGER DEFAULT 0, estimated_value REAL,
            notes TEXT DEFAULT '', email TEXT, contact_page_url TEXT, facebook_url TEXT,
            instagram_url TEXT, whatsapp_url TEXT, created_at TEXT, updated_at TEXT
        )"""
    )
    existing = {row[1] for row in conn.execute("PRAGMA table_info(leads)")}
    migrations = {
        "assigned_to": "TEXT", "next_follow_up_at": "TEXT", "last_contacted_at": "TEXT",
        "do_not_contact": "INTEGER DEFAULT 0", "estimated_value": "REAL",
        "prospect_probability": "REAL", "prospect_tier": "TEXT",
    }
    for column, definition in migrations.items():
        if column not in existing:
            conn.execute(f"ALTER TABLE leads ADD COLUMN {column} {definition}")
    defaults_changed = initialize_scoring(conn)
    rescore_leads(conn, only_unscored=not defaults_changed)
    conn.commit()
    return conn


def upsert_lead(conn: sqlite3.Connection, lead: dict[str, Any]) -> str:
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    row = {column: lead.get(column) for column in LEAD_COLUMNS}
    row["prospect_probability"], row["prospect_tier"] = category_score(conn, row.get("category"))
    row["created_at"] = now
    row["updated_at"] = now
    for key in ("has_phone", "no_website", "likely_small_business", "do_not_contact"):
        row[key] = int(bool(row[key]))
    existing = conn.execute("SELECT 1 FROM leads WHERE place_id = ?", (row["place_id"],)).fetchone()
    protected = {
        "place_id", "created_at", "status", "assigned_to", "next_follow_up_at",
        "last_contacted_at", "do_not_contact", "estimated_value", "notes",
    }
    update_columns = [column for column in LEAD_COLUMNS if column not in protected]
    update_sql = ", ".join(f"{column} = excluded.{column}" for column in update_columns)
    update_sql += ", status = COALESCE(NULLIF(leads.status, ''), excluded.status)"
    update_sql += ", notes = COALESCE(NULLIF(leads.notes, ''), excluded.notes), updated_at = excluded.updated_at"
    placeholders = ",".join("?" for _ in LEAD_COLUMNS)
    conn.execute(
        f"""INSERT INTO leads ({','.join(LEAD_COLUMNS)}) VALUES ({placeholders})
            ON CONFLICT(place_id) DO UPDATE SET {update_sql}""",
        [row[column] for column in LEAD_COLUMNS],
    )
    return "updated" if existing else "new"


def load_export_rows(conn: sqlite3.Connection, options: LeadFilterOptions) -> list[dict[str, Any]]:
    clauses: list[str] = []
    params: list[Any] = []
    if not options.include_do_not_contact:
        clauses.append("COALESCE(do_not_contact, 0) = 0")
    if options.lead_preset in {"no_website_phone", "no_website", "mobile_no_website"}:
        clauses.append("no_website = 1")
    if options.lead_preset == "no_website_phone":
        clauses.append("has_phone = 1")
    if options.lead_preset == "mobile_no_website":
        clauses.append("mobile_phone IS NOT NULL AND mobile_phone != ''")
    if options.only_no_website:
        clauses.append("no_website = 1")
    if options.has_phone:
        clauses.append("has_phone = 1")
    if options.mobile_only:
        clauses.append("mobile_phone IS NOT NULL AND mobile_phone != ''")
    for value, operator, column in (
        (options.min_rating, ">=", "rating"), (options.max_rating, "<=", "rating"),
        (options.min_reviews, ">=", "review_count"), (options.max_reviews, "<=", "review_count"),
    ):
        if value is not None:
            clauses.append(f"{column} {operator} ?")
            params.append(value)
    if options.include_terms:
        matches = []
        for term in options.include_terms:
            matches.append("(name LIKE ? OR category LIKE ? OR address LIKE ? OR city LIKE ?)")
            params.extend([f"%{term}%"] * 4)
        clauses.append(f"({' OR '.join(matches)})")
    for term in options.exclude_terms or []:
        clauses.append("NOT (name LIKE ? OR category LIKE ? OR address LIKE ? OR city LIKE ?)")
        params.extend([f"%{term}%"] * 4)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    rows = conn.execute(
        f"""SELECT {','.join(LEAD_COLUMNS)} FROM leads {where}
            ORDER BY prospect_probability DESC, no_website DESC, has_phone DESC,
                     likely_small_business DESC, review_count DESC""",
        params,
    ).fetchall()
    return [dict(row) for row in rows]
