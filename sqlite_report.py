#!/usr/bin/env python3
"""Generate a self-contained HTML dashboard from a NoSite Scout SQLite database."""

from __future__ import annotations

import argparse
import html
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from nosite_scout import connect_db


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


def prospect_category_table(conn: sqlite3.Connection) -> str:
    rows = conn.execute(
        """SELECT COALESCE(NULLIF(category, ''), 'Unknown') AS category,
                  ROUND(AVG(COALESCE(prospect_probability, 40)), 1) AS probability,
                  COALESCE(MAX(prospect_tier), 'low') AS tier,
                  COUNT(*) AS total,
                  SUM(CASE WHEN no_website = 1 AND has_phone = 1 THEN 1 ELSE 0 END) AS qualified,
                  SUM(CASE WHEN status IN ('contacted','replied','meeting','won','lost') THEN 1 ELSE 0 END) AS contacted,
                  SUM(CASE WHEN status = 'won' THEN 1 ELSE 0 END) AS won,
                  SUM(CASE WHEN status = 'lost' THEN 1 ELSE 0 END) AS lost
           FROM leads GROUP BY category
           ORDER BY probability DESC, qualified DESC, total DESC, category"""
    ).fetchall()
    body = "".join(
        "<tr>"
        f'<td><button class="category-link" data-category="{html.escape(str(category), quote=True)}">{html.escape(str(category))}</button></td>'
        f"<td><strong>{float(probability):.1f}%</strong></td>"
        f"<td><span class=\"tier tier-{html.escape(str(tier))}\">{html.escape(str(tier).replace('_', ' '))}</span></td>"
        f"<td>{int(total)}</td><td>{int(qualified or 0)}</td><td>{int(contacted or 0)}</td>"
        f"<td>{int(won or 0)}</td><td>{int(lost or 0)}</td></tr>"
        for category, probability, tier, total, qualified, contacted, won, lost in rows
    )
    return (
        '<section class="panel prospect-table"><h2>Prospect categories: best to worst</h2>'
        '<p class="section-note">Probability currently uses category only. Won/lost outcomes let you test and revise these estimates later.</p>'
        '<div class="table-wrap"><table><thead><tr><th>Category</th><th>Probability</th><th>Priority</th>'
        '<th>All</th><th>Qualified</th><th>Contacted</th><th>Won</th><th>Lost</th>'
        f'</tr></thead><tbody>{body}</tbody></table></div></section>'
    )


