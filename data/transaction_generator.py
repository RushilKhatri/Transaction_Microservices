"""
data/transaction_generator.py
Generates a configurable volume of random realistic transactions.
Used to populate Kibana dashboards with enough data for meaningful visualisations.

Usage:
    python transaction_generator.py --count 50 --mode mixed
    python transaction_generator.py --count 100 --mode normal
    TRANSACTION_URL=http://localhost:5001 python transaction_generator.py --count 200 --mode mixed
"""

import os
import sys
import json
import random
import logging
import argparse
import requests
from pythonjsonlogger import jsonlogger

# ── Logger ────────────────────────────────────────────────────────────────────
_log = logging.getLogger("tx-generator")
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
IDS_FILE        = os.path.join(os.path.dirname(__file__), "account_ids.json")

# ── Account groups ────────────────────────────────────────────────────────────
ESTABLISHED = [
    "Arjun Sharma",
    "Priya Mehta",
    "Rohan Verma",
    "Sneha Iyer",
    "Karan Malhotra",
    "Vikram Nair",
    "Deepika Rao",
    "Test Merchant",
]
NEW_ACCOUNTS = [
    "Ananya Bose",
    "Suspicious Actor",
]
ALL_ACCOUNTS = ESTABLISHED + NEW_ACCOUNTS


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate random transactions for the Banking Demo system."
    )
    parser.add_argument(
        "--count",
        type=int,
        default=50,
        help="Number of transactions to generate (default: 50)",
    )
    parser.add_argument(
        "--mode",
        choices=["normal", "mixed"],
        default="mixed",
        help="Transaction mix: 'normal' (low amounts, established accounts) or "
             "'mixed' (70% normal + 20% new-account + 10% large) (default: mixed)",
    )
    return parser.parse_args()


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


def _pick_transaction(mode: str, ids: dict) -> tuple[str, str, float] | None:
    """
    Return (from_name, to_name, amount) based on the chosen mode.
    Returns None if a valid pair cannot be chosen.
    """
    roll = random.random()

    if mode == "normal":
        # Random established → established (different account)
        from_name = random.choice(ESTABLISHED)
        candidates = [n for n in ESTABLISHED if n != from_name and n in ids]
        if not candidates:
            return None
        to_name = random.choice(candidates)
        amount = round(random.uniform(1_000, 20_000), 2)

    else:  # mixed
        if roll < 0.70:
            # 70% normal
            from_name = random.choice([n for n in ESTABLISHED if n in ids])
            candidates = [n for n in ESTABLISHED if n != from_name and n in ids]
            if not candidates:
                return None
            to_name = random.choice(candidates)
            amount = round(random.uniform(1_000, 20_000), 2)

        elif roll < 0.90:
            # 20% new-account transactions
            available_new = [n for n in NEW_ACCOUNTS if n in ids]
            if not available_new:
                # Fallback to normal if new accounts don't exist in IDs file
                from_name = random.choice([n for n in ESTABLISHED if n in ids])
                candidates = [n for n in ESTABLISHED if n != from_name and n in ids]
                if not candidates:
                    return None
                to_name = random.choice(candidates)
                amount = round(random.uniform(1_000, 20_000), 2)
            else:
                from_name = random.choice(available_new)
                candidates = [n for n in ALL_ACCOUNTS if n != from_name and n in ids]
                if not candidates:
                    return None
                to_name = random.choice(candidates)
                amount = round(random.uniform(10_000, 80_000), 2)

        else:
            # 10% large-amount from established accounts
            from_name = random.choice([n for n in ESTABLISHED if n in ids])
            candidates = [n for n in ALL_ACCOUNTS if n != from_name and n in ids]
            if not candidates:
                return None
            to_name = random.choice(candidates)
            amount = round(random.uniform(50_001, 200_000), 2)

    # Ensure both accounts are in our IDs map
    if from_name not in ids or to_name not in ids:
        return None

    return from_name, to_name, amount


