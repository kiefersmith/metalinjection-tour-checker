from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright
from contextlib import contextmanager
from collections import namedtuple
from datetime import datetime
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import argparse
import random
import time
import json
import os
import logging
import sys
import traceback
import re

import geo
from db import (
    init_db,
    insert_article,
    known_urls,
    insert_tour_dates,
    articles_without_tour_dates,
)

# Email configuration
EMAIL_ADDRESS = "kieferisgreat@gmail.com"
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD")
TO_EMAIL = "kieferisgreat@gmail.com"
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587

# Monitoring configuration
URL = "https://metalinjection.net/category/tour-dates"
CHECK_INTERVAL = 12*3600  # in seconds
REQUEST_TIMEOUT = 30  # seconds; without this a stalled connection blocks forever
FETCH_DELAY = 2  # seconds between article fetches, to stay a polite client
FAILURE_CUTOFF = 3  # consecutive article failures before abandoning city checks for a run
# Failed runs in a row before emailing an alert. A failed run sends no email, so
# without this a lasting failure looks exactly like "no new tours" — it once went
# unnoticed for five months. Two runs is about a day, enough to ride out a blip.
ALERT_AFTER_FAILED_RUNS = 2
LEGACY_CONTENT_FILE = "articles/previous_articles.json"
# Where you are. Any show within RADIUS_MILES of here counts, which catches
# nearby cities you'd never think to list (Durham is 21 miles out; Fayetteville
# 52) without naming them all.
HOME = ("Raleigh", "NC")
RADIUS_MILES = 100

# Always match these, however far away — places worth the drive, plus anywhere
# the geocoder can't resolve. Hillsborough, NC is under the dataset's population
# floor, so without this entry the radius alone would silently never match it.
SEARCH_CITIES = [
    ("Raleigh", "NC"),
    ("Greensboro", "NC"),
    ("Charlotte", "NC"),
    ("Jacksonville", "NC"),
    ("Chapel Hill", "NC"),
    ("Hillsborough", "NC"),
    ("Asheville", "NC"),
]

logging.basicConfig(stream=sys.stdout, level=logging.DEBUG)

# "Durham, NC" — a city followed by a two-letter state. Requiring the state is
# what stops "Jacksonville" (Florida) and "Charlotte" (a person's name) from
# matching; the pair is then checked against HOME/SEARCH_CITIES.
CITY_STATE_PATTERN = re.compile(r"\b([A-Z][A-Za-z.'\-]*(?: [A-Z][A-Za-z.'\-]*){0,3})\s*,\s*([A-Z]{2})\b")

_WANTED_CITIES = {(city.casefold(), state.upper()) for city, state in SEARCH_CITIES}


def is_near_home(city, state):
    """True if a show in this city is one you'd want to know about."""
    if not city or not state:
        return False
    if (city.strip().casefold(), state.strip().upper()) in _WANTED_CITIES:
        return True
    distance = geo.distance_from(HOME, city, state)
    return distance is not None and distance <= RADIUS_MILES


def describe_place(city, state):
    """'Durham, NC (21 mi)' — the distance is what makes a match checkable."""
    distance = geo.distance_from(HOME, city, state)
    return f"{city}, {state}" + (f" ({distance:.0f} mi)" if distance is not None else "")


def find_new_articles(articles, seen_urls):
    """Finds articles whose URLs haven't been recorded yet."""
    return [article for article in articles if article["url"] not in seen_urls]

def extract_content(content):
    content_list = []
    c = BeautifulSoup(content, "html.parser").find("div", id="zox-home-cont-wrap")
    if c is None:
        raise ValueError("Could not find the article list; the page layout may have changed")
    for cc in c.find_all("div", class_="zox-art-title"):
        link = cc.find("a")
        heading = cc.find("h2")
        if link is None or heading is None or not link.get("href"):
            continue
        content_list.append({"title": heading.get_text(strip=True), "url": link["href"]})
    return content_list

