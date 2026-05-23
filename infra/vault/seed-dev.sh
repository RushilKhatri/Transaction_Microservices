#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
ENV_FILE="$ROOT_DIR/.env.docker"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "Missing $ENV_FILE"
  exit 1
fi

set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a

# Accept container name as first argument, default to banking-vault for local/non-smoke tests
CONTAINER_NAME="${1:-banking-vault}"

echo "Waiting for Vault dev server..."
until docker exec "$CONTAINER_NAME" sh -lc 'export VAULT_ADDR=http://127.0.0.1:8200 VAULT_TOKEN=root; vault status >/dev/null 2>&1'; do
  sleep 1
done

echo "Seeding Vault KV secrets..."

docker exec "$CONTAINER_NAME" sh -lc "
  export VAULT_ADDR=http://127.0.0.1:8200 VAULT_TOKEN=root
  vault secrets enable -path=secret kv-v2 >/dev/null 2>&1 || true

  vault kv put secret/banking/transaction-service \
    DB_HOST='${DB_HOST}' \
    DB_PORT='${DB_PORT}' \
    DB_NAME='${DB_NAME}' \
    DB_USER='${DB_USER}' \
    DB_PASSWORD='${DB_PASSWORD}' \
    JWT_SECRET_KEY='${JWT_SECRET_KEY}'

  vault kv put secret/banking/fraud-detection-service \
    JWT_SECRET_KEY='${JWT_SECRET_KEY}'

  vault kv put secret/banking/notification-service \
    DB_HOST='${DB_HOST}' \
    DB_PORT='${DB_PORT}' \
    DB_NAME='${DB_NAME}' \
    DB_USER='${DB_USER}' \
    DB_PASSWORD='${DB_PASSWORD}' \
    JWT_SECRET_KEY='${JWT_SECRET_KEY}' \
    SMTP_HOST='smtp.example.local' \
    SMTP_PORT='587' \
    SMTP_USER='demo-smtp-user' \
    SMTP_PASSWORD='demo-smtp-pass' \
    ALERT_EMAIL_TO='security@example.local'
"

echo "Vault secrets seeded successfully."
