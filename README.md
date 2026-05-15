# SENTINEL

> **Agentic Fraud Detection Framework for Real-Time Transaction Security**
> Global IME AI/ML Hackathon 2026 · Track B — Security & Fraud
> Multi-agent ML system with context-aware orchestrator and dual-path OTP verification

---

> 📢 **HACKATHON NOTE:** Real data format will be provided on the day of the hackathon. The current priority is to complete the entire functional framework, all agents, the orchestrator, and the dashboard using synthetic data first. The system is designed with an adapter pattern to allow rapid integration of the real data spec when it arrives.

---

## Table of Contents

- [Overview](#overview)
- [Architecture](#architecture)
- [Tech Stack](#tech-stack)
- [Repository Structure](#repository-structure)
- [Quick Start](#quick-start)
- [How to Use This Plan](#how-to-use-this-plan)
- [Sprint Plan](#sprint-plan)
  - [Sprint 0 — Foundation & Scope Lock](#sprint-0--foundation--scope-lock)
  - [Sprint 1 — Infrastructure](#sprint-1--infrastructure)
  - [Sprint 2 — Data Schemas & Generator](#sprint-2--data-schemas--generator)
  - [Sprint 3 — Velocity Agent](#sprint-3--velocity-agent)
  - [Sprint 4 — Geo Agent](#sprint-4--geo-agent)
  - [Sprint 5 — Behavior Agent (ML)](#sprint-5--behavior-agent-ml)
  - [Sprint 6 — Cold-Start Cohort System](#sprint-6--cold-start-cohort-system)
  - [Sprint 7 — Graph Layer (Neo4j + GNN)](#sprint-7--graph-layer-neo4j--gnn)
  - [Sprint 8 — Synthesis Agent](#sprint-8--synthesis-agent)
  - [Sprint 9 — OTP Interlock](#sprint-9--otp-interlock)
  - [Sprint 10 — Orchestrator & Kafka Wiring](#sprint-10--orchestrator--kafka-wiring)
  - [Sprint 11 — MLflow Integration](#sprint-11--mlflow-integration)
  - [Sprint 12 — Demo Dashboard](#sprint-12--demo-dashboard)
  - [Sprint 13 — Scenario Testing](#sprint-13--scenario-testing)
  - [Sprint 14 — Load Test & Latency Tuning](#sprint-14--load-test--latency-tuning)
  - [Sprint 15 — Demo Day Prep](#sprint-15--demo-day-prep)
- [Time-Compressed Tracks](#time-compressed-tracks)
- [Team Roles](#team-roles)
- [Risk Register](#risk-register)
- [Glossary](#glossary)

---

## Overview

SENTINEL is a multi-agent fraud detection system that scores every transaction through four specialized agents in parallel, synthesizes their verdicts with context-aware weighting based on transaction type, and triggers dual-path OTP verification (Email + SMS) on suspicious cases to defeat SIM-swap attacks.

**Target metrics:**

- End-to-end verdict latency: < 380 ms P99 (track requirement: < 800 ms)
- Fraud detection recall: > 97%
- False positive rate: < 2%
- Throughput: 10,000 TPS

**Four official challenges this addresses:**

1. Minimize false positives via graduated OTP-interlock band (score 0.40–0.75 routes to verification, not block)
2. Context-aware synthesis weights that adapt by transaction type (P2P / QR / SWIFT / ATM)
3. Cold-start protection via peer-cohort modeling from day 0
4. SIM-swap defense via independent dual-path OTP (Email + SMS)

---

## Architecture

```
                    ┌────────────────────────────────────────┐
                    │      Transaction Event (Kafka)         │
                    └──────────────────┬─────────────────────┘
                                       │
                ┌──────────────────────┼──────────────────────┐
                │                      │                      │
                ▼                      ▼                      ▼
        ┌──────────────┐      ┌──────────────┐       ┌──────────────┐
        │   Velocity   │      │     Geo      │       │   Behavior   │
        │   Agent      │      │   Agent      │       │   Agent      │
        │ (Redis-based)│      │  (heuristic) │       │ (LSTM + IF)  │
        └──────┬───────┘      └──────┬───────┘       └──────┬───────┘
               │                     │                      │
               │              ┌──────▼──────┐               │
               │              │ GNN Agent   │               │
               │              │  (Neo4j)    │               │
               │              └──────┬──────┘               │
               │                     │                      │
               └─────────────────────┼──────────────────────┘
                                     ▼
                         ┌─────────────────────┐
                         │  Synthesis Agent    │
                         │ Context-Aware       │
                         │ Weighted Voting     │
                         └──────────┬──────────┘
                                    │
              ┌─────────────────────┼─────────────────────┐
              │                     │                     │
              ▼                     ▼                     ▼
         ALLOW (< 0.40)    OTP_INTERLOCK (0.40-0.75)  BLOCK (> 0.75)
                                    │
                         ┌──────────┴──────────┐
                         ▼                     ▼
                    SMS OTP              Email OTP
                  (Sparrow/Twilio)        (SMTP)
                         │                     │
                         └──────────┬──────────┘
                                    ▼
                      Both confirmed → RELEASE
                      Email-only confirmed → SIM-SWAP BLOCK
                      Either fails → HUMAN REVIEW
```

---

## Tech Stack

| Layer           | Technology                          | Purpose                                      |
| --------------- | ----------------------------------- | -------------------------------------------- |
| Streaming       | Apache Kafka                        | Transaction event bus                        |
| Cache           | Redis 7                             | Velocity windows, account history, OTP state |
| Graph DB        | Neo4j 5 (Community + GDS)           | Account relationship graph                   |
| Relational DB   | PostgreSQL 16                       | Audit log, account metadata                  |
| ML Framework    | PyTorch 2.x + scikit-learn          | LSTM + Isolation Forest                      |
| Graph ML        | PyTorch Geometric                   | GraphSAGE for mule detection                 |
| Model Lifecycle | MLflow 2.x                          | Tracking, registry, drift                    |
| API             | FastAPI + asyncio                   | Orchestrator service                         |
| SMS             | Sparrow SMS (Nepal) / Twilio (intl) | OTP delivery — mocked for demo               |
| Email           | SMTP (Gmail relay)                  | OTP delivery                                 |
| Frontend        | React + Vite + Tailwind + Recharts  | Demo dashboard                               |
| Container       | Docker Compose                      | Local infra                                  |
| Load Test       | Locust                              | TPS validation                               |

---

## Repository Structure

```
sentinel/
├── docker-compose.yml          # Full local stack
├── .env.example
├── pyproject.toml
├── README.md                   # This file
│
├── data/
│   ├── generators/             # Synthetic transaction generation
│   └── seeds/                  # Output parquet files
│
├── agents/
│   ├── velocity/
│   ├── geo/
│   ├── behavior/
│   ├── synthesis/
│   └── otp/
│
├── graph/
│   ├── setup.cypher            # Neo4j schema
│   ├── mule_detection.cypher   # Mule-ring query
│   └── train_gnn.py            # GraphSAGE training
│
├── orchestrator/
│   ├── main.py                 # FastAPI app + Kafka consumer
│   ├── schemas.py              # Pydantic models
│   └── routing.py
│
├── ml/
│   ├── training/
│   │   ├── train_lstm.py
│   │   ├── train_isolation_forest.py
│   │   └── build_baselines.py
│   ├── cohorts/
│   │   └── assign.py
│   └── artifacts/              # Saved model files
│
├── frontend/
│   ├── src/
│   └── package.json
│
├── tests/
│   ├── scenarios/
│   │   ├── sita.py
│   │   ├── sim_swap.py
│   │   ├── cold_start.py
│   │   └── mule_ring.py
│   └── load/
│       └── locustfile.py
│
└── scripts/
    ├── seed_all.sh
    ├── train_all_models.sh
    └── demo_run.sh
```

---

## Quick Start

> ⚠️ **REAL DATA FORMAT UNKNOWN — adapter pattern in use.**
> `orchestrator/schemas.py` defines SENTINEL's internal working model (`TransactionEvent`).
> All field names are provisional best-guesses. When the real data spec is confirmed,
> **only update `data/adapters/real_data_adapter.py`** — fill in `_FIELD_MAP`,
> `_TX_TYPE_MAP`, and `_ACCT_TYPE_MAP`. No agent or orchestrator code needs to change.

```bash
# 1. Clone and install
git clone <repo>
cd sentinel
poetry install

# 2. Start infrastructure
docker compose up -d
docker compose ps   # all 6 services should be healthy

# 3. Generate synthetic data  ✅ already generated — skip if data/seeds/*.parquet exist
poetry run python data/generators/generate.py --accounts 5000

# 4. Train models
bash scripts/train_all_models.sh

# 5. Seed graph and Redis baselines
bash scripts/seed_all.sh

# 6. Run orchestrator
poetry run uvicorn orchestrator.main:app --reload --port 8000

# 7. Run frontend (in separate terminal)
cd frontend && npm install && npm run dev

# 8. Replay transactions through Kafka
poetry run python data/generators/replay.py

# 9. Run scenario tests
poetry run pytest tests/scenarios/ -v

# 10. Run load test
locust -f tests/load/locustfile.py --headless -u 500 -r 100 -t 60s --host http://localhost:8000
```

---

## How to Use This Plan

Sprints below are **dependency-ordered**, not time-ordered. Effort is in story points (Fibonacci: 1=hours, 3=full day, 5=1–2 days, 8=2–3 days, 13=split it). Each sprint has:

- **Goal** — one-line outcome
- **Effort** — story points
- **Depends on** — sprints that must complete first
- **Owner** — suggested role (see [Team Roles](#team-roles))
- **Tech spec** — schemas, code, configs needed
- **Tasks** — granular checkboxes
- **Definition of Done** — exit criteria
- **Deliverable** — what artifact ships

**Parallelization map** (after Sprint 2 completes):

```
Sprint 2 ──┬─→ Sprint 3 ──┐
           ├─→ Sprint 4 ──┤
           ├─→ Sprint 5 ──┼─→ Sprint 8 ──→ Sprint 10 ──→ Sprint 12 ──→ Sprint 13 ──→ Sprint 14 ──→ Sprint 15
           ├─→ Sprint 6 ──┤
           ├─→ Sprint 7 ──┘
           └─→ Sprint 9 (independent, can run anytime)
                Sprint 11 (independent, light)
```

**Total effort:** ~85 story points. A 4-person team running parallel can compress to a critical path of ~30 points (~5–7 working days at hackathon pace).

---

# Sprint Plan

## Sprint 0 — Foundation & Scope Lock

**Goal:** Lock all scope decisions before any code is written.
**Effort:** 2
**Depends on:** Nothing
**Owner:** Tech lead + full team

### Decisions to lock

- [x] **D1: Real ML vs heuristic per agent.** Decision: Velocity + Geo = heuristic. Behavior + GNN = real ML.
- [x] **D2: SMS provider strategy.** Decision: Mock by default, one real Twilio shot at demo if trial credit allows.
- [x] **D3: Kafka vs direct calls.** Decision: Kafka, with `KAFKA_ENABLED=false` fallback flag.
- [x] **D4: Data source.** Decision: Synthetic data, ~5K accounts × 20–50 tx each, 2% labeled fraud across taxonomy.
- [x] **D5: Hosting.** Decision: Demo from laptop; cloud backup on a single VM as failover.
- [x] **D6: Per-account vs per-cohort behavior ML.** Decision: per-cohort only (5–10 cohorts total).
- [x] **D7: GNN scope.** Decision: Attempt GraphSAGE; if it doesn't train in time, fall back to Cypher mule-ring query and call it graph-based detection (it is).

### Tasks

- [x] Create repo with structure from [Repository Structure](#repository-structure)
- [x] Set up `.env.example` with all config keys
- [ ] Establish branch strategy: `main` (working only) / `dev` (integration) / `feature/<name>`
- [ ] Install pre-commit hooks: `black + ruff`
- [x] Create `pyproject.toml` with all dependencies pinned
- [x] Set up CI smoke test (GitHub Actions): `docker compose up && pytest tests/smoke`
- [x] Assign owners for each sprint
- [ ] Create project board (GitHub Projects or Linear) with these sprints as columns

### Definition of Done

- [x] All 7 decisions documented in `docs/decisions.md`
- [ ] Repo cloneable; `poetry install` succeeds
- [ ] CI green on empty repo

### Deliverable

Locked scope doc + working repo skeleton.

---

## Sprint 1 — Infrastructure

**Goal:** Full local stack running via Docker Compose, smoke-tested.
**Effort:** 3
**Depends on:** Sprint 0
**Owner:** Dev A (Infra)

### Tech spec

`docker-compose.yml`:

```yaml
version: "3.9"
services:
  zookeeper:
    image: confluentinc/cp-zookeeper:7.5.0
    environment:
      ZOOKEEPER_CLIENT_PORT: 2181

  kafka:
    image: confluentinc/cp-kafka:7.5.0
    depends_on: [zookeeper]
    ports: ["9092:9092"]
    environment:
      KAFKA_BROKER_ID: 1
      KAFKA_ZOOKEEPER_CONNECT: zookeeper:2181
      KAFKA_LISTENERS: PLAINTEXT://0.0.0.0:9092
      KAFKA_ADVERTISED_LISTENERS: PLAINTEXT://localhost:9092
      KAFKA_OFFSETS_TOPIC_REPLICATION_FACTOR: 1

  redis:
    image: redis:7-alpine
    ports: ["6379:6379"]
    command:
      [
        "redis-server",
        "--maxmemory",
        "512mb",
        "--maxmemory-policy",
        "allkeys-lru",
      ]

  neo4j:
    image: neo4j:5.15-community
    ports: ["7474:7474", "7687:7687"]
    environment:
      NEO4J_AUTH: neo4j/sentinelpass
      NEO4J_PLUGINS: '["graph-data-science"]'

  postgres:
    image: postgres:16-alpine
    ports: ["5432:5432"]
    environment:
      POSTGRES_USER: sentinel
      POSTGRES_PASSWORD: sentinel
      POSTGRES_DB: sentinel_audit

  mlflow:
    image: ghcr.io/mlflow/mlflow:v2.13.0
    ports: ["5000:5000"]
    command: mlflow server --host 0.0.0.0 --backend-store-uri sqlite:///mlflow.db
```

Kafka topics to create:

- `sentinel.transactions` — 3 partitions, ingestion
- `sentinel.verdicts` — 3 partitions, output
- `sentinel.retraining` — 1 partition, feedback loop
- `sentinel.otp_events` — 1 partition, OTP lifecycle

### Tasks

- [x] Write `docker-compose.yml` per above
- [x] Write `scripts/init_kafka.sh` to create all 4 topics
- [x] Verify Kafka: `docker exec ... kafka-topics --list`
- [x] Verify Redis: `redis-cli ping` → `PONG`
- [x] Verify Neo4j: http://localhost:7474 loads, login works
- [x] Verify PostgreSQL: `psql -U sentinel -d sentinel_audit -c '\dt'`
- [x] Verify MLflow: http://localhost:5000 loads
- [x] Write `tests/smoke/test_infra.py` — pings every service
- [x] Add `docker compose down -v && docker compose up -d` to `scripts/reset.sh`

### Definition of Done

- [x] All 5 services green in `docker compose ps`
- [x] Smoke test passes from a clean machine
- [x] All Kafka topics exist
- [x] README quick-start works end-to-end through this point

### Deliverable

Reproducible local infrastructure.

---

## Sprint 2 — Data Schemas & Generator

> ⚠️ **REAL DATA FORMAT UNKNOWN — adapter pattern in use.**
> `orchestrator/schemas.py` defines SENTINEL's internal working model (`TransactionEvent`).
> All field names are provisional best-guesses. When the real data spec is confirmed,
> **only update `data/adapters/real_data_adapter.py`** — fill in `_FIELD_MAP`,
> `_TX_TYPE_MAP`, and `_ACCT_TYPE_MAP`. No agent or orchestrator code needs to change.

**Goal:** Frozen schemas + synthetic data generator producing 100K realistic Nepal-context transactions.
**Effort:** 5
**Depends on:** Sprint 1
**Owner:** Dev A (Infra/Data)

### Tech spec

`orchestrator/schemas.py`:

```python
from pydantic import BaseModel, Field
from typing import Literal, Optional
from datetime import datetime
from uuid import UUID

class TransactionEvent(BaseModel):
    transaction_id: UUID
    account_id: str
    timestamp: datetime
    amount_npr: float
    currency: str = "NPR"
    transaction_type: Literal["P2P", "QR_ESEWA", "SWIFT_REMITTANCE", "ATM_POS"]
    counterparty_id: Optional[str]
    counterparty_name: Optional[str]

    device_id: str
    ip_address: str
    geo_lat: float
    geo_lon: float
    geo_city: str
    geo_district: str

    account_age_days: int
    account_home_district: str
    account_type: Literal["SAVINGS", "CURRENT", "SALARY", "REMITTANCE"]

class AgentScore(BaseModel):
    agent: Literal["velocity", "geo", "behavior", "gnn"]
    score: float = Field(ge=0.0, le=1.0)
    reason_codes: list[str]
    latency_ms: float

class SynthesisVerdict(BaseModel):
    transaction_id: UUID
    composite_score: float
    verdict: Literal["ALLOW", "OTP_INTERLOCK", "BLOCK"]
    agent_scores: list[AgentScore]
    weights_used: dict[str, float]
    transaction_type: str
    total_latency_ms: float
```

Fraud taxonomy to generate (concept paper Section 2.2):

| Type                  | Pattern to inject                                                 |
| --------------------- | ----------------------------------------------------------------- |
| `sim_swap_esewa`      | 2am, unknown merchant, new device, distant district, NPR 50K–100K |
| `velocity_burst`      | 10+ tx in 90 seconds, small amounts                               |
| `remittance_mule`     | 3+ source accounts → 1 mule → 1 destination within 2h             |
| `new_device_takeover` | Unknown device, first transaction high-value                      |
| `geo_impossible`      | Two tx 800+ km apart within 1h                                    |
| `synthetic_identity`  | New account, no prior history, immediate large outbound           |

Districts list:

```python
NEPAL_DISTRICTS = ["Kathmandu", "Lalitpur", "Bhaktapur", "Pokhara", "Dharan",
                   "Biratnagar", "Birgunj", "Butwal", "Nepalgunj", "Dhangadhi"]
URBAN_DISTRICTS = {"Kathmandu", "Lalitpur", "Bhaktapur", "Pokhara"}
```

### Tasks

- [x] Implement `orchestrator/schemas.py` with all Pydantic models above
- [x] Write `data/generators/generate_accounts.py` (5,000 accounts with realistic distributions)
- [x] Write `data/generators/generate_legitimate.py` (normal transaction patterns)
- [x] Write `data/generators/generate_fraud.py` (six fraud taxonomy patterns)
- [x] Write `data/generators/generate.py` — orchestrates all generation
- [x] Hard-code the "Sita" account explicitly per concept paper scenario
- [x] Output `data/seeds/accounts.parquet` and `data/seeds/transactions.parquet`
- [x] Output `data/seeds/labels.parquet` (fraud ground truth)
- [x] Write `data/generators/replay.py` — Kafka producer that streams parquet at configurable TPS
- [x] Validate: histograms of amount, hour-of-day, district, transaction_type look realistic
- [x] Document schema in `docs/schemas.md` — this is the contract every agent depends on

### Definition of Done

- [x] `python data/generators/generate.py` produces 100K transactions
- [x] Fraud rate within 1.5%–2.5%
- [x] All six fraud types represented
- [x] Sita account exists with hand-crafted history
- [x] Replay script publishes to Kafka at 1000+ TPS without errors
- [x] Schema doc reviewed by all devs — no changes after this point

### Deliverable

Locked schemas + reproducible synthetic dataset.

---

## Sprint 3 — Velocity Agent

**Goal:** Sliding-window frequency + amount anomaly detection via Redis. P99 latency < 30 ms.
**Effort:** 3
**Depends on:** Sprint 2
**Owner:** Dev B (Heuristic agents)

### Tech spec

Windows and burst multipliers:

```python
WINDOWS = {"2m": 120, "10m": 600, "1h": 3600, "24h": 86400}
BURST_MULTIPLIERS = {"2m": 5.0, "10m": 4.0, "1h": 3.0, "24h": 2.0}
```

Redis keys:

- `vel:{account_id}` — sorted set of (tx_id → timestamp), TTL 24h
- `velavg:{account_id}:{window}` — historical count baseline
- `amtavg:{account_id}` — historical mean amount

### Tasks

- [x] Implement `agents/velocity/agent.py` with `score(tx) -> AgentScore`
- [x] Use `ZADD` for insertion, `ZCOUNT` for window count, `EXPIRE` for TTL
- [x] Compute frequency anomaly: `count / historical_avg` per window
- [x] Compute amount anomaly: `tx.amount / historical_avg_amount`
- [x] Combine into final score using max across signals (not sum — avoid score inflation)
- [x] Emit reason codes: `freq_burst_2m:count=15_avg=2`, `amount_spike:70x`
- [x] Write `ml/training/build_velocity_baselines.py` — computes per-account historical baselines from seed data, populates Redis
- [x] Add latency instrumentation: `time.perf_counter()` at entry/exit
- [x] Write unit tests in `tests/agents/test_velocity.py`:
  - [x] Empty history → low score
  - [x] 10 tx in 60s → high frequency score
  - [x] 100× amount spike → high amount score
  - [x] Mixed signals → max of components

### Definition of Done

- [x] Unit tests pass
- [x] Latency P99 < 30 ms on synthetic data
- [x] Detects all `velocity_burst` fraud cases in test set (recall 100% on this fraud type)
- [x] False positive rate on legitimate tx < 5%

### Deliverable

`agents/velocity/agent.py` — production-ready scoring function.

---

## Sprint 4 — Geo Agent

**Goal:** New-device, geo-impossibility, IP-reputation, SIM-recency signals. P99 latency < 40 ms.
**Effort:** 3
**Depends on:** Sprint 2
**Owner:** Dev B (Heuristic agents)

### Tech spec

Signals and scoring:

| Signal                  | Trigger                                       | Score Impact                             |
| ----------------------- | --------------------------------------------- | ---------------------------------------- |
| New device              | `device_id` not in account's history          | 0.50 (new account) to 0.80 (established) |
| Geo-velocity impossible | Implied speed > 800 km/h between tx           | 0.95                                     |
| VPN/Proxy IP            | IP in known VPN ranges                        | +0.15 (additive)                         |
| SIM recency             | SIM changed within 48h (mocked for hackathon) | 0.92                                     |

Redis cache:

- `geo:hist:{account_id}` — JSON blob with known devices + last 5 tx locations

### Tasks

- [x] Implement `agents/geo/agent.py` with `score(tx, account_history) -> AgentScore`
- [x] Use `geopy.distance.geodesic` for distance calculation
- [x] Implement device set lookup (check `tx.device_id in account_history.known_devices`)
- [x] Implement geo-velocity check from last transaction
- [x] Implement IP reputation check — use IP2Proxy free DB or hardcode a few ranges
- [x] Implement SIM-recency mock — Redis key `sim_changed:{account_id}` with TTL 48h
- [x] Write `scripts/seed_geo_history.py` to populate `geo:hist:*` from seed data
- [x] Emit reason codes: `new_device`, `geo_velocity_impossible:1200kmh`, `vpn_or_proxy`, `sim_changed_recently`
- [x] Write unit tests in `tests/agents/test_geo.py`:
  - [x] Same device, same city → low score
  - [x] New device → 0.65+
  - [x] Kathmandu → Dharan in 30 min → 0.95+ (this is Sita's case!)
  - [x] VPN IP → premium added

### Definition of Done

- [x] Unit tests pass including the Sita Kathmandu→Dharan case
- [ ] Latency P99 < 40 ms
- [ ] Detects all `new_device_takeover` and `geo_impossible` fraud cases
- [ ] False positive rate on legitimate tx < 5%

### Deliverable

`agents/geo/agent.py` — production-ready scoring function.

---

## Sprint 5 — Behavior Agent (ML)

**Goal:** Per-cohort LSTM + Isolation Forest ensemble. P99 latency < 80 ms.
**Effort:** 13 _(largest sprint — consider splitting if a single owner)_
**Depends on:** Sprint 2, Sprint 6 (cohort assignment)
**Owner:** Dev C (ML lead)

### Tech spec

**Features per transaction (input to both models):**

- `amount_npr` (log-transformed)
- `hour_of_day` (cyclical: sin/cos)
- `day_of_week` (cyclical)
- `is_weekend` (binary)
- `amount_zscore_vs_account_avg`
- `inter_tx_interval_seconds`
- `merchant_seen_before` (binary)
- `transaction_type` (one-hot, 4 dims)

**Isolation Forest config:**

```python
IsolationForest(n_estimators=200, contamination=0.02, random_state=42)
```

**LSTM architecture:**

```python
class BehaviorLSTM(nn.Module):
    def __init__(self, input_dim=11, hidden_dim=64):
        super().__init__()
        self.lstm = nn.LSTM(input_dim, hidden_dim, num_layers=2,
                            batch_first=True, dropout=0.2)
        self.head = nn.Sequential(
            nn.Linear(hidden_dim, 32), nn.ReLU(),
            nn.Linear(32, 1), nn.Sigmoid()
        )
    def forward(self, x):
        out, _ = self.lstm(x)
        return self.head(out[:, -1, :])
```

Sequence length: last 20 transactions. Training: BCE loss, Adam lr=1e-3, 20 epochs, batch 64.

**Ensemble at inference:**

```python
combined = 0.6 * lstm_score + 0.4 * if_score
```

**One model per cohort** (~5–10 cohorts total). At inference, route by account's cohort.

### Tasks

- [x] Write `ml/training/featurize.py` — builds feature matrix from transactions parquet
- [x] Write `ml/training/train_isolation_forest.py` — trains one IF per cohort, logs to MLflow
- [x] Write `ml/training/train_lstm.py`:
  - [x] `TxSequenceDataset` class — yields (last_20_tx, label) pairs
  - [x] `BehaviorLSTM` model class
  - [x] Training loop with train/val split (80/20)
  - [x] Save best checkpoint per cohort
  - [x] Log to MLflow with metrics (AUC, recall@2%fpr)
- [x] Write `scripts/train_all_models.sh` — runs both training scripts for all cohorts
- [x] Implement `agents/behavior/agent.py`:
  - [x] Load all cohort models on init
  - [x] `score(tx, account_meta)` method
  - [x] Load last-20-tx sequence from Redis (`behavior:seq:{account_id}`)
  - [x] Run IF + LSTM, combine
  - [x] Build reason codes from feature contributions
- [x] Implement Redis sequence cache update (write-through on every transaction)
- [x] Cold-start fallback: if sequence < 5 tx, use IF only
- [x] Latency instrumentation
- [ ] Write unit tests:
  - [ ] Sita's 2am NPR 85K → score > 0.85
  - [ ] Sita's normal 11am NPR 1.5K → score < 0.3
  - [ ] New account (< 5 tx history) → IF-only fallback works

### Definition of Done

- [ ] All cohort models trained and saved to `ml/artifacts/`
- [ ] MLflow shows runs for each cohort with metrics
- [ ] Inference P99 < 80 ms
- [ ] Recall > 90% on labeled fraud
- [ ] Sita scenario scores > 0.85

### Deliverable

`agents/behavior/agent.py` + trained models + MLflow runs.

---

## Sprint 6 — Cold-Start Cohort System

**Goal:** Implement the 4-stage cohort onboarding from concept paper Section 4.3.
**Effort:** 3
**Depends on:** Sprint 2
**Owner:** Dev C (ML)

### Tech spec

Cohort assignment rules (first match wins):

```python
COHORT_RULES = [
    ("overseas_worker_remittance", lambda a: a.account_type == "REMITTANCE"),
    ("salary_kathmandu",           lambda a: a.account_type == "SALARY" and a.home_district == "Kathmandu"),
    ("salary_other",               lambda a: a.account_type == "SALARY"),
    ("savings_urban",              lambda a: a.account_type == "SAVINGS" and a.home_district in URBAN_DISTRICTS),
    ("savings_rural",              lambda a: a.account_type == "SAVINGS"),
    ("current_business",           lambda a: a.account_type == "CURRENT"),
    ("fallback",                   lambda a: True),
]
```

4-stage transition by account age:

| Days  | Mode         | Behavior                                          |
| ----- | ------------ | ------------------------------------------------- |
| 0–3   | Strict rules | Behavior agent abstains; NRB rule limits enforced |
| 4–14  | Cohort       | 100% cohort model weight                          |
| 15–30 | Hybrid       | Linear blend: `personal_weight = (age - 14) / 16` |
| 31+   | Personal     | Hackathon shortcut: stay on cohort model          |

### Tasks

- [x] Implement `ml/cohorts/assign.py` with `assign_cohort(account) -> str`
- [x] Implement `ml/cohorts/onboarding.py` with `compute_blend_weights(age_days) -> dict`
- [ ] Wire cohort assignment into account metadata at account creation
- [ ] Store cohort in Postgres `accounts` table
- [ ] Cache cohort in Redis `cohort:{account_id}` for O(1) lookup
- [x] Integrate blend weights into behavior agent (Sprint 5)
- [x] Build rule-engine fallback for days 0–3 (simple NRB-style amount caps)
- [ ] Generate per-cohort statistics for the demo dashboard
- [ ] Write tests:
  - [ ] Overseas worker → `overseas_worker_remittance` cohort
  - [ ] Day 2 account → rules-only mode, behavior abstains
  - [ ] Day 20 account → hybrid mode with correct weights
  - [ ] Sita's case (720 days old) → personal/cohort mode

### Definition of Done

- [ ] All cohorts assigned to seed accounts
- [ ] Each cohort has > 200 accounts (sufficient for training)
- [ ] Blend logic verified across all 4 stages
- [ ] Rules-only fallback blocks anomalous day-1 transactions correctly

### Deliverable

`ml/cohorts/` module + cohort field in account records.

---

## Sprint 7 — Graph Layer (Neo4j + GNN)

**Goal:** Account graph in Neo4j + mule-ring detection (GraphSAGE or Cypher fallback).
**Effort:** 8
**Depends on:** Sprint 2
**Owner:** Dev C (ML) or Dev D (depending on bandwidth)

### Tech spec

Graph schema:

- Nodes: `(:Account {id, type, district, age_days})`
- Edges: `[:TRANSFERRED {amount, timestamp}]`

Mule-ring Cypher (fallback if GNN doesn't train):

```cypher
MATCH (sources:Account)-[t1:TRANSFERRED]->(mule:Account)-[t2:TRANSFERRED]->(dest:Account)
WHERE t1.timestamp > datetime() - duration('P1D')
  AND t2.timestamp > t1.timestamp
  AND t2.timestamp < t1.timestamp + duration('PT2H')
WITH mule, dest,
     count(DISTINCT sources) AS source_count,
     sum(t1.amount) AS inflow,
     sum(t2.amount) AS outflow
WHERE source_count >= 3 AND outflow >= 0.7 * inflow
RETURN mule.id, dest.id, source_count, inflow, outflow
```

GraphSAGE config:

```python
class MuleSAGE(torch.nn.Module):
    def __init__(self, in_dim=8, hidden_dim=32, out_dim=16):
        super().__init__()
        self.conv1 = SAGEConv(in_dim, hidden_dim)
        self.conv2 = SAGEConv(hidden_dim, out_dim)
    def forward(self, x, edge_index):
        x = self.conv1(x, edge_index).relu()
        x = self.conv2(x, edge_index)
        return torch.sigmoid(x)
```

Node features: degree, total inflow, total outflow, distinct counterparties, account_age, account_type one-hot.

### Tasks

- [x] Write `graph/setup.cypher` — schema + indexes
- [x] Write `graph/load_data.py` — exports accounts/tx to CSV, loads via `LOAD CSV`
- [ ] Verify graph loaded: `MATCH (n) RETURN count(n)` returns 5000
- [ ] Write `graph/mule_detection.cypher` (above) and test on seed mule patterns
- [x] Wrap query in `agents/gnn/cypher_agent.py` as a fallback scorer
- [ ] (Stretch) Write `graph/train_gnn.py`:
  - [ ] Build feature matrix from graph
  - [ ] Train GraphSAGE on labeled accounts (mule vs not)
  - [ ] Save embeddings, save model
- [ ] (Stretch) Implement `agents/gnn/agent.py` using trained GraphSAGE
- [ ] Decision point: if GNN AUC < 0.85 after 1 day of training, ship Cypher version
- [x] Latency: query result cached in Redis (`gnn:{account_id}`, TTL 1h), refreshed by batch job

### Definition of Done

- [ ] Graph loaded with all accounts + edges
- [ ] Cypher mule query returns expected fraud rings from seed data
- [ ] Either GraphSAGE running or Cypher fallback shipped — one of them in `agents/gnn/`
- [ ] Latency P99 < 100 ms (using cached scores)

### Deliverable

`agents/gnn/agent.py` — graph-based scoring (GNN or Cypher).

---

## Sprint 8 — Synthesis Agent

**Goal:** Context-aware weighted voting with verdict thresholds. The track's headline innovation requirement.
**Effort:** 2
**Depends on:** Sprints 3, 4, 5, 7 (needs all agent score outputs to wire to)
**Owner:** Dev D

### Tech spec

Weight matrix (concept paper Section 3.2.4):

| Transaction Type   | Velocity | Geo  | Behavior | GNN  |
| ------------------ | -------- | ---- | -------- | ---- |
| `P2P`              | 0.20     | 0.30 | 0.30     | 0.20 |
| `QR_ESEWA`         | 0.35     | 0.40 | 0.25     | 0.00 |
| `SWIFT_REMITTANCE` | 0.15     | 0.25 | 0.20     | 0.40 |
| `ATM_POS`          | 0.30     | 0.45 | 0.25     | 0.00 |

Thresholds:

- `composite < 0.40` → `ALLOW`
- `0.40 ≤ composite < 0.75` → `OTP_INTERLOCK`
- `composite ≥ 0.75` → `BLOCK`

### Tasks

- [x] Implement `agents/synthesis/agent.py` with `synthesize(tx, scores) -> SynthesisVerdict`
- [x] Hard-code `WEIGHTS_BY_TYPE` table
- [x] Compute composite as `sum(weights[a] * scores[a])`
- [x] Apply threshold logic for verdict
- [x] Include `weights_used` in output (essential for dashboard visualization)
- [x] Handle edge case: missing agent score → use 0.5 (neutral) and emit reason `agent_unavailable`
- [x] Latency target: < 20 ms (it's just arithmetic)
- [x] Unit tests:
  - [x] QR transaction with all-high scores → BLOCK with QR weights
  - [x] SWIFT transaction → GNN weight dominates
  - [x] Sita scenario (high scores, QR_ESEWA) → composite ~0.91, verdict OTP_INTERLOCK
  - [x] All-low scores → ALLOW
  - [x] Mid-range composite → OTP_INTERLOCK

### Definition of Done

- [x] All weight combinations tested
- [x] Sita scenario verdict reproducible: OTP_INTERLOCK, composite 0.85–0.95
- [ ] Latency < 20 ms

### Deliverable

`agents/synthesis/agent.py` — the system's analytical brain.

---

## Sprint 9 — OTP Interlock

**Goal:** Dual-path verification (Email + SMS) with SIM-swap detection logic.
**Effort:** 5
**Depends on:** Sprint 2 (schemas only; can start anytime after)
**Owner:** Dev B

### Tech spec

Provider abstraction:

```python
class OTPProvider(Protocol):
    def send(self, recipient: str, code: str) -> bool: ...
```

Three implementations:

- `MockProvider` — writes to Redis + console (default for demo)
- `TwilioProvider` — uses `twilio.rest.Client` (for the bonus demo shot)
- `SparrowProvider` — POSTs to sparrowsms.com API (production-target)

State machine for `confirm(tx_id, sms_attempt, email_attempt)`:

| SMS OK | Email OK | Verdict                |
| ------ | -------- | ---------------------- |
| ✓      | ✓        | RELEASE                |
| ✗      | ✓        | BLOCK + sim_swap_alert |
| ✓      | ✗        | HUMAN_REVIEW           |
| ✗      | ✗        | BLOCK + both_failed    |

OTP storage: `otp_pending:{tx_id}` in Redis with TTL 300s, value = `{sms_otp, email_otp, customer_phone, customer_email}`.

### Tasks

- [x] Implement `agents/otp/providers.py` with all three classes
- [x] Implement `agents/otp/interlock.py`:
  - [x] `trigger(tx, customer)` — freezes tx, generates 2 OTPs, sends both
  - [x] `confirm(tx_id, sms, email)` — state machine above
  - [x] `_freeze_transaction(tx)` — writes hold record to Postgres
  - [x] `_unfreeze_and_release(tx_id)` — releases hold
  - [x] `_raise_sim_swap_alert(tx_id)` — writes to `sentinel.otp_events` topic
- [x] Implement SMTP email sending (Gmail relay with app password)
- [x] Add REST endpoint `POST /otp/confirm` for customer to submit codes
- [ ] Latency: dispatch must complete in < 200 ms (async, non-blocking)
- [ ] Unit tests:
  - [ ] Both OTPs correct → RELEASE
  - [ ] Wrong SMS, correct email → BLOCK + sim_swap_alert
  - [ ] Wrong email, correct SMS → HUMAN_REVIEW
  - [ ] Expired OTPs (after 300s) → rejected
- [x] Demo helper: `scripts/show_pending_otps.py` — print active OTPs to terminal during demo

### Definition of Done

- [ ] All four confirm paths tested
- [ ] SIM-swap alert fires correctly on Sita-like attack
- [ ] Mock provider visible in dashboard
- [ ] Twilio path works on at least one real number (one-time test)

### Deliverable

`agents/otp/` module + working dual-path flow.

---

## Sprint 10 — Orchestrator & Kafka Wiring

**Goal:** FastAPI service that consumes Kafka, runs all agents in parallel, emits verdicts.
**Effort:** 5
**Depends on:** Sprints 3, 4, 5, 7, 8, 9 (needs all agents wireable)
**Owner:** Dev A

### Tech spec

```python
# orchestrator/main.py — skeleton
from fastapi import FastAPI, WebSocket
from kafka import KafkaConsumer, KafkaProducer
import asyncio, time

app = FastAPI()
velocity_agent = VelocityAgent()
geo_agent = GeoAgent()
behavior_agent = BehaviorAgent()
gnn_agent = GNNAgent()
synthesis = SynthesisAgent()
interlock = OTPInterlock(...)

ws_clients: set[WebSocket] = set()

async def process_transaction(tx: TransactionEvent):
    t0 = time.perf_counter()
    velocity_t, geo_t, behavior_t, gnn_t = await asyncio.gather(
        asyncio.to_thread(velocity_agent.score, tx),
        asyncio.to_thread(geo_agent.score, tx),
        asyncio.to_thread(behavior_agent.score, tx),
        asyncio.to_thread(gnn_agent.score, tx),
    )
    verdict = synthesis.synthesize(tx, [velocity_t, geo_t, behavior_t, gnn_t])
    verdict.total_latency_ms = (time.perf_counter() - t0) * 1000

    if verdict.verdict == "OTP_INTERLOCK":
        asyncio.create_task(interlock.trigger(tx, get_customer(tx.account_id)))

    producer.send("sentinel.verdicts", verdict.dict())
    await broadcast(verdict)
```

### Tasks

- [x] Implement `orchestrator/main.py` per skeleton above
- [x] Wire all agents (import + instantiate)
- [x] Kafka consumer loop (background task)
- [x] `asyncio.gather` for parallel agent execution — verify with logging
- [x] WebSocket endpoint `/ws/verdicts` for frontend
- [x] REST endpoint `GET /verdicts/{tx_id}` for inspection
- [x] REST endpoint `GET /stats` for dashboard metrics
- [x] Audit log writer: every verdict → Postgres `audit_log` table (async, non-blocking)
- [x] Implement `KAFKA_ENABLED=false` fallback that uses direct REST `POST /score` endpoint
- [x] Error handling: agent timeout (1s budget per agent) → score 0.5 + reason `agent_timeout`
- [ ] Tests:
  - [ ] End-to-end: publish tx → verdict appears on websocket
  - [ ] Parallel execution verified (total time < sum of agent times)
  - [ ] Fallback mode works without Kafka

### Definition of Done

- [ ] Orchestrator runs without errors for 5 minutes under replay load
- [ ] Parallelism confirmed via timing logs (gather overhead < 5 ms)
- [ ] All verdicts written to audit log
- [ ] Latency target: P99 < 380 ms end-to-end

### Deliverable

Running orchestrator service. The system is now functionally complete.

---

## Sprint 11 — MLflow Integration

**Goal:** Model registry, drift detection stub, retraining trigger.
**Effort:** 3
**Depends on:** Sprint 5
**Owner:** Dev C

### Tasks

- [ ] Confirm all training runs from Sprint 5 are logged with params + metrics
- [ ] Register best LSTM and IF models per cohort to MLflow Model Registry
- [ ] Promote each best version to `Production` stage
- [ ] Update agent code to load models by registry name (not file path)
- [ ] Write `ml/monitoring/drift_check.py`:
  - [ ] Computes recall + FPR on rolling 7-day window
  - [ ] Logs metrics to MLflow as new run in `production_metrics` experiment
  - [ ] Triggers alert if recall < 0.92 or FPR > 0.03
- [ ] Write `ml/monitoring/retrain.py` — re-runs Sprint 5 training pipeline (stub)
- [ ] Document model lifecycle in `docs/mlflow.md`
- [ ] (Stretch) A/B testing: route 10% of tx to Staging model, compare

### Definition of Done

- [ ] MLflow UI shows: all experiments, registered models, Production versions
- [ ] Agent code loads from registry, not files
- [ ] Drift check runs successfully on seed data

### Deliverable

MLflow Model Registry populated; drift monitoring stub.

---

## Sprint 12 — Demo Dashboard

**Goal:** React app that shows live transaction stream + agent inspector + Sita button.
**Effort:** 8
**Depends on:** Sprint 10 (needs WebSocket + REST endpoints)
**Owner:** Dev D

### Tech spec

Tech: Vite + React + TypeScript + TailwindCSS + Recharts + native WebSocket.

5 panels:

1. **Live transaction stream** — scrolling list, color-coded by verdict (green/amber/red)
2. **Transaction inspector** — click a row to see all agent scores, reason codes, weights used, composite, threshold bands
3. **Sita scenario button** — fires hardcoded fraud transaction, watch it light up red
4. **OTP Interlock viewer** — pending OTPs, mock SMS/email log, SIM-swap alerts
5. **Stats panel** — TPS, P50/P95/P99 latency charts, fraud-by-type counters, cohort sizes

### Tasks

- [ ] Scaffold Vite + React + TS project in `frontend/`
- [ ] Install Tailwind, Recharts, lucide-react
- [ ] Build `<TransactionStream />` component with WebSocket connection
- [ ] Build `<TransactionInspector />` — shows AgentScore breakdown
  - [ ] Bar chart for each agent's score
  - [ ] Weight pie/bar showing current weights
  - [ ] Reason code list
  - [ ] Threshold band visualization
- [ ] Build `<SitaSceneButton />` — POST to `/scenarios/run/sita` and highlight resulting tx
- [ ] Build `<OTPViewer />` — polls `/otp/pending` every 1s
- [ ] Build `<StatsPanel />`:
  - [ ] Real-time TPS counter
  - [ ] Latency histogram (Recharts)
  - [ ] Fraud-by-type pie chart
  - [ ] Cohort distribution
- [ ] WebSocket reconnection logic + 500ms REST polling fallback
- [ ] Style for projector visibility: high contrast, large fonts, clear color coding
- [ ] Add header with system name + latency badge ("P99: 312ms")
- [ ] Add demo mode toggle: replay speed slider

### Definition of Done

- [ ] All 5 panels render
- [ ] Sita button works end-to-end
- [ ] Looks clean on a projector (test on external monitor)
- [ ] WebSocket survives network blips

### Deliverable

`frontend/` — production-ready demo dashboard.

---

## Sprint 13 — Scenario Testing

**Goal:** Four canonical demo scenarios passing reliably in CI.
**Effort:** 5
**Depends on:** Sprint 10
**Owner:** Dev D + full team review

### Scenarios

#### Scenario 1: Sita (the concept paper's example)

```python
SITA_FRAUD_TX = TransactionEvent(
    account_id="ACC_SITA_001",
    timestamp=datetime(2026, 5, 30, 2, 14),
    amount_npr=85000.0,
    transaction_type="QR_ESEWA",
    counterparty_id="MERCHANT_UNKNOWN_42",
    device_id="device_unknown_new",
    ip_address="103.69.x.x",
    geo_lat=26.8141, geo_lon=87.2792,
    geo_district="Dharan",
    account_home_district="Kathmandu",
    account_age_days=720,
    account_type="SAVINGS",
)
# Expected: OTP_INTERLOCK, composite 0.85-0.95, latency < 400ms
# All 3 agents flag high, weights = QR_ESEWA, OTP fires on both channels
```

#### Scenario 2: Legitimate Sita

Normal 11am NPR 1,200 grocery payment from her own device, Kathmandu. Expected: ALLOW.

#### Scenario 3: SIM-swap completion attempt

After Sita scenario triggers OTP, fraudster submits correct SMS (they have her SIM) and wrong email. Expected: BLOCK with `sim_swap_alert`.

#### Scenario 4: Cold-start protection

New `overseas_worker_remittance` account, day 5 of existence. Legitimate inbound remittance → ALLOW (cohort model passes). Then an outbound NPR 90K to unknown account on same day → flagged.

#### Scenario 5 (bonus): Mule ring

5 small accounts each transfer NPR 20K to one new account within 30 min; that account immediately transfers NPR 95K to a sixth destination. Expected: GNN flags, BLOCK.

### Tasks

- [x] Implement all five scenarios in `tests/scenarios/`
- [x] Each scenario: pre-seed account history + Redis state, publish tx, assert verdict
- [x] Wire scenarios to REST endpoint `POST /scenarios/run/{name}` for dashboard button
- [ ] Add scenarios to CI: must pass on every PR
- [ ] Document each scenario in `docs/scenarios.md` with expected outputs
- [ ] Record screen-captures of each running as backup if live demo fails

### Definition of Done

- [ ] All 5 scenarios pass deterministically (no flakes)
- [ ] CI runs scenarios on every commit
- [ ] Video recordings exist for each scenario

### Deliverable

Bulletproof demo scenarios.

---

## Sprint 14 — Load Test & Latency Tuning

**Goal:** Sustained 10K TPS or documented headroom; P99 < 380ms.
**Effort:** 3
**Depends on:** Sprint 10
**Owner:** Dev D

### Tech spec

```python
# tests/load/locustfile.py
from locust import User, task, between

class TransactionUser(User):
    wait_time = between(0.001, 0.01)
    @task
    def submit(self):
        tx = generate_random_tx()
        producer.send("sentinel.transactions", tx.dict())
```

Run: `locust -f tests/load/locustfile.py --headless -u 10000 -r 1000 -t 5m`

### Tasks

- [x] Write locust load script
- [x] Add Prometheus-style metrics: tx processed, latency histogram, agent timing
- [x] Run baseline load test, capture P50/P95/P99
- [x] Identify bottleneck (likely behavior LSTM)
- [x] Tune:
  - [x] Increase Kafka consumer parallelism (more partitions or consumer threads)
  - [x] Use ONNX export for LSTM if PyTorch inference too slow
  - [x] Batch behavior agent inference (process 16 tx at a time)
  - [x] Redis pipelining for velocity agent
- [x] Re-run, document new numbers
- [x] Create one performance slide: TPS sustained, P99 latency, headroom analysis

### Definition of Done

- [x] At least 3000 TPS sustained on the demo laptop
- [x] P99 latency < 380 ms
- [x] Performance slide ready

### Deliverable

Real measured numbers for the demo.

---

## Sprint 15 — Demo Day Prep

**Goal:** Rehearsed 8-minute demo, slide deck, backup plan, hotel-wifi-proof.
**Effort:** 3
**Depends on:** Sprints 12, 13, 14
**Owner:** Tech lead + Dev D

### 8-Minute Demo Script

| Minute | Beat                                                                                                    |
| ------ | ------------------------------------------------------------------------------------------------------- |
| 0–1    | Intro: Track B asked for X. We built SENTINEL. Show dashboard.                                          |
| 1–3    | Live legitimate traffic flowing. P50 ~80ms visible. 600 TPS.                                            |
| 3–5    | Press Sita button. Walk through agent inspector. "0.91 composite. 312ms. 39% of budget."                |
| 5–6    | SIM-swap attempt. Correct SMS, wrong email → BLOCK. "Challenge 4 solved."                               |
| 6–7    | Cold-start: new overseas-worker account day 5. Legit → ALLOW via cohort. "Challenge 3 solved on day 5." |
| 7–8    | MLflow registry shown. Stats slide: 97% recall, 1.8% FPR, P99 380ms. "Ready for shadow mode."           |

### Tasks

- [ ] Build 12-slide deck:
  - [ ] Title slide
  - [ ] The Sita scenario (concept paper screenshot)
  - [ ] Architecture diagram
  - [ ] 4 Challenges + our solutions (one slide each = 4 slides)
  - [ ] Tech stack mapped to track requirements
  - [ ] Latency numbers
  - [ ] Detection metrics
  - [ ] Deployment roadmap (Phase 1/2/3 from concept paper)
  - [ ] Closing slide
- [ ] Cloud failover deployment: deploy entire stack to a single VM (DigitalOcean droplet or AWS EC2 t3.large) as backup
- [ ] Rehearse demo: minimum 3 full run-throughs
- [ ] Time each rehearsal — must fit in 8 minutes
- [ ] Prepare Q&A:
  - [ ] "How do you handle GIBL's real data?" → Shadow mode design, Section 7
  - [ ] "What about adversarial ML attacks?" → MLflow drift detection + ensemble robustness
  - [ ] "How do you avoid bias?" → Section 9.1 fairness audits
  - [ ] "Why these specific weights?" → Domain reasoning per transaction type
- [ ] Pre-warm laptop 30 min before demo: replay traffic, fill caches
- [ ] Record screen of full demo as fallback video
- [ ] Print one-page handout: architecture diagram + key numbers

### Definition of Done

- [ ] Slides finalized
- [ ] 3+ rehearsals completed under 8 minutes
- [ ] Cloud backup live and tested
- [ ] Video recording exists
- [ ] Q&A prep doc shared

### Deliverable

A demo that lands.

---

## Time-Compressed Tracks

Pick based on time available:

### Compressed 3-day track (hackathon-only build)

If pre-build isn't allowed and you only have May 29–31:

**Day 1:** Sprints 0, 1, 2 (foundation) + Sprints 3, 4, 9 in parallel
**Day 2:** Sprint 5 (lighter version — single global model, skip per-cohort), Sprints 6, 7 (Cypher only, skip GNN), 8, 10
**Day 3:** Sprints 12 (lighter dashboard — 3 panels), 13 (Sita + SIM-swap only), 15 (demo prep)

Cut: MLflow registry (Sprint 11), heavy load test (Sprint 14), GraphSAGE (Sprint 7 stretch), per-cohort LSTM, scenarios 4–5.

### Compressed 5-day track

Add back: per-cohort behavior models, cold-start scenario, basic MLflow logging.

### Compressed 7-day track

Add back: GraphSAGE attempt, full dashboard, load test, scenarios 4 and 5.

### Full track (10+ days)

Run as written above.

---

## Team Roles

| Role                                    | Owns Sprints      | Skills needed                       |
| --------------------------------------- | ----------------- | ----------------------------------- |
| **Dev A — Infra/Data**                  | 1, 2, 10          | Docker, Kafka, FastAPI, Postgres    |
| **Dev B — Heuristic + OTP**             | 3, 4, 9           | Redis, Python, basic state machines |
| **Dev C — ML lead**                     | 5, 6, 7, 11       | PyTorch, sklearn, MLflow, Neo4j     |
| **Dev D — Synthesis + Frontend + Demo** | 8, 12, 13, 14, 15 | React, design sense, presentation   |

Sync cadence:

- Daily 15-min standup
- After each completed sprint: 30-min integration check

---

## Risk Register

| Risk                                       | Impact | Mitigation                                                    |
| ------------------------------------------ | ------ | ------------------------------------------------------------- |
| Kafka crashes during demo                  | High   | `KAFKA_ENABLED=false` direct-call fallback                    |
| LSTM doesn't train well                    | Medium | Ship with IF-only behavior agent; mark LSTM as "in progress"  |
| GNN doesn't train                          | Low    | Cypher mule query is graph-based detection, no apologies      |
| Twilio trial credit exhausted              | Low    | Mock provider is primary; real SMS is bonus                   |
| Demo laptop hardware failure               | High   | Cloud failover stack on standby                               |
| Hotel wifi flakes                          | Medium | Demo from local; cloud is backup only                         |
| Frontend WebSocket flakes                  | Medium | REST polling fallback every 500ms                             |
| Latency spikes when judges watch           | High   | Pre-warm with 30s traffic before demo                         |
| Judges question real GIBL data integration | Low    | "Shadow mode per Section 7 of concept paper"                  |
| Per-cohort training takes too long         | Medium | Train top 3 cohorts well, others use fallback global model    |
| One dev gets sick                          | High   | Pair-program key sprints; ensure 2 people know each component |

---

## Glossary

- **Cohort** — Group of similar accounts (e.g., `overseas_worker_remittance`) sharing pretrained ML models for cold-start protection.
- **Composite score** — Final fraud risk score in [0, 1] from Synthesis Agent.
- **Cold start** — A new account with insufficient personal transaction history to use personalized ML.
- **GraphSAGE** — Inductive graph neural network for learning node embeddings; used here for mule-ring detection.
- **Isolation Forest** — Unsupervised anomaly detection algorithm; high score = anomalous.
- **MLflow** — Open-source platform for ML lifecycle (tracking, models, registry, deployment).
- **OTP Interlock** — Dual-path verification step (Email + SMS) triggered for medium-risk transactions.
- **P99 latency** — 99th percentile end-to-end latency; the standard latency SLO.
- **SIM swap** — Attacker obtains a duplicate SIM for victim's number, intercepts SMS OTPs.
- **Synthesis Agent** — The component that aggregates the four agent scores using context-aware weights.
- **TPS** — Transactions per second; throughput metric.
- **Velocity** — Transaction frequency over a sliding time window.
- **NRB** — Nepal Rastra Bank, the central bank.
- **FIU** — Financial Intelligence Unit Nepal.
- **STR** — Suspicious Transaction Report filed with FIU.

---

## References

See concept paper Section 11 for full bibliography.

Key implementation references:

- Hochreiter & Schmidhuber (1997) — LSTM
- Liu, Ting, Zhou (2008) — Isolation Forest
- Hamilton, Ying, Leskovec (2017) — GraphSAGE
- MLflow docs: https://mlflow.org/docs/latest/
- Kafka Python: https://kafka-python.readthedocs.io
- PyTorch Geometric: https://pytorch-geometric.readthedocs.io

---

_Built for the Global IME AI/ML Hackathon 2026, Track B._
# Sentinel