@contextmanager
def article_fetcher():
    """Yields a url -> html callable backed by one headless Firefox instance.

    The whole site sits behind Cloudflare, which returns 403 to plain HTTP clients
    whatever headers they send — a full Firefox-like header set still gets
    blocked, so only a real browser engine gets through. The listing page used to
    be exempt, served from the edge cache, until that stopped in 2026; it now
    goes through here too.

    The browser is launched once per run, not once per article: startup costs
    far more than the fetch itself.
    """
    with sync_playwright() as playwright:
        browser = playwright.firefox.launch(headless=True)
        try:
            def fetch(url):
                page = browser.new_page()
                try:
                    response = page.goto(
                        url, wait_until="domcontentloaded", timeout=REQUEST_TIMEOUT * 1000
                    )
                    # Without this an error page would parse as a body-less article
                    # and be recorded as "checked, no cities" — a silent false negative.
                    if response is not None and response.status >= 400:
                        raise RuntimeError(f"HTTP {response.status} fetching {url}")
                    return page.content()
                finally:
                    page.close()

            yield fetch
        finally:
            browser.close()

# What one article fetch yielded.
#   places — (city, state) pairs near home, deduplicated, for storage and email
#   shows  — the matching (date, city, state, venue) rows, when dates parsed
#   dates  — every show parsed from the article, near or not
#   text   — the body, kept so nothing needs a second trip through the browser
ArticleCheck = namedtuple("ArticleCheck", "places text shows dates")

EMPTY_CHECK = ArticleCheck([], "", [], [])

def check_article(url, fetch):
    """Returns an ArticleCheck: which nearby places an article mentions, and why.

    Matching prefers the parsed show listings, because those carry a state and so
    can tell Jacksonville NC from Jacksonville FL. Prose is only consulted when
    no dates parsed at all, and even then a bare city name is ignored — the state
    has to be right there next to it.
    """
    body = BeautifulSoup(fetch(url), "html.parser").find("div", class_="zox-post-main")
    if body is None:
        # Not a standard post layout (video embed, redirect, ...); nothing to match on.
        logging.warning("No article body found at %s", url)
        return EMPTY_CHECK

    text = body.get_text(" ", strip=True)
    dates = parse_tour_dates(text)

    if dates:
        shows = [d for d in dates if is_near_home(d[1], d[2])]
        places = _unique_places((city, state) for _, city, state, _ in shows)
        return ArticleCheck(places, text, shows, dates)

    # No parseable listing. Fall back to any "City, ST" in the prose, which still
    # rejects a bare "Charlotte", but can't say which night the show is.
    places = _unique_places(
        (match.group(1), match.group(2))
        for match in CITY_STATE_PATTERN.finditer(text)
        if is_near_home(match.group(1), match.group(2))
    )
    return ArticleCheck(places, text, [], [])

def _unique_places(pairs):
    """Deduplicates (city, state) pairs case-insensitively, keeping first seen."""
    seen = set()
    unique = []
    for city, state in pairs:
        key = (city.casefold(), state.upper())
        if key not in seen:
            seen.add(key)
            unique.append((city, state.upper()))
    return unique

def check_articles(content_list, fetch):
    """Maps each article URL to its ArticleCheck, or None if it couldn't be read.

    fetch is the run's article_fetcher, shared with the listing-page fetch so the
    browser only starts once.

    A single unreachable or oddly-shaped article must not abort the whole run, so
    failures here are logged and the article is mapped to None — "not checked",
    which is deliberately different from ArticleCheck([], ...) ("checked, no
    cities"). Widespread failure is a different problem — usually the Cloudflare
    rule tightening — and is called out loudly, because otherwise it is
    indistinguishable from "no cities mentioned".
    """
    checks_by_url = {article["url"]: None for article in content_list}
    if not content_list:
        return checks_by_url

    failures, checked = _check_each_article(content_list, checks_by_url, fetch)

    if failures and failures == checked:
        logging.error(
            "Every city check failed (%d/%d) — assume the site is blocking us or has "
            "changed, NOT that no cities were mentioned",
            failures, checked,
        )
    elif failures:
        logging.warning("%d of %d city checks failed", failures, checked)

    return checks_by_url

