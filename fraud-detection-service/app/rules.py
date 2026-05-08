"""
app/rules.py — Fraud Detection Service
Four independent fraud-scoring functions.
Each accepts a transaction dict and returns an integer score contribution.
Rules are designed to be individually testable and easily extensible.
"""

import requests
import os
from datetime import datetime, timezone, timedelta
import jwt
from flask import current_app, has_app_context

from app.utils import setup_logger

logger = setup_logger("fraud-detection-service")


def _cfg(key: str, default):
    """Read config from Flask app context when available, else environment."""
    if has_app_context():
        return current_app.config.get(key, default)
    return os.environ.get(key, default)


def _build_internal_service_token() -> str:
    """Create a short-lived JWT used for internal service-to-service requests."""
    service_id = str(_cfg("INTERNAL_SERVICE_ID", "fraud-detection-service"))
    audience = str(_cfg("INTERNAL_JWT_AUDIENCE", "internal-services"))
    ttl_seconds = int(_cfg("INTERNAL_JWT_TTL_SECONDS", 120))
    secret = str(_cfg("JWT_SECRET_KEY", "change-me-in-vault"))

    now = datetime.now(timezone.utc)
    payload = {
        "sub": service_id,
        "service": service_id,
        "scope": "internal_history_read",
        "aud": audience,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(seconds=ttl_seconds)).timestamp()),
    }
    return jwt.encode(payload, secret, algorithm="HS256")


def rule_large_amount(tx: dict) -> int:
    """
    Score 40 if the transaction amount exceeds 50,000.
    Rationale: large transfers are statistically correlated with fraud.
    """
    amount = float(tx.get("amount", 0))
    if amount > 50_000:
        logger.info(
            "rule_large_amount triggered",
            extra={"transaction_id": tx.get("id"), "amount": amount, "score": 40},
        )
        return 40
    return 0


def rule_velocity_check(tx: dict) -> int:
    """
    Score 35 if the source account has more than 3 transactions in the last 60 seconds.
    Calls back to the transaction service history endpoint.
    If the call fails, scores 0 to avoid blocking legitimate transactions.
    """
    account_id = tx.get("from_account_id")
    transaction_service_url = _cfg(
        "TRANSACTION_SERVICE_URL", "http://transaction-service:5001"
    )
    internal_token = _build_internal_service_token()

    try:
        resp = requests.get(
            f"{transaction_service_url}/history/{account_id}",
            headers={"Authorization": f"Bearer {internal_token}"},
            timeout=3,
        )
        if resp.status_code != 200:
            logger.warning(
                "velocity_check: history endpoint returned non-200",
                extra={"account_id": account_id, "status": resp.status_code},
            )
            return 0

        history = resp.json()
        cutoff = datetime.now(timezone.utc) - timedelta(seconds=60)

        recent_count = 0
        for entry in history:
            created_raw = entry.get("created_at")
            if created_raw:
                try:
                    created_dt = datetime.fromisoformat(created_raw)
                    # Ensure aware datetime for comparison
                    if created_dt.tzinfo is None:
                        created_dt = created_dt.replace(tzinfo=timezone.utc)
                    if created_dt >= cutoff:
                        recent_count += 1
                except ValueError:
                    pass

        if recent_count > 3:
            logger.info(
                "rule_velocity_check triggered",
                extra={
                    "transaction_id": tx.get("id"),
                    "account_id": account_id,
                    "recent_count": recent_count,
                    "score": 35,
                },
            )
            return 35
    except requests.RequestException as exc:
        logger.warning(
            "rule_velocity_check: could not reach transaction service",
            extra={"account_id": account_id, "error": str(exc)},
        )
    return 0


def rule_odd_hours(tx: dict) -> int:
    """
    Score 25 if the current UTC hour is between 2 and 5 (inclusive).
    Rationale: most fraudulent transactions occur during off-hours.
    """
    current_hour = datetime.now(timezone.utc).hour
    if 2 <= current_hour <= 5:
        logger.info(
            "rule_odd_hours triggered",
            extra={"transaction_id": tx.get("id"), "utc_hour": current_hour, "score": 25},
        )
        return 25
    return 0


def rule_new_account(tx: dict) -> int:
    """
    Score 30 if the source account is less than 7 days old.
    Rationale: newly created accounts used for large transfers are suspicious.
    The transaction payload must include 'account_created_at' (ISO 8601 string).
    """
    created_raw = tx.get("account_created_at")
    if not created_raw:
        return 0

    try:
        created_dt = datetime.fromisoformat(created_raw)
        if created_dt.tzinfo is None:
            created_dt = created_dt.replace(tzinfo=timezone.utc)

        age = datetime.now(timezone.utc) - created_dt
        if age < timedelta(days=7):
            logger.info(
                "rule_new_account triggered",
                extra={
                    "transaction_id": tx.get("id"),
                    "account_age_days": age.days,
                    "score": 30,
                },
            )
            return 30
    except (ValueError, TypeError) as exc:
        logger.warning(
            "rule_new_account: could not parse account_created_at",
            extra={"value": created_raw, "error": str(exc)},
        )
    return 0