def main() -> int:
    args = parse_args()
    if args.top < 1:
        raise SystemExit("--top must be at least 1")
    db_path = Path(args.db_path)
    if not db_path.exists():
        raise SystemExit(f"Database not found: {db_path}")

    conn = connect_db(str(db_path))
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
        prospect_table = prospect_category_table(conn)
        report_leads = [
            dict(row)
            for row in conn.execute(
                """SELECT place_id, name, category, city, phone_preferred, website,
                          prospect_probability, prospect_tier, no_website, has_phone,
                          status, assigned_to, next_follow_up_at, last_contacted_at,
                          do_not_contact, estimated_value, notes
                   FROM leads
                   ORDER BY prospect_probability DESC, no_website DESC, has_phone DESC, name"""
            ).fetchall()
        ]
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
    lead_json = json.dumps(report_leads, ensure_ascii=False).replace("<", "\\u003c")
    interactive_script = r"""
<script>
const leads = JSON.parse(document.getElementById('lead-data').textContent);
let selectedCategory = '', page = 1, pageSize = 15;
const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
function renderLeads() {
  const filtered = leads.filter(lead => (lead.category || 'Unknown') === selectedCategory);
  const pages = Math.max(1, Math.ceil(filtered.length / pageSize));
  page = Math.min(page, pages);
  const shown = filtered.slice((page - 1) * pageSize, page * pageSize);
  document.getElementById('lead-title').textContent = `${selectedCategory} — ${filtered.length} leads`;
  document.getElementById('lead-rows').innerHTML = shown.map(lead => `<tr>
    <td><strong>${esc(lead.name || 'Unnamed')}</strong></td><td>${esc(lead.city)}</td>
    <td>${esc(lead.phone_preferred)}</td><td>${lead.no_website ? 'Yes' : 'No'}</td>
    <td>${Number(lead.prospect_probability || 0).toFixed(1)}%</td><td>${esc(lead.prospect_tier)}</td>
    <td>${esc(lead.status)}</td><td>${esc(lead.assigned_to)}</td><td>${esc(lead.last_contacted_at)}</td>
    <td>${esc(lead.next_follow_up_at)}</td><td>${esc(lead.notes)}</td>
  </tr>`).join('');
  document.getElementById('page-info').textContent = `Page ${page} of ${pages}`;
  document.getElementById('prev-page').disabled = page <= 1;
  document.getElementById('next-page').disabled = page >= pages;
  document.getElementById('lead-list').hidden = false;
}
document.querySelectorAll('.category-link').forEach(button => button.addEventListener('click', () => {
  selectedCategory = button.dataset.category; page = 1; renderLeads();
  document.getElementById('lead-list').scrollIntoView({behavior:'smooth', block:'start'});
}));
document.getElementById('page-size').addEventListener('change', event => { pageSize = Number(event.target.value); page = 1; renderLeads(); });
document.getElementById('prev-page').addEventListener('click', () => { page--; renderLeads(); });
document.getElementById('next-page').addEventListener('click', () => { page++; renderLeads(); });
</script>
"""
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
.prospect-table{{margin-top:20px}} .section-note{{color:var(--muted);margin:-8px 0 16px}} .table-wrap{{overflow-x:auto}}
table{{width:100%;border-collapse:collapse}} th,td{{padding:10px 12px;border-bottom:1px solid var(--line);text-align:right;white-space:nowrap}}
th:first-child,td:first-child{{text-align:left}} th{{color:#475569;font-size:13px}} .tier{{padding:4px 8px;border-radius:999px;font-size:12px;text-transform:capitalize}}
.tier-high{{background:#dcfce7;color:#166534}} .tier-medium{{background:#dbeafe;color:#1e40af}} .tier-low{{background:#fef3c7;color:#92400e}} .tier-last_priority{{background:#fee2e2;color:#991b1b}}
.category-link{{border:0;background:none;padding:0;color:#2563eb;font:inherit;font-weight:650;cursor:pointer;text-decoration:underline;text-underline-offset:3px}}
.lead-list{{margin-top:20px;scroll-margin-top:16px}} .list-tools,.pagination{{display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin:12px 0}}
button{{border:1px solid #cbd5e1;background:#fff;border-radius:8px;padding:8px 12px;cursor:pointer}} button:disabled{{opacity:.45;cursor:not-allowed}}
select{{border:1px solid #cbd5e1;border-radius:7px;padding:7px;font:inherit;background:#fff}}
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
{prospect_table}
<section id="lead-list" class="panel lead-list" hidden>
  <h2 id="lead-title">Select a category above</h2>
  <div class="list-tools"><label>Rows per page <select id="page-size"><option>10</option><option selected>15</option><option>20</option></select></label></div>
  <div class="table-wrap"><table><thead><tr><th>Name</th><th>City</th><th>Phone</th><th>No website</th><th>Probability</th><th>Priority</th><th>Status</th><th>Assigned</th><th>Contacted</th><th>Follow-up</th><th>Notes</th></tr></thead><tbody id="lead-rows"></tbody></table></div>
  <div class="pagination"><button id="prev-page">Previous</button><span id="page-info"></span><button id="next-page">Next</button></div>
</section>
<p class="note"><strong>Interpretation:</strong> “No website” is based on provider data and profile-domain rules; it still needs manual verification. Prospect probability is an editable category-based estimate, not a factual conversion rate. Phone and mobile rates measure stored data completeness, not consent to contact.</p>
</main><script id="lead-data" type="application/json">{lead_json}</script>{interactive_script}</body></html>"""

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(document, encoding="utf-8")
    print(f"Dashboard written to: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
