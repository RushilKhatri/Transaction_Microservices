# ── Notification Service Dockerfile ──────────────────────────────────────────

FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev gcc \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

ENV PORT=5003
ENV PROMETHEUS_MULTIPROC_DIR=/tmp/prometheus-metrics

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 5003

CMD ["gunicorn", "--config=gunicorn.conf.py", "run:app"]
