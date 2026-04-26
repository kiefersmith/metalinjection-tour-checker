## Metal Tour Check

A small script that monitors [metalinjection.net/category/tour-dates](https://metalinjection.net/category/tour-dates) for new tour announcements, checks article content for cities of interest, and sends email notifications.

### Configuration

Edit the constants at the top of `main.py`:

- `EMAIL_ADDRESS` / `TO_EMAIL` / `SMTP_SERVER` / `SMTP_PORT` — email settings
- `SEARCH_CITIES` — list of cities to scan for in article text
- `CHECK_INTERVAL` — base interval in seconds between checks (default 12 hours); a random jitter of up to 30 minutes is added each cycle

Set your email password via environment variable:

```bash
export EMAIL_PASSWORD=your_app_password
```

A Google App Password works well here.

### Running

```bash
# Main monitoring loop
EMAIL_PASSWORD=<password> python main.py

# Backfill tour dates for articles already in the DB
python main.py --backfill

# Query the database
python browse_db.py --limit 10
python browse_db.py --city          # only city-matched articles
python browse_db.py --band "MASTODON"
```

### Docker

```bash
docker build -t metal-tour-check .
docker run -e EMAIL_PASSWORD=<password> metal-tour-check
```

### Dependencies

- `requests` + `BeautifulSoup` — scrapes the tour-dates listing page
- `playwright` (Firefox) — fetches individual article pages; required to bypass Cloudflare bot protection on article URLs
- `sqlite3` — stores scraped articles in `articles/tours.db`

After installing requirements, the Firefox browser binary must be installed once:

```bash
python -m playwright install-deps firefox
python -m playwright install firefox
```

The Docker build handles this automatically.
