# Open decision: how to get show dates (paused 2026-08-01)

> ## Correction 2026-08-02 — `master` was never stranded
> The sections below describe `master`/`save` as unmerged work. That was wrong, and
> came from reading a **stale local `main`**. On GitHub, PR #1 merged `master` into
> `main` on 2026-04-26; remote `main` has had the Playwright fetch, the `tour_dates`
> parser, `web.py` and `--backfill` ever since. The local clone had simply never
> pulled. `save` is a redundant orphan snapshot of the same work — still ignorable.
>
> Consequence: the August branch was built on a base four months behind, and briefly
> looked like it "added" Playwright that already existed. It has now been merged with
> `origin/main`, keeping both sides — see the merge commit.
>
> ## RESOLVED 2026-08-02 — option 2 is implemented
> The Playwright fetch is ported onto `august-improvements` and working: article
> bodies fetch again and the city check is live (it matched Charlotte and
> Jacksonville on the PEELINGFLESH dates on its first real run). The rest of this
> file is kept as the record of how the block was diagnosed and why the other
> options were weighed.
>
> **Still open:** option 1 (an events API) is the only route to *historical*
> "when did BAND last play CITY" data. The scraper still only accumulates forward.
> That decision is untouched by this work.
>
> `web.py`, `start.sh` and `--backfill` all came in with the merge and are kept.
>
> ~~**Known gap:** `parse_tour_dates` only handles the numeric listing format.~~
> Fixed — the `Oct 21 – Charlotte, NC @ Venue` style parses now too.
>
> **Location matching was rebuilt on top of that (2026-08-02).** The old check
> matched bare city names anywhere in the body, which was wrong in both directions:
>
> - Every `Jacksonville` row in the database is Florida. That entry in
>   `SEARCH_CITIES` had only ever produced false alarms.
> - `Charlotte` matched Charlotte Wessels, a vocalist. `Chapel Hill` matched a road
>   in Dallas. All seven adversarial cases tried came back positive.
> - Meanwhile Durham (21 mi) and Fayetteville (52 mi) never matched at all, though
>   both are closer than Greensboro and Jacksonville NC, which were listed.
>
> Now: matching runs over the parsed show rows (which carry a state), a city only
> counts alongside its state, and anything within `RADIUS_MILES` of `HOME` counts
> whether or not it's listed. `SEARCH_CITIES` remains for long drives and for towns
> below the geocoder's population floor — Hillsborough, NC among them.

## Re-check 2026-08-02 — block still applies, nothing has changed

Ran the probe at the bottom of this file. **Articles are still 403.** Option 2 is not
back on the table, and plain scraping is still dead.

- Article, no trailing slash → 403
- Same article, **with** trailing slash → 403
- A fresh canonical article URL taken straight from `/feed/` → 403

So it isn't a stale-permalink or URL-variant artifact for articles; the rule covers them
however you spell them.

### New: the category page only works in one URL variant

    /category/tour-dates     200   cf-cache-status=HIT   age=4081     <-- what main.py uses
    /category/tour-dates/    403   (no cf-cache-status header at all)

Only the no-trailing-slash form is edge-cached. The trailing-slash form misses cache and
gets challenged like an article does. **The whole pipeline currently survives on this one
detail** — if that cache entry is ever evicted or the canonical form changes, new-article
detection dies too and there is no fallback. Undocumented single point of failure; do not
"tidy" `URL` in `main.py` by adding a trailing slash.

Verified the surviving path still parses end-to-end (read-only, no email, no writes):
23 articles extracted from the category page, all 23 new relative to the DB.

### Events APIs: no change from 2026-08-01

setlist.fm 403, Bandsintown 403, Songkick 401 — identical to the table below, all still
"register for a key". MusicBrainz returned 503 once and **200 on retry 5s later**; that
was transient rate-limiting/outage, not a policy change. MusicBrainz still works unkeyed.

### Option 2 was already built in April and lives on `master`

**`main` is one commit behind `master`, and `master` is where the Playwright work is.**

    main            b511e15
    master  = main + 1c404c0  "…use playwright instead of only requests."  2026-04-26
    origin/master   1c404c0   (pushed)

`master` descends cleanly from `main` and is pushed to origin. There is also a `save`
branch with near-identical content, but it is an **orphan** commit (no parent, no
merge-base with `main`) and differs from `master` only in `.gitignore`, `browse_db.py`,
`db.py`, `requirements.txt`. Treat `save` as a redundant snapshot and ignore it; `master`
is the real line of work.

What `master` already has:

- `get_article_content_playwright()` — headless **Firefox**, used for article pages only
- a persistent `requests.Session` with Firefox-like headers for the listing page, with
  `Accept-Encoding` deliberately omitted so the server doesn't reply with Brotli
