"""
app/routes.py — Fraud Detection Service
POST /analyse: runs all fraud rules, aggregates score, notifies if flagged.
GET  /health : Kubernetes probe endpoint.
"""

import requests
from flask import Blueprint, request, jsonify, current_app

from app.rules import (
    rule_large_amount,
    rule_velocity_check,
    rule_odd_hours,
    rule_new_account,
)
from app.utils import setup_logger

logger = setup_logger("fraud-detection-service")
api = Blueprint("api", __name__)

# ── Ordered list of (rule_name, rule_fn) ─────────────────────────────────────
RULES = [
    ("rule_large_amount", rule_large_amount),
    ("rule_velocity_check", rule_velocity_check),
    ("rule_odd_hours", rule_odd_hours),
    ("rule_new_account", rule_new_account),
]

FRAUD_THRESHOLD = 50


@api.route("/analyse", methods=["POST"])
def analyse():
    """
    Receives a transaction dict, runs all fraud rules, aggregates the score.
    If fraud_flagged (score >= 50), calls the notification service.
    Returns: {"fraud_flagged": bool, "fraud_score": int, "rules_triggered": [...]}
    No JWT required — internal service call from transaction service.
    """
    try:
        tx = request.get_json(force=True) or {}

        if not tx.get("id"):
            return jsonify({"error": "transaction id is required", "code": 400}), 400

        rules_triggered = []
        total_score = 0

        for rule_name, rule_fn in RULES:
            try:
                score = rule_fn(tx)
                if score > 0:
                    rules_triggered.append(rule_name)
                    total_score += score
            except Exception as rule_exc:  # pylint: disable=broad-except
                logger.error(
                    "Rule execution failed",
                    extra={
                        "rule": rule_name,
                        "transaction_id": tx.get("id"),
                        "error": str(rule_exc),
                    },
                )

        fraud_flagged = total_score >= FRAUD_THRESHOLD

        logger.info(
            "Fraud analysis complete",
            extra={
                "transaction_id": tx.get("id"),
                "fraud_score": total_score,
                "fraud_flagged": fraud_flagged,
                "rules_triggered": rules_triggered,
            },
        )

        # ── Notify if flagged ─────────────────────────────────────────────────
        if fraud_flagged:
            notification_url = current_app.config.get(
                "NOTIFICATION_SERVICE_URL", "http://notification-service:5003"
            )
            alert_payload = {
                **tx,
                "fraud_score": total_score,
                "rules_triggered": rules_triggered,
            }
            try:
                notif_resp = requests.post(
                    f"{notification_url}/alert",
                    json=alert_payload,
                    timeout=5,
                )
                logger.info(
                    "Alert sent to notification service",
                    extra={
                        "transaction_id": tx.get("id"),
                        "notif_status": notif_resp.status_code,
                    },
                )
            except requests.RequestException as req_exc:
                logger.warning(
                    "Could not reach notification service",
                    extra={"transaction_id": tx.get("id"), "error": str(req_exc)},
                )

        return jsonify(
            {
                "fraud_flagged": fraud_flagged,
                "fraud_score": total_score,
                "rules_triggered": rules_triggered,
            }
        ), 200

    except Exception as exc:  # pylint: disable=broad-except
        logger.error("analyse endpoint error", extra={"error": str(exc)})
        return jsonify({"error": str(exc), "code": 500}), 500


@api.route("/health", methods=["GET"])
def health():
    """Kubernetes liveness/readiness probe. No auth required."""
    return jsonify({"status": "ok", "service": "fraud-detection-service"}), 200
