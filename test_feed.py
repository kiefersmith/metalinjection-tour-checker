"""RSS listing parsing: titles, links, and where band names come from.

Run with: python test_feed.py
"""
import logging
import sys

logging.disable(logging.CRITICAL)

from main import extract_content

FEED = b"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:mi="https://metalinjection.net/rss/klaviyo">
<channel>
  <title>Tour Dates Archives - Metal Injection</title>
  <item>
    <title>Dying Fetus, Cryptopsy, and Gorgasm Announce North American Tour</title>
    <link>https://metalinjection.net/tour-dates/dying-fetus-tour</link>
    <mi:artists>Dying Fetus, Cryptopsy</mi:artists>
  </item>
  <item>
    <title>We Are Very Jealous of Faith No More&#039;s South America Shows</title>
    <link>https://metalinjection.net/tour-dates/fnm</link>
    <mi:artists>Faith No More</mi:artists>
  </item>
  <item>
    <title>MASTODON Announce Tour With GOJIRA</title>
    <link>https://metalinjection.net/tour-dates/mastodon</link>
    <mi:artists></mi:artists>
  </item>
  <item>
    <title>No link, so skipped</title>
  </item>
</channel>
</rss>"""

failures = []

articles = extract_content(FEED)
expected = [
    {"title": "Dying Fetus, Cryptopsy, and Gorgasm Announce North American Tour",
     "url": "https://metalinjection.net/tour-dates/dying-fetus-tour",
     "bands": ["Dying Fetus", "Cryptopsy"]},
    {"title": "We Are Very Jealous of Faith No More's South America Shows",
     "url": "https://metalinjection.net/tour-dates/fnm",
     "bands": ["Faith No More"]},
    # Empty <mi:artists> falls back to the all-caps title regex.
    {"title": "MASTODON Announce Tour With GOJIRA",
     "url": "https://metalinjection.net/tour-dates/mastodon",
     "bands": ["GOJIRA", "MASTODON"]},
]
if articles != expected:
    failures.append(f"extract_content:\n  got      {articles}\n  expected {expected}")

# An HTML error page instead of a feed must fail loudly, not read as "no articles".
for bad in (b"<html><body>Just a moment...</body></html>", b"not xml"):
    try:
        extract_content(bad)
        failures.append(f"no error raised for {bad!r}")
    except Exception:
        pass

if failures:
    print("\n".join(failures))
    sys.exit(1)
print("All feed tests passed.")
