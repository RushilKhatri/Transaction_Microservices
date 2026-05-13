# ── Fraud Detection Service Dockerfile ───────────────────────────────────────
# Stateless service — no DB, no libpq needed.

FROM python:3.12-slim

WORKDIR /app

ENV PORT=5002
ENV PROMETHEUS_MULTIPROC_DIR=/tmp/prometheus-metrics

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 5002

CMD ["gunicorn", "--config=gunicorn.conf.py", "run:app"]
