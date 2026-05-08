"""
data/demo_runner.py
Main evaluation script for the Secure Banking Transaction System.
Reads account IDs from account_ids.json and executes a carefully designed
sequence of 10+ transactions demonstrating every system feature:
  - Normal transfers (no fraud)
  - Edge cases (partial scores)
  - Fraud-flagged transactions (high score)
  - Velocity fraud (rapid-fire sends)
  - Balance rejection (expected failure)

Usage:
    python demo_runner.py
    TRANSACTION_URL=http://localhost:5001 python demo_runner.py
"""

import os
import sys
import json
import time
import logging
import requests
from pythonjsonlogger import jsonlogger

# ── Logger ────────────────────────────────────────────────────────────────────
_log = logging.getLogger("demo-runner")
_handler = logging.StreamHandler()
_handler.setFormatter(
    jsonlogger.JsonFormatter(
        fmt="%(asctime)s %(levelname)s %(name)s %(message)s",
        rename_fields={"asctime": "timestamp", "levelname": "level", "name": "service"},
        datefmt="%Y-%m-%dT%H:%M:%S",
    )
)
_log.addHandler(_handler)
_log.setLevel(logging.INFO)

# ── Config ────────────────────────────────────────────────────────────────────
TRANSACTION_URL = os.environ.get("TRANSACTION_URL", "http://localhost:5001")
FRAUD_URL       = os.environ.get("FRAUD_URL",       "http://localhost:5002")
IDS_FILE        = os.path.join(os.path.dirname(__file__), "account_ids.json")

# ── Counters ──────────────────────────────────────────────────────────────────
stats = {
    "attempted": 0,
    "succeeded": 0,
    "rejected": 0,
    "fraud_flagged": 0,
    "flagged_accounts": set(),
}


