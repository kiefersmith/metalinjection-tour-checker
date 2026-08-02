# Debian, not Alpine: Playwright's browser builds are glibc-only.
FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

# Pulls the system libraries Firefox needs, then the browser itself. Kept above
# the source COPY so a code change doesn't re-download the browser.
RUN python -m playwright install-deps firefox && \
    python -m playwright install firefox

COPY *.py .

# Overwritten by the mounted volume at runtime; present so local runs work too.
RUN mkdir articles

CMD [ "python", "main.py" ]
