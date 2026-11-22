# Debian, not Alpine: Playwright's browser builds are glibc-only.
FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .

# geonamescache ships four city datasets (~180 MB); geo.py's GeonamesCache()
# defaults to the 15000-population one, so the other ~165 MB is never read.
RUN pip install --no-cache-dir -r requirements.txt && \
    find /usr/local/lib/python3.12/site-packages/geonamescache/data \
      -name 'cities*.json' ! -name 'cities15000.json' -delete

# Pulls the system libraries Firefox needs, then the browser itself. Kept above
# the source COPY so a code change doesn't re-download the browser.
# libatomic1 first: newer Playwright releases bundle a Node driver that needs it
# just to run, and install-deps can't install anything until that driver starts.
RUN apt-get update && apt-get install -y --no-install-recommends libatomic1 && \
    rm -rf /var/lib/apt/lists/* && \
    python -m playwright install-deps firefox && \
    python -m playwright install firefox

COPY *.py .
COPY start.sh .

# Overwritten by the mounted volume at runtime; present so local runs work too.
RUN mkdir articles

# start.sh runs the scraper loop and the web UI side by side.
EXPOSE 5000

CMD [ "sh", "start.sh" ]
