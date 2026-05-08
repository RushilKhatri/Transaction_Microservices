"""
data/seed.py
Sets up the baseline state for the Secure Banking Transaction System demo.
Idempotent: saves account UUIDs to account_ids.json so re-running does not
create duplicate accounts.

Usage:
    python seed.py
    TRANSACTION_URL=http://localhost:5001 python seed.py
"""

import os
import sys
import json
import time
import logging
import requests
from pythonjsonlogger import jsonlogger

# ── Logger ────────────────────────────────────────────────────────────────────
_log = logging.getLogger("seed")
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
IDS_FILE = os.path.join(os.path.dirname(__file__), "account_ids.json")

# ── Account profiles ──────────────────────────────────────────────────────────
ACCOUNTS = [
    {"owner_name": "Arjun Sharma",    "balance": 500_000.0,  "note": "normal user, 120d old"},
    {"owner_name": "Priya Mehta",     "balance": 250_000.0,  "note": "normal user, 90d old"},
    {"owner_name": "Rohan Verma",     "balance": 750_000.0,  "note": "high value, 180d old"},
    {"owner_name": "Sneha Iyer",      "balance": 100_000.0,  "note": "normal user, 45d old"},
    {"owner_name": "Karan Malhotra",  "balance": 1_000_000.0,"note": "premium user, 365d old"},
    {"owner_name": "Ananya Bose",     "balance": 50_000.0,   "note": "new account (3d) — fraud risk"},
    {"owner_name": "Vikram Nair",     "balance": 200_000.0,  "note": "normal user, 60d old"},
    {"owner_name": "Deepika Rao",     "balance": 150_000.0,  "note": "normal user, 30d old"},
    {"owner_name": "Suspicious Actor","balance": 800_000.0,  "note": "new account (2d) — fraud risk"},
    {"owner_name": "Test Merchant",   "balance": 999_999.0,  "note": "merchant, 200d old"},
]


def _get_token(session: requests.Session) -> str:
    """Obtain a JWT token from the transaction service."""
    try:
        resp = session.post(
            f"{TRANSACTION_URL}/auth/token",
            json={"username": "admin", "password": "admin123"},
            timeout=10,
        )
        resp.raise_for_status()
        token = resp.json()["access_token"]
        _log.info("JWT token obtained", extra={"url": TRANSACTION_URL})
        return token
    except requests.RequestException as exc:
        print(f"\n❌  Cannot reach transaction service at {TRANSACTION_URL}")
        print(f"    Error: {exc}")
        print("    Is the service running? Try: cd transaction-service && python run.py")
        sys.exit(1)


def _load_existing_ids() -> dict:
    """Load previously saved account IDs if the file exists."""
    if os.path.exists(IDS_FILE):
        with open(IDS_FILE, "r") as fh:
            return json.load(fh)
    return {}


def _save_ids(id_map: dict) -> None:
    with open(IDS_FILE, "w") as fh:
        json.dump(id_map, fh, indent=2)
    _log.info("Account IDs saved", extra={"path": IDS_FILE})


def main() -> None:
    print("\n" + "=" * 60)
    print("  🏦  Banking Demo — Seed Script")
    print("=" * 60)
    print(f"  Transaction service : {TRANSACTION_URL}")
    print(f"  Account IDs file    : {IDS_FILE}")
    print("=" * 60 + "\n")

    session = requests.Session()
    token = _get_token(session)
    session.headers.update({"Authorization": f"Bearer {token}"})

    existing = _load_existing_ids()
    if existing:
        print(f"⚠️   Found existing account_ids.json with {len(existing)} accounts.")
        print("    Skipping creation — using existing IDs.\n")
        _print_summary(existing)
        return

    id_map: dict = {}

    print(f"  Creating {len(ACCOUNTS)} accounts...\n")
    for i, profile in enumerate(ACCOUNTS, start=1):
        try:
            resp = session.post(
                f"{TRANSACTION_URL}/account/create",
                json={"owner_name": profile["owner_name"], "balance": profile["balance"]},
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json()
            account_id = data["id"]
            id_map[profile["owner_name"]] = account_id
            _log.info(
                "Account created",
                extra={
                    "index": i,
                    "owner": profile["owner_name"],
                    "account_id": account_id,
                    "balance": profile["balance"],
                },
            )
            print(
                f"  [{i:02d}/10] ✅  {profile['owner_name']:<20s}"
                f"  Balance: ₹{profile['balance']:>12,.0f}"
                f"  ID: {account_id}"
            )
        except requests.RequestException as exc:
            print(f"  [{i:02d}/10] ❌  Failed to create {profile['owner_name']}: {exc}")
            _log.error("Account creation failed", extra={"owner": profile["owner_name"], "error": str(exc)})
        time.sleep(0.1)

    _save_ids(id_map)
    _print_summary(id_map)


def _print_summary(id_map: dict) -> None:
    print("\n" + "=" * 60)
    print("  📋  Account Summary")
    print("=" * 60)
    print(f"  {'#':<4} {'Owner':<22} {'Account ID':<38}")
    print("  " + "-" * 56)
    for idx, (name, uid) in enumerate(id_map.items(), start=1):
        print(f"  {idx:<4} {name:<22} {uid}")
    print("=" * 60)
    print(f"\n  ✅  Seed complete — {len(id_map)} accounts ready.")
    print(f"  Run demo_runner.py next to execute the demo transaction sequence.\n")


if __name__ == "__main__":
    main()
