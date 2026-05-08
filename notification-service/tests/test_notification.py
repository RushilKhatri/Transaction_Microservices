"""
tests/test_notification.py — Notification Service
All tests use:
  - SQLite in-memory (no PostgreSQL needed)
  - Mocked get_secret() returning empty strings
  - No real SMTP connections — email is skipped silently when SMTP_HOST is empty
"""

import uuid
import pytest
from unittest.mock import patch

with patch("config.get_secret", return_value=""):
    from config import TestingConfig
    from app import create_app, db as _db
    from app.models import Alert


@pytest.fixture(scope="function")
def app():
    with patch("config.get_secret", return_value=""):
        application = create_app(TestingConfig)
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
    """Get JWT from transaction-service auth endpoint — mocked inline."""
    from flask_jwt_extended import create_access_token
    with client.application.app_context():
        return create_access_token(identity="admin")


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def _alert_payload(**overrides):
    base = {
        "id": str(uuid.uuid4()),
        "from_account_id": str(uuid.uuid4()),
        "fraud_score": 70.0,
        "rules_triggered": ["rule_large_amount", "rule_new_account"],
    }
    base.update(overrides)
    return base


# ── POST /alert ───────────────────────────────────────────────────────────────

class TestCreateAlert:
    def test_alert_persisted_and_email_skipped_gracefully(self, client, db):
        """SMTP not configured → email skipped silently, alert still saved."""
        payload = _alert_payload()
        resp = client.post("/alert", json=payload)
        assert resp.status_code == 201
        data = resp.get_json()
        assert "alert_id" in data
        assert data["sent"] is False  # SMTP not configured in TestingConfig

    def test_alert_missing_required_fields_returns_400(self, client, db):
        resp = client.post("/alert", json={"fraud_score": 80})
        assert resp.status_code == 400

    def test_alert_rules_stored_correctly(self, client, db, app):
        payload = _alert_payload()
        resp = client.post("/alert", json=payload)
        alert_id = resp.get_json()["alert_id"]

        with app.app_context():
            alert = _db.session.get(Alert, alert_id)
            assert alert is not None
            assert "rule_large_amount" in alert.rules_triggered


# ── GET /alerts ───────────────────────────────────────────────────────────────

class TestGetAllAlerts:
    def test_get_all_alerts_returns_list(self, client, db):
        # Create two alerts
        client.post("/alert", json=_alert_payload())
        client.post("/alert", json=_alert_payload())

        token = _get_token(client)
        resp = client.get("/alerts", headers=_auth(token))
        assert resp.status_code == 200
        assert len(resp.get_json()) == 2

    def test_get_alerts_requires_jwt(self, client, db):
        resp = client.get("/alerts")
        assert resp.status_code == 401


# ── GET /alerts/<account_id> ──────────────────────────────────────────────────

class TestGetAlertsByAccount:
    def test_returns_only_matching_account_alerts(self, client, db):
        account_id = str(uuid.uuid4())
        other_account_id = str(uuid.uuid4())

        # Alert for our account
        client.post("/alert", json=_alert_payload(from_account_id=account_id))
        # Alert for another account
        client.post("/alert", json=_alert_payload(from_account_id=other_account_id))

        token = _get_token(client)
        resp = client.get(f"/alerts/{account_id}", headers=_auth(token))
        assert resp.status_code == 200
        data = resp.get_json()
        assert len(data) == 1
        assert data[0]["account_id"] == account_id

    def test_returns_empty_list_for_unknown_account(self, client, db):
        token = _get_token(client)
        resp = client.get(f"/alerts/{uuid.uuid4()}", headers=_auth(token))
        assert resp.status_code == 200
        assert resp.get_json() == []

    def test_requires_jwt(self, client, db):
        resp = client.get(f"/alerts/{uuid.uuid4()}")
        assert resp.status_code == 401


# ── PATCH /alerts/<alert_id>/dismiss ─────────────────────────────────────────

class TestDismissAlert:
    def test_dismiss_sets_dismissed_true(self, client, db, app):
        payload = _alert_payload()
        create_resp = client.post("/alert", json=payload)
        alert_id = create_resp.get_json()["alert_id"]

        token = _get_token(client)
        resp = client.patch(f"/alerts/{alert_id}/dismiss", headers=_auth(token))
        assert resp.status_code == 200
        assert resp.get_json()["dismissed"] is True

    def test_dismiss_nonexistent_alert_returns_404(self, client, db):
        token = _get_token(client)
        resp = client.patch(f"/alerts/{uuid.uuid4()}/dismiss", headers=_auth(token))
        assert resp.status_code == 404

    def test_dismiss_requires_jwt(self, client, db):
        resp = client.patch(f"/alerts/{uuid.uuid4()}/dismiss")
        assert resp.status_code == 401


# ── Health ────────────────────────────────────────────────────────────────────

class TestHealth:
    def test_health_returns_ok(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["status"] == "ok"
        assert data["service"] == "notification-service"

    def test_health_no_auth_required(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
