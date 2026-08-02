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
                PRIMARY KEY (article_id, city)
            )
        ''')
        conn.execute("CREATE INDEX IF NOT EXISTS idx_bands_band ON article_bands(band)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_cities_city ON article_cities(city)")
        _backfill_bands(conn, band_extractor)

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

def _link_cities(conn, article_id, cities):
    conn.executemany(
        "INSERT OR IGNORE INTO article_cities (article_id, city) VALUES (?, ?)",
        [(article_id, city) for city in cities if city],
    )

def known_urls():
    """Returns the set of article URLs already recorded, used for deduplication."""
    with _connect() as conn:
        return {row[0] for row in conn.execute("SELECT url FROM tour_articles")}

def insert_article(title, bands, url, cities):
    """Records an article and its bands/cities.

    `cities` is the list of matched cities, or None when the check never ran (the
    city columns then stay NULL rather than claiming a negative result).
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
                None if cities is None else bool(cities),
                datetime.now().isoformat(),
            ))
        except sqlite3.IntegrityError:
            # Duplicate URL — already inserted
            return

        _link_bands(conn, cursor.lastrowid, bands)
        _link_cities(conn, cursor.lastrowid, cities or [])
