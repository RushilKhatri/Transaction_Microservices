# ── Transaction Service Dockerfile ────────────────────────────────────────────
# python:3.12-slim keeps the image small; gunicorn replaces the dev server.

FROM python:3.12-slim

# System deps needed by psycopg2 (libpq)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev gcc \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

ENV PORT=5001
ENV PROMETHEUS_MULTIPROC_DIR=/tmp/prometheus-metrics

# Install Python dependencies first (layer-cache friendly)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source
COPY . .

# Expose Flask port
EXPOSE 5001

# Gunicorn: 2 workers by default, configured in gunicorn.conf.py
# run:app → file run.py exposes the Flask `app` object
CMD ["gunicorn", "--config=gunicorn.conf.py", "run:app"]
