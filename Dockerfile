# The app's image: Python's slim image with the runtime requirements only (no pytest, no Node), one process.
# Python 3.15.2 is the current patch release (2026-11-16); move the tag forward with each patch release.
FROM python:3.15.2-slim

# Production settings as real environment variables, which win over .env (not copied: see .dockerignore).
# Listen on every interface, keep the data on the volume, and trust X-Forwarded-For/-Proto from the proxy in
# front of the container (narrow FORWARDED_ALLOW_IPS to its address in your own production).
ENV APP_HOST=0.0.0.0 APP_PORT=8000 DATA_DIR=/app/storage FORWARDED_ALLOW_IPS=* \
    PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY . .

# Not root: the app only writes to /app/storage (the database, uploads, visitor sandboxes, relay snapshots)
RUN useradd --system --uid 10001 --home-dir /app --shell /usr/sbin/nologin app \
    && mkdir -p /app/storage && chown app:app /app/storage
USER app

EXPOSE 8000
# One uvicorn process: the relay rooms, the countries cache and the demo's AI counter live in its memory.
# It creates and seeds the database on start. serve.py refuses a busy port and logs to stderr.
CMD ["python", "serve.py"]
