# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Metal Tour Check is a Python web scraping application that monitors metalinjection.net/category/tour-dates for new tour announcements. It checks every 12 hours, extracts band names from article titles, parses show dates out of article bodies, flags shows near home (Raleigh, NC), stores results in SQLite, and sends email notifications. A small Flask UI searches the database.

## Running

```bash
# Main monitoring loop (requires EMAIL_PASSWORD env var)
EMAIL_PASSWORD=<password> python main.py

# Backfill tour dates for articles already in the DB
python main.py --backfill

# Docker
docker build -t metal-tour-check .
docker run -e EMAIL_PASSWORD=<password> metal-tour-check

# Query the database
python browse_db.py --limit 10
python browse_db.py --city          # only city-matched articles
python browse_db.py --city Durham   # articles matching one city
python browse_db.py --band "MASTODON"
python browse_db.py --list-bands    # or --list-cities

# Web search UI on port 5000
python web.py

# Tests (plain scripts, no framework)
python test_bands.py
python test_cities.py
```

There is no linter. CI (`.github/workflows/`) builds the Docker image, runs both test scripts inside it, and checks that the bundled Firefox launches.

## Architecture

**main.py** — Single-file application containing all core logic:
- Every page — the listing page and each article — is fetched with `playwright` (headless Firefox) and parsed with BeautifulSoup. Cloudflare returns 403 to plain HTTP clients whatever headers they send; the listing page escaped that via the edge cache until September 2026, then got blocked too. One browser instance serves a whole run (`article_fetcher()` in `monitor_page`)
- Listing extraction reads `div.zox-art-title` entries inside `div#zox-home-cont-wrap`
- A failed run sends no email, so the main loop emails an alert after `ALERT_AFTER_FAILED_RUNS` consecutive failed runs (once per streak, with the traceback)
- Location matching (`check_article`) works on "City, ST" pairs, never bare city names, so Jacksonville FL and a person named Charlotte don't match. It prefers the show rows from `parse_tour_dates`, and only falls back to "City, ST" in the prose when no dates parse. A pair counts if it's within `RADIUS_MILES` of `HOME`, or is listed in `SEARCH_CITIES` (for long drives and for towns the geocoder can't resolve)
- An article whose fetch fails is stored with `city_found` NULL ("not checked"), which is deliberately distinct from 0 ("checked, nothing matched")
- Band name extraction uses regex for ALL-CAPS names from titles
- New articles are emailed, then recorded in SQLite. Recording only after a successful send means a failed send is retried next run
- Runs as an infinite loop with a 12-hour base sleep plus up to 30 minutes of random jitter; article fetches are spaced `FETCH_DELAY` (2 s) apart, and a run abandons city checks after `FAILURE_CUTOFF` consecutive fetch failures

**db.py** — All SQLite access: schema, inserts, and the queries `main.py` uses

**geo.py** — Offline city coordinates (geonamescache, US and Canada, places above ~15k population) and distance. An unresolved city is "unknown", never "far away"

**browse_db.py** — CLI query tool using argparse and tabulate

**web.py** — Flask search UI over the same database. `start.sh`, the Docker entrypoint, runs it alongside the scraper loop

**Database:** SQLite at `articles/tours.db`. `tour_articles` (title, bands, url, city_found, date_scraped) is the source of truth for deduplication. `article_bands` and `article_cities` hold the normalized bands and matched places per article. `tour_dates` holds parsed individual shows (band, date, city, state, venue)

**articles/previous_articles.json** — From a previous version. If present, `migrate_legacy_articles` imports its URLs into the DB once and renames it to `.migrated`

**NOTES.md** — Record of the Cloudflare block and the options weighed; one decision (an events API for historical data) is still open

## Configuration

Email settings, `HOME`, `RADIUS_MILES` and `SEARCH_CITIES` are hardcoded constants at the top of main.py. The only external config is the `EMAIL_PASSWORD` environment variable.

## Docker

The image is based on `python:3.12-slim` (Debian). Alpine is not supported because playwright requires glibc and system libraries not available on Alpine. The Dockerfile installs playwright's Firefox browser binary via `playwright install-deps firefox && playwright install firefox` as part of the build. It also deletes geonamescache's larger city datasets (~165 MB), keeping only `cities15000.json`, which is the one `geo.py` loads; lowering geo.py's population cutoff means updating that line too.
