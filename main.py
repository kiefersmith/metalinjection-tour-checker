import requests
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import time
import os
import logging
import sys
import re
import sqlite3
import random
from datetime import datetime


# Email configuration
EMAIL_ADDRESS = "kieferisgreat@gmail.com"
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD")
TO_EMAIL = "kieferisgreat@gmail.com"
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587

# Monitoring configuration
URL = "https://metalinjection.net/category/tour-dates"
CHECK_INTERVAL = 12*3600  # in seconds; actual sleep adds random jitter up to 30 min

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64; rv:125.0) Gecko/20100101 Firefox/125.0"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
    "DNT": "1",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
}
DB_FILE = "articles/tours.db"

SEARCH_CITIES = ["Raleigh","Greensboro","Charlotte","Jacksonville","Chapel Hill","Hillsborough","Asheville"]

logging.basicConfig(stream=sys.stdout, level=logging.DEBUG)


_session = requests.Session()
_session.headers.update(HEADERS)


def get_page_content(url):
    response = _session.get(url, timeout=30)
    response.raise_for_status()
    return response.text


def get_article_content_playwright(url):
    """Fetch an article page using a headless Firefox browser to bypass Cloudflare."""
    with sync_playwright() as p:
        browser = p.firefox.launch(headless=True)
        page = browser.new_page()
        page.goto(url, wait_until="domcontentloaded", timeout=30000)
        html = page.content()
        browser.close()
    return html

def find_new_articles(all_articles):
    if not all_articles:
        return []
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    urls = [a["url"] for a in all_articles]
    placeholders = ",".join("?" for _ in urls)
    cursor.execute(f"SELECT url FROM tour_articles WHERE url IN ({placeholders})", urls)
    existing_urls = {row[0] for row in cursor.fetchall()}
    conn.close()
    return [a for a in all_articles if a["url"] not in existing_urls]

def extract_content(content):
    content_list = []
    soup = BeautifulSoup(content, "html.parser")
    for article in soup.find_all("article", class_="zox-art-wrap"):
        title_div = article.find("div", class_="zox-art-title")
        if not title_div:
            continue
        a = title_div.find("a")
        heading = title_div.find(re.compile(r"^h[1-6]$"))
        if not a or not heading:
            continue
        content_list.append({"title": heading.get_text(strip=True), "url": a["href"]})
    return content_list

def fetch_article_text(url):
    """Fetch an article page and return (city_found, full_text)."""
    html = get_article_content_playwright(url)
    soup = BeautifulSoup(html, "html.parser").find("div", class_="zox-post-main")
    if not soup:
        return False, ""
    paragraphs = soup.find_all("p")
    full_text = " ".join(p.get_text() for p in paragraphs)
    city_found = any(city in p.text for p in paragraphs for city in SEARCH_CITIES)
    return city_found, full_text


def find_city(content_list):
    article_list = []
    for content in content_list:
        city_found, full_text = fetch_article_text(content["url"])
        content["article_text"] = full_text
        content["city_found"] = city_found
        if city_found:
            article_list.append(content)
        time.sleep(random.uniform(2, 5))
    return article_list

def extract_all_caps_bands(text):
    pattern = r"\b[A-Z0-9][A-Z0-9\s&\-/]{1,}\b"
    matches = re.findall(pattern, text)
    bands = set()

    for m in matches:
        m_clean = m.strip()
        if len(m_clean) < 3:
            continue
        # Reject if it's only digits or mostly digits
        if re.fullmatch(r"[0-9\s\-\/]+", m_clean):
            continue
        # Reject Roman numerals (optional)
        if re.fullmatch(r"[IVXLCDM]+", m_clean) and len(m_clean) < 6:
            continue
        
        split_parts = [part.strip() for part in re.split(r"\s*&\s*", m_clean) if part.strip()]
        bands.update(split_parts)

    return list(bands)

def extract_band_names(title):
    return extract_all_caps_bands(title)

def format_articles(articles):
    email_body = "Here are the latest articles:\n"
    for article in articles:
        email_body += f'- {article["title"]} {article["url"]}\n'

    return email_body

def format_city_articles(articles):
    email_body = "These announcements have a city of interest in them:\n"
    for article in articles:
        email_body += f'- {article["title"]} {article["url"]}\n'

    return email_body

def send_email(subject, body):
    msg = MIMEMultipart()
    msg["From"] = EMAIL_ADDRESS
    msg["To"] = TO_EMAIL
    msg["Subject"] = subject

    msg.attach(MIMEText(body, "plain"))
    with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
        server.starttls()
        server.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
        server.send_message(msg)
    logging.info("sending email")