def _get_token(session: requests.Session) -> str:
    try:
        resp = session.post(
            f"{TRANSACTION_URL}/auth/token",
            json={"username": "admin", "password": "admin123"},
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json()["access_token"]
    except requests.RequestException as exc:
        print(f"\n❌  Cannot reach transaction service at {TRANSACTION_URL}")
        print(f"    Error: {exc}")
        sys.exit(1)


def _load_ids() -> dict:
    if not os.path.exists(IDS_FILE):
        print(f"\n❌  account_ids.json not found at {IDS_FILE}")
        print("    Run seed.py first:  python data/seed.py")
        sys.exit(1)
    with open(IDS_FILE) as fh:
        return json.load(fh)


def _send_transaction(
    session: requests.Session,
    ids: dict,
    from_name: str,
    to_name: str,
    amount: float,
    label: str = "",
    expect_reject: bool = False,
) -> dict | None:
    """
    Execute one transfer and print a rich one-line result.
    Returns the response JSON on success, None on failure.
    """
    stats["attempted"] += 1
    from_id = ids.get(from_name)
    to_id   = ids.get(to_name)

    if not from_id or not to_id:
        print(f"  ❓  Unknown account name in IDs file: {from_name!r} or {to_name!r}")
        return None

    prefix = f"  [TX {stats['attempted']:02d}]"
    print(f"{prefix} {from_name} → {to_name}  ₹{amount:>10,.0f}"
          + (f"  ({label})" if label else ""))

    try:
        resp = session.post(
            f"{TRANSACTION_URL}/transaction",
            json={
                "from_account_id": from_id,
                "to_account_id":   to_id,
                "amount":          amount,
                "transaction_type": "debit",
            },
            timeout=15,
        )
    except requests.RequestException as exc:
        print(f"{prefix} ❌  Network error: {exc}")
        _log.error("Transaction network error", extra={"from": from_name, "to": to_name, "error": str(exc)})
        return None

    data = resp.json()

    if resp.status_code == 422 or (resp.status_code >= 400 and "Insufficient" in data.get("error", "")):
        stats["rejected"] += 1
        tag = "✅  EXPECTED REJECTION" if expect_reject else "⚠️   REJECTED"
        print(f"         └─ {tag}: {data.get('error', 'insufficient balance')}")
        _log.warning("Transaction rejected", extra={"from": from_name, "to": to_name, "amount": amount})
        return None

    if resp.status_code not in (200, 201):
        print(f"         └─ ❌  HTTP {resp.status_code}: {data.get('error', 'unknown error')}")
        _log.error("Transaction failed", extra={"status": resp.status_code, "body": data})
        return None

    # ── Success ───────────────────────────────────────────────────────────────
    stats["succeeded"] += 1
    tx_id        = data.get("id", "?")
    fraud_flagged = data.get("fraud_flagged", False)
    fraud_score   = data.get("fraud_score", 0.0)

    if fraud_flagged:
        stats["fraud_flagged"] += 1
        stats["flagged_accounts"].add(from_name)
        flag_str = f"🚨  FRAUD FLAGGED  score={fraud_score:.0f}"
    else:
        flag_str = f"✅  OK  score={fraud_score:.0f}"

    print(f"         └─ {flag_str}  tx_id={tx_id[:8]}…")
    _log.info(
        "Transaction complete",
        extra={
            "from": from_name,
            "to": to_name,
            "amount": amount,
            "fraud_flagged": fraud_flagged,
            "fraud_score": fraud_score,
            "tx_id": tx_id,
        },
    )
    return data


def _section(title: str) -> None:
    print(f"\n{'─' * 60}")
    print(f"  {title}")
    print(f"{'─' * 60}")


def main() -> None:
    print("\n" + "=" * 60)
    print("  🏦  Banking Demo — Transaction Demo Runner")
    print("=" * 60)
    print(f"  Transaction service : {TRANSACTION_URL}")
    print(f"  Fraud service       : {FRAUD_URL}")
    print("=" * 60)

    session = requests.Session()
    token = _get_token(session)
    session.headers.update({"Authorization": f"Bearer {token}"})
    print("  🔑  JWT token acquired\n")

    ids = _load_ids()
    print(f"  📂  Loaded {len(ids)} accounts from account_ids.json\n")

    # ────────────────────────────────────────────────────────────────────────────
    # BATCH 1 — Normal transactions
    # ────────────────────────────────────────────────────────────────────────────
    _section("BATCH 1 — Normal Transactions (no fraud expected)")

    _send_transaction(session, ids, "Arjun Sharma",   "Priya Mehta",   10_000, "normal debit, established account")
    time.sleep(1)
    _send_transaction(session, ids, "Rohan Verma",    "Test Merchant",  25_000, "payment, high-value account")
    time.sleep(1)
    _send_transaction(session, ids, "Karan Malhotra", "Deepika Rao",    5_000,  "small transfer, premium account")
    time.sleep(1)
    _send_transaction(session, ids, "Vikram Nair",    "Sneha Iyer",     8_000,  "normal transfer")
    time.sleep(1)

    # ────────────────────────────────────────────────────────────────────────────
    # BATCH 2 — Edge cases
    # ────────────────────────────────────────────────────────────────────────────
    _section("BATCH 2 — Edge Cases (partial scores, may not flag)")

    _send_transaction(session, ids, "Arjun Sharma", "Test Merchant", 45_000, "large but under 50k threshold")
    time.sleep(1)
    _send_transaction(session, ids, "Deepika Rao",  "Rohan Verma",   30_000, "significant portion of balance")
    time.sleep(1)

    # ────────────────────────────────────────────────────────────────────────────
    # BATCH 3 — Fraud scenarios
    # ────────────────────────────────────────────────────────────────────────────
    _section("BATCH 3 — Fraud Scenarios (expect FLAGGED 🚨)")
    print("  Expected: rule_large_amount (40) + rule_new_account (30) = 70 pts ≥ 50 → FLAGGED\n")

    _send_transaction(
        session, ids,
        "Suspicious Actor", "Test Merchant", 60_000,
        "large_amount(40) + new_account(30) = 70 → FLAGGED",
    )
    time.sleep(1)
    _send_transaction(
        session, ids,
        "Ananya Bose", "Karan Malhotra", 55_000,
        "large_amount(40) + new_account(30) = 70 → FLAGGED",
    )
    time.sleep(1)
    _send_transaction(
        session, ids,
        "Suspicious Actor", "Priya Mehta", 52_000,
        "second large TX from new account → FLAGGED",
    )
    time.sleep(1)

    # ────────────────────────────────────────────────────────────────────────────
    # BATCH 4 — Velocity fraud (rapid-fire, no sleep between sends)
    # ────────────────────────────────────────────────────────────────────────────
    _section("BATCH 4 — Velocity Fraud (4 rapid sends from Rohan Verma)")
    print("  Sending 4 transactions within seconds — 4th may trigger velocity rule (35 pts)\n")

    velocity_targets = ["Arjun Sharma", "Priya Mehta", "Sneha Iyer", "Vikram Nair"]
    for target in velocity_targets:
        _send_transaction(session, ids, "Rohan Verma", target, 1_000, "velocity test")
        # No sleep — intentionally rapid to trigger velocity rule

    time.sleep(1)

    # ────────────────────────────────────────────────────────────────────────────
    # BATCH 5 — Rejection (expected failure)
    # ────────────────────────────────────────────────────────────────────────────
    _section("BATCH 5 — Expected Rejection (insufficient balance)")
    print("  Sneha Iyer balance ≈ ₹92,000 after batch 1; attempting ₹500,000 transfer\n")

    _send_transaction(
        session, ids,
        "Sneha Iyer", "Karan Malhotra", 500_000,
        "EXPECTED: insufficient balance",
        expect_reject=True,
    )

    # ────────────────────────────────────────────────────────────────────────────
    # Final summary
    # ────────────────────────────────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("  📊  Demo Run Summary")
    print("=" * 60)
    print(f"  Transactions attempted  : {stats['attempted']}")
    print(f"  Successful              : {stats['succeeded']}")
    print(f"  Rejected (insuf. funds) : {stats['rejected']}")
    print(f"  Fraud flagged           : {stats['fraud_flagged']}")
    if stats["flagged_accounts"]:
        print(f"  Flagged accounts        : {', '.join(sorted(stats['flagged_accounts']))}")
    print("=" * 60 + "\n")

    _log.info(
        "Demo run complete",
        extra={
            "attempted": stats["attempted"],
            "succeeded": stats["succeeded"],
            "rejected": stats["rejected"],
            "fraud_flagged": stats["fraud_flagged"],
        },
    )


if __name__ == "__main__":
    main()
