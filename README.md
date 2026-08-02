This is a small script that checks the tour announcements page at metalinjection.net.

You'll need to change the variables under "email configuration" at the top.  You'll also need to set the environment variable "EMAIL_PASSWORD" to your email password.  I used a Google app password for my email password.

## Where you want to see shows

Two settings at the top of `main.py`, and a show matches if *either* applies:

    HOME = ("Raleigh", "NC")   # anything within RADIUS_MILES of here counts
    RADIUS_MILES = 100
    SEARCH_CITIES = [...]      # always match these, however far away

The radius catches nearby cities you'd never think to list — Durham is 21 miles
out, Fayetteville 52 — without naming them all. `SEARCH_CITIES` covers the two
cases a radius can't: places worth a longer drive (Charlotte at 130 miles,
Asheville at 220), and places the geocoder doesn't know. Coordinates come from
`geonamescache`, which only carries towns above roughly 15,000 people, so
Hillsborough, NC has to be listed explicitly or it would never match.

**Cities are always matched together with their state.** A bare "Jacksonville"
is ignored — every Jacksonville in the database so far has been Florida, not the
one in NC — as is a "Charlotte" that turns out to be a person's name.

## Running

    pip install -r requirements.txt
    python -m playwright install firefox   # once; article pages need a real browser

    EMAIL_PASSWORD=<password> python main.py     # the monitoring loop
    python main.py --backfill                    # parse show dates for stored articles
    python web.py                                # web UI on :5000

In Docker, `start.sh` runs the loop and the web UI together.

## State

Everything lives in `articles/`:

- `tours.db` — SQLite database of every article seen, with the bands parsed out of the
  title and whether one of your cities was mentioned. This is also what the script uses
  to decide which articles are new, so it needs to persist between runs.

Articles are only recorded *after* the notification email sends successfully, so a mail
failure means they're retried on the next run rather than silently dropped.

If you have an old `previous_articles.json` from a previous version, it's imported into
the database automatically on the next run and renamed to `.migrated`.

## Browsing

    python browse_db.py --limit 20            # most recent articles
    python browse_db.py --city                # anything mentioning a city of interest
    python browse_db.py --city Raleigh        # a specific city
    python browse_db.py --band SLAYER         # exact band name, not a substring
    python browse_db.py --band SLAYER --city Raleigh
    python browse_db.py --list-bands          # every band seen, by mention count
    python browse_db.py --list-cities         # every matched city, by mention count

Band and city matching are exact (case-insensitive), so `--band DEATH` no longer
returns UNDEATH articles.

Rows recorded before cities were tracked individually show `(unrecorded)` in the
Cities column: a city matched, but which one wasn't stored at the time.

**Note:** the site's Cloudflare configuration returns 403 to plain HTTP clients on
individual article pages, and has since roughly April 2026. Browser-like request
headers don't help — only a real browser engine gets through — so article bodies are
fetched with Playwright's headless Firefox. The category listing still uses `requests`,
because it's served from Cloudflare's edge cache.

Two consequences worth knowing:

- **`requirements.txt` alone isn't enough.** After `pip install -r requirements.txt`,
  run `playwright install firefox` to fetch the browser binary. The Docker image does
  this at build time.
- **The listing page depends on the exact URL.** `/category/tour-dates` is cached and
  returns 200; `/category/tour-dates/` *with* a trailing slash misses the cache and gets
  403. Don't "tidy" the `URL` constant in `main.py`.

If a fetch fails, the article is stored with `city_found` NULL ("not checked"), which is
deliberately distinct from 0 ("checked, nothing matched"), and the email says so.

### Show dates

Individual show dates are parsed out of article bodies into the `tour_dates` table
(band, date, city, state, venue) and browsable in the web UI. `python main.py --backfill`
fills them in for articles already stored but not yet parsed.

Both listing styles the site uses are understood:

    3/25 Philadelphia, PA Milkboy3/26 Hamden, CT Cellar on Treadwell
    Oct 21 – Charlotte, NC @ The Underground

The second form requires the dash. That's deliberate: it's what separates a listing
from prose like "Oct 3 at the House of Blues in San Diego", which otherwise runs on
until it hits an unrelated `City, ST` and invents a show.

Because matching prefers these parsed rows, the email can name the night and the
venue rather than just a city — which makes a wrong match visible instead of silent.
Prose is only consulted when an article has no parseable listing at all.

### What this can't tell you yet

The database only accumulates going forward: shows announced before it started
recording aren't available, so "when did BAND *last* play Raleigh" can't be answered
for anything older than the first run. That needs an events API (setlist.fm and
friends) rather than the scraper — see `NOTES.md`.

## Docker

`articles/` must be mounted to persistent storage, otherwise the database is lost on
every restart and every article gets re-notified:

    docker run -v /path/to/storage:/app/articles -e EMAIL_PASSWORD=... metal-tour-check
