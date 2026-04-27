# ⛓️ Blockchain Service

Production-ready lightweight blockchain microservice built with **Python**, **FastAPI**, **PostgreSQL**, and **SQLAlchemy** — fully instrumented with metrics, logs, and distributed tracing via the Grafana observability stack.

Supports two use cases:
1. **Order integrity** — immutable ledger for order transactions
2. **Payment integrity** — immutable ledger for payment confirmations

> This is **NOT a cryptocurrency**. No mining, no tokens, no consensus. This is an integrity and auditability ledger.

---

## Tech Stack

| Layer | Technology |
|---|---|
| Language | Python 3.11 |
| Framework | FastAPI |
| Database | PostgreSQL (asyncpg + SQLAlchemy async) |
| Hashing | SHA256 (hashlib) |
| Validation | Pydantic v2 |
| Config | pydantic-settings |
| Metrics | prometheus-client → Prometheus |
| Logs | structlog (JSON) → Alloy → Loki |
| Traces | OpenTelemetry → Alloy → Tempo |
| Visualization | Grafana |

---

## Project Structure

```
blockchain-service/
├── app/
│   ├── config.py                  # pydantic-settings config
│   ├── main.py                    # FastAPI app, lifespan, middleware
│   ├── db/
│   │   ├── database.py            # Async SQLAlchemy engine + session
│   │   └── models.py              # blockchain_blocks ORM model
│   ├── models/
│   │   └── block.py               # Pydantic request/response models
│   ├── routes/
│   │   └── blockchain.py          # All /blockchain/* endpoints
│   ├── services/
│   │   └── blockchain.py          # Core Blockchain class
│   └── utils/
│       ├── logger.py              # structlog JSON logger (injects trace_id)
│       ├── metrics.py             # Prometheus metrics registry
│       └── tracing.py             # OpenTelemetry SDK setup
├── .env.example
├── Dockerfile                     # Multi-stage production image
└── requirements.txt
```

---

## Getting Started

### Prerequisites

- Python 3.11+
- PostgreSQL >= 14

### 1. Install

```bash
cd blockchain-service
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Configure Environment

```bash
cp .env.example .env
```

```env
DATABASE_URL="postgresql+asyncpg://postgres:yourpassword@localhost:5436/blockchain_db"
PORT=8000
NODE_ENV=development
SERVICE_NAME=blockchain-service
LOG_LEVEL=DEBUG

# Observability
OTEL_EXPORTER_OTLP_ENDPOINT="http://localhost:4317"
```

### 3. Start

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Swagger UI: http://localhost:8000/docs

---

## API Reference

### Endpoint Summary

| Method | Endpoint | Auth | Description |
|---|---|---|---|
| GET | `/health` | — | Health check |
| GET | `/metrics` | — | Prometheus metrics |
| GET | `/docs` | — | Swagger UI (auto-generated) |
| POST | `/blockchain/order` | — | Add order transaction block |
| POST | `/blockchain/payment` | — | Add payment transaction block |
| GET | `/blockchain/chain` | — | Get full blockchain |
| GET | `/blockchain/validate` | — | Validate chain integrity |
| GET | `/blockchain/verify/order/{order_id}` | — | Verify order integrity |
| GET | `/blockchain/verify/payment/{payment_id}` | — | Verify payment integrity |

---

### POST /blockchain/order

Records an order transaction as an immutable block. `order_id` must be unique.

**Request:**
```json
{
  "order_id":    "ORD-123",
  "user_id":     "U-001",
  "items":       [{ "book_id": "uuid", "quantity": 2, "price": 35.99 }],
  "total_price": 71.98,
  "status":      "PENDING"
}
```

**201 Created:**
```json
{
  "success": true,
  "message": "Order 'ORD-123' recorded on blockchain at index 1",
  "block": {
    "index":         1,
    "timestamp":     "2025-01-01T00:00:00.000000+00:00",
    "block_type":    "order",
    "data":          { "order_id": "ORD-123", "user_id": "U-001", "..." : "..." },
    "previous_hash": "abc123...",
    "hash":          "def456..."
  }
}
```

**409 Conflict (duplicate order_id):**
```json
{ "detail": "Order 'ORD-123' already exists in the blockchain" }
```

---

### POST /blockchain/payment

Records a payment confirmation as an immutable block. `payment_id` must be unique.

**Request:**
```json
{
  "payment_id": "PAY-123",
  "order_id":   "ORD-123",
  "amount":     71980,
  "status":     "PAID"
}
```

**201 Created:**
```json
{
  "success": true,
  "message": "Payment 'PAY-123' recorded on blockchain at index 2",
  "block": { "..." : "..." }
}
```

---

### GET /blockchain/validate

Recomputes every block hash and verifies chain linkage.

**200 OK (valid):**
```json
{ "valid": true, "message": "Chain is valid", "checked": 5 }
```

**200 OK (tampered):**
```json
{ "valid": false, "message": "Block 3 hash is invalid — data may have been tampered", "checked": 4 }
```

---

### GET /blockchain/verify/order/{order_id}

Verifies that an order record has not been tampered with since it was added to the chain.

**200 OK (valid):**
```json
{
  "found":   true,
  "status":  "VALID",
  "message": "Order 'ORD-123' blockchain record is VALID — data integrity confirmed",
  "block":   { "..." : "..." }
}
```

**200 OK (tampered):**
```json
{
  "found":   true,
  "status":  "TAMPERED",
  "message": "Order 'ORD-123' blockchain record is TAMPERED — hash mismatch detected"
}
```

**200 OK (not found):**
```json
{
  "found":   false,
  "status":  "NOT_FOUND",
  "message": "No blockchain record found for order 'ORD-123'"
}
```

---

### GET /blockchain/verify/payment/{payment_id}

Verifies that a payment record has not been tampered with.

**200 OK:**
```json
{
  "found":   true,
  "status":  "VALID",
  "message": "Payment 'PAY-123' blockchain record is VALID — data integrity confirmed",
  "block":   { "..." : "..." }
}
```

---

## How the Blockchain Works

### Block Structure

```
Block {
  index:         int          — position in chain (0 = genesis)
  timestamp:     ISO8601      — UTC timestamp of block creation
  block_type:    string       — "genesis" | "order" | "payment"
  data:          JSON         — the actual payload
  previous_hash: SHA256       — hash of the preceding block (links the chain)
  hash:          SHA256       — SHA256(index + timestamp + type + data + previous_hash)
}
```

### Hash Formula

```python
hash = SHA256(
    str(index) +
    timestamp  +
    block_type +
    json.dumps(data, sort_keys=True) +  # canonical JSON — deterministic
    previous_hash
)
```

### Chain Integrity

```
[Genesis]  →  [Order Block]  →  [Payment Block]  →  [Order Block]
  hash: "abc..."      hash: "def..."    hash: "ghi..."      hash: "jkl..."
  prev: "000..."      prev: "abc..."    prev: "def..."      prev: "ghi..."
