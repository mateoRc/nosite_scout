#!/usr/bin/env python3
"""Update NoSite Scout workflow data directly or import it from Excel/CSV."""

from __future__ import annotations

import argparse
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

try:
    import pandas as pd
except ModuleNotFoundError:
    pd = None

from .scoring import set_category_score
from .storage import connect_db


STATUSES = ("new", "verified", "contacted", "replied", "meeting", "won", "lost", "invalid")
WORKFLOW_COLUMNS = (
    "status",
    "assigned_to",
    "next_follow_up_at",
    "last_contacted_at",
    "do_not_contact",
    "estimated_value",
    "notes",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Manage lead qualification and ownership in SQLite.")
    parser.add_argument("--db-path", default="nosite_scout.sqlite")
    subparsers = parser.add_subparsers(dest="command", required=True)

    update = subparsers.add_parser("update", help="Update one lead by place_id.")
    update.add_argument("--place-id", required=True)
    update.add_argument("--status", choices=STATUSES)
    update.add_argument("--assigned-to")
    update.add_argument("--next-follow-up-at")
    update.add_argument("--last-contacted-at")
    update.add_argument("--do-not-contact", choices=("yes", "no"))
    update.add_argument("--estimated-value", type=float)
    update.add_argument("--notes")

    importer = subparsers.add_parser("import", help="Import workflow columns from CSV or XLSX.")
    importer.add_argument("path")
    importer.add_argument("--dry-run", action="store_true")

    score = subparsers.add_parser("category-score", help="Set prospect probability for a category pattern.")
    score.add_argument("--pattern", required=True, help="SQLite LIKE pattern, e.g. tourism:apartment or craft:%")
    score.add_argument("--probability", required=True, type=float, help="Estimated acceptance probability, 0-100.")
    score.add_argument("--rationale", default="")

    subparsers.add_parser("list-category-scores", help="List configurable category probabilities.")
    return parser.parse_args()


def clean(value: Any) -> Any:
    if pd is not None and pd.isna(value):
        return None
    if isinstance(value, str):
        value = value.strip()
        return value or None
    return value


def parse_date(value: Any, field: str) -> str | None:
    value = clean(value)
    if value is None:
        return None
    if hasattr(value, "isoformat") and not isinstance(value, str):
        return value.isoformat()
    text = str(value)
    try:
        datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{field} must be an ISO date/time, got {text!r}") from exc
    return text


def parse_bool(value: Any) -> int:
    value = clean(value)
    if value is None:
        return 0
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float)) and value in (0, 1):
        return int(value)
    normalized = str(value).strip().lower()
    if normalized in {"yes", "true", "1", "y"}:
        return 1
    if normalized in {"no", "false", "0", "n"}:
        return 0
    raise ValueError(f"do_not_contact must be yes/no or true/false, got {value!r}")


def validate_changes(values: dict[str, Any]) -> dict[str, Any]:
    changes = {key: clean(value) for key, value in values.items() if key in WORKFLOW_COLUMNS}
    status = changes.get("status")
    if status is not None and status not in STATUSES:
        raise ValueError(f"status must be one of: {', '.join(STATUSES)}")
    if "do_not_contact" in changes:
        changes["do_not_contact"] = parse_bool(changes["do_not_contact"])
    for field in ("next_follow_up_at", "last_contacted_at"):
        if field in changes:
            changes[field] = parse_date(changes[field], field)
    if changes.get("estimated_value") is not None:
        changes["estimated_value"] = float(changes["estimated_value"])
        if changes["estimated_value"] < 0:
            raise ValueError("estimated_value cannot be negative")
    return changes


def update_lead(conn: sqlite3.Connection, place_id: str, changes: dict[str, Any]) -> bool:
    if not changes:
        raise ValueError("No workflow fields supplied")
    assignments = ", ".join(f"{column} = ?" for column in changes)
    cursor = conn.execute(
        f"UPDATE leads SET {assignments}, updated_at = ? WHERE place_id = ?",
        [*changes.values(), datetime.now().astimezone().isoformat(timespec="seconds"), place_id],
    )
    return cursor.rowcount == 1


def import_file(conn: sqlite3.Connection, path: Path, dry_run: bool) -> tuple[int, int, int]:
    if pd is None:
        raise ValueError("pandas is required for CSV/XLSX imports; run: pip install -r requirements.txt")
    if path.suffix.lower() == ".csv":
        frame = pd.read_csv(path)
    elif path.suffix.lower() == ".xlsx":
        frame = pd.read_excel(path, engine="openpyxl")
    else:
        raise ValueError("Import file must be .csv or .xlsx")
    if "place_id" not in frame.columns:
        raise ValueError("Import file must contain place_id")

    available = [column for column in WORKFLOW_COLUMNS if column in frame.columns]
    if not available:
        raise ValueError(f"Import file must contain at least one workflow column: {', '.join(WORKFLOW_COLUMNS)}")
    updated = missing = skipped = 0
    for index, row in frame.iterrows():
        place_id = clean(row.get("place_id"))
        if not place_id:
            skipped += 1
            continue
        try:
            # Blank spreadsheet cells mean "leave the database value unchanged".
            changes = validate_changes(
                {column: row[column] for column in available if clean(row[column]) is not None}
            )
            if not changes:
                skipped += 1
                continue
        except ValueError as exc:
            raise ValueError(f"Row {index + 2}: {exc}") from exc
        if dry_run:
            exists = conn.execute("SELECT 1 FROM leads WHERE place_id = ?", (place_id,)).fetchone()
            updated += int(bool(exists))
            missing += int(not exists)
        elif update_lead(conn, str(place_id), changes):
            updated += 1
        else:
            missing += 1
    if dry_run:
        conn.rollback()
    else:
        conn.commit()
    return updated, missing, skipped


def main() -> int:
    args = parse_args()
    conn = connect_db(args.db_path)
    try:
        if args.command == "update":
            raw = {
                "status": args.status,
                "assigned_to": args.assigned_to,
                "next_follow_up_at": args.next_follow_up_at,
                "last_contacted_at": args.last_contacted_at,
                "do_not_contact": args.do_not_contact,
                "estimated_value": args.estimated_value,
                "notes": args.notes,
            }
            changes = validate_changes({key: value for key, value in raw.items() if value is not None})
            if not update_lead(conn, args.place_id, changes):
                raise ValueError(f"Unknown place_id: {args.place_id}")
            conn.commit()
            print(f"Updated {args.place_id}: {', '.join(changes)}")
        elif args.command == "import":
            updated, missing, skipped = import_file(conn, Path(args.path), args.dry_run)
            mode = "Dry run" if args.dry_run else "Import"
            print(f"{mode}: {updated} updated, {missing} unknown place_id, {skipped} skipped")
        elif args.command == "category-score":
            rescored = set_category_score(conn, args.pattern, args.probability, args.rationale)
            conn.commit()
            print(
                f"Set {args.pattern} to {args.probability:.1f}% and rescored "
                f"{rescored} matching leads"
            )
        else:
            rows = conn.execute(
                """SELECT category_pattern, probability, rationale
                   FROM category_prospect_scores
                   ORDER BY probability DESC, category_pattern"""
            ).fetchall()
            for pattern, probability, rationale in rows:
                print(f"{probability:5.1f}%  {pattern:24}  {rationale}")
    except ValueError as exc:
        conn.rollback()
        raise SystemExit(f"Error: {exc}") from exc
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
