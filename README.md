This is a small script that checks the tour announcements page at metalinjection.net.

You'll need to change the variables under "email configuration" at the top.  You'll also need to set the environment variable "EMAIL_PASSWORD" to your email password.  I used a Google app password for my email password.

You can update the SEARCH_CITIES variable to look for cities near you / cities of interest.

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

**Note:** as of August 2026 the site's Cloudflare configuration returns 403 to
non-browser clients for individual article pages, so the city check may fail and store
`city_found` as NULL ("not checked") rather than 0. The article listing and email still
work — the category page is served from Cloudflare's cache. Check with:

    curl -s -o /dev/null -w "%{http_code}\n" https://metalinjection.net/tour-dates/<any-article>

### What this can't tell you yet

There are no *show* dates — only the date an article was scraped — so "when did BAND
last play Raleigh" and "when are they back" can't be answered directly. That needs the
per-date listings parsed out of article bodies into a shows table. It also only
accumulates going forward; nothing before the database started recording is available.

## Docker

`articles/` must be mounted to persistent storage, otherwise the database is lost on
every restart and every article gets re-notified:

    docker run -v /path/to/storage:/app/articles -e EMAIL_PASSWORD=... metal-tour-check
