"""Application orchestration for discovery, persistence, and export."""

from __future__ import annotations

import argparse
import os
import sqlite3
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import requests

from .cli import (
    apply_campaign_defaults, build_search_targets, manual_lead_from_args, parse_args, validate_args,
)
from .exporting import export_rows, parse_formats
from .lead_factory import google_detail_to_lead, osm_to_lead
from .providers import fetch_place_details, search_google_places, search_osm_places
from .storage import connect_db, load_export_rows, upsert_lead

try:
    from dotenv import load_dotenv
except ModuleNotFoundError:
    load_dotenv = None


@dataclass
class RunStats:
    places_found: int = 0
    new_leads: int = 0
    updated_leads: int = 0
    skipped_searches: int = 0

    def record_save(self, result: str) -> None:
        if result == "new":
            self.new_leads += 1
        else:
            self.updated_leads += 1


def search_one(args: argparse.Namespace, api_key: str, keyword: str, target: str) -> list[dict]:
    if args.provider == "google":
        return search_google_places(
            api_key, keyword, target, args.max_results,
            args.center_lat, args.center_lng, args.radius_km,
        )
    return search_osm_places(
        keyword, target, args.max_results,
        args.center_lat, args.center_lng, args.radius_km, args.osm_retries,
    )


def place_identifier(provider: str, place: dict) -> str | None:
    if provider == "google":
        return place.get("place_id")
    element_type, element_id = place.get("type"), place.get("id")
    return f"osm:{element_type}:{element_id}" if element_type and element_id is not None else None


def build_lead(args: argparse.Namespace, api_key: str, place: dict,
               keyword: str, target: str) -> dict | None:
    if args.provider == "osm":
        return osm_to_lead(place, keyword, target, args.review_threshold, args.secondary_scrape)
    detail = fetch_place_details(api_key, place.get("place_id", ""))
    if not detail:
        return None
    return google_detail_to_lead(detail, keyword, args.review_threshold, args.secondary_scrape)


def discover(args: argparse.Namespace, conn: sqlite3.Connection, api_key: str) -> RunStats:
    stats = RunStats()
    seen: set[str] = set()
    for target in build_search_targets(args):
        for keyword in args.keywords:
            print(f"Searching {args.provider}: {keyword} in {target}")
            if args.request_delay:
                time.sleep(args.request_delay)
            try:
                places = search_one(args, api_key, keyword, target)
            except (requests.RequestException, RuntimeError) as exc:
                if args.provider != "osm":
                    raise
                stats.skipped_searches += 1
                print(f"Warning: skipped OSM search for {keyword} in {target}: {exc}", file=sys.stderr)
                continue
            stats.places_found += len(places)
            for place in places:
                identifier = place_identifier(args.provider, place)
                if not identifier or identifier in seen:
                    continue
                seen.add(identifier)
                # Google needs a detail request per result; OSM payloads already
                # contain the required tags and need no artificial per-row delay.
                if args.provider == "google":
                    time.sleep(0.15)
                lead = build_lead(args, api_key, place, keyword, target)
                if lead:
                    stats.record_save(upsert_lead(conn, lead))
            conn.commit()
    return stats


def print_summary(args: argparse.Namespace, stats: RunStats,
                  rows: list[dict], paths: list[Path]) -> None:
    print("\nNoSite Scout summary")
    print(f"- searched target count: {len(build_search_targets(args))}")
    print(f"- searched keywords count: {len(args.keywords)}")
    print(f"- skipped searches count: {stats.skipped_searches}")
    print(f"- total places found: {stats.places_found}")
    print(f"- new leads saved: {stats.new_leads}")
    print(f"- updated leads saved: {stats.updated_leads}")
    print(f"- no-website leads count: {sum(bool(row.get('no_website')) for row in rows)}")
    print(f"- leads with phone count: {sum(bool(row.get('has_phone')) for row in rows)}")
    print(f"- mobile-looking phone count: {sum(bool(row.get('mobile_phone')) for row in rows)}")
    print("- export file paths:")
    for path in paths:
        print(f"  {path}")


def print_manual_summary(stats: RunStats, rows: list[dict], paths: list[Path]) -> None:
    print("\nNoSite Scout summary")
    print("- manual lead saved: 1")
    print(f"- new leads saved: {stats.new_leads}")
    print(f"- updated leads saved: {stats.updated_leads}")
    print(f"- exported rows count: {len(rows)}")
    print("- export file paths:")
    for path in paths:
        print(f"  {path}")


def run(args: argparse.Namespace) -> int:
    validate_args(args)
    formats = parse_formats(args.formats)
    api_key = os.getenv("GOOGLE_MAPS_API_KEY", "")
    if args.provider == "google" and not api_key:
        raise ValueError("GOOGLE_MAPS_API_KEY is required only when using --provider google.")
    conn = connect_db(args.db_path)
    try:
        stats = RunStats()
        if args.manual_add:
            stats.record_save(upsert_lead(conn, manual_lead_from_args(args)))
            conn.commit()
        else:
            stats = discover(args, conn, api_key)
        rows = load_export_rows(conn, args)
        paths = export_rows(rows, formats, args.out_dir)
        if args.manual_add:
            print_manual_summary(stats, rows, paths)
        else:
            print_summary(args, stats, rows, paths)
        return 0
    except (requests.RequestException, RuntimeError):
        conn.rollback()
        raise
    finally:
        conn.close()


def main() -> int:
    if load_dotenv:
        load_dotenv()
    args = apply_campaign_defaults(parse_args())
    try:
        return run(args)
    except (ValueError, requests.RequestException, RuntimeError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
