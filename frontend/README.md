# SecureBank — Transaction Monitor Dashboard

A real-time frontend dashboard for the Secure Banking Transaction System, built with Vite + React 18. No external UI libraries — pure CSS.

---

## Prerequisites

- **Node.js 18+** — check with `node --version`
- All three Flask microservices must be running:
  - Transaction service → `http://localhost:5001`
  - Fraud detection service → `http://localhost:5002`
  - Notification service → `http://localhost:5003`
- `seed.py` must have been executed at least once (creates `data/account_ids.json`)

---

## Step 1 — Add Flask-CORS to each backend service

The browser will block requests from `localhost:3000` to the Flask services unless CORS is enabled.

**For each service** (`transaction-service`, `fraud-detection-service`, `notification-service`):

```bash
# Activate the venv for that service, then:
pip install flask-cors
```

Then in each service's `app/__init__.py`, add these two lines:

```python
from flask_cors import CORS

def create_app(config_object=None):
    app = Flask(__name__)
    # ... existing setup ...
    CORS(app)            # ← add this line after creating the Flask app
    # ... rest of factory ...
    return app
```

---

## Step 2 — Copy account_ids.json to public/

After running `seed.py`, copy the generated IDs file so the frontend can load it:

```bash
cp ../data/account_ids.json public/account_ids.json
```

This file contains the mapping of account owner names to UUIDs. The dashboard needs it to fetch account details.

---

## Step 3 — Configure environment variables (optional)

If your services run on different ports, edit `.env`:

```env
VITE_TRANSACTION_URL=http://localhost:5001
VITE_FRAUD_URL=http://localhost:5002
VITE_NOTIFICATION_URL=http://localhost:5003
```

---

## Step 4 — Install and run

```bash
cd banking-devsecops/frontend
npm install
npm run dev
```

Dashboard opens at **http://localhost:3000**

Other scripts:
- `npm run build` — production bundle
- `npm run preview` — preview production build locally

---

## What the dashboard shows

| Section | What it does |
|---|---|
| **Header** | App title + 3 coloured dots showing live health of all services (green = up, red = down) |
| **Fraud Alert Banner** | Red banner listing every unresolved fraud alert; each row has a Dismiss button |
| **Stat Cards** | Total transactions · Fraud flagged count (red if > 0) · Total INR volume · Active alerts (amber/red) |
| **Send Transaction** | Form to transfer funds between any two accounts; shows inline result (success / fraud / insufficient funds) |
| **Transaction Feed** | Live scrolling feed of the 20 most recent transactions; new rows flash yellow; flagged rows are red-tinted |
| **Account Balances** | Grid of all 10 seeded accounts with animated balance bars; high-risk accounts show red border + HIGH RISK badge |

All data refreshes automatically every **3 seconds** via polling — no page reload needed.

---

## How to trigger a live fraud alert for evaluation

1. Open the dashboard at http://localhost:3000
2. In **Send Transaction**, set **From Account** → `Suspicious Actor`
3. Set **To Account** → any other account (e.g. `Test Merchant`)
4. Enter amount **`60000`** (₹60,000 — above the ₹50,000 threshold)
5. Click **Send Transaction**

**What you will see:**
- Inline result box turns **red**: `Transaction completed but FRAUD FLAGGED — Score: XX%`
- The **Fraud Alert Banner** appears at the top of the page within 3 seconds (next poll)
- The transaction in the **Transaction Feed** shows a red `FLAGGED` badge with a red-tinted row
- The **Fraud Flagged** stat card number increments and turns red
- **Suspicious Actor**'s account card in Account Balances shows **HIGH RISK** badge and red border

Click **Dismiss** on any alert row in the banner to remove it immediately (optimistic update).

---

## Project structure

```
frontend/
├── public/
│   ├── index.html
│   └── account_ids.json        ← copy here from data/account_ids.json
├── src/
│   ├── api/
│   │   └── client.js           ← all API calls, centralised
│   ├── components/
│   │   ├── StatCards.jsx
│   │   ├── TransactionForm.jsx
│   │   ├── TransactionFeed.jsx
│   │   ├── AccountBalances.jsx
│   │   ├── FraudAlertBanner.jsx
│   │   └── ServiceStatus.jsx
│   ├── hooks/
│   │   ├── useAccounts.js
│   │   ├── useTransactions.js
│   │   └── useAlerts.js
│   ├── AuthContext.jsx
│   ├── App.jsx
│   ├── App.css
│   └── main.jsx
├── .env
├── package.json
├── vite.config.js
└── README.md
```
