"""
app/routes.py — Notification Service
POST /alert               : persist fraud alert, attempt email (silent fail)
GET  /alerts              : all alerts, JWT required
GET  /alerts/<account_id> : alerts for one account, JWT required
PATCH /alerts/<id>/dismiss: mark dismissed, JWT required
GET  /health              : Kubernetes probe, no auth
"""

import uuid
import smtplib
from email.mime.text import MIMEText
from datetime import datetime, timezone

from flask import Blueprint, request, jsonify, current_app
from flask_jwt_extended import jwt_required

from app import db
from app.models import Alert
from app.utils import setup_logger

logger = setup_logger("notification-service")
api = Blueprint("api", __name__)


def _try_send_email(subject: str, body: str, config) -> bool:
    """
    Attempt to send an email via SMTP.
    If SMTP credentials are not configured, log a warning and return False.
    Never raises — always fails silently so the main alert flow is not blocked.
    """
    smtp_host = config.get("SMTP_HOST", "")
    smtp_user = config.get("SMTP_USER", "")
    smtp_password = config.get("SMTP_PASSWORD", "")
    alert_to = config.get("ALERT_EMAIL_TO", "")

    if not all([smtp_host, smtp_user, smtp_password, alert_to]):
        logger.warning(
            "SMTP not configured — skipping email notification",
            extra={"smtp_host": smtp_host or "not-set"},
        )
        return False

    try:
        smtp_port = int(config.get("SMTP_PORT", 587))
        msg = MIMEText(body)
        msg["Subject"] = subject
        msg["From"] = smtp_user
        msg["To"] = alert_to

        with smtplib.SMTP(smtp_host, smtp_port) as server:
            server.starttls()
            server.login(smtp_user, smtp_password)
            server.send_message(msg)

        logger.info("Alert email sent", extra={"to": alert_to})
        return True
    except Exception as exc:  # pylint: disable=broad-except
        logger.warning(
            "Email send failed — continuing without notification",
            extra={"error": str(exc)},
        )
        return False


# ── POST /alert ───────────────────────────────────────────────────────────────

@api.route("/alert", methods=["POST"])
def create_alert():
    """
    Internal endpoint called by the fraud detection service.
    Persists fraud alert; attempts email silently.
    No JWT required — internal service call.
    """
    try:
        data = request.get_json(force=True) or {}

        transaction_id = data.get("id") or data.get("transaction_id")
        account_id = data.get("from_account_id") or data.get("account_id")
        fraud_score = float(data.get("fraud_score", 0.0))
        rules_triggered = data.get("rules_triggered", [])

        if not transaction_id or not account_id:
            return jsonify({"error": "transaction_id and account_id are required", "code": 400}), 400

        if isinstance(rules_triggered, list):
            rules_str = ",".join(rules_triggered)
        else:
            rules_str = str(rules_triggered)

        alert = Alert(
            id=str(uuid.uuid4()),
            transaction_id=str(transaction_id),
            account_id=str(account_id),
            fraud_score=fraud_score,
            rules_triggered=rules_str,
            alert_sent=False,  # will update below
            dismissed=False,
        )
        db.session.add(alert)
        db.session.commit()

        logger.info(
            "Alert persisted",
            extra={
                "alert_id": alert.id,
                "transaction_id": transaction_id,
                "account_id": account_id,
                "fraud_score": fraud_score,
            },
        )

        # ── Attempt email (fail silently) ─────────────────────────────────────
        subject = f"[FRAUD ALERT] Transaction {transaction_id} flagged"
        body = (
            f"Transaction ID : {transaction_id}\n"
            f"Account ID     : {account_id}\n"
            f"Fraud Score    : {fraud_score}\n"
            f"Rules Triggered: {', '.join(rules_triggered) if isinstance(rules_triggered, list) else rules_triggered}\n"
        )
        email_sent = _try_send_email(subject, body, current_app.config)

        # Update alert_sent flag
        alert.alert_sent = email_sent
        db.session.commit()

        return jsonify({"alert_id": alert.id, "sent": email_sent}), 201

    except Exception as exc:
        db.session.rollback()
        logger.error("create_alert error", extra={"error": str(exc)})
        return jsonify({"error": str(exc), "code": 500}), 500


# ── GET /alerts ───────────────────────────────────────────────────────────────

@api.route("/alerts", methods=["GET"])
@jwt_required()
def get_all_alerts():
    """Return all alerts ordered by created_at descending. Requires JWT."""
    try:
        alerts = Alert.query.order_by(Alert.created_at.desc()).all()
        logger.info("All alerts fetched", extra={"count": len(alerts)})
        return jsonify([a.to_dict() for a in alerts]), 200
    except Exception as exc:
        logger.error("get_all_alerts error", extra={"error": str(exc)})
        return jsonify({"error": str(exc), "code": 500}), 500


# ── GET /alerts/<account_id> ──────────────────────────────────────────────────

@api.route("/alerts/<account_id>", methods=["GET"])
@jwt_required()
def get_alerts_for_account(account_id):
    """Return alerts for a specific account. Requires JWT."""
    try:
        alerts = (
            Alert.query
            .filter_by(account_id=account_id)
            .order_by(Alert.created_at.desc())
            .all()
        )
        logger.info(
            "Account alerts fetched",
            extra={"account_id": account_id, "count": len(alerts)},
        )
        return jsonify([a.to_dict() for a in alerts]), 200
    except Exception as exc:
        logger.error("get_alerts_for_account error", extra={"error": str(exc)})
        return jsonify({"error": str(exc), "code": 500}), 500


# ── PATCH /alerts/<alert_id>/dismiss ─────────────────────────────────────────

@api.route("/alerts/<alert_id>/dismiss", methods=["PATCH"])
@jwt_required()
def dismiss_alert(alert_id):
    """Mark an alert as dismissed. Requires JWT."""
    try:
        alert = db.session.get(Alert, alert_id)
        if not alert:
            return jsonify({"error": "Alert not found", "code": 404}), 404

        alert.dismissed = True
        db.session.commit()
        logger.info("Alert dismissed", extra={"alert_id": alert_id})
        return jsonify(alert.to_dict()), 200
    except Exception as exc:
        db.session.rollback()
        logger.error("dismiss_alert error", extra={"error": str(exc)})
        return jsonify({"error": str(exc), "code": 500}), 500


# ── GET /health ───────────────────────────────────────────────────────────────

@api.route("/health", methods=["GET"])
def health():
    """Kubernetes liveness/readiness probe. No auth required."""
    return jsonify({"status": "ok", "service": "notification-service"}), 200
