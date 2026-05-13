"""
tests/test_fraud.py — Fraud Detection Service
Tests:
  - Each fraud rule independently returning the correct score
  - /analyse endpoint aggregating correctly and flagging when score >= 50
  - /health endpoint
All external HTTP calls are mocked via unittest.mock.patch.
"""

import uuid
import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime, timedelta, timezone

with patch("config.get_secret", return_value=""):
    from config import TestingConfig
    from app import create_app


@pytest.fixture(scope="function")
def app():
    with patch("config.get_secret", return_value=""):
        application = create_app(TestingConfig)
    yield application


@pytest.fixture(scope="function")
def client(app):
    return app.test_client()


def _sample_tx(**overrides):
    """Return a minimal valid transaction dict."""
    base = {
        "id": str(uuid.uuid4()),
        "from_account_id": str(uuid.uuid4()),
        "to_account_id": str(uuid.uuid4()),
        "amount": 100.0,
        "transaction_type": "debit",
        "status": "success",
        "fraud_flagged": False,
        "fraud_score": 0.0,
        "account_created_at": (
            datetime.now(timezone.utc) - timedelta(days=30)
        ).isoformat(),  # old account by default
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    base.update(overrides)
    return base


# ── Rule: rule_large_amount ───────────────────────────────────────────────────

class TestRuleLargeAmount:
    def test_score_40_when_amount_exceeds_50000(self):
        from app.rules import rule_large_amount
        tx = _sample_tx(amount=75000.0)
        assert rule_large_amount(tx) == 40

    def test_score_0_when_amount_below_threshold(self):
        from app.rules import rule_large_amount
        tx = _sample_tx(amount=49999.99)
        assert rule_large_amount(tx) == 0

    def test_score_0_exactly_at_threshold(self):
        from app.rules import rule_large_amount
        tx = _sample_tx(amount=50000.0)
        assert rule_large_amount(tx) == 0


# ── Rule: rule_velocity_check ─────────────────────────────────────────────────

class TestRuleVelocityCheck:
    @patch("app.rules.requests.get")
    def test_score_35_when_more_than_3_recent_transactions(self, mock_get):
        from app.rules import rule_velocity_check

        now = datetime.now(timezone.utc)
        # 4 transactions in the last 60 seconds
        history = [
            {"created_at": (now - timedelta(seconds=i * 10)).isoformat()}
            for i in range(4)
        ]
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = history
        mock_get.return_value = mock_resp

        tx = _sample_tx()
        assert rule_velocity_check(tx) == 35
        _, kwargs = mock_get.call_args
        assert "headers" in kwargs
        assert kwargs["headers"]["Authorization"].startswith("Bearer ")

    @patch("app.rules.requests.get")
    def test_score_0_when_3_or_fewer_recent_transactions(self, mock_get):
        from app.rules import rule_velocity_check

        now = datetime.now(timezone.utc)
        history = [
            {"created_at": (now - timedelta(seconds=i * 10)).isoformat()}
            for i in range(3)
        ]
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = history
        mock_get.return_value = mock_resp

        tx = _sample_tx()
        assert rule_velocity_check(tx) == 0

    @patch("app.rules.requests.get")
    def test_score_0_when_service_unreachable(self, mock_get):
        import requests as req_lib
        from app.rules import rule_velocity_check
        mock_get.side_effect = req_lib.RequestException("connection refused")
        tx = _sample_tx()
        # Should not raise; returns 0 gracefully
        assert rule_velocity_check(tx) == 0


# ── Rule: rule_odd_hours ──────────────────────────────────────────────────────

class TestRuleOddHours:
    @patch("app.rules.datetime")
    def test_score_25_during_odd_hours(self, mock_dt):
        from app.rules import rule_odd_hours
        # Hour = 3 (inside odd window 2-5)
        mock_dt.now.return_value = datetime(2025, 1, 1, 3, 0, 0, tzinfo=timezone.utc)
        mock_dt.fromisoformat = datetime.fromisoformat
        tx = _sample_tx()
        assert rule_odd_hours(tx) == 25

    @patch("app.rules.datetime")
    def test_score_0_during_business_hours(self, mock_dt):
        from app.rules import rule_odd_hours
        # Hour = 10 (outside odd window)
        mock_dt.now.return_value = datetime(2025, 1, 1, 10, 0, 0, tzinfo=timezone.utc)
        mock_dt.fromisoformat = datetime.fromisoformat
        tx = _sample_tx()
        assert rule_odd_hours(tx) == 0

    @patch("app.rules.datetime")
    def test_score_25_at_boundary_hour_2(self, mock_dt):
        from app.rules import rule_odd_hours
        mock_dt.now.return_value = datetime(2025, 1, 1, 2, 0, 0, tzinfo=timezone.utc)
        mock_dt.fromisoformat = datetime.fromisoformat
        tx = _sample_tx()
        assert rule_odd_hours(tx) == 25

    @patch("app.rules.datetime")
    def test_score_25_at_boundary_hour_5(self, mock_dt):
        from app.rules import rule_odd_hours
        mock_dt.now.return_value = datetime(2025, 1, 1, 5, 0, 0, tzinfo=timezone.utc)
        mock_dt.fromisoformat = datetime.fromisoformat
        tx = _sample_tx()
        assert rule_odd_hours(tx) == 25


# ── Rule: rule_new_account ────────────────────────────────────────────────────

class TestRuleNewAccount:
    def test_score_30_when_account_less_than_7_days_old(self):
        from app.rules import rule_new_account
        created = (datetime.now(timezone.utc) - timedelta(days=3)).isoformat()
        tx = _sample_tx(account_created_at=created)
        assert rule_new_account(tx) == 30

    def test_score_0_when_account_older_than_7_days(self):
        from app.rules import rule_new_account
        created = (datetime.now(timezone.utc) - timedelta(days=10)).isoformat()
        tx = _sample_tx(account_created_at=created)
        assert rule_new_account(tx) == 0

    def test_score_0_when_created_at_missing(self):
        from app.rules import rule_new_account
        tx = _sample_tx(account_created_at=None)
        assert rule_new_account(tx) == 0


# ── /analyse endpoint ─────────────────────────────────────────────────────────

class TestAnalyseEndpoint:
    @patch("app.routes.requests.post")
    @patch("app.rules.requests.get")
    def test_analyse_flags_high_score(self, mock_get, mock_post, client, app):
        """Amount > 50k (40) + new account (30) = 70 → flagged."""
        mock_get.return_value = MagicMock(status_code=200, json=MagicMock(return_value=[]))

        mock_notif = MagicMock()
        mock_notif.status_code = 200
        mock_post.return_value = mock_notif

        tx = _sample_tx(
            amount=60000.0,
            account_created_at=(datetime.now(timezone.utc) - timedelta(days=2)).isoformat(),
        )
        resp = client.post("/analyse", json=tx)
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["fraud_flagged"] is True
        assert data["fraud_score"] >= 50
        assert "rule_large_amount" in data["rules_triggered"]
        assert "rule_new_account" in data["rules_triggered"]

    @patch("app.rules.requests.get")
    def test_analyse_does_not_flag_low_score(self, mock_get, client, app):
        """Small amount + old account + business hours = 0 → not flagged."""
        mock_get.return_value = MagicMock(status_code=200, json=MagicMock(return_value=[]))

        tx = _sample_tx(
            amount=100.0,
            account_created_at=(datetime.now(timezone.utc) - timedelta(days=30)).isoformat(),
        )
        with patch("app.rules.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2025, 1, 1, 10, 0, 0, tzinfo=timezone.utc)
            mock_dt.fromisoformat = datetime.fromisoformat
            resp = client.post("/analyse", json=tx)

        assert resp.status_code == 200
        data = resp.get_json()
        assert data["fraud_flagged"] is False

    def test_analyse_missing_id_returns_400(self, client, app):
        resp = client.post("/analyse", json={"amount": 100})
        assert resp.status_code == 400


# ── Health ────────────────────────────────────────────────────────────────────

class TestHealth:
    def test_health_returns_ok(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["status"] == "ok"
        assert data["service"] == "fraud-detection-service"

    def test_metrics_endpoint_exposes_prometheus_metrics(self, client):
        client.get("/health")
        resp = client.get("/metrics")
        assert resp.status_code == 200
        assert b"banking_http_requests_total" in resp.data
        assert b'banking_service="fraud-detection-service"' in resp.data