```

> Any modification to a block changes its hash, breaking the `previous_hash` link of the next block — making tampering immediately detectable during validation.

---

## Example API Usage (curl)

```bash
BASE=http://localhost:8000

# Add order block
curl -X POST $BASE/blockchain/order \
  -H "Content-Type: application/json" \
  -d '{
    "order_id": "ORD-001",
    "user_id": "U-001",
    "items": [{"book_id": "uuid", "quantity": 2, "price": 35.99}],
    "total_price": 71.98,
    "status": "PENDING"
  }'

# Add payment block
curl -X POST $BASE/blockchain/payment \
  -H "Content-Type: application/json" \
  -d '{
    "payment_id": "PAY-001",
    "order_id": "ORD-001",
    "amount": 71980,
    "status": "PAID"
  }'

# Validate chain
curl $BASE/blockchain/validate

# Verify order
curl $BASE/blockchain/verify/order/ORD-001

# Verify payment
curl $BASE/blockchain/verify/payment/PAY-001

# Get full chain
curl $BASE/blockchain/chain

# Health check
curl $BASE/health

# Swagger UI
# Open http://localhost:8000/docs in browser
```

---

## 📊 Observability

### Architecture

```
┌──────────────────────────────────────────────────────────┐
│              blockchain-service :8000                     │
│                                                            │
│  /metrics  ──────────────────────────► Prometheus          │
│  stdout (JSON logs) ─────► Alloy ───► Loki                │
│  OTLP traces (gRPC) ─────► Alloy ───► Tempo               │
└──────────────────────────────────────────────────────────┘
                                             │
                                             ▼
                                         Grafana :8000
                              (metrics + logs + traces correlated)
```

### Signal Pipeline

| Signal | Produced by | Collector | Storage |
|---|---|---|---|
| **Metrics** | `prometheus-client` → `/metrics` | Prometheus scrape | Prometheus TSDB |
| **Logs** | `structlog` JSON → stdout | Alloy Docker scrape | Loki |
| **Traces** | `OpenTelemetry` → OTLP/gRPC | Alloy OTLP receiver | Tempo |

### Prometheus Metrics

| Metric | Type | Labels | Description |
|---|---|---|---|
| `http_requests_total` | Counter | `method`, `route`, `status_code` | HTTP requests |
| `http_request_duration_seconds` | Histogram | `method`, `route`, `status_code` | Request latency |
| `blockchain_blocks_total` | Gauge | — | Total blocks in chain |
| `blockchain_chain_valid` | Gauge | — | 1=valid, 0=tampered |
| `blockchain_operations_total` | Counter | `operation`, `block_type`, `status` | Blockchain ops |
| `chain_validation_duration_seconds` | Histogram | — | Full chain validation time |

---

## Scripts

| Command | Description |
|---|---|
| `uvicorn app.main:app --reload` | Start with hot reload |
| `uvicorn app.main:app` | Start production |

---

## Security Notes

- All inputs validated with Pydantic v2 before processing
- `order_id` uniqueness enforced — prevents duplicate entries
- Blocks are immutable — no UPDATE or DELETE on `blockchain_blocks` table
- SHA256 with canonical JSON (sorted keys) prevents hash manipulation via key reordering
- Non-root container user (UID 1001) in Docker