import sqlite3
from contextlib import closing
from tabulate import tabulate
import argparse

DB_FILE = "articles/tours.db"

# Sentinel for "--city" with no value: any city, rather than a named one.
ANY_CITY = object()

def _connect():
    return closing(sqlite3.connect(DB_FILE))

def get_articles(limit=10, city=None, band=None):
    """Articles, newest first, optionally filtered by city and/or exact band name."""
    query = '''
        SELECT a.title,
               a.bands,
               COALESCE(
                   (SELECT GROUP_CONCAT(c.city, ', ') FROM article_cities c
                     WHERE c.article_id = a.id),
                   CASE WHEN a.city_found = 1 THEN '(unrecorded)' ELSE '' END
               ) AS cities,
               a.date_scraped,
               a.url
          FROM tour_articles a
    '''
    filters = []
    params = []

    if city is ANY_CITY:
        filters.append("a.city_found = 1")
    elif city:
        # Exact city name, case-insensitive.
        filters.append(
            "EXISTS (SELECT 1 FROM article_cities c"
            "         WHERE c.article_id = a.id AND c.city = ? COLLATE NOCASE)"
        )
        params.append(city)
    if band:
        # Whole band name, not a substring of the joined list: searching DEATH
        # must not return UNDEATH.
        filters.append(
            "EXISTS (SELECT 1 FROM article_bands b"
            "         WHERE b.article_id = a.id AND b.band = ? COLLATE NOCASE)"
        )
        params.append(band)
    if filters:
        query += " WHERE " + " AND ".join(filters)

    query += " ORDER BY a.date_scraped DESC LIMIT ?"
    params.append(limit)

    with _connect() as conn:
        return conn.execute(query, params).fetchall()

def get_bands(limit=None):
    """Every known band with how many articles mention it."""
    query = '''
        SELECT b.band, COUNT(*) AS mentions, MAX(a.date_scraped) AS latest
          FROM article_bands b JOIN tour_articles a ON a.id = b.article_id
         GROUP BY b.band COLLATE NOCASE
         ORDER BY mentions DESC, b.band
    '''
    params = []
    if limit:
        query += " LIMIT ?"
        params.append(limit)
    with _connect() as conn:
        return conn.execute(query, params).fetchall()

def get_cities():
    """Every matched city with how many articles mention it."""
    with _connect() as conn:
        return conn.execute('''
            SELECT c.city, COUNT(*) AS mentions, MAX(a.date_scraped) AS latest
              FROM article_cities c JOIN tour_articles a ON a.id = c.article_id
             GROUP BY c.city COLLATE NOCASE
             ORDER BY mentions DESC, c.city
        ''').fetchall()

def main():
    parser = argparse.ArgumentParser(description="Browse Metal Injection tour database.")
    parser.add_argument("--limit", type=int, default=10, help="Limit number of results")
    parser.add_argument(
        "--city", nargs="?", const=ANY_CITY, default=None, metavar="NAME",
        help="Only articles mentioning NAME, or any city of interest if given no value",
    )
    parser.add_argument("--band", type=str, help="Search by exact band name")
    parser.add_argument("--list-bands", action="store_true", help="List known bands by mention count")
    parser.add_argument("--list-cities", action="store_true", help="List matched cities by mention count")

    args = parser.parse_args()

    if args.list_bands:
        rows = get_bands(limit=args.limit)
        _show(rows, ["Band", "Articles", "Last seen"], "No bands recorded yet.")
        return
    if args.list_cities:
        rows = get_cities()
        _show(rows, ["City", "Articles", "Last seen"], "No cities recorded yet.")
        return

    rows = get_articles(limit=args.limit, city=args.city, band=args.band)
    _show(rows, ["Title", "Bands", "Cities", "Scraped", "URL"], "No matching articles found.")

def _show(rows, headers, empty_message):
    if rows:
        print(tabulate(rows, headers=headers, tablefmt="grid"))
    else:
        print(empty_message)

if __name__ == "__main__":
    main()