def _send(
    session: requests.Session,
    ids: dict,
    from_name: str,
    to_name: str,
    amount: float,
    index: int,
    total: int,
) -> tuple[bool, float]:
    """
    Execute one transaction.
    Returns (fraud_flagged, fraud_score).
    """
    try:
        resp = session.post(
            f"{TRANSACTION_URL}/transaction",
            json={
                "from_account_id":  ids[from_name],
                "to_account_id":    ids[to_name],
                "amount":           amount,
                "transaction_type": "debit",
            },
            timeout=15,
        )
        data = resp.json()

        if resp.status_code in (200, 201):
            flagged = data.get("fraud_flagged", False)
            score   = float(data.get("fraud_score", 0))
            print(
                f"  [TX {index:>4}/{total}] {from_name:<20s} → {to_name:<20s}"
                f"  ₹{amount:>10,.0f}"
                f"  | fraud_flagged: {str(flagged):<5}"
                f"  | score: {score:.0f}"
            )
            _log.info(
                "Generated transaction",
                extra={
                    "index": index,
                    "from": from_name,
                    "to": to_name,
                    "amount": amount,
                    "fraud_flagged": flagged,
                    "fraud_score": score,
                },
            )
            return flagged, score

        elif resp.status_code == 422:
            # Insufficient balance — log quietly and skip
            print(
                f"  [TX {index:>4}/{total}] {from_name:<20s} → {to_name:<20s}"
                f"  ₹{amount:>10,.0f}"
                f"  | SKIPPED (insufficient balance)"
            )
            return False, 0.0

        else:
            print(
                f"  [TX {index:>4}/{total}] ❌  HTTP {resp.status_code}: {data.get('error', 'error')}"
            )
            return False, 0.0

    except requests.RequestException as exc:
        print(f"  [TX {index:>4}/{total}] ❌  Network error: {exc}")
        _log.error("Network error", extra={"index": index, "error": str(exc)})
        return False, 0.0


def main() -> None:
    args = _parse_args()
    count = args.count
    mode  = args.mode

    print("\n" + "=" * 72)
    print("  🏦  Banking Demo — Transaction Generator")
    print("=" * 72)
    print(f"  Mode                : {mode}")
    print(f"  Transactions        : {count}")
    print(f"  Transaction service : {TRANSACTION_URL}")
    print("=" * 72 + "\n")

    session = requests.Session()
    token = _get_token(session)
    session.headers.update({"Authorization": f"Bearer {token}"})
    print("  🔑  JWT token acquired\n")

    ids = _load_ids()
    print(f"  📂  Loaded {len(ids)} accounts from account_ids.json\n")

    if mode == "mixed":
        print(f"  Distribution: 70% normal | 20% new-account | 10% large-amount\n")
    else:
        print(f"  Distribution: 100% normal (₹1k–₹20k, established accounts)\n")

    print(f"  {'#':>6}  {'From':<20}  {'To':<20}  {'Amount':>12}  {'Flagged':<10}  Score")
    print("  " + "─" * 80)

    flagged_count = 0
    generated     = 0

    for i in range(1, count + 1):
        tx = _pick_transaction(mode, ids)
        if tx is None:
            _log.warning("Could not pick a valid transaction pair, skipping", extra={"index": i})
            continue

        from_name, to_name, amount = tx
        flagged, _ = _send(session, ids, from_name, to_name, amount, i, count)
        generated += 1
        if flagged:
            flagged_count += 1

    print("\n" + "=" * 72)
    print("  📊  Generator Summary")
    print("=" * 72)
    print(f"  Transactions generated : {generated}")
    print(f"  Fraud flagged          : {flagged_count} / {generated}"
          + (f"  ({100*flagged_count//generated}%)" if generated else ""))
    print("=" * 72 + "\n")

    _log.info(
        "Generator complete",
        extra={"generated": generated, "flagged": flagged_count, "mode": mode},
    )


if __name__ == "__main__":
    main()
