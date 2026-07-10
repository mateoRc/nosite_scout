# NoSite Scout

NoSite Scout is a Dockerized command-line tool for discovering local businesses, saving them to SQLite, and exporting qualified leads to CSV, JSON, XLSX, or XML.

It is designed primarily for finding small businesses that have no real website and do have a phone number. The default OpenStreetMap (OSM) mode is free and needs no API key. An optional Google Places mode provides ratings, review counts, Maps links, and generally richer coverage, but requires a paid Google API.

## What it does

For each location and keyword, NoSite Scout:

1. Searches OpenStreetMap or Google Places.
2. Normalizes the business name, category, address, city, phone, website, and available contact fields.
3. Treats social profiles, booking pages, Linktree, Google Maps, and similar profile pages as **not a real website**.
4. Marks likely Croatian mobile numbers separately.
5. Upserts results into SQLite using the provider's stable place ID.
6. Filters the full database using the selected lead preset and optional filters.
7. Writes timestamped export files.

The default preset is `no_website_phone`, so the normal export contains businesses that have no real website and have a callable phone number.

> **Important:** the database is persistent. A run exports all matching records already stored in that database, not only records discovered during the current run. Repeated searches update existing records instead of duplicating them. Use a different `--db-path` for an isolated campaign.

## Quick start with Docker

Requirements: Docker Desktop with Docker Compose.

Build once:

```powershell
docker compose build
```

Run a small first search:

```powershell
docker compose run --rm scout --location "Pula, Croatia" --keywords restaurants cafes --max-results 25 --output-format csv
```

The CSV will appear in `exports/` and the reusable database will be `nosite_scout.sqlite` in the project folder.

No `.env` file is required for OSM mode.

## Recommended lead-generation workflow

### Focused accommodation campaign

The built-in accommodation campaign supplies provider-specific accommodation queries. Pass towns through `--locations` so each destination gets its own result allowance instead of relying on one region-wide query:

```powershell
docker compose run --rm scout `
  --campaign accommodation `
  --provider osm `
  --locations Pula Rovinj Porec Umag Medulin Novigrad Vrsar Fazana Labin `
  --countries Croatia `
  --lead-preset no_website_phone `
  --output-format csv,xlsx
```

OSM mode uses one broad structured accommodation query per location with a 12 km radius by default.

For the most detailed accommodation search available without Google Places, use a town-by-town OSM campaign. This command raises the per-town result allowance, widens each town search to 15 km, tolerates more temporary Overpass failures, retains every discovered record, and enriches records that expose a website:

```powershell
docker compose run --rm scout `
  --campaign accommodation `
  --provider osm `
  --locations Pula Rovinj Porec Umag Medulin Novigrad Vrsar Fazana Labin Rabac Pazin Buje Buzet Motovun Vodnjan Bale Tar-Vabriga Liznjan `
  --countries Croatia `
  --radius-km 15 `
  --max-results 250 `
  --request-delay 3 `
  --osm-retries 4 `
  --lead-preset all `
  --secondary-scrape `
  --output-format csv,json,xlsx
```

The locations overlap intentionally; stable OSM IDs are deduplicated in SQLite. Public Nominatim and Overpass instances can still rate-limit or time out, so let the run finish and rerun it later if the summary reports skipped searches. Use `--lead-preset no_website_phone` instead of `all` when you only want the immediate call list in the exports.

### 1. Start with a focused campaign

Search a specific town and two or three service categories rather than a whole country at once:

```powershell
docker compose run --rm scout `
  --location "Pula, Croatia" `
  --keywords plumbers electricians beauty_salon `
  --max-results 50 `
  --lead-preset no_website_phone `
  --output-format xlsx
```

For the most predictable OSM radius search, supply a center point:

```powershell
docker compose run --rm scout `
  --location Pula `
  --center-lat 44.8666 `
  --center-lng 13.8496 `
  --radius-km 25 `
  --keywords restaurants cafes `
  --output-format csv
```

Without coordinates, OSM geocodes the location text and uses a 25 km default radius. Coordinates are recommended when the intended center matters.

### 2. Review and qualify the export

Open the XLSX or CSV and check at least:

