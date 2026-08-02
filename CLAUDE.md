# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Metal Tour Check is a Python web scraping application that monitors metalinjection.net/category/tour-dates for new tour announcements. It checks every 12 hours, extracts band names from article titles, searches article content for target cities (NC area), stores results in SQLite, and sends email notifications.

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
python browse_db.py --band "MASTODON"
```

There are no tests, linter, or build step configured.

## Architecture

**main.py** — Single-file application containing all core logic:
- Listing page scraped with `requests` + BeautifulSoup; individual article pages fetched with `playwright` (headless Firefox) to bypass Cloudflare bot protection
- A persistent `requests.Session` with Firefox-like headers (User-Agent, Accept, Accept-Language, DNT) is used for the listing page; `Accept-Encoding` is intentionally omitted so the server does not respond with Brotli, which `requests` cannot decompress
- Article extraction targets `article.zox-art-wrap` elements (changed from the old `div#zox-home-cont-wrap` wrapper which no longer exists in the site's HTML)
- City search is case-sensitive substring matching in article paragraph text
- Band name extraction uses regex for ALL-CAPS names from titles
- SQLite storage → email notification
- Runs as an infinite loop with a 12-hour base sleep plus up to 30 minutes of random jitter; article fetches have a 2–5 second random delay between them to avoid rate-limiting

**db.py** — Duplicated subset of database functions from main.py (legacy, not imported anywhere)

**browse_db.py** — CLI query tool using argparse and tabulate

**Database:** SQLite at `articles/tours.db` with tables `tour_articles` (title, bands, url, city_found, date_scraped) and `tour_dates` (parsed individual show dates per band)

**articles/previous_articles.json** — Leftover from a previous version; no longer read or written by the application. The DB is the source of truth for deduplication.

## Configuration

Email settings and search cities are hardcoded constants at the top of main.py. The only external config is the `EMAIL_PASSWORD` environment variable.

## Docker

The image is based on `python:3.12-slim` (Debian). Alpine is not supported because playwright requires glibc and system libraries not available on Alpine. The Dockerfile installs playwright's Firefox browser binary via `playwright install-deps firefox && playwright install firefox` as part of the build.