- `web.py` (151 lines), `start.sh`, a Playwright-ready `Dockerfile` (python:3.12-slim,
  not Alpine — Playwright needs glibc), a `--backfill` mode
- a `CLAUDE.md` that states as settled fact that article pages are "fetched with
  playwright (headless Firefox) **to bypass Cloudflare bot protection**"

So the block predates the 2026-08-01 diagnosis below, and option 2 was not just proposed
but implemented and documented as working back in April. The "this postdates April 2026"
paragraph further down is therefore **wrong** — the April `city_found = 1` rows were
scraped on 2026-04-11, and the Cloudflare response came two weeks later on 2026-04-26.

**Tested 2026-08-02: the Playwright fetch still works. Option 2 is live.**

Ran `master`'s `get_article_content_playwright()` (headless Firefox) against four real
article URLs — every one returned **200** with a full `div.zox-post-main` body:

| URL | requests/curl | Playwright |
|---|---|---|
| `afi-announces-handful-of-european-tour-dates` | 403 | **200**, 8 paragraphs |
| `peelingflesh-to-be-joined-by-friends-...` | 403 | **200**, 9 paragraphs |
| `faith-no-more-system-of-a-down-tour-2027` | — | **200**, 2058 chars |
| `dead-poet-society-announce-co-headlining-...` | — | **200**, 2874 chars |

The city scan runs clean over the extracted text (no matches on those four, all
European/non-NC dates — a correct negative, not a failure).

Two supporting findings:

- **Headers alone are not enough.** `master`'s Firefox-like `requests.Session`
  (full UA + Accept + Accept-Language + DNT) still gets **403** on an article. The
  bypass comes from the real browser, not the header set. Don't try to shortcut it.
- A deliberately wrong URL returned **404, not 403** — i.e. Playwright is reaching
  WordPress itself rather than being stopped at the Cloudflare edge. Independent
  confirmation the bypass is genuine.

Environment note: `playwright` is already installed in `venv/`, and the Firefox binary
is already present at `~/.cache/ms-playwright/firefox-1509/`. No install needed locally;
the Docker image still needs `playwright install-deps firefox && playwright install
firefox` as `master`'s Dockerfile already does.

### How to test it without endangering the uncommitted work

Do **not** `git checkout master`/`save`. Seven files are modified-uncommitted on `main`
and all differ across the branches, so the checkout gets refused and the tempting next
move (`git stash`, `checkout -f`) is how ~490 lines of August work goes missing.

The fetcher is eight lines. Extract it and run it standalone:

    git show master:main.py > <scratchpad>/master_main.py
    pip install playwright && playwright install firefox
    # then call get_article_content_playwright() on one article URL

`master`'s durable value is the Dockerfile/`web.py`/`start.sh` wiring, not that function.

### Also on `master`: the site layout may have changed

`master`'s `CLAUDE.md` says article extraction was moved to `article.zox-art-wrap`
because `div#zox-home-cont-wrap` "no longer exists in the site's HTML". But `main`'s
`extract_content()` still uses `div#zox-home-cont-wrap` and **it parsed 23 articles fine
today**. Most likely explanation: the no-trailing-slash category URL is serving an older
cached generation of the page. Worth keeping in mind — the version of the page we can
still reach may not be the version the site is actually publishing.

### State of the data — nothing has been lost yet

The scraper has not run since **2026-04-11**. The DB holds 23 articles, `city_found`
breakdown is 15 zeros and 8 ones — **zero NULL rows**. The "durable cost" warned about
below has cost nothing so far.

But the site has moved on: all 23 articles currently on the category page are new. So the
first run after restart will, in one go, send one email about 23 articles and write **23
permanently-NULL rows** that dedup will never revisit. Don't start the container just to
see if it works — that write is irreversible and the email is real. Use a read-only dry
run instead (import `main`, call `get_page_content`/`extract_content`/`find_new_articles`,
touch nothing else).

## The blocker

Individual article pages on metalinjection.net return **403 to non-browser clients**.
This is a standing Cloudflare bot rule, not a rate limit and not our IP being flagged.

Evidence gathered 2026-08-01:

- A single request after 25 minutes idle → 403. Not a rolling window, so crawling
  slower does not help.
- `curl` (different TLS fingerprint) → 403. Not a User-Agent problem.
- The three hottest articles on the site → 403.
- Confirmed from a second, independent IP (the Unraid box).
- `robots.txt` has **no** `Crawl-delay` and says `User-agent: * / Allow: /`, so there
  is no published rate we're violating.

The mechanism is visible in response headers — Cloudflare serves cached content to
anyone and challenges everything that misses:

    category page   200   cf-cache-status=HIT    age=90
    /feed/          200   cf-cache-status=HIT    age=87
    article page    403   cf-cache-status=None

Article pages are never edge-cached for us, so they always miss and always get blocked.

This postdates April 2026 — the existing April rows have `city_found = 1`, so article
bodies fetched fine back then.

> **Corrected 2026-08-02:** the block started around **2026-04-26**, not later. The
> `city_found = 1` rows were scraped 2026-04-11; two weeks after that, the `master`
> branch added Playwright specifically "to bypass Cloudflare bot protection". See the
> re-check section at the top.

## What still works

- The category listing page (cache HIT), so new-article detection and the notification
  emails are unaffected.
- `browse_db.py` querying over everything already stored.
- The site-wide RSS feed at `/feed/` (200). Contains `pubDate` and WordPress tag
  categories — which are real band names, better than parsing titles with a regex —
  but only excerpts, no tour-date listings, only 25 items, and all categories mixed.
  The tour-dates-specific feed (`/category/tour-dates/feed/`) is 403.

## What is broken

City matching on new articles. It fails cleanly rather than lying: `city_found` is
stored NULL ("not checked", distinct from 0 "checked, no match"), the log emits a loud
ERROR, and the email says "could not check" instead of "no nearby cities mentioned".

**Durable cost:** articles seen during the block get `city_found` NULL and are never
re-checked, because deduplication is by URL. If the block lifts there is no backfill
path for that window. Worth writing a one-off re-check script if it ever does.

## The options

> **Update 2026-08-02:** option 2 is verified working (see top). The recommendation below
> was written when article bodies looked unreachable. Option 2 is now the cheap path back
> to a *working* city check; option 1 remains the only path to *historical* "when did BAND
> last play CITY" data. They are complementary, not exclusive — option 2 first is the
> lower-risk order.

### 1. Events API (recommended)

Drops the dependency on the blocked site entirely and is the only path that answers
"when did BAND last play CITY" with real historical data — the current design only ever
accumulates going forward.

Probed 2026-08-01; all the useful ones need a key you have to register for:

| Source | Status without key | Notes |
|---|---|---|
| setlist.fm | 403 | Free key. Historical setlists by artist + city — the best fit for "when did they last play here". |
| Bandsintown | 403 (explicit deny) | Needs a registered/approved `app_id`. Good for upcoming dates. |
| Songkick | 401 | API key by application. Upcoming + past. |
| MusicBrainz | **200, no key** | Works unauthenticated, but concert/event coverage is sparse. |

Plan: get a setlist.fm key for past shows and Bandsintown or Songkick for upcoming,
then build a `shows(band, city, venue, show_date)` table and query CLI on top. The
existing `article_bands` table gives the list of bands to look up.

### 2. Headless browser container — already built, on `master`

Add Playwright to the image so article bodies fetch again. This is **not** greenfield:
`master` (2026-04-26) already has the headless-Firefox fetcher, a web UI and a Docker
setup for it, documented as working. Start by testing whether that fetch still returns
200 before rebuilding anything — see the extraction recipe at the top of this file.

The real work here is not the fetcher, it's reconciling `master`'s April code with the
~490 lines of uncommitted August work on `main` (NULL `city_found` handling,
`FAILURE_CUTOFF`, logging, legacy-JSON migration), which `master` predates entirely. Restores the city
check and enables parsing tour dates out of article bodies. Works, but it's a heavy
dependency for a small scraper, slower per run, and still only accumulates forward.

### 3. Leave it

Keep the title/URL notifier and the improved browsing. Accept NULL city data on new
articles.

## First thing to do when picking this back up

Re-check whether the block still applies (done 2026-08-02 — still 403, see top of file):

    curl -s -o /dev/null -w "%{http_code}\n" https://metalinjection.net/tour-dates/<any-article>

200 means the situation changed and option 2 (or plain scraping) is back on the table.
Check the trailing-slash variant too — variant sensitivity is real on this site.

Done, on branch `august-improvements` (2026-08-02):

1. ~~Commit the uncommitted August work~~ — `811e54e`, `e9a5dc0`.
2. ~~Fix the band parser~~ — `f1b75c9`. All-caps connectives are kept inside names now
   (`FAITH NO MORE`, `SYSTEM OF A DOWN`); `test_bands.py` covers 21 real headlines.
3. ~~Port the Playwright fetch~~ — `22ed1ca`. Browser launched once per run, non-2xx
   raises so a block page can't read as "no cities", base image moved to `python:3.12-slim`.

Left to decide:

- Whether `master`'s `web.py` / `start.sh` / `--backfill` are worth porting too.
- Option 1 (events API) for historical show dates — unaffected by any of the above.
- The NULL-row backfill script is still unnecessary: there are no NULL rows yet.

**Before the first real run**, note it will email about ~23 articles at once, since the
DB last saw the site on 2026-04-11. Nothing is lost by that — with the fetch working
again those rows get real `city_found` values rather than NULLs — but the email will be
long. Consider seeding the DB quietly first if that's not wanted.