- `name`, `category`, `city`, and `address` are relevant to the campaign.
- `phone_preferred` is usable.
- `website` is empty or only a profile/booking/social URL.
- The business is active and is not a branch or chain.
- You have a legitimate, compliant reason and channel for outreach.

Useful fields include:

| Field | Meaning |
|---|---|
| `place_id` | Stable provider ID used for deduplication |
| `phone_preferred` | Best normalized phone number available |
| `mobile_phone` | Number that looks like a Croatian mobile number |
| `no_website` | `1` when no real standalone website was detected |
| `likely_small_business` | Basic local-category, local-address, chain, and review-count heuristic |
| `prospect_probability`, `prospect_tier` | Editable category-only estimate used to prioritize outreach |
| `source` | `openstreetmap`, `google_places`, or `manual` |
| `status`, `assigned_to`, `notes` | Qualification stage, owner, and persistent working notes |
| `next_follow_up_at`, `last_contacted_at` | ISO date/time values used to manage follow-ups |
| `do_not_contact` | Suppression flag; suppressed leads are excluded from normal exports |
| `estimated_value` | Your estimated deal value in your chosen currency |
| `created_at`, `updated_at` | UTC timestamps for database maintenance |

`likely_small_business` is only a prioritization heuristic, not proof. In free OSM mode, ratings and review counts are unavailable and are stored as empty/zero values.

### 3. Keep campaigns separate when needed

By default, searches accumulate in `nosite_scout.sqlite`. Use named database and export folders to isolate a campaign:

```powershell
docker compose run --rm scout `
  --location "Rovinj, Croatia" `
  --keywords apartments restaurants `
  --db-path campaigns/rovinj.sqlite `
  --out-dir campaigns/rovinj_exports `
  --output-format csv
```

Because the project is mounted at `/data` in the container, those relative paths are created in the project folder.

### 4. Expand systematically

Multiple locations can be searched in one run:

```powershell
docker compose run --rm scout `
  --locations Pula Rovinj Porec `
  --countries Croatia `
  --keywords restaurants cafes mechanics `
  --max-results 50 `
  --output-format csv,xlsx
```

`--countries` combines every country with every location unless the country is already present in the location string.

## Lead presets and filtering

Presets control which stored records are exported:

| Preset | Exported records |
|---|---|
| `no_website_phone` | No real website and any phone; default |
| `no_website` | No real website, phone optional |
| `mobile_no_website` | No real website and Croatian-looking mobile phone |
| `all` | All stored records |

Examples:

```powershell
# All no-website records, including those without a phone
docker compose run --rm scout --location "Labin, Croatia" --lead-preset no_website --output-format csv

# Mobile-first call list
docker compose run --rm scout --location "Pazin, Croatia" --lead-preset mobile_no_website --output-format xlsx

# Export every stored record
docker compose run --rm scout --location "Istria, Croatia" --lead-preset all --output-format all

# Include relevant terms and remove unwanted categories/names/areas
docker compose run --rm scout `
  --location "Istria, Croatia" `
  --lead-preset no_website_phone `
  --include-terms restaurant cafe `
  --exclude-terms hotel resort chain `
  --output-format csv
```

`--include-terms` matches if **any** term occurs in name, category, address, or city. Every `--exclude-terms` term is excluded. Matching uses SQLite `LIKE` and is normally case-insensitive for ASCII text.

The flags `--only-no-website`, `--has-phone`, and `--mobile-only` add filters on top of the chosen preset. For most uses, selecting the corresponding preset is clearer.

Rating and review filters are most useful with Google because OSM does not provide this data:

```powershell
docker compose run --rm scout `
  --provider google `
  --location "Pula, Croatia" `
  --lead-preset all `
  --min-rating 3.0 `
  --max-rating 4.5 `
  --max-reviews 200 `
  --output-format xlsx
```

## Search keywords

Default keywords:

```text
restaurants cafes apartments plumbers electricians beauty_salon massage wellness_spa physiotherapy mechanics dentists private_clinics small_shops local_services
```

In Google mode, keywords are normal text-search queries. In OSM mode, common keywords map to OSM tags. Custom OSM keywords use a broader name/category tag match and may be less complete. Prefer focused category terms and inspect the resulting `category` field.

`apartments` includes OSM apartments, holiday chalets/homes, guest houses, and hotels. Use `holiday_homes` or `vacation_rentals` for a narrower holiday-accommodation search. `beauty_salon` includes beauty salons and hairdressers. `private_clinics` includes clinics and doctors' offices; dentists remain available separately through `dentists`.

Additional focused service keywords include `massage`, `wellness_spa`, `physiotherapy`, `fitness_centres`, `veterinarians`, and `photographers`. Massage, wellness/spa, and physiotherapy are included in the default search; the others can be requested explicitly with `--keywords`.

`--max-results` applies per keyword and search target. The same business found under multiple keywords is processed once per run and deduplicated permanently by `place_id` in SQLite.

## Optional Google Places mode

Google mode can improve coverage and adds ratings, review counts, Google Maps URLs, and formatted phone data.

Create `.env` beside `compose.yml`:

```env
GOOGLE_MAPS_API_KEY=your_google_maps_api_key_here
```

Then run:

```powershell
docker compose run --rm scout --provider google --location "Istria, Croatia" --keywords plumbers electricians --max-results 25
```

Google API requests may incur charges. Configure quotas and billing limits in Google Cloud before larger runs. With Google, `--radius-km` requires both `--center-lat` and `--center-lng`.

## Secondary website enrichment

Secondary scraping is off by default. It only applies to records that already have a real website and attempts to extract email, contact-page, Facebook, Instagram, and WhatsApp links from that site:

```powershell
docker compose run --rm scout `
  --location "Pula, Croatia" `
  --lead-preset all `
  --secondary-scrape `
  --output-format xlsx
```

It does not improve the core no-website preset and increases network traffic and runtime. Website owners may block requests, and extracted contact details must still be verified.

## Add a lead manually

Manual entries are useful for businesses found through referrals or other research:

```powershell
docker compose run --rm scout `
  --manual-add `
  --manual-name "Business Name" `
  --manual-category "restaurant" `
  --manual-phone "+385 91 123 4567" `
  --manual-website "https://example.hr" `
  --manual-address "Street 1, 52100 Pula, Croatia" `
  --manual-notes "Review website quality and mobile usability" `
  --manual-status review_website_age `
  --lead-preset all `
  --output-format csv
```

`--manual-name` is required with `--manual-add`. A manual ID is derived from the website when present, otherwise from the name. Adding the same derived ID updates the lead while preserving non-empty `status` and `notes` already in the database.

## Export formats and storage

One format:

```powershell
docker compose run --rm scout --location "Pula, Croatia" --output-format csv
```

Several formats:

```powershell
docker compose run --rm scout --location "Pula, Croatia" --output-format csv,json,xlsx,xml
```

All formats:

```powershell
docker compose run --rm scout --location "Pula, Croatia" --output-format all
```

Files are timestamped in `exports/` by default:

```text
nosite_scout_YYYYMMDD_HHMMSS.csv
nosite_scout_YYYYMMDD_HHMMSS.json
nosite_scout_YYYYMMDD_HHMMSS.xlsx
nosite_scout_YYYYMMDD_HHMMSS.xml
```

Rows are sorted by no website, phone availability, likely-small-business flag, and descending review count.

## Lead qualification workflow

SQLite is the source of truth. XLSX/CSV files are review and bulk-editing surfaces: export them from SQLite, edit workflow columns, and import those changes back using the stable `place_id`. Never edit `place_id`.

Supported statuses:

```text
new verified contacted replied meeting won lost invalid
```

Update one lead directly in SQLite:

```powershell
python lead_workflow.py update `
  --place-id "osm:node:123456" `
  --status contacted `
  --assigned-to "Mateo" `
  --last-contacted-at "2026-07-10" `
  --next-follow-up-at "2026-07-17" `
  --estimated-value 1200 `
  --notes "Interested in a simple brochure website"
```

Mark a lead as suppressed:

```powershell
python lead_workflow.py update --place-id "osm:node:123456" --do-not-contact yes
```

Normal lead exports automatically exclude suppressed records. Use `--include-do-not-contact` only for administrative review.

For bulk review, generate XLSX, edit only these workflow columns, save the file, and dry-run the import first:

```text
status assigned_to next_follow_up_at last_contacted_at do_not_contact estimated_value notes
```

```powershell
python lead_workflow.py import exports/nosite_scout_YYYYMMDD_HHMMSS.xlsx --dry-run
python lead_workflow.py import exports/nosite_scout_YYYYMMDD_HHMMSS.xlsx
```

Imports match only on `place_id`; unknown IDs are reported and never inserted. Blank workflow cells leave existing database values unchanged. Dates should use ISO format such as `2026-07-10` or `2026-07-10T14:30:00+02:00`. Subsequent discovery runs refresh business data while preserving all workflow fields.

### Category prospect probabilities

Every lead receives an initial `prospect_probability` from 0–100 and a `prospect_tier` using only its category. These are conservative prioritization hypotheses, not measured conversion rates. Accommodation and private healthcare start higher, while cafés start last at 0.5%.

List the current rules:

```powershell
python lead_workflow.py list-category-scores
```

Change an exact category and immediately rescore all matching stored leads:

```powershell
python lead_workflow.py category-score `
  --pattern "tourism:apartment" `
  --probability 85 `
  --rationale "Direct-booking pitch performed well in our calls"
```

Patterns use SQLite `LIKE`, so `craft:%` changes every craft category. Record real outcomes with the existing `won` and `lost` statuses. The HTML report shows predictions alongside contacted/won/lost counts, allowing the category assumptions to be revised after enough calls.

## SQLite dashboard

Generate a self-contained HTML dashboard directly from the accumulated SQLite data:

```powershell
python sqlite_report.py
```

Open `reports/lead_dashboard.html` in a browser. It shows the total lead funnel, top categories, top cities, qualification statuses, data sources, and a best-to-worst category prospect table. No additional Python packages or internet connection are required.

For a campaign-specific database or output file:

```powershell
python sqlite_report.py --db-path campaigns/pula_pilot.sqlite --output campaigns/pula_dashboard.html --top 15
```

Run the report again after a search or qualification update to refresh it.

## Complete option reference

| Option | Description |
|---|---|
| `--provider osm\|google` | Search provider; default `osm` |
| `--campaign accommodation` | Apply provider-specific accommodation search terms to any location(s) |
| `--location TEXT` | One search area; default `Istria, Croatia` |
| `--locations TEXT ...` | Multiple areas; overrides `--location` |
| `--countries TEXT ...` | Countries combined with each location |
| `--keywords TEXT ...` | Categories/search queries; defaults listed above |
| `--max-results N` | Maximum provider results per keyword and target; default `50` |
| `--radius-km N`, `--range-km N` | Radius in km; OSM defaults to `25` if omitted |
| `--center-lat N`, `--center-lng N` | Explicit radius center; provide both |
| `--request-delay N` | Seconds before each provider search; default `2.0` |
| `--osm-retries N` | Retries for OSM 429/502/503/504 responses; default `2` |
| `--review-threshold N` | Maximum review count for small-business heuristic; default `300` |
| `--lead-preset NAME` | `no_website_phone`, `no_website`, `mobile_no_website`, or `all` |
| `--min-rating N`, `--max-rating N` | Export rating range, 0 through 5 |
| `--min-reviews N`, `--max-reviews N` | Export review-count range |
| `--include-terms TEXT ...` | Require any term in name/category/address/city |
| `--exclude-terms TEXT ...` | Reject terms in name/category/address/city |
| `--only-no-website` | Add a no-real-website export filter |
| `--has-phone` | Add a phone-required export filter |
| `--mobile-only` | Add a Croatian-looking-mobile export filter |
| `--include-do-not-contact` | Include suppressed leads; excluded by default |
| `--secondary-scrape`, `--no-secondary-scrape` | Enable/disable website contact enrichment; default off |
| `--formats LIST`, `--output-format LIST` | `csv,json,xlsx,xml` or `all`; default `csv,json,xlsx` |
| `--db-path PATH` | SQLite file; default `nosite_scout.sqlite` |
| `--out-dir PATH` | Export directory; default `exports` |
| `--manual-add` | Save one manual record instead of searching |
| `--manual-name TEXT` | Required name for a manual record |
| `--manual-phone TEXT` | Manual phone |
| `--manual-website URL` | Manual website |
| `--manual-address TEXT` | Manual address |
| `--manual-city TEXT` | Manual city |
| `--manual-category TEXT` | Manual category; default `manual_review` |
| `--manual-notes TEXT` | Persistent qualification/outreach notes |
| `--manual-status TEXT` | Persistent workflow status; default `review_website_age` |

Show the live CLI help after building:

```powershell
docker compose run --rm scout --help
```

## Run without Docker

Python 3.10+ is recommended:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python nosite_scout.py --location "Pula, Croatia" --keywords restaurants cafes --output-format csv
```

Copy `.env.example` to `.env` only if using Google mode.

## Troubleshooting

- **OSM search is skipped:** public Nominatim/Overpass endpoints can rate-limit or time out. The tool retries transient Overpass failures, reports skipped searches, and continues. Wait and rerun with modest scopes and the default delay.
- **Few phone-qualified leads:** OSM data is community-maintained; many businesses lack phone or website tags. Try adjacent towns/categories, export `no_website` for manual enrichment, contribute verified data to OSM, or use Google mode.
- **Old leads appear in an export:** exports read the whole selected database. Use a campaign-specific `--db-path`, or archive/remove the database only when you intentionally want a clean start.
- **Empty export:** the preset or additional filters may be too strict. Retry with `--lead-preset all`, then inspect available data.
- **Google key error:** confirm `.env` exists, contains `GOOGLE_MAPS_API_KEY`, and the required Places API is enabled in the correct Google Cloud project.
- **Docker-created files are not visible:** confirm the command is run from the folder containing `compose.yml`; that folder is mounted to `/data`.

## Is this enough for lead generation?

Yes—for a small, human-reviewed outbound workflow, the current version is enough to discover, deduplicate, filter, and export prospect lists. It is best viewed as a **lead sourcing tool**, not a complete sales system.

Before contacting anyone, manually verify that the business is active, that it genuinely lacks a suitable website, and that the contact data is current. Follow applicable privacy, electronic communications, telemarketing, and platform rules. Do not treat an exported phone number as automatic consent for bulk outreach.

For higher-volume or multi-user operation, it still lacks automated lead validation, database cleanup/archiving, in-tool status editing, outreach history, suppression/consent controls, CRM synchronization, scheduling, and reporting.

## Proposed next steps

Prioritized by value:

1. **Pilot the current workflow first.** Run 3–5 narrow town/category campaigns, manually review roughly 100 exported rows, and measure valid-business rate, usable-phone rate, true-no-website rate, duplicates, and positive response rate. This determines whether data quality—not more software—is the actual constraint.
2. **Add a qualification workflow.** Provide CLI commands to list/update `status` and `notes`, with stages such as `new`, `verified`, `contacted`, `interested`, `not_interested`, `invalid`, and `do_not_contact`. Add export filters for status and age.
3. **Improve data quality.** Add phone canonicalization by country, cross-provider deduplication using normalized name/address/phone, inactive-business checks, and a confidence score that explains why a lead qualifies.
4. **Add safe campaign controls.** Maintain do-not-contact/suppression records, outreach timestamps, contact source, verification date, and configurable retention. These matter before automating any outreach.
5. **Only then add integrations.** After the pilot proves useful, add opt-in CRM export/sync and campaign reporting. Keep message sending human-approved until the targeting and compliance process is established.
6. **Operationalize if volume justifies it.** Add tests, structured logging, configuration files for repeatable campaigns, alternate Overpass endpoints/backoff, migrations, and scheduled runs.

The immediate recommendation is therefore: **use the tool now for a measured, manually reviewed pilot; do not build automated outreach yet.** The first implementation upgrade should be status/qualification management, followed by validation and cross-provider deduplication.

## Limitations

- OSM coverage and contact tags vary by region and category.
- Public Nominatim and Overpass services are not intended for aggressive high-volume scraping; keep searches modest and respect their usage policies.
- A missing website tag does not prove that no website exists.
- Profile-domain detection and Croatian-mobile detection are heuristics.
- Google coverage is richer but paid and subject to Google's API terms and data-use restrictions.
- Secondary scraping can fail because of blocking, dynamic sites, unusual HTML, or network errors.
- NoSite Scout does not send outreach, verify consent, or replace legal/compliance review.