def _check_each_article(content_list, checks_by_url, fetch):
    """Fills in checks_by_url in place; returns (failures, articles attempted)."""
    failures = 0
    consecutive = 0
    checked = 0

    for index, content in enumerate(content_list):
        if consecutive >= FAILURE_CUTOFF:
            # Something is refusing us wholesale — the Cloudflare rule tightening
            # again, or the browser wedged. Grinding through the rest just burns
            # FETCH_DELAY per article for no result.
            logging.error(
                "Giving up on city checks after %d consecutive failures; "
                "%d article(s) left unchecked",
                consecutive, len(content_list) - index,
            )
            break
        if index:
            # Space out requests rather than fetching back-to-back.
            time.sleep(FETCH_DELAY)

        checked += 1
        try:
            checks_by_url[content["url"]] = check_article(content["url"], fetch)
            consecutive = 0
        except Exception:
            failures += 1
            consecutive += 1
            logging.exception("Could not check cities for %s", content["url"])

    return failures, checked

# All-caps words that show up in headlines but are never band names on their own.
# Everything here genuinely appears capitalised in copy — "LISTEN:", "U.S.", "NYC".
NON_BAND_TOKENS = {
    "US", "USA", "UK", "EU", "NYC", "LA", "TV", "EP", "LP", "CD", "DVD", "VIP",
    "NEW", "LIVE", "TOUR", "TOURS", "SHOW", "SHOWS", "DATES", "VIDEO",
    "WATCH", "LISTEN", "PREMIERE", "STREAM",
    "FT", "FEAT", "DJ", "RIP", "PSA", "WTF", "OMG", "NSFW",
}

# Connectives ("OF", "AND", "A", "THE", "IN", "TO", "NO", "MORE") are deliberately
# absent from that set. This site writes band names in ALL CAPS and editorial prose
# in Title Case, so a capitalised connective is nearly always *inside* a name —
# CORROSION OF CONFORMITY, COHEED AND CAMBRIA, A PERFECT CIRCLE, IN FLAMES,
# STICK TO YOUR GUNS, FAITH NO MORE. The editorial forms are Title Case ("Of",
# "And", "More"), so they already end a run by failing _is_caps_token().

# Bands whose names genuinely contain '&'. Without these, 'X & Y' is assumed to be
# two separate acts, which is how these headlines read the vast majority of the time.
AMPERSAND_BANDS = {
    "AUTHOR & PUNISHER",
}

def _normalize(token):
    """Strips surrounding punctuation and interior dots so 'U.S.' compares as 'US'."""
    return token.strip("-/.'").replace(".", "").upper()

def _is_filler(token):
    return token == "&" or _normalize(token) in NON_BAND_TOKENS

def _is_caps_token(token):
    """True for an all-caps word that could be part of a band name.

    Single letters count, so 'A PERFECT CIRCLE' keeps its first word. A stray 'A'
    from Title Case prose ('In A Connecticut Arena') survives this check but is
    thrown out by _finish_run(), which refuses one-letter runs.
    """
    core = token.strip("-/.'")
    if not core or core != core.upper():
        return False
    return any(ch.isalpha() for ch in core)

def _split_on_ampersand(run):
    """Splits 'GWAR & CANNIBAL CORPSE' into two bands, keeping known '&' names whole."""
    if run.upper() in AMPERSAND_BANDS:
        return [run]
    return [p.strip() for p in re.split(r"\s+&\s+", run) if p.strip()]

def extract_band_names(title):
    """Pulls likely band names out of a headline by finding runs of all-caps words."""
    bands = set()
    # Only true separators end a run; letters of any alphabet are left intact so
    # names like 'ILL NIÑO' survive. '|' is not a separator — BIG|BRAVE is one band.
    for segment in re.split(r"[,;:()\[\]\"“”…]+", title):
        run = []
        for token in segment.split():
            # A numeric token continues a run ('POWERMAN 5000') but can't start one.
            # It has to actually contain a digit, so a stray '+' ends the run
            # instead of being swallowed ('IN FLAMES + More').
            numeric_tail = (
                run
                and any(ch.isdigit() for ch in token)
                and not any(ch.isalpha() for ch in token)
            )
            if _is_caps_token(token) or token == "&" or numeric_tail:
                run.append(token)
                continue
            bands.update(_finish_run(run))
            run = []
        bands.update(_finish_run(run))

    return sorted(bands)

