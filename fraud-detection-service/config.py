"""
config.py — Fraud Detection Service
Secret management: Vault-first, env-var fallback.
No database connection needed — this service is stateless.
"""

import os
import logging

logger = logging.getLogger(__name__)


def get_secret(key: str) -> str:
    """
    Dual-mode secret resolver:
      1. If VAULT_ADDR is set  → fetch from HashiCorp Vault at
         secret/data/banking/fraud-detection-service
      2. Otherwise              → read from OS environment variable named <key>
    """
    vault_addr = os.environ.get("VAULT_ADDR")
    if vault_addr:
        try:
            import hvac  # noqa: PLC0415
            vault_token = os.environ.get("VAULT_TOKEN", "")
            client = hvac.Client(url=vault_addr, token=vault_token)
            secret_response = client.secrets.kv.v2.read_secret_version(
                path="banking/fraud-detection-service",
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
    """Base configuration for the fraud detection service."""

    # ── JWT (needed to validate tokens on protected endpoints if added later) ─
    JWT_SECRET_KEY = get_secret("JWT_SECRET_KEY") or "change-me-in-vault"

    # ── Service-to-service URLs (defaults = Docker Compose / K8s service names)
    TRANSACTION_SERVICE_URL = os.environ.get(
        "TRANSACTION_SERVICE_URL", "http://transaction-service:5001"
    )
    NOTIFICATION_SERVICE_URL = os.environ.get(
        "NOTIFICATION_SERVICE_URL", "http://notification-service:5003"
    )

    # ── Internal service-to-service auth ────────────────────────────────────
    INTERNAL_SERVICE_ID = os.environ.get("INTERNAL_SERVICE_ID", "fraud-detection-service")
    INTERNAL_JWT_AUDIENCE = os.environ.get("INTERNAL_JWT_AUDIENCE", "internal-services")
    INTERNAL_JWT_TTL_SECONDS = int(os.environ.get("INTERNAL_JWT_TTL_SECONDS", "120"))

    DEBUG = os.environ.get("FLASK_DEBUG", "false").lower() == "true"
    TESTING = False


class TestingConfig(Config):
    """Config overrides used by the pytest suite."""

    TESTING = True
    JWT_SECRET_KEY = "test-secret-key"
    TRANSACTION_SERVICE_URL = "http://transaction-service:5001"
    NOTIFICATION_SERVICE_URL = "http://notification-service:5003"
    INTERNAL_SERVICE_ID = "fraud-detection-service"
    INTERNAL_JWT_AUDIENCE = "internal-services"
    INTERNAL_JWT_TTL_SECONDS = 120
