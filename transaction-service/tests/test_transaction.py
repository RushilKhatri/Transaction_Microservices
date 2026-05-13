"""
tests/test_transaction.py — Transaction Service
All tests use:
  - SQLite in-memory (no PostgreSQL needed)
  - Mocked get_secret() returning test values
  - Mocked requests.post for fraud service calls
"""

import json
import uuid
import pytest
import jwt
from unittest.mock import patch, MagicMock
from datetime import datetime, timedelta, timezone

# ── Patch get_secret BEFORE importing the app module ─────────────────────────
with patch("config.get_secret", return_value=""):
    from config import TestingConfig
    from app import create_app, db as _db
    from app.models import Account, Transaction


@pytest.fixture(scope="function")
def app():
    """Create a fresh app with in-memory SQLite for each test."""
    with patch("config.get_secret", return_value=""):
        application = create_app(TestingConfig)
    application.config["JWT_SECRET_KEY"] = "test-secret-key"
    application.config["FRAUD_SERVICE_URL"] = "http://fraud-detection-service:5002"
    yield application


@pytest.fixture(scope="function")
def client(app):
    return app.test_client()


@pytest.fixture(scope="function")
def db(app):
    with app.app_context():
        _db.create_all()
        yield _db
        _db.session.remove()
        _db.drop_all()


def _get_token(client):
    """Helper: obtain a JWT token from the dev endpoint."""
    resp = client.post(
        "/auth/token",
        json={"username": "admin", "password": "admin123"},
    )
    return resp.get_json()["access_token"]


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def _service_token(service="fraud-detection-service", scope="internal_history_read"):
    now = datetime.now(timezone.utc)
    payload = {
        "sub": service,
        "service": service,
        "scope": scope,
        "aud": "internal-services",
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=5)).timestamp()),
    }
    return jwt.encode(payload, "test-secret-key", algorithm="HS256")


# ── Auth endpoint ─────────────────────────────────────────────────────────────

class TestAuthToken:
    def test_valid_credentials_returns_token(self, client, db):
        resp = client.post("/auth/token", json={"username": "admin", "password": "admin123"})
        assert resp.status_code == 200
        data = resp.get_json()
        assert "access_token" in data

    def test_invalid_credentials_returns_401(self, client, db):
        resp = client.post("/auth/token", json={"username": "admin", "password": "wrong"})
        assert resp.status_code == 401
        assert resp.get_json()["code"] == 401


# ── Account endpoints ─────────────────────────────────────────────────────────

class TestAccount:
    def test_create_account_happy_path(self, client, db):
        token = _get_token(client)
        resp = client.post(
            "/account/create",
            json={"owner_name": "Alice", "balance": 1000.0},
            headers=_auth(token),
        )
        assert resp.status_code == 201
        data = resp.get_json()
        assert data["owner_name"] == "Alice"
        assert data["balance"] == 1000.0
        assert "id" in data

    def test_create_account_missing_owner_name(self, client, db):
        token = _get_token(client)
        resp = client.post(
            "/account/create",
            json={"balance": 500.0},
            headers=_auth(token),
        )
        assert resp.status_code == 400

    def test_get_account_happy_path(self, client, db):
        token = _get_token(client)
        create_resp = client.post(
            "/account/create",
            json={"owner_name": "Bob", "balance": 500.0},
            headers=_auth(token),
        )
        account_id = create_resp.get_json()["id"]

        get_resp = client.get(f"/account/{account_id}", headers=_auth(token))
        assert get_resp.status_code == 200
        assert get_resp.get_json()["id"] == account_id

    def test_get_account_not_found(self, client, db):
        token = _get_token(client)
        resp = client.get(f"/account/{uuid.uuid4()}", headers=_auth(token))
        assert resp.status_code == 404

    def test_create_account_requires_jwt(self, client, db):
        resp = client.post("/account/create", json={"owner_name": "Eve"})
        assert resp.status_code == 401


# ── Transaction endpoints ─────────────────────────────────────────────────────

