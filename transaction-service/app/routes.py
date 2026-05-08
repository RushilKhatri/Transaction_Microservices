"""
app/routes.py — Transaction Service
All HTTP endpoints for the transaction service.
Every route:
  - Returns JSON (never HTML)
  - Wraps logic in try/except
  - Uses the structured logger for all output
"""

from flask import Blueprint, request, jsonify, current_app
from flask_jwt_extended import create_access_token, jwt_required, get_jwt_identity, get_jwt
import requests
import uuid
from datetime import datetime, timezone

from app import db
from app.models import Account, Transaction
from app.utils import setup_logger

logger = setup_logger("transaction-service")
api = Blueprint("api", __name__)

# ── Dev-only admin credentials (not a real auth system) ───────────────────────
_ADMIN_USER = "admin"
_ADMIN_PASS = "admin123"


# ── Auth ──────────────────────────────────────────────────────────────────────

@api.route("/auth/token", methods=["POST"])
def get_token():
    """
    Development-only token endpoint.
    POST {"username": "admin", "password": "admin123"} → JWT token.
    """
    try:
        data = request.get_json(force=True) or {}
        if data.get("username") == _ADMIN_USER and data.get("password") == _ADMIN_PASS:
            token = create_access_token(identity=_ADMIN_USER)
            logger.info("Token issued", extra={"username": _ADMIN_USER})
            return jsonify({"access_token": token}), 200
        logger.warning("Failed login attempt", extra={"username": data.get("username")})
        return jsonify({"error": "Invalid credentials", "code": 401}), 401
    except Exception as exc:  # pylint: disable=broad-except
        logger.error("Token endpoint error", extra={"error": str(exc)})
        return jsonify({"error": str(exc), "code": 500}), 500


# ── Account ───────────────────────────────────────────────────────────────────

@api.route("/account/create", methods=["POST"])
@jwt_required()
def create_account():
    """Create a new bank account. Requires JWT."""
    try:
        data = request.get_json(force=True) or {}
        owner_name = data.get("owner_name", "").strip()
        if not owner_name:
            return jsonify({"error": "owner_name is required", "code": 400}), 400

        initial_balance = float(data.get("balance", 0.0))
        account = Account(
            id=str(uuid.uuid4()),
            owner_name=owner_name,
            balance=initial_balance,
        )
        db.session.add(account)
        db.session.commit()
        logger.info(
            "Account created",
            extra={"account_id": account.id, "owner": owner_name},
        )
        return jsonify(account.to_dict()), 201
    except Exception as exc:
        db.session.rollback()
        logger.error("create_account error", extra={"error": str(exc)})
        return jsonify({"error": str(exc), "code": 500}), 500


@api.route("/account/<account_id>", methods=["GET"])
@jwt_required()
def get_account(account_id):
    """Retrieve account details. Requires JWT."""
    try:
        account = db.session.get(Account, account_id)
        if not account:
            return jsonify({"error": "Account not found", "code": 404}), 404
        logger.info("Account fetched", extra={"account_id": account_id})
        return jsonify(account.to_dict()), 200
    except Exception as exc:
        logger.error("get_account error", extra={"error": str(exc)})
        return jsonify({"error": str(exc), "code": 500}), 500


# ── Transaction ───────────────────────────────────────────────────────────────

