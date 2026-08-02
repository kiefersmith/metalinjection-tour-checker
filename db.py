import sqlite3
from contextlib import closing
from datetime import datetime

DB_FILE = "articles/tours.db"

def _connect():
    # `with conn` commits the transaction but does not close the handle,
    # so callers pair it with closing().
    return closing(sqlite3.connect(DB_FILE))

def init_db(band_extractor=None):
    """Creates the schema and backfills the band links.

    `band_extractor` is an optional title -> [band] callable. It's passed in rather
    than imported so this module stays free of scraping code; when supplied it's
    used to re-derive bands for older rows, whose stored `bands` column was written
    by an earlier, worse parser.
    """
    with _connect() as conn, conn:
        conn.execute('''
            CREATE TABLE IF NOT EXISTS tour_articles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                bands TEXT NOT NULL,
                url TEXT NOT NULL UNIQUE,
                city_found BOOLEAN,
                date_scraped TEXT
            )
        ''')
        # One row per (article, band) so searches match a whole band name instead
        # of a substring of the comma-joined list.
        conn.execute('''
            CREATE TABLE IF NOT EXISTS article_bands (
                article_id INTEGER NOT NULL REFERENCES tour_articles(id),
                band TEXT NOT NULL,
                PRIMARY KEY (article_id, band)
            )
        ''')
        # Which cities matched, not just whether any did.
        conn.execute('''
            CREATE TABLE IF NOT EXISTS article_cities (
                article_id INTEGER NOT NULL REFERENCES tour_articles(id),
                city TEXT NOT NULL,
                state TEXT NOT NULL DEFAULT '',
                PRIMARY KEY (article_id, city, state)
            )
        ''')
        # Individual show dates parsed out of the article body: the only table
        # here that answers "when is BAND playing CITY".
        conn.execute('''
            CREATE TABLE IF NOT EXISTS tour_dates (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                article_id INTEGER NOT NULL REFERENCES tour_articles(id),
                band TEXT NOT NULL,
                date TEXT NOT NULL,
                city TEXT NOT NULL,
                state TEXT NOT NULL,
                venue TEXT NOT NULL
            )
        ''')
        conn.execute("CREATE INDEX IF NOT EXISTS idx_bands_band ON article_bands(band)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_cities_city ON article_cities(city)")
        for column in ("band", "city", "state", "date", "article_id"):
            conn.execute(
                f"CREATE INDEX IF NOT EXISTS idx_tour_dates_{column} ON tour_dates({column})"
            )
        _backfill_bands(conn, band_extractor)

def insert_tour_dates(article_id, bands, tour_dates):
    """Records one row per (band, show date) for an article."""
    if not article_id or not tour_dates:
        return
    rows = [
        (article_id, band, date_iso, city, state, venue)
        for band in bands
        for date_iso, city, state, venue in tour_dates
    ]
    with _connect() as conn, conn:
        conn.executemany('''
            INSERT INTO tour_dates (article_id, band, date, city, state, venue)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', rows)

def articles_without_tour_dates():
    """Returns (id, title, url) for articles that have no show dates recorded."""
    with _connect() as conn, conn:
        return conn.execute('''
            SELECT id, title, url FROM tour_articles
            WHERE id NOT IN (SELECT DISTINCT article_id FROM tour_dates)
            ORDER BY id
        ''').fetchall()

def _backfill_bands(conn, band_extractor=None):
    """Populates article_bands for rows written before the table existed.

    Idempotent: only articles with no rows yet are touched. Falls back to splitting
    the stored `bands` column when no extractor is available.
    """
    rows = conn.execute('''
        SELECT id, title, bands FROM tour_articles
        WHERE id NOT IN (SELECT article_id FROM article_bands)
    ''').fetchall()
    for article_id, title, bands in rows:
        if band_extractor:
            names = band_extractor(title)
            # Keep the display column consistent with what we just derived.
            conn.execute(
                "UPDATE tour_articles SET bands = ? WHERE id = ?",
                (", ".join(names), article_id),
            )
        else:
            names = [b.strip() for b in (bands or "").split(",")]
        _link_bands(conn, article_id, names)

def _link_bands(conn, article_id, bands):
    conn.executemany(
        "INSERT OR IGNORE INTO article_bands (article_id, band) VALUES (?, ?)",
        [(article_id, band) for band in bands if band],
    )

def _link_cities(conn, article_id, places):
    """`places` is a list of (city, state) pairs. The state is what makes
    Jacksonville NC distinguishable from Jacksonville FL when querying later."""
    conn.executemany(
        "INSERT OR IGNORE INTO article_cities (article_id, city, state) VALUES (?, ?, ?)",
        [(article_id, city, state) for city, state in places if city],
    )

def known_urls():
    """Returns the set of article URLs already recorded, used for deduplication."""
    with _connect() as conn:
        return {row[0] for row in conn.execute("SELECT url FROM tour_articles")}

def insert_article(title, bands, url, places):
    """Records an article, its bands, and the nearby places it mentions.

    `places` is a list of (city, state) pairs, or None when the check never ran
    (city_found then stays NULL rather than claiming a negative result).
    """
    with _connect() as conn, conn:
        try:
            cursor = conn.execute('''
                INSERT INTO tour_articles (title, bands, url, city_found, date_scraped)
                VALUES (?, ?, ?, ?, ?)
            ''', (
                title,
                ", ".join(bands),
                url,
                None if places is None else bool(places),
                datetime.now().isoformat(),
            ))
        except sqlite3.IntegrityError:
            # Duplicate URL — already inserted
            return None

        _link_bands(conn, cursor.lastrowid, bands)
        _link_cities(conn, cursor.lastrowid, places or [])
        # Returned so the caller can attach show dates to this article.
        return cursor.lastrowid
