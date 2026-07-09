# NoSite Scout

NoSite Scout is a Dockerized internal CLI for finding small/local business leads, storing them in SQLite, and exporting them for outreach.

Default mode is free: it uses OpenStreetMap data through Nominatim and Overpass. No Google API key is required unless you explicitly run `--provider google`.

The default export is already focused on the useful lead target: businesses with no real website and a phone number. The script still stores all found records in SQLite, but exports `--lead-preset no_website_phone` unless you ask for something else.

## Setup With Docker

You do not need local Python or local Python packages. Install Docker Desktop, then build the image:

```powershell
docker compose build
```

No `.env` file is needed for the default free OpenStreetMap provider.

## Free Usage

```powershell
docker compose run --rm scout --location "Istria, Croatia"
docker compose run --rm scout --location "Pula, Croatia" --radius-km 15
docker compose run --rm scout --locations Istria Dalmatia --countries Croatia --keywords restaurants cafes
docker compose run --rm scout --location "Istria, Croatia" --max-results 50 --output-format all
docker compose run --rm scout --location "Istria, Croatia" --lead-preset no_website_phone --output-format csv
```

For best free-mode results, provide coordinates when you know them:

```powershell
docker compose run --rm scout --location Pula --radius-km 25 --center-lat 44.8666 --center-lng 13.8496
```

Export all raw records instead of only callable no-website leads:

```powershell
docker compose run --rm scout --location "Istria, Croatia" --lead-preset all --output-format all
```

Add a manual lead that has a website but should be reviewed as possibly old/outdated:

```powershell
docker compose run --rm scout --manual-add --manual-name "Business Name" --manual-website "https://example.hr" --manual-phone "+385 91 123 4567" --manual-notes "Has website, check if old/outdated: https://example.hr" --lead-preset all --output-format csv
```

## Optional Google Mode

Google Places can return richer business data, but it is a paid API. Use it only if you want that:

```powershell
docker compose run --rm scout --provider google --location "Istria, Croatia" --max-results 5
```

Google mode requires `.env`:

```env
GOOGLE_MAPS_API_KEY=your_google_maps_api_key_here
```

## Output Formats

Generate one format:

```powershell
docker compose run --rm scout --location "Istria, Croatia" --output-format csv
```

Generate multiple formats:

```powershell
docker compose run --rm scout --location "Istria, Croatia" --output-format csv,json,xlsx,xml
```

Generate every supported format:

```powershell
docker compose run --rm scout --location "Istria, Croatia" --output-format all
```

Supported formats:

```text
csv json xlsx xml all
```

## Options

```text
--provider             osm or google, default osm
--location             Default: "Istria, Croatia"
--locations            One or more areas; overrides --location
--countries            One or more countries to combine with each location
--radius-km            Search radius in kilometers; default 25 in osm mode
--range-km             Alias for --radius-km
--center-lat           Optional latitude for radius search
--center-lng           Optional longitude for radius search
--keywords             One or more search keywords
--max-results          Maximum results per keyword, default 50
--review-threshold     Review-count cutoff for Google small-business heuristic, default 300
--min-rating           Export only leads with rating at or above this value
--max-rating           Export only leads with rating at or below this value
--min-reviews          Export only leads with at least this many reviews
--max-reviews          Export only leads with no more than this many reviews
--include-terms        Export only leads matching any term in name/category/address/city
--exclude-terms        Exclude exported leads matching any term in name/category/address/city
--lead-preset          no_website_phone, no_website, mobile_no_website, all
--secondary-scrape     Optional enrichment for records with real websites; disabled by default
--no-secondary-scrape  Explicitly disable secondary website enrichment
--formats              Comma-separated exports: csv,json,xlsx,xml,all
--output-format        Alias for --formats
--only-no-website      Export only leads marked as no website
--has-phone            Export only leads with a preferred phone number
--mobile-only          Export only leads with a mobile-looking Croatian phone number
--db-path              SQLite path, default nosite_scout.sqlite
--out-dir              Export folder, default exports
--manual-add           Add one lead manually, then export
--manual-name          Manual lead business name
--manual-phone         Manual lead phone number
--manual-website       Manual lead website URL
--manual-address       Manual lead address
--manual-city          Manual lead city
--manual-notes         Manual lead notes
--manual-status        Manual lead status, default review_website_age
```

Default keywords:

```text
restaurants cafes apartments plumbers electricians beauty_salon mechanics dentists small_shops local_services
```

## Output

The container runs with the project folder mounted at `/data`, so the script creates `nosite_scout.sqlite` in this folder unless `--db-path` is set.

Exports are written to `exports` by default with timestamped names:

```text
nosite_scout_YYYYMMDD_HHMMSS.csv
nosite_scout_YYYYMMDD_HHMMSS.json
nosite_scout_YYYYMMDD_HHMMSS.xml
nosite_scout_YYYYMMDD_HHMMSS.xlsx
```

Rows are sorted by likely outreach value:

1. `no_website` true
2. `has_phone` true
3. `likely_small_business` true
4. `review_count` descending

## Limitations

Free OpenStreetMap mode depends on community-maintained tags. It can find businesses with no website and phone numbers when those tags exist, but it cannot guarantee complete coverage. OSM does not provide Google-style ratings or review counts.

The script uses public Nominatim and Overpass endpoints. Keep runs modest and avoid aggressive repeated scraping.

Secondary website scraping is disabled by default because the core goal is no-website leads. Enable `--secondary-scrape` only when you want to enrich records that do have a real website.
