import sqlite3
from tabulate import tabulate
import argparse

DB_FILE = "articles/tours.db"

def get_articles(limit=10, city_only=False, band_search=None):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()

    query = "SELECT title, bands, url, city_found, date_scraped FROM tour_articles"
    filters = []
    params = []

    if city_only:
        filters.append("city_found = 1")
    if band_search:
        filters.append("bands LIKE ?")
        params.append(f"%{band_search}%")
    if filters:
        query += " WHERE " + " AND ".join(filters)

    query += " ORDER BY date_scraped DESC LIMIT ?"
    params.append(limit)

    c.execute(query, params)
    rows = c.fetchall()
    conn.close()
    return rows

def main():
    parser = argparse.ArgumentParser(description="Browse Metal Injection tour database.")
    parser.add_argument("--limit", type=int, default=10, help="Limit number of results")
    parser.add_argument("--city", action="store_true", help="Only show articles with matching cities")
    parser.add_argument("--band", type=str, help="Search by band name")

    args = parser.parse_args()
    results = get_articles(limit=args.limit, city_only=args.city, band_search=args.band)

    if results:
        print(tabulate(results, headers=["Title", "Bands", "URL", "City Match", "Scraped", "URL"], tablefmt="grid"))
    else:
        print("No matching articles found.")

if __name__ == "__main__":
    main()