class TestTransaction:
    def _create_two_accounts(self, client, db, token):
        a = client.post(
            "/account/create",
            json={"owner_name": "Sender", "balance": 2000.0},
            headers=_auth(token),
        ).get_json()
        b = client.post(
            "/account/create",
            json={"owner_name": "Receiver", "balance": 0.0},
            headers=_auth(token),
        ).get_json()
        return a["id"], b["id"]

    @patch("app.routes.requests.post")
    def test_transaction_happy_path(self, mock_post, client, db):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"fraud_flagged": False, "fraud_score": 0}
        mock_post.return_value = mock_resp

        token = _get_token(client)
        from_id, to_id = self._create_two_accounts(client, db, token)

        resp = client.post(
            "/transaction",
            json={
                "from_account_id": from_id,
                "to_account_id": to_id,
                "amount": 500.0,
                "transaction_type": "debit",
            },
            headers=_auth(token),
        )
        assert resp.status_code == 201
        data = resp.get_json()
        assert data["amount"] == 500.0
        assert data["status"] == "success"
        assert data["fraud_flagged"] is False

    @patch("app.routes.requests.post")
    def test_transaction_insufficient_balance(self, mock_post, client, db):
        token = _get_token(client)
        from_id, to_id = self._create_two_accounts(client, db, token)

        resp = client.post(
            "/transaction",
            json={
                "from_account_id": from_id,
                "to_account_id": to_id,
                "amount": 99999.0,
                "transaction_type": "debit",
            },
            headers=_auth(token),
        )
        assert resp.status_code == 422
        assert resp.get_json()["error"] == "Insufficient balance"

    def test_transaction_requires_jwt(self, client, db):
        resp = client.post("/transaction", json={})
        assert resp.status_code == 401

    @patch("app.routes.requests.post")
    def test_get_transaction(self, mock_post, client, db):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"fraud_flagged": False, "fraud_score": 0}
        mock_post.return_value = mock_resp

        token = _get_token(client)
        from_id, to_id = self._create_two_accounts(client, db, token)
        tx_id = client.post(
            "/transaction",
            json={"from_account_id": from_id, "to_account_id": to_id, "amount": 100.0, "transaction_type": "debit"},
            headers=_auth(token),
        ).get_json()["id"]

        resp = client.get(f"/transaction/{tx_id}", headers=_auth(token))
        assert resp.status_code == 200
        assert resp.get_json()["id"] == tx_id

    @patch("app.routes.requests.post")
    def test_get_history(self, mock_post, client, db):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"fraud_flagged": False, "fraud_score": 0}
        mock_post.return_value = mock_resp

        token = _get_token(client)
        from_id, to_id = self._create_two_accounts(client, db, token)

        # Create two transactions
        for _ in range(2):
            client.post(
                "/transaction",
                json={"from_account_id": from_id, "to_account_id": to_id, "amount": 50.0, "transaction_type": "debit"},
                headers=_auth(token),
            )

        resp = client.get(f"/history/{from_id}", headers=_auth(token))
        assert resp.status_code == 200
        assert len(resp.get_json()) == 2

    @patch("app.routes.requests.post")
    def test_get_history_allows_trusted_internal_service_token(self, mock_post, client, db):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"fraud_flagged": False, "fraud_score": 0}
        mock_post.return_value = mock_resp

        user_token = _get_token(client)
        from_id, to_id = self._create_two_accounts(client, db, user_token)
        client.post(
            "/transaction",
            json={"from_account_id": from_id, "to_account_id": to_id, "amount": 50.0, "transaction_type": "debit"},
            headers=_auth(user_token),
        )

        svc_token = _service_token()
        resp = client.get(f"/history/{from_id}", headers=_auth(svc_token))
        assert resp.status_code == 200
        assert len(resp.get_json()) == 1

    @patch("app.routes.requests.post")
    def test_get_history_rejects_internal_service_with_bad_scope(self, mock_post, client, db):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"fraud_flagged": False, "fraud_score": 0}
        mock_post.return_value = mock_resp

        user_token = _get_token(client)
        from_id, _ = self._create_two_accounts(client, db, user_token)

        svc_token = _service_token(scope="wrong_scope")
        resp = client.get(f"/history/{from_id}", headers=_auth(svc_token))
        assert resp.status_code == 403


# ── Health ────────────────────────────────────────────────────────────────────

class TestHealth:
    def test_health_returns_ok(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["status"] == "ok"
        assert data["service"] == "transaction-service"

    def test_health_no_auth_required(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200

    def test_metrics_endpoint_exposes_prometheus_metrics(self, client):
        client.get("/health")
        resp = client.get("/metrics")
        assert resp.status_code == 200
        assert b"banking_http_requests_total" in resp.data
        assert b'banking_service="transaction-service"' in resp.data
