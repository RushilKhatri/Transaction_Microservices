# ── Transaction Service Dockerfile ────────────────────────────────────────────
# python:3.12-slim keeps the image small; gunicorn replaces the dev server.

FROM python:3.12-slim

# System deps needed by psycopg2 (libpq)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev gcc \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies first (layer-cache friendly)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source
COPY . .

# Expose Flask port
EXPOSE 5001

# Gunicorn: 2 workers, bind to 0.0.0.0:5001
# run:app → file run.py exposes the Flask `app` object
CMD ["gunicorn", "--workers=2", "--bind=0.0.0.0:5001", "--timeout=60", "run:app"]
