#!/usr/bin/env python3
"""Generate a self-contained HTML dashboard from a NoSite Scout SQLite database."""

from __future__ import annotations

import argparse
import html
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate a NoSite Scout SQLite dashboard.")
    parser.add_argument("--db-path", default="nosite_scout.sqlite", help="SQLite database path.")
    parser.add_argument("--output", default="reports/lead_dashboard.html", help="HTML report path.")
    parser.add_argument("--top", type=int, default=10, help="Number of categories and cities to show.")
    return parser.parse_args()


def scalar(conn: sqlite3.Connection, sql: str) -> int:
    return int(conn.execute(sql).fetchone()[0])


def grouped(conn: sqlite3.Connection, expression: str, limit: int) -> list[tuple[str, int]]:
    rows = conn.execute(
        f"""SELECT COALESCE(NULLIF({expression}, ''), 'Unknown') AS label, COUNT(*) AS total
            FROM leads GROUP BY label ORDER BY total DESC, label LIMIT ?""",
        (limit,),
    ).fetchall()
    return [(str(label), int(total)) for label, total in rows]


def bar_chart(title: str, rows: list[tuple[str, int]], color: str = "#2563eb") -> str:
    maximum = max((value for _, value in rows), default=1)
    bars = []
    for label, value in rows:
        width = max(1.0, value / maximum * 100)
        bars.append(
            f'<div class="bar-row"><div class="bar-label" title="{html.escape(label)}">'
            f'{html.escape(label)}</div><div class="bar-track"><div class="bar" '
            f'style="width:{width:.1f}%;background:{color}"></div></div><strong>{value}</strong></div>'
        )
    return f'<section class="panel"><h2>{html.escape(title)}</h2>{"".join(bars)}</section>'


def main() -> int:
    args = parse_args()
    if args.top < 1:
        raise SystemExit("--top must be at least 1")
    db_path = Path(args.db_path)
    if not db_path.exists():
        raise SystemExit(f"Database not found: {db_path}")

    conn = sqlite3.connect(db_path)
    try:
        total = scalar(conn, "SELECT COUNT(*) FROM leads")
        no_website = scalar(conn, "SELECT COUNT(*) FROM leads WHERE no_website = 1")
        with_phone = scalar(conn, "SELECT COUNT(*) FROM leads WHERE has_phone = 1")
        qualified = scalar(conn, "SELECT COUNT(*) FROM leads WHERE no_website = 1 AND has_phone = 1")
        mobile = scalar(
            conn,
            "SELECT COUNT(*) FROM leads WHERE no_website = 1 AND mobile_phone IS NOT NULL AND mobile_phone != ''",
        )
        categories = grouped(conn, "category", args.top)
        cities = grouped(conn, "city", args.top)
        statuses = grouped(conn, "status", args.top)
        sources = grouped(conn, "source", args.top)
    finally:
        conn.close()

    def percent(value: int) -> str:
        return f"{value / total * 100:.1f}%" if total else "0.0%"

    cards = [
        ("All stored", total, "100%" if total else "0%"),
        ("No real website", no_website, percent(no_website)),
        ("Any phone", with_phone, percent(with_phone)),
        ("No website + phone", qualified, percent(qualified)),
        ("No website + mobile", mobile, percent(mobile)),
    ]
    card_html = "".join(
        f'<article class="card"><span>{html.escape(label)}</span><strong>{value}</strong><small>{rate} of all</small></article>'
        for label, value, rate in cards
    )
    generated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    document = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>NoSite Scout dashboard</title>
<style>
:root{{--bg:#f4f7fb;--panel:#fff;--text:#172033;--muted:#64748b;--line:#e2e8f0}}
*{{box-sizing:border-box}} body{{margin:0;background:var(--bg);color:var(--text);font:15px system-ui,sans-serif}}
main{{max-width:1180px;margin:auto;padding:32px 20px}} h1{{margin:0 0 6px;font-size:30px}} .meta{{color:var(--muted);margin:0 0 24px}}
.cards{{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:14px;margin-bottom:20px}}
.card,.panel{{background:var(--panel);border:1px solid var(--line);border-radius:14px;box-shadow:0 4px 14px #0f172a0a}}
.card{{padding:18px}} .card span,.card small{{display:block;color:var(--muted)}} .card strong{{display:block;font-size:32px;margin:5px 0}}
.grid{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:20px}} .panel{{padding:20px}} h2{{font-size:18px;margin:0 0 16px}}
.bar-row{{display:grid;grid-template-columns:minmax(90px,150px) 1fr 38px;align-items:center;gap:10px;margin:10px 0}}
.bar-label{{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:#334155}} .bar-track{{height:18px;background:#eef2f7;border-radius:5px;overflow:hidden}}
.bar{{height:100%;border-radius:5px}} .note{{margin-top:20px;padding:16px 18px;background:#fffbeb;border:1px solid #fde68a;border-radius:12px;color:#78350f}}
@media(max-width:720px){{.grid{{grid-template-columns:1fr}}.bar-row{{grid-template-columns:100px 1fr 35px}}}}
</style></head><body><main>
<h1>NoSite Scout lead dashboard</h1><p class="meta">Database: {html.escape(str(db_path))} · Generated {generated}</p>
<div class="cards">{card_html}</div>
<div class="grid">
{bar_chart("Top categories", categories)}
{bar_chart("Top cities", cities, "#7c3aed")}
{bar_chart("Qualification status", statuses, "#059669")}
{bar_chart("Data sources", sources, "#ea580c")}
</div>
<p class="note"><strong>Interpretation:</strong> “No website” is based on provider data and profile-domain rules; it still needs manual verification. Phone and mobile rates measure stored data completeness, not consent to contact.</p>
</main></body></html>"""

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(document, encoding="utf-8")
    print(f"Dashboard written to: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
