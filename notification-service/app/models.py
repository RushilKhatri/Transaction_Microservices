"""
app/models.py — Notification Service
Alert model: stores fraud alerts in the database.
rules_triggered stored as a comma-separated string to avoid needing a join table.
"""

import uuid
from datetime import datetime, timezone
from app import db


def _uuid():
    return str(uuid.uuid4())


def _now():
    return datetime.now(timezone.utc)


class Alert(db.Model):
    __tablename__ = "alerts"

    id = db.Column(db.String(36), primary_key=True, default=_uuid)
    transaction_id = db.Column(db.String(36), nullable=False, index=True)
    account_id = db.Column(db.String(36), nullable=False, index=True)
    fraud_score = db.Column(db.Float, nullable=False, default=0.0)
    rules_triggered = db.Column(db.Text, nullable=True)   # comma-separated strings
    alert_sent = db.Column(db.Boolean, default=True, nullable=False)
    dismissed = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), default=_now, nullable=False)

    def to_dict(self):
        return {
            "id": self.id,
            "transaction_id": self.transaction_id,
            "account_id": self.account_id,
            "fraud_score": self.fraud_score,
            "rules_triggered": self.rules_triggered.split(",") if self.rules_triggered else [],
            "alert_sent": self.alert_sent,
            "dismissed": self.dismissed,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
