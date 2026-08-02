import sqlite3
from flask import Flask, request, render_template_string

app = Flask(__name__)
DB_FILE = "articles/tours.db"

TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Metal Tour Search</title>
    <style>
        * { box-sizing: border-box; }
        body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; margin: 0; padding: 20px; background: #1a1a2e; color: #eee; }
        h1 { color: #e94560; margin-bottom: 20px; }
        form { background: #16213e; padding: 20px; border-radius: 8px; margin-bottom: 20px; display: flex; flex-wrap: wrap; gap: 15px; align-items: end; }
        .field { display: flex; flex-direction: column; }
        .field label { font-size: 0.85em; margin-bottom: 4px; color: #aaa; }
        .field input { padding: 8px 12px; border: 1px solid #333; border-radius: 4px; background: #0f3460; color: #eee; font-size: 0.95em; }
        button { padding: 8px 20px; background: #e94560; color: white; border: none; border-radius: 4px; cursor: pointer; font-size: 0.95em; }
        button:hover { background: #c73650; }
        table { width: 100%; border-collapse: collapse; background: #16213e; border-radius: 8px; overflow: hidden; }
        th { background: #0f3460; padding: 12px; text-align: left; font-size: 0.85em; text-transform: uppercase; color: #aaa; }
        td { padding: 10px 12px; border-top: 1px solid #1a1a2e; }
        tr:hover { background: #1a2744; }
        a { color: #53a8f5; text-decoration: none; }
        a:hover { text-decoration: underline; }
        .empty { text-align: center; padding: 40px; color: #666; }
        .count { color: #888; margin-bottom: 10px; font-size: 0.9em; }
    </style>
</head>
<body>
    <h1>Metal Tour Search</h1>
    <form method="get" action="/">
        <div class="field">
            <label>Band</label>
            <input type="text" name="band" value="{{ band }}" placeholder="e.g. MASTODON">
        </div>
        <div class="field">
            <label>City</label>
            <input type="text" name="city" value="{{ city }}" placeholder="e.g. Raleigh">
        </div>
        <div class="field">
            <label>State</label>
            <input type="text" name="state" value="{{ state }}" placeholder="e.g. NC" maxlength="2">
        </div>
        <div class="field">
            <label>From Date</label>
            <input type="date" name="date_from" value="{{ date_from }}">
        </div>
        <div class="field">
            <label>To Date</label>
            <input type="date" name="date_to" value="{{ date_to }}">
        </div>
        <button type="submit">Search</button>
    </form>

    {% if results is not none %}
    <div class="count">{{ results|length }} result{{ "s" if results|length != 1 }} found</div>
    {% if results %}
    <table>
        <thead>
            <tr>
                <th>Date</th>
                <th>Band</th>
                <th>City</th>
                <th>State</th>
                <th>Venue</th>
                <th>Article</th>
            </tr>
        </thead>
        <tbody>
            {% for row in results %}
            <tr>
                <td>{{ row.date }}</td>
                <td>{{ row.band }}</td>
                <td>{{ row.city }}</td>
                <td>{{ row.state }}</td>
                <td>{{ row.venue }}</td>
                <td><a href="{{ row.url }}" target="_blank">{{ row.title[:60] }}{% if row.title|length > 60 %}...{% endif %}</a></td>
            </tr>
            {% endfor %}
        </tbody>
    </table>
    {% else %}
    <div class="empty">No tour dates found matching your search.</div>
    {% endif %}
    {% endif %}
</body>
</html>
"""


def search_tour_dates(band=None, city=None, state=None, date_from=None, date_to=None):
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    query = """
        SELECT td.date, td.band, td.city, td.state, td.venue, ta.title, ta.url
        FROM tour_dates td
        JOIN tour_articles ta ON td.article_id = ta.id
    """
    filters = []
    params = []

    if band:
        filters.append("td.band LIKE ?")
        params.append(f"%{band}%")
    if city:
        filters.append("td.city LIKE ?")
        params.append(f"%{city}%")
    if state:
        filters.append("td.state = ?")
        params.append(state.upper())
    if date_from:
        filters.append("td.date >= ?")
        params.append(date_from)
    if date_to:
        filters.append("td.date <= ?")
        params.append(date_to)

    if filters:
        query += " WHERE " + " AND ".join(filters)

    query += " ORDER BY td.date ASC LIMIT 500"

    c.execute(query, params)
    rows = c.fetchall()
    conn.close()
    return rows


@app.route("/")
def index():
    band = request.args.get("band", "").strip()
    city = request.args.get("city", "").strip()
    state = request.args.get("state", "").strip()
    date_from = request.args.get("date_from", "").strip()
    date_to = request.args.get("date_to", "").strip()

    has_search = any([band, city, state, date_from, date_to])
    results = search_tour_dates(band or None, city or None, state or None, date_from or None, date_to or None) if has_search else None

    return render_template_string(TEMPLATE,
        band=band, city=city, state=state, date_from=date_from, date_to=date_to,
        results=results)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