def _finish_run(run):
    """Cleans up one run of consecutive all-caps tokens and yields the band names in it."""
    # Drop leading/trailing filler so 'PIG DESTROYER US' becomes 'PIG DESTROYER'.
    # A leading 'THE' is kept — it's part of the name in 'THE OFFSPRING'.
    while run and _is_filler(run[0]):
        run = run[1:]
    while run and (_is_filler(run[-1]) or _normalize(run[-1]) == "THE"):
        run = run[:-1]
    if not run:
        return []
    # A run of one short token is the stray article from Title Case prose
    # ('In A Connecticut Arena'), not a band. Costs us one-letter acts like X.
    if len(run) == 1 and len(_normalize(run[0])) < 2:
        return []
    if len(run) == 1 and _normalize(run[0]) == "THE":
        return []

    text = " ".join(run)
    # Reject pure numbers and short Roman numerals ('III', '2026').
    if not any(ch.isalpha() for ch in text):
        return []
    if re.fullmatch(r"[IVXLCDM]+", text):
        return []

    return [part for part in _split_on_ampersand(text) if part]

def format_articles(heading, articles, empty_text=None, checks_by_url=None):
    lines = [heading]
    if articles:
        for article in articles:
            check = (checks_by_url or {}).get(article["url"])
            places = check.places if check else None
            suffix = (
                f' [{", ".join(describe_place(c, s) for c, s in places)}]' if places else ""
            )
            lines.append(f'- {article["title"]}{suffix} {article["url"]}')
            # Naming the night and the venue makes a wrong match obvious, where
            # a bare city name hides it.
            for date_iso, city, state, venue in (check.shows if check else []):
                lines.append(f'    {date_iso}  {city}, {state} @ {venue}')
    else:
        lines.append(empty_text or "(none)")
    return "\n".join(lines) + "\n"

def send_email(subject, body):
    if not EMAIL_PASSWORD:
        raise RuntimeError("EMAIL_PASSWORD is not set; cannot send email")

    msg = MIMEMultipart()
    msg["From"] = EMAIL_ADDRESS
    msg["To"] = TO_EMAIL
    msg["Subject"] = subject

    msg.attach(MIMEText(body, "plain"))
    with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
        server.starttls()
        server.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
        server.send_message(msg)
    logging.info("Sent email to %s", TO_EMAIL)

def send_failure_alert(failed_runs, error):
    """Emails that the monitor keeps failing. Never raises: the alert is a
    best-effort extra, and the loop must keep running either way."""
    try:
        send_email(
            "Metal Tour Check is failing",
            f"The last {failed_runs} runs failed, so no tour updates are being "
            f"checked. It will keep retrying every 12 hours; you'll get no more "
            f"alerts until a run succeeds.\n\nLatest error:\n\n{error}",
        )
    except Exception:
        logging.exception("Could not send the failure alert")

def migrate_legacy_articles():
    """Seeds the DB from the old previous_articles.json, once.

    The JSON file and the DB were separate sources of truth that had drifted apart.
    Recording the JSON URLs here stops those articles being re-notified now that
    deduplication reads from the DB alone.
    """
    if not os.path.exists(LEGACY_CONTENT_FILE):
        return

    try:
        with open(LEGACY_CONTENT_FILE, "r") as file:
            legacy = json.load(file)
    except (json.JSONDecodeError, OSError):
        logging.exception("Could not read %s; skipping migration", LEGACY_CONTENT_FILE)
        return

    seen = known_urls()
    added = 0
    for article in legacy:
        if article.get("url") and article["url"] not in seen:
            # city_found is left unknown — these were never checked against SEARCH_CITIES.
            insert_article(article["title"], extract_band_names(article["title"]), article["url"], None)
            added += 1

    os.rename(LEGACY_CONTENT_FILE, LEGACY_CONTENT_FILE + ".migrated")
    logging.info("Migrated %d article(s) from %s into the database", added, LEGACY_CONTENT_FILE)

MONTH_NAMES = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
MONTH_NUMBERS = {name.casefold(): number for number, name in enumerate(MONTH_NAMES, start=1)}
_MONTH_ALT = "|".join(MONTH_NAMES)
_DATE_HEAD = rf"(?:{_MONTH_ALT})[a-z]*\.?\s+\d{{1,2}}"

# "Oct 21 – Charlotte, NC @ The Underground (w/ Gridiron)". The dash is what
# separates a listing from prose like "Oct 3 at the House of Blues in San Diego",
# which otherwise runs on until it finds an unrelated comma-state pair.
MONTH_DATE_PATTERN = re.compile(
    rf"({_MONTH_ALT})[a-z]*\.?\s+(\d{{1,2}})\s*[–—-]+\s*"
    rf"([^,\d]{{2,28}}?)\s*,\s*([A-Z]{{2}})\b\s*@?\s*(.*?)(?=\s*{_DATE_HEAD}\b|$)"
)

def _parse_month_name_dates(text, year_hint):
    """Parses the 'Oct 21 – City, ST @ Venue' listing style."""
    results = []
    for month, day, city, state, venue in MONTH_DATE_PATTERN.findall(text):
        month_int = MONTH_NUMBERS[month.casefold()]
        day_int = int(day)
        if not 1 <= day_int <= 31:
            continue
        venue = venue.strip(" .–—-")
        if not venue:
            continue
        results.append((f"{year_hint}-{month_int:02d}-{day_int:02d}", city.strip(), state, venue))
    return results

def parse_tour_dates(article_text, year_hint=None):
    """Parses individual show dates out of an article body.

    Two listing styles appear on the site:
      3/25 Philadelphia, PA Milkboy3/26 Hamden, CT Cellar on Treadwell
      Oct 21 – Charlotte, NC @ The Underground

    Returns list of (date_iso, city, state, venue) tuples.
    """
    if not article_text:
        return []

    # Non-breaking spaces are everywhere in these listings and would otherwise
    # defeat every \s-based boundary below.
    article_text = article_text.replace("\xa0", " ")

    # Infer year from article text or default to current year
    if year_hint is None:
        year_match = re.search(r'20[2-3]\d', article_text)
        year_hint = int(year_match.group()) if year_match else datetime.now().year

    # Preprocess: insert a newline before date patterns that are glued to
    # previous text (e.g. "Venue 20265/16" -> "Venue 2026\n5/16")
    text = re.sub(r'(20\d{2})(\d{1,2}/\d{1,2})', r'\1\n\2', article_text)
    # Also split when venue text runs directly into a date like "Club5/18"
    text = re.sub(r'([a-zA-Z)])(\d{1,2}/\d{1,2}\s)', r'\1\n\2', text)

    # Pattern: M/DD City, ST Venue (followed by next date or end of line)
    pattern = r'(\d{1,2}/\d{1,2})\s+(.+?,\s*[A-Z]{2})\s+(.+?)(?=\n?\d{1,2}/|$)'
    matches = re.findall(pattern, text)

    results = []
    for date_str, city_state, venue in matches:
        # Strip trailing year (e.g. "Venue Name 2026" -> "Venue Name")
        venue = re.sub(r'\s*20\d{2}$', '', venue.strip())
        if not venue:
            continue
        parts = city_state.rsplit(',', 1)
        if len(parts) != 2:
            continue
        city = parts[0].strip()
        state = parts[1].strip()

        try:
            month, day = date_str.split('/')
            month_int, day_int = int(month), int(day)
            if month_int < 1 or month_int > 12 or day_int < 1 or day_int > 31:
                continue
            date_iso = f"{year_hint}-{month_int:02d}-{day_int:02d}"
        except (ValueError, IndexError):
            continue

        results.append((date_iso, city, state, venue))

    # The two styles don't co-occur in practice, so this just picks up whichever
    # one the article used.
    results.extend(_parse_month_name_dates(article_text, year_hint))

    # Deduplicate while preserving order
    seen = set()
    unique = []
    for r in results:
        if r not in seen:
            seen.add(r)
            unique.append(r)
    return unique

def backfill_tour_dates():
    """Re-fetches articles that have no show dates recorded and parses them.

    Useful after a spell where article fetches were failing, or after the date
    parser improves. Articles that already have rows are left alone.
    """
    init_db(band_extractor=extract_band_names)
    articles = articles_without_tour_dates()
    if not articles:
        logging.info("Nothing to backfill; every article already has show dates.")
        return

    logging.info("Backfilling show dates for %d article(s)", len(articles))
    filled = 0
    try:
        with article_fetcher() as fetch:
            for index, (article_id, title, url) in enumerate(articles):
                if index:
                    time.sleep(FETCH_DELAY)
                try:
                    dates = check_article(url, fetch).dates
                    if dates:
                        insert_tour_dates(article_id, extract_band_names(title), dates)
                        filled += 1
                        logging.info("Backfilled %d date(s) for: %s", len(dates), title)
                    else:
                        logging.info("No show dates found in: %s", title)
                except Exception:
                    logging.exception("Could not backfill %s", url)
    except Exception:
        logging.exception("Could not start the browser; backfill did not run")
        return

    logging.info("Backfill complete: %d of %d article(s) gained dates", filled, len(articles))

def monitor_page():
    """Runs one check. Returns None on success, or the traceback of a run that
    failed outright, so the caller can notice a streak of failures and say why.
    """
    try:
        init_db(band_extractor=extract_band_names)
        migrate_legacy_articles()
        # One browser serves the listing page and every article in the run.
        with article_fetcher() as fetch:
            _check_for_new_articles(fetch)
        return None
    except Exception:
        logging.exception("Run failed")
        return traceback.format_exc()

def _check_for_new_articles(fetch):
    content = fetch(URL)
    articles = extract_content(content)
    articles_to_send = find_new_articles(articles, known_urls())

    if articles_to_send:
        logging.info("Found %d new article(s)", len(articles_to_send))
        checks_by_url = check_articles(articles_to_send, fetch)
        articles_city = [
            a for a in articles_to_send
            if (checks_by_url.get(a["url"]) or EMPTY_CHECK).places
        ]

        # Distinguish "checked, nothing matched" from "could not check", so a
        # blocked run never reads as good news.
        unchecked = sum(1 for value in checks_by_url.values() if value is None)
        if unchecked == len(articles_to_send):
            empty_text = "(could not check — every article fetch failed, see logs)"
        elif unchecked:
            empty_text = f"(none found, but {unchecked} article(s) could not be checked)"
        else:
            empty_text = "(no shows near you this time)"

        email_body = format_articles(
            f"These announcements have a show within {RADIUS_MILES} miles of "
            f"{HOME[0]}, {HOME[1]} (or in your listed cities):",
            articles_city,
            empty_text=empty_text,
            checks_by_url=checks_by_url,
        )
        email_body += "\n" + format_articles(
            "Here are the latest articles:", articles_to_send
        )
        logging.debug(email_body)
        send_email(
            "Metalinjection Tour Page Update Detected",
            email_body
        )

        # Only record articles once the email is actually out. If sending fails,
        # they stay unseen and are retried on the next run rather than lost.
        for article in articles_to_send:
            bands = extract_band_names(article["title"])
            check = checks_by_url.get(article["url"])
            # None here means the check failed, and is stored as "unknown"
            # rather than as "no cities".
            article_id = insert_article(
                article["title"], bands, article["url"],
                check.places if check else None,
            )
            # Dates were already parsed during the check, so storing them
            # costs nothing extra here.
            if article_id and check:
                insert_tour_dates(article_id, bands, check.dates)
    else:
        logging.info("No changes found.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Monitor metalinjection.net for tour announcements.")
    parser.add_argument(
        "--backfill",
        action="store_true",
        help="Parse show dates for articles already stored, then exit.",
    )
    args = parser.parse_args()

    if args.backfill:
        # No email is sent, so a missing password is fine here.
        backfill_tour_dates()
        sys.exit(0)

    # Fail immediately on a misconfigured container rather than after a full
    # scrape cycle 12 hours from now.
    if not EMAIL_PASSWORD:
        sys.exit("EMAIL_PASSWORD is not set; refusing to start.")

    failed_runs = 0
    while True:
        error = monitor_page()
        if error is None:
            if failed_runs >= ALERT_AFTER_FAILED_RUNS:
                logging.info("Run succeeded after %d failed run(s)", failed_runs)
            failed_runs = 0
        else:
            failed_runs += 1
            # Send once per streak: a lasting block would otherwise mean an alert
            # every 12 hours.
            if failed_runs == ALERT_AFTER_FAILED_RUNS:
                send_failure_alert(failed_runs, error)
        # Jitter so repeated restarts don't settle into hitting the site at the
        # same moment every cycle.
        time.sleep(CHECK_INTERVAL + random.randint(0, 1800))