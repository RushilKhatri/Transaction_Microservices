"""
config.py — Transaction Service
Secret management: Vault-first, env-var fallback.
All secrets are fetched via get_secret() so no credentials ever appear in code.
"""

import os
import logging

logger = logging.getLogger(__name__)


def get_secret(key: str) -> str:
    """
    Dual-mode secret resolver:
      1. If VAULT_ADDR is set  → fetch from HashiCorp Vault at
         secret/data/banking/transaction-service
      2. Otherwise              → read from OS environment variable named <key>

    This lets the service run locally with plain env vars and in production
    with Vault, with zero code changes.
    """
    vault_addr = os.environ.get("VAULT_ADDR")
    if vault_addr:
        try:
            import hvac  # noqa: PLC0415
            vault_token = os.environ.get("VAULT_TOKEN", "")
            client = hvac.Client(url=vault_addr, token=vault_token)
            secret_response = client.secrets.kv.v2.read_secret_version(
                path="banking/transaction-service",
                mount_point="secret",
            )
            data = secret_response["data"]["data"]
            if key in data:
                return data[key]
        except Exception as exc:  # pylint: disable=broad-except
            logger.warning(
                "Vault lookup failed for key '%s', falling back to env var. Error: %s",
                key,
                exc,
            )
    return os.environ.get(key, "")


class Config:
    """Base configuration assembled entirely from get_secret() calls."""

    # ── Database ──────────────────────────────────────────────────────────────
    # Individual components so K8s can inject each as a separate Secret/ConfigMap
    _DB_HOST = get_secret("DB_HOST") or "postgres"          # Docker Compose service name
    _DB_PORT = get_secret("DB_PORT") or "5432"
    _DB_NAME = get_secret("DB_NAME") or "banking"
    _DB_USER = get_secret("DB_USER") or "banking_user"
    _DB_PASS = get_secret("DB_PASSWORD") or ""

    SQLALCHEMY_DATABASE_URI = (
        f"postgresql+psycopg2://{_DB_USER}:{_DB_PASS}"
        f"@{_DB_HOST}:{_DB_PORT}/{_DB_NAME}"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # ── JWT ───────────────────────────────────────────────────────────────────
    JWT_SECRET_KEY = get_secret("JWT_SECRET_KEY") or "change-me-in-vault"
    JWT_ACCESS_TOKEN_EXPIRES = False  # tokens don't expire in dev; set via env in prod

    # ── Service-to-service URLs (defaults = Docker Compose / K8s service names) ──
    FRAUD_SERVICE_URL = os.environ.get(
        "FRAUD_SERVICE_URL", "http://fraud-detection-service:5002"
    )

    # ── Internal service-to-service auth ────────────────────────────────────
    TRUSTED_INTERNAL_SERVICES = os.environ.get(
        "TRUSTED_INTERNAL_SERVICES", "fraud-detection-service"
    )
    INTERNAL_REQUIRED_SCOPE = os.environ.get("INTERNAL_REQUIRED_SCOPE", "internal_history_read")

    # ── Application ───────────────────────────────────────────────────────────
    DEBUG = os.environ.get("FLASK_DEBUG", "false").lower() == "true"
    TESTING = False


class TestingConfig(Config):
    """Config overrides used by the pytest suite — no real DB or Vault needed."""

    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    JWT_SECRET_KEY = "test-secret-key"
    FRAUD_SERVICE_URL = "http://fraud-detection-service:5002"
    TRUSTED_INTERNAL_SERVICES = "fraud-detection-service"
    INTERNAL_REQUIRED_SCOPE = "internal_history_read"
