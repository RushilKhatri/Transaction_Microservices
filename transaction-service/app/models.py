"""
app/models.py — Transaction Service
SQLAlchemy models for Account and Transaction.
All PKs are UUIDs generated with uuid.uuid4().
"""

import uuid
from datetime import datetime, timezone
from app import db


def _uuid():
    return str(uuid.uuid4())


def _now():
    return datetime.now(timezone.utc)


class Account(db.Model):
    __tablename__ = "accounts"

    id = db.Column(db.String(36), primary_key=True, default=_uuid)
    owner_name = db.Column(db.String(255), nullable=False)
    balance = db.Column(db.Float, default=0.0, nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), default=_now, nullable=False)

    # Relationships
    outgoing_transactions = db.relationship(
        "Transaction",
        foreign_keys="Transaction.from_account_id",
        backref="from_account",
        lazy="dynamic",
    )
    incoming_transactions = db.relationship(
        "Transaction",
        foreign_keys="Transaction.to_account_id",
        backref="to_account",
        lazy="dynamic",
    )

    def to_dict(self):
        return {
            "id": self.id,
            "owner_name": self.owner_name,
            "balance": self.balance,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class Transaction(db.Model):
    __tablename__ = "transactions"

    id = db.Column(db.String(36), primary_key=True, default=_uuid)
    from_account_id = db.Column(
        db.String(36), db.ForeignKey("accounts.id"), nullable=False
    )
    to_account_id = db.Column(
        db.String(36), db.ForeignKey("accounts.id"), nullable=False
    )
    amount = db.Column(db.Float, nullable=False)
    transaction_type = db.Column(db.String(10), nullable=False)  # "debit" | "credit"
    status = db.Column(db.String(10), default="success", nullable=False)
    fraud_flagged = db.Column(db.Boolean, default=False, nullable=False)
    fraud_score = db.Column(db.Float, default=0.0, nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), default=_now, nullable=False)

    def to_dict(self):
        return {
            "id": self.id,
            "from_account_id": self.from_account_id,
            "to_account_id": self.to_account_id,
            "amount": self.amount,
            "transaction_type": self.transaction_type,
            "status": self.status,
            "fraud_flagged": self.fraud_flagged,
            "fraud_score": self.fraud_score,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
