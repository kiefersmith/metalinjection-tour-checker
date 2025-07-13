import sqlite3
from datetime import datetime

DB_FILE = "articles/tours.db"

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
    conn.commit()
    conn.close()

def insert_article(title, bands, url, city_found):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    try:
        c.execute('''
            INSERT INTO tour_articles (title, bands, url, city_found, date_scraped)
            VALUES (?, ?, ?, ?, ?)
        ''', (title, ", ".join(bands) , url, city_found, datetime.now().isoformat()))
    except sqlite3.IntegrityError:
        # Duplicate URL — already inserted
        pass
    conn.commit()
    conn.close()
