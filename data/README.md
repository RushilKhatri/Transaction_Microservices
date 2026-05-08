# Data Layer Scripts

Scripts to seed, demo, and populate the Secure Banking Transaction System with realistic data.

---

## Order of Execution

```
1. seed.py  →  2. demo_runner.py  →  3. transaction_generator.py
```

> **Note:** `seed.py` must be re-run if the database is reset (e.g. after `docker compose down -v`).  
> Delete `account_ids.json` before re-running so new account UUIDs are saved correctly.

---

## Script Reference

### 1. `seed.py` — Baseline Setup

Creates the 10 demo accounts (Arjun Sharma, Priya Mehta, Rohan Verma, etc.) and saves their UUIDs to `data/account_ids.json`. **Idempotent** — if `account_ids.json` already exists it prints the existing accounts and exits without creating duplicates.

```bash
# From the banking-devsecops/ root:
python data/seed.py

# Or with custom service URL:
TRANSACTION_URL=http://localhost:5001 python data/seed.py
```

**Expected output:**
```
============================================================
  🏦  Banking Demo — Seed Script
============================================================
  [01/10] ✅  Arjun Sharma        Balance: ₹    500,000  ID: <uuid>
  [02/10] ✅  Priya Mehta         Balance: ₹    250,000  ID: <uuid>
  ...
  [10/10] ✅  Test Merchant       Balance: ₹    999,999  ID: <uuid>

  ✅  Seed complete — 10 accounts ready.
```

---

### 2. `demo_runner.py` — Evaluation Demo

Reads `account_ids.json` and executes a choreographed sequence of **11 transactions** across 5 batches, demonstrating every system feature. Pauses 1 second between transactions so logs are clearly separated.

| Batch | What it demonstrates |
|---|---|
| 1 — Normal | 4 routine transfers; all pass, zero fraud score |
| 2 — Edge cases | Large but sub-threshold amounts; partial scores |
| 3 — Fraud | 3 transactions from new accounts with amounts >₹50k → **FLAGGED** |
| 4 — Velocity | 4 rapid transfers from same account → may trigger velocity rule |
| 5 — Rejection | Attempt over-balance transfer → **expected 422 rejection** |

```bash
python data/demo_runner.py

# Custom URL:
TRANSACTION_URL=http://localhost:5001 FRAUD_URL=http://localhost:5002 python data/demo_runner.py
```

**Expected final summary:**
```
============================================================
  📊  Demo Run Summary
============================================================
  Transactions attempted  : 11
  Successful              : 10
  Rejected (insuf. funds) : 1
  Fraud flagged           : 3
  Flagged accounts        : Ananya Bose, Suspicious Actor
============================================================
```

---

### 3. `transaction_generator.py` — Dashboard Population

Generates a configurable volume of randomised transactions to populate Kibana dashboards with enough data for meaningful visualisations.

**Arguments:**

| Argument | Default | Description |
|---|---|---|
| `--count` | 50 | Number of transactions to generate |
| `--mode` | `mixed` | `normal` (low amounts, established accounts only) or `mixed` |

**Mixed mode distribution:**

| Segment | Weight | Description |
|---|---|---|
| Normal | 70% | ₹1,000–₹20,000 between established accounts |
| New-account | 20% | ₹10,000–₹80,000 from Ananya Bose or Suspicious Actor |
| Large-amount | 10% | ₹50,001–₹200,000 from established accounts |

```bash
# 50 mixed transactions (recommended for first run):
python data/transaction_generator.py --count 50 --mode mixed

# 200 normal transactions (for baseline ELK data):
python data/transaction_generator.py --count 200 --mode normal

# 500 mixed for full Kibana dashboard population:
TRANSACTION_URL=http://localhost:5001 python data/transaction_generator.py --count 500 --mode mixed
```

**Expected per-transaction output:**
```
  [TX    1/50] Arjun Sharma       → Test Merchant        ₹    12,450  | fraud_flagged: False  | score: 0
  [TX    2/50] Suspicious Actor   → Priya Mehta          ₹    62,300  | fraud_flagged: True   | score: 70
  ...
```

**Expected summary:**
```
  Transactions generated : 50
  Fraud flagged          : 11 / 50  (22%)
```

---

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `TRANSACTION_URL` | `http://localhost:5001` | Transaction service base URL |
| `FRAUD_URL` | `http://localhost:5002` | Fraud detection service base URL |
| `NOTIFICATION_URL` | `http://localhost:5003` | Notification service base URL |

> These defaults match the Docker Compose / Kubernetes service names when running locally. Override to point at deployed services.

---

## Re-seeding After a Database Reset

```bash
# 1. Delete the saved IDs file
rm data/account_ids.json

# 2. Re-run seed
python data/seed.py

# 3. Run the demo again
python data/demo_runner.py
```