@api.route("/transaction", methods=["POST"])
@jwt_required()
def create_transaction():
    """
    Execute a transfer between two accounts.
    1. Validates balance.
    2. Atomically writes transaction to DB.
    3. Calls fraud-detection service.
    4. Updates transaction record with fraud result.
    """
    try:
        data = request.get_json(force=True) or {}
        from_id = data.get("from_account_id")
        to_id = data.get("to_account_id")
        amount = data.get("amount")
        tx_type = data.get("transaction_type", "debit")

        if not all([from_id, to_id, amount]):
            return jsonify({"error": "from_account_id, to_account_id, amount required", "code": 400}), 400

        amount = float(amount)
        if amount <= 0:
            return jsonify({"error": "Amount must be positive", "code": 400}), 400

        from_account = db.session.get(Account, from_id)
        to_account = db.session.get(Account, to_id)

        if not from_account:
            return jsonify({"error": "Source account not found", "code": 404}), 404
        if not to_account:
            return jsonify({"error": "Destination account not found", "code": 404}), 404

        # ── Balance check ─────────────────────────────────────────────────────
        if from_account.balance < amount:
            logger.warning(
                "Insufficient balance",
                extra={
                    "account_id": from_id,
                    "balance": from_account.balance,
                    "requested": amount,
                },
            )
            return jsonify({"error": "Insufficient balance", "code": 422}), 422

        # ── Atomic DB write ───────────────────────────────────────────────────
        tx = Transaction(
            id=str(uuid.uuid4()),
            from_account_id=from_id,
            to_account_id=to_id,
            amount=amount,
            transaction_type=tx_type,
            status="success",
        )
        from_account.balance -= amount
        to_account.balance += amount
        db.session.add(tx)
        db.session.commit()

        logger.info(
            "Transaction created",
            extra={"transaction_id": tx.id, "amount": amount, "from": from_id, "to": to_id},
        )

        # ── Fraud detection call ──────────────────────────────────────────────
        fraud_url = current_app.config.get("FRAUD_SERVICE_URL", "http://fraud-detection-service:5002")
        fraud_payload = {
            **tx.to_dict(),
            "account_created_at": from_account.created_at.isoformat() if from_account.created_at else None,
        }

        fraud_flagged = False
        fraud_score = 0.0
        try:
            fraud_resp = requests.post(
                f"{fraud_url}/analyse",
                json=fraud_payload,
                timeout=5,
            )
            if fraud_resp.status_code == 200:
                fraud_data = fraud_resp.json()
                fraud_flagged = fraud_data.get("fraud_flagged", False)
                fraud_score = float(fraud_data.get("fraud_score", 0.0))
        except requests.RequestException as req_err:
            logger.warning(
                "Fraud service unreachable, continuing without fraud check",
                extra={"transaction_id": tx.id, "error": str(req_err)},
            )

        # ── Update transaction with fraud result ──────────────────────────────
        tx.fraud_flagged = fraud_flagged
        tx.fraud_score = fraud_score
        db.session.commit()

        logger.info(
            "Transaction finalised",
            extra={
                "transaction_id": tx.id,
                "fraud_flagged": fraud_flagged,
                "fraud_score": fraud_score,
            },
        )
        return jsonify(tx.to_dict()), 201

    except Exception as exc:
        db.session.rollback()
        logger.error("create_transaction error", extra={"error": str(exc)})
        return jsonify({"error": str(exc), "code": 500}), 500


@api.route("/transaction/<transaction_id>", methods=["GET"])
@jwt_required()
def get_transaction(transaction_id):
    """Retrieve a transaction by ID. Requires JWT."""
    try:
        tx = db.session.get(Transaction, transaction_id)
        if not tx:
            return jsonify({"error": "Transaction not found", "code": 404}), 404
        logger.info("Transaction fetched", extra={"transaction_id": transaction_id})
        return jsonify(tx.to_dict()), 200
    except Exception as exc:
        logger.error("get_transaction error", extra={"error": str(exc)})
        return jsonify({"error": str(exc), "code": 500}), 500


@api.route("/history/<account_id>", methods=["GET"])
@jwt_required()
def get_history(account_id):
    """
    Return all transactions involving this account, newest first.
    Used by the fraud detection service's velocity rule.
    """
    try:
        jwt_claims = get_jwt()
        service_name = jwt_claims.get("service")

        # If token represents an internal service, validate service allowlist + scope.
        if service_name:
            trusted_raw = current_app.config.get("TRUSTED_INTERNAL_SERVICES", "fraud-detection-service")
            trusted_services = {
                item.strip() for item in trusted_raw.split(",") if item.strip()
            }
            required_scope = current_app.config.get("INTERNAL_REQUIRED_SCOPE", "internal_history_read")
            token_scope = jwt_claims.get("scope")

            if service_name not in trusted_services:
                logger.warning(
                    "Rejected untrusted internal service token",
                    extra={"service": service_name, "account_id": account_id},
                )
                return jsonify({"error": "Forbidden", "code": 403}), 403

            if required_scope and token_scope != required_scope:
                logger.warning(
                    "Rejected internal service token with invalid scope",
                    extra={"service": service_name, "scope": token_scope, "account_id": account_id},
                )
                return jsonify({"error": "Forbidden", "code": 403}), 403

        _ = get_jwt_identity()  # keeps explicit identity resolution for both user/service tokens

        account = db.session.get(Account, account_id)
        if not account:
            return jsonify({"error": "Account not found", "code": 404}), 404

        txs = (
            Transaction.query.filter(
                (Transaction.from_account_id == account_id)
                | (Transaction.to_account_id == account_id)
            )
            .order_by(Transaction.created_at.desc())
            .all()
        )
        logger.info(
            "History fetched",
            extra={"account_id": account_id, "count": len(txs)},
        )
        return jsonify([t.to_dict() for t in txs]), 200
    except Exception as exc:
        logger.error("get_history error", extra={"error": str(exc)})
        return jsonify({"error": str(exc), "code": 500}), 500


# ── Health ────────────────────────────────────────────────────────────────────

@api.route("/health", methods=["GET"])
def health():
    """Kubernetes liveness/readiness probe target. No auth required."""
    return jsonify({"status": "ok", "service": "transaction-service"}), 200
