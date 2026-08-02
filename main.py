import requests
from bs4 import BeautifulSoup
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import time
import json
import os
import logging
import sys
import re

from db import init_db, insert_article, known_urls

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
LEGACY_CONTENT_FILE = "articles/previous_articles.json"
SEARCH_CITIES = ["Raleigh","Greensboro","Charlotte","Jacksonville","Chapel Hill","Hillsborough","Asheville"]

logging.basicConfig(stream=sys.stdout, level=logging.DEBUG)

# Matches a city only as a whole word, so "Charlotte" doesn't hit "Charlottesville".
CITY_PATTERN = re.compile(
    r"\b(" + "|".join(re.escape(city) for city in SEARCH_CITIES) + r")\b",
    re.IGNORECASE,
)


def get_page_content(url):
    response = requests.get(
        url,
        timeout=REQUEST_TIMEOUT,
        headers={"User-Agent": "metal-tour-check (personal tour-date notifier)"},
    )
    response.raise_for_status()
    return response.text

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

def cities_in_article(url):
    """Returns the cities of interest named in the article body, in SEARCH_CITIES order."""
    body = BeautifulSoup(get_page_content(url), "html.parser").find("div", class_="zox-post-main")
    if body is None:
        # Not a standard post layout (video embed, redirect, ...); nothing to match on.
        logging.warning("No article body found at %s", url)
        return []

    text = body.get_text(" ", strip=True)
    found = {match.group(1).lower() for match in CITY_PATTERN.finditer(text)}
    return [city for city in SEARCH_CITIES if city.lower() in found]

def find_cities(content_list):
    """Maps each article URL to the cities of interest it mentions.

    A single unreachable or oddly-shaped article must not abort the whole run, so
    failures here are logged and the article is mapped to None — "not checked",
    which is deliberately different from [] ("checked, no cities"). Widespread
    failure is a different problem — usually rate limiting — and is called out
    loudly, because otherwise it is indistinguishable from "no cities mentioned".
    """
    cities_by_url = {article["url"]: None for article in content_list}
    failures = 0
    consecutive = 0
    checked = 0

    for index, content in enumerate(content_list):
        if consecutive >= FAILURE_CUTOFF:
            # Article pages are blocked wholesale (Cloudflare serves 403 to
            # non-browser clients on a cache miss). Grinding through the rest just
            # burns FETCH_DELAY per article for no result.
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
            cities_by_url[content["url"]] = cities_in_article(content["url"])
            consecutive = 0
        except Exception:
            failures += 1
            consecutive += 1
            logging.exception("Could not check cities for %s", content["url"])

    if failures and failures == checked:
        logging.error(
            "Every city check failed (%d/%d) — assume the site is blocking us or has "
            "changed, NOT that no cities were mentioned",
            failures, checked,
        )
    elif failures:
        logging.warning("%d of %d city checks failed", failures, checked)

    return cities_by_url

# All-caps words that show up in headlines but are never band names on their own.
NON_BAND_TOKENS = {
    "US", "USA", "UK", "EU", "NYC", "LA", "TV", "EP", "LP", "CD", "DVD", "VIP",
    "AND", "OR", "VS", "OF", "IN", "ON", "AT", "TO", "FOR", "WITH", "AN",
    "NEW", "LIVE", "TOUR", "TOURS", "SHOW", "SHOWS", "DATES", "VIDEO", "WATCH",
    "FT", "FEAT", "DJ", "RIP", "PSA", "WTF", "OMG", "NSFW", "MORE",
}

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
    """True for an all-caps word long enough to plausibly be part of a band name."""
    core = token.strip("-/.'")
    if len(core) < 2 or core != core.upper():
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
    # names like 'ILL NIÑO' survive.
    for segment in re.split(r"[,;:()\[\]|\"“”…]+", title):
        run = []
        for token in segment.split():
            # A digits-only token continues a run ('POWERMAN 5000') but can't start one.
            if _is_caps_token(token) or token == "&" or (run and not any(c.isalpha() for c in token)):
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
    if not run or (len(run) == 1 and _normalize(run[0]) == "THE"):
        return []

    text = " ".join(run)
    # Reject pure numbers and short Roman numerals ('III', '2026').
    if not any(ch.isalpha() for ch in text):
        return []
    if re.fullmatch(r"[IVXLCDM]+", text):
        return []

    return [part for part in _split_on_ampersand(text) if part]

def format_articles(heading, articles, empty_text=None, cities_by_url=None):
    lines = [heading]
    if articles:
        for article in articles:
            cities = (cities_by_url or {}).get(article["url"])
            suffix = f' [{", ".join(cities)}]' if cities else ""
            lines.append(f'- {article["title"]}{suffix} {article["url"]}')
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

def monitor_page():
    try:
        init_db(band_extractor=extract_band_names)
        migrate_legacy_articles()

        content = get_page_content(URL)
        articles = extract_content(content)
        articles_to_send = find_new_articles(articles, known_urls())

        if articles_to_send:
            logging.info("Found %d new article(s)", len(articles_to_send))
            cities_by_url = find_cities(articles_to_send)
            articles_city = [a for a in articles_to_send if cities_by_url.get(a["url"])]

            # Distinguish "checked, nothing matched" from "could not check", so a
            # blocked run never reads as good news.
            unchecked = sum(1 for value in cities_by_url.values() if value is None)
            if unchecked == len(articles_to_send):
                empty_text = "(could not check — every article fetch failed, see logs)"
            elif unchecked:
                empty_text = f"(none found, but {unchecked} article(s) could not be checked)"
            else:
                empty_text = "(no nearby cities mentioned this time)"

            email_body = format_articles(
                "These announcements have a city of interest in them:",
                articles_city,
                empty_text=empty_text,
                cities_by_url=cities_by_url,
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
                # None here means the check failed, and is stored as "unknown"
                # rather than as "no cities".
                insert_article(
                    article["title"], bands, article["url"], cities_by_url.get(article["url"])
                )
        else:
            logging.info("No changes found.")

    except Exception:
        logging.exception("Run failed")

if __name__ == "__main__":
    # Fail immediately on a misconfigured container rather than after a full
    # scrape cycle 12 hours from now.
    if not EMAIL_PASSWORD:
        sys.exit("EMAIL_PASSWORD is not set; refusing to start.")

    while True:
        monitor_page()
        time.sleep(CHECK_INTERVAL)