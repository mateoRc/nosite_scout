# NoSite Scout

NoSite Scout is a small internal Python CLI for finding local businesses in Google Places that likely do not have a real website, storing the leads in SQLite, and exporting them for outreach.

The `no_website` and `mobile_phone` fields are heuristics. Google Places does not provide employee counts, and mobile-looking phone detection is best-effort only.

## Setup

Use Python 3.11 or newer.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Copy `.env.example` to `.env` and add a Google Maps API key:

```powershell
Copy-Item .env.example .env
```

Enable the Places API for the key in Google Cloud Console. The script uses Places Text Search and Place Details from the Google Maps Platform.

## Usage

```powershell
python nosite_scout.py --location "Istria, Croatia"
python nosite_scout.py --location "Istria, Croatia" --keywords restaurants cafes plumbers electricians
python nosite_scout.py --location "Istria, Croatia" --max-results 50 --formats csv,json,xlsx,xml
python nosite_scout.py --only-no-website --has-phone
```

Default keywords:

```text
restaurants cafes apartments plumbers electricians beauty_salon mechanics dentists small_shops local_services
```

Useful options:

```text
--location             Default: "Istria, Croatia"
--keywords             One or more search keywords
--max-results          Maximum Places results per keyword, default 50
--review-threshold     Review-count cutoff for the small-business heuristic, default 300
--formats              Comma-separated exports: csv,json,xlsx,xml
--only-no-website      Export only leads marked as no website
--has-phone            Export only leads with a preferred phone number
--mobile-only          Export only leads with a mobile-looking Croatian phone number
--db-path              SQLite path, default nosite_scout.sqlite
--out-dir              Export folder, default exports
```

## Output

The script creates a SQLite database at `nosite_scout.sqlite` unless `--db-path` is set. Leads are upserted by `place_id`; existing non-empty `status` and `notes` values are preserved.

Exports are written to `exports` by default with timestamped names:

```text
nosite_scout_YYYYMMDD_HHMMSS.csv
nosite_scout_YYYYMMDD_HHMMSS.json
nosite_scout_YYYYMMDD_HHMMSS.xml
nosite_scout_YYYYMMDD_HHMMSS.xlsx
```

Exported rows are sorted by likely outreach value:

1. `no_website` true
2. `has_phone` true
3. `likely_small_business` true
4. `review_count` descending

## Limitations

Google Places usually does not return emails. For MVP use, NoSite Scout fetches only the business homepage when it looks like a real website, then extracts visible email addresses and obvious contact/social links with simple regex checks.

`no_website` is not guaranteed to be correct. Social/profile/listing URLs such as Facebook, Instagram, Booking, Tripadvisor, WhatsApp, Google Maps, Linktree, and `business.site` are treated as not being a real website.

Croatian mobile detection checks for numbers that look like `+385 9...` or `09...`; this is not guaranteed.
