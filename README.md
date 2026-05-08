# Secure Banking Transaction System

A three-microservice banking backend built with Flask, SQLAlchemy, and Flask-JWT-Extended, designed from the ground up for integration with **Docker Compose**, **Kubernetes**, **HashiCorp Vault**, **Jenkins CI/CD**, and the **ELK stack**.

---

## Architecture

```
┌────────────────────────────┐      ┌──────────────────────────────┐      ┌─────────────────────────────┐
│   Transaction Service      │─────▶│  Fraud Detection Service     │─────▶│  Notification Service       │
│   Port 5001                │      │  Port 5002 (stateless)       │      │  Port 5003                  │
│   PostgreSQL (accounts,    │      │  4 fraud scoring rules       │      │  PostgreSQL (alerts)        │
│   transactions)            │      │  Returns fraud_score         │      │  SMTP email (optional)      │
└────────────────────────────┘      └──────────────────────────────┘      └─────────────────────────────┘
```

---

## Services

| Service | Port | Database | Description |
|---|---|---|---|
| `transaction-service` | 5001 | PostgreSQL | Account + transaction management, JWT auth |
| `fraud-detection-service` | 5002 | None (stateless) | 4-rule fraud scoring engine |
| `notification-service` | 5003 | PostgreSQL | Alert persistence + optional SMTP email |

---

## Design Principles

### 🔐 Secret Management (Vault-ready)
Every secret is resolved through `get_secret(key)` in each service's `config.py`:
1. If `VAULT_ADDR` env var is set → fetches from Vault at `secret/data/banking/<service-name>`
2. Otherwise → reads from `os.environ[key]`

**No credentials are ever hardcoded.** When deploying with Vault, simply set `VAULT_ADDR` and `VAULT_TOKEN` — zero code changes required.

### 📊 Structured JSON Logging (ELK-ready)
All services emit structured JSON logs via `python-json-logger`. Every log line contains:
- `timestamp`, `level`, `service`, `message`
- Context fields: `transaction_id`, `account_id`, `fraud_score`, etc.

Compatible with Logstash/Filebeat/Kibana ingestion out of the box.

### 🛢️ Database URI Assembly (K8s-ready)
The DB connection string is assembled from **individual secrets** (`DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`), allowing Kubernetes to inject each component as a separate `Secret` or `ConfigMap`. Default host is `postgres` (matching the Docker Compose service name).

### 🔗 Internal Service JWT (service-to-service auth)
For internal calls, the fraud service now signs a short-lived JWT and sends it to transaction service when calling `/history/<account_id>` for the velocity rule.

- Fraud service issues token with claims: `service`, `scope=internal_history_read`.
- Transaction service validates internal tokens against:
  - `TRUSTED_INTERNAL_SERVICES`
  - `INTERNAL_REQUIRED_SCOPE`

Environment variables:
- `INTERNAL_SERVICE_ID`
- `INTERNAL_JWT_AUDIENCE`
- `INTERNAL_JWT_TTL_SECONDS`
- `TRUSTED_INTERNAL_SERVICES`
- `INTERNAL_REQUIRED_SCOPE`

---

## Local Development

### Prerequisites
- Python 3.11+
- PostgreSQL (or use Docker Compose — Dockerfile/compose files to be added)

### Docker Compose + Vault dev flow (Phase 2)
Use this sequence to ensure services resolve secrets from Vault at startup:

1. Start infra containers:
  - `docker compose up -d vault postgres`
2. Seed Vault dev KV with DB/JWT/SMTP values:
  - `bash infra/vault/seed-dev.sh`
3. Start app services (+frontend if needed):
  - `docker compose up -d transaction-service fraud-detection-service notification-service frontend`

Notes:
- Services are configured Vault-first via `get_secret()` and still fall back to environment variables if Vault is unavailable.
- Vault dev defaults are provided via `.env.docker` (`VAULT_ADDR`, `VAULT_TOKEN`).

### Run each service
```bash
# Set required environment variables
export JWT_SECRET_KEY="dev-secret-key"
export DB_HOST=localhost
export DB_PORT=5432
export DB_NAME=banking
export DB_USER=banking_user
export DB_PASSWORD=yourpassword

# Transaction Service
cd transaction-service
pip install -r requirements.txt
python run.py

# Fraud Detection Service (new terminal)
cd fraud-detection-service
pip install -r requirements.txt
python run.py

# Notification Service (new terminal)
cd notification-service
pip install -r requirements.txt
python run.py
```

### Get a JWT token (dev mode)
```bash
curl -X POST http://localhost:5001/auth/token \
  -H "Content-Type: application/json" \
  -d '{"username": "admin", "password": "admin123"}'
```

### Create an account
```bash
TOKEN="<paste token here>"
curl -X POST http://localhost:5001/account/create \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"owner_name": "Alice", "balance": 10000}'
```

### Execute a transaction
```bash
curl -X POST http://localhost:5001/transaction \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "from_account_id": "<from-id>",
    "to_account_id": "<to-id>",
    "amount": 500,
    "transaction_type": "debit"
  }'
```

---

## Running Tests

Each service's tests are fully self-contained: they use **SQLite in-memory**, **mock `get_secret()`**, and **mock all external HTTP calls** — no real database, Vault, or network required.

```bash
# Transaction Service
cd transaction-service && pytest tests/ -v

# Fraud Detection Service
cd fraud-detection-service && pytest tests/ -v

# Notification Service
cd notification-service && pytest tests/ -v
```

---

## Jenkins CI/CD (Phase 3)

A root [Jenkinsfile](Jenkinsfile) is included with these stages:

1. Checkout
2. Unit tests (`pytest` for all three backend services)
3. SAST scan (`bandit`)
4. Dependency audit (`safety` + `npm audit`)
5. Docker build (all services + frontend)
6. Image scan (`trivy`, HIGH/CRITICAL gate)
7. Docker Compose smoke test (Vault seed + health checks + end-to-end transaction)
8. Optional push to Docker Hub
9. Optional deploy step (Ansible if playbook exists)

### Jenkins job setup notes

- Pipeline type: **Pipeline script from SCM**
- Script path: `Jenkinsfile`
- Required tools on Jenkins agent: `docker`, `docker compose`, `python3`, `pip`, `node/npm`
- Optional credential for push stage:
  - Jenkins credentials id: `dockerhub-creds` (`usernamePassword`)

### Pipeline parameters

- `PUSH_IMAGES` (bool): push tagged images to Docker Hub
- `RUN_DEPLOY` (bool): run deploy stage after push
- `DOCKERHUB_NAMESPACE` (string): Docker Hub namespace/user

For a complete step-by-step Jenkins installation, job configuration, webhook, and troubleshooting guide, see [docs/jenkins-setup.md](docs/jenkins-setup.md).

---

## API Reference

### Transaction Service (port 5001)

| Method | Endpoint | Auth | Description |
|---|---|---|---|
| POST | `/auth/token` | None | Get JWT token (dev only) |
| POST | `/account/create` | JWT | Create bank account |
| GET | `/account/<id>` | JWT | Get account details |
| POST | `/transaction` | JWT | Execute transfer |
| GET | `/transaction/<id>` | JWT | Get transaction details |
| GET | `/history/<account_id>` | JWT | Transaction history |
| GET | `/health` | None | Health check |

### Fraud Detection Service (port 5002)

| Method | Endpoint | Auth | Description |
|---|---|---|---|
| POST | `/analyse` | None (internal) | Score transaction for fraud |
| GET | `/health` | None | Health check |

#### Fraud Rules
| Rule | Trigger | Score |
|---|---|---|
| `rule_large_amount` | Amount > 50,000 | +40 |
| `rule_velocity_check` | >3 transactions in last 60s | +35 |
| `rule_odd_hours` | UTC hour 2–5 (inclusive) | +25 |
| `rule_new_account` | Account < 7 days old | +30 |

**Flagged** if total score ≥ 50.

### Notification Service (port 5003)

| Method | Endpoint | Auth | Description |
|---|---|---|---|
| POST | `/alert` | None (internal) | Create fraud alert |
| GET | `/alerts` | JWT | All alerts |
| GET | `/alerts/<account_id>` | JWT | Alerts for account |
| PATCH | `/alerts/<id>/dismiss` | JWT | Dismiss alert |
| GET | `/health` | None | Health check |

---

## Future Integration Points

| Integration | Status | Notes |
|---|---|---|
| **Docker Compose** | Planned | Service names already match defaults (`postgres`, `fraud-detection-service`, etc.) |
| **Kubernetes** | Planned | DB URI components injectable as K8s Secrets/ConfigMaps |
| **HashiCorp Vault** | Ready | `get_secret()` already supports Vault via `VAULT_ADDR` env var |
| **Jenkins CI/CD** | Planned | Tests runnable as `pytest` commands in pipeline stages |
| **ELK Stack** | Ready | All logs are structured JSON; compatible with Filebeat/Logstash |
| **Ansible** | Planned | Service startup/deployment playbooks to be added |

---

## Project Structure

```
banking-devsecops/
├── transaction-service/
│   ├── app/
│   │   ├── __init__.py     # Flask app factory
│   │   ├── models.py       # Account, Transaction models
│   │   ├── routes.py       # All HTTP endpoints
│   │   └── utils.py        # JSON logger setup
│   ├── tests/
│   │   └── test_transaction.py
│   ├── config.py           # get_secret() + Config classes
│   ├── requirements.txt
│   └── run.py
├── fraud-detection-service/
│   ├── app/
│   │   ├── __init__.py
│   │   ├── rules.py        # 4 fraud scoring rules
│   │   ├── routes.py
│   │   └── utils.py
│   ├── tests/
│   │   └── test_fraud.py
│   ├── config.py
│   ├── requirements.txt
│   └── run.py
├── notification-service/
│   ├── app/
│   │   ├── __init__.py
│   │   ├── models.py       # Alert model
│   │   ├── routes.py
│   │   └── utils.py
│   ├── tests/
│   │   └── test_notification.py
│   ├── config.py
│   ├── requirements.txt
│   └── run.py
└── README.md
```