def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS tour_articles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            bands TEXT NOT NULL,
            url TEXT NOT NULL UNIQUE,
            city_found BOOLEAN,
            date_scraped TEXT
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS tour_dates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            article_id INTEGER NOT NULL,
            band TEXT NOT NULL,
            date TEXT NOT NULL,
            city TEXT NOT NULL,
            state TEXT NOT NULL,
            venue TEXT NOT NULL,
            FOREIGN KEY (article_id) REFERENCES tour_articles(id)
        )
    ''')
    c.execute('CREATE INDEX IF NOT EXISTS idx_tour_dates_band ON tour_dates(band)')
    c.execute('CREATE INDEX IF NOT EXISTS idx_tour_dates_city ON tour_dates(city)')
    c.execute('CREATE INDEX IF NOT EXISTS idx_tour_dates_state ON tour_dates(state)')
    c.execute('CREATE INDEX IF NOT EXISTS idx_tour_dates_date ON tour_dates(date)')
    c.execute('CREATE INDEX IF NOT EXISTS idx_tour_dates_article ON tour_dates(article_id)')
    conn.commit()
    conn.close()

def insert_article(title, bands, url, city_found):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    article_id = None
    try:
        c.execute('''
            INSERT INTO tour_articles (title, bands, url, city_found, date_scraped)
            VALUES (?, ?, ?, ?, ?)
        ''', (title, ", ".join(bands) , url, city_found, datetime.now().isoformat()))
        article_id = c.lastrowid
    except sqlite3.IntegrityError:
        # Duplicate URL — already inserted
        pass
    conn.commit()
    conn.close()
    return article_id


def parse_tour_dates(article_text, year_hint=None):
    """Parse tour dates from article text.

    Articles list dates as concatenated text like:
    3/25 Philadelphia, PA Milkboy3/26 Hamden, CT Cellar on Treadwell

    Returns list of (date_iso, city, state, venue) tuples.
    """
    if not article_text:
        return []

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
        # Parse city and state
        parts = city_state.rsplit(',', 1)
        if len(parts) != 2:
            continue
        city = parts[0].strip()
        state = parts[1].strip()

        # Parse date
        try:
            month, day = date_str.split('/')
            month_int, day_int = int(month), int(day)
            if month_int < 1 or month_int > 12 or day_int < 1 or day_int > 31:
                continue
            date_iso = f"{year_hint}-{month_int:02d}-{day_int:02d}"
        except (ValueError, IndexError):
            continue

        results.append((date_iso, city, state, venue))

    # Deduplicate while preserving order
    seen = set()
    unique = []
    for r in results:
        if r not in seen:
            seen.add(r)
            unique.append(r)
    return unique


def insert_tour_dates(article_id, bands, tour_dates):
    if not article_id or not tour_dates:
        return
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    for band in bands:
        for date_iso, city, state, venue in tour_dates:
            c.execute('''
                INSERT INTO tour_dates (article_id, band, date, city, state, venue)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (article_id, band, date_iso, city, state, venue))
    conn.commit()
    conn.close()


def monitor_page():
    try:
        content = get_page_content(URL)
        new_articles = extract_content(content)
        articles_to_send = find_new_articles(new_articles)
        articles_city = find_city(articles_to_send)

        if articles_to_send:
            logging.info("Found articles to send")

            # Save to DB
            for article in articles_to_send:
                city_match = article.get("city_found", article in articles_city)
                bands = extract_band_names(article["title"])
                article_id = insert_article(article["title"], bands, article["url"], city_match)
                # Parse and store individual tour dates
                article_text = article.get("article_text", "")
                if article_text and article_id:
                    tour_dates = parse_tour_dates(article_text)
                    insert_tour_dates(article_id, bands, tour_dates)

            email_body = format_city_articles(articles_city)
            email_body += "\n" + format_articles(articles_to_send)
            logging.debug(email_body)
            send_email(
                "Metalinjection Tour Page Update Detected",
                email_body
            )
        else:
            logging.info("No changes found.")

    except Exception as e:
        logging.error(f"Error: {e}")

def backfill_tour_dates():
    """Re-fetch all existing articles and parse their tour dates."""
    init_db()
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("""
        SELECT ta.id, ta.title, ta.url FROM tour_articles ta
        WHERE ta.id NOT IN (SELECT DISTINCT article_id FROM tour_dates)
    """)
    articles = c.fetchall()
    conn.close()

    logging.info(f"Backfilling tour dates for {len(articles)} articles")
    for article_id, title, url in articles:
        try:
            _, article_text = fetch_article_text(url)
            if article_text:
                bands = extract_band_names(title)
                tour_dates = parse_tour_dates(article_text)
                if tour_dates:
                    insert_tour_dates(article_id, bands, tour_dates)
                    logging.info(f"Backfilled {len(tour_dates)} dates for: {title}")
                else:
                    logging.info(f"No tour dates found for: {title}")
        except Exception as e:
            logging.error(f"Error backfilling {url}: {e}")


if __name__ == "__main__":
    import argparse as _argparse
    parser = _argparse.ArgumentParser()
    parser.add_argument("--backfill", action="store_true", help="Backfill tour dates for existing articles")
    args = parser.parse_args()

    if args.backfill:
        backfill_tour_dates()
    else:
        init_db()
        while True:
            monitor_page()
            jitter = random.randint(0, 1800)  # up to 30 min extra
            time.sleep(CHECK_INTERVAL + jitter)
git pull --rebase origin main