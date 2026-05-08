# ── Fraud Detection Service Dockerfile ───────────────────────────────────────
# Stateless service — no DB, no libpq needed.

FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 5002

CMD ["gunicorn", "--workers=2", "--bind=0.0.0.0:5002", "--timeout=60", "run:app"]
