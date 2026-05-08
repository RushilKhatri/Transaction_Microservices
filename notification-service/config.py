"""
config.py — Notification Service
Secret management: Vault-first, env-var fallback.
SMTP credentials are fetched via get_secret() — never hardcoded.
"""

import os
import logging

logger = logging.getLogger(__name__)


def get_secret(key: str) -> str:
    """
    Dual-mode secret resolver:
      1. If VAULT_ADDR is set  → fetch from HashiCorp Vault at
         secret/data/banking/notification-service
      2. Otherwise              → read from OS environment variable named <key>
    """
    vault_addr = os.environ.get("VAULT_ADDR")
    if vault_addr:
        try:
            import hvac  # noqa: PLC0415
            vault_token = os.environ.get("VAULT_TOKEN", "")
            client = hvac.Client(url=vault_addr, token=vault_token)
            secret_response = client.secrets.kv.v2.read_secret_version(
                path="banking/notification-service",
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
    _DB_HOST = get_secret("DB_HOST") or "postgres"
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

    # ── SMTP (fetched via get_secret, not hardcoded) ───────────────────────────
    SMTP_HOST = get_secret("SMTP_HOST") or ""
    SMTP_PORT = int(get_secret("SMTP_PORT") or 587)
    SMTP_USER = get_secret("SMTP_USER") or ""
    SMTP_PASSWORD = get_secret("SMTP_PASSWORD") or ""
    ALERT_EMAIL_TO = get_secret("ALERT_EMAIL_TO") or ""

    DEBUG = os.environ.get("FLASK_DEBUG", "false").lower() == "true"
    TESTING = False


class TestingConfig(Config):
    """Config overrides for the pytest suite."""

    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    JWT_SECRET_KEY = "test-secret-key"
    # SMTP fields left empty → email is skipped silently in tests
    SMTP_HOST = ""
    SMTP_USER = ""
    SMTP_PASSWORD = ""
    ALERT_EMAIL_TO = ""
