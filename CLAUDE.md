# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

SENTINEL is a multi-agent, real-time fraud-detection framework for Nepal's banking sector (Global IME AI/ML Hackathon 2026, Track B). A transaction is scored in parallel by four specialized agents, their scores are fused by a **context-aware weighted vote** that depends on transaction type, and the resulting composite score routes to one of three verdicts: `ALLOW`, `OTP_INTERLOCK`, or `BLOCK`.

## Commands

Dependencies are managed with **Poetry** (`pyproject.toml`), though docs invoke scripts with plain `python3`/`pytest`. The `.venv/` in the repo is a local interpreter.

```bash
# Full stack (data + models + 8 docker services + frontend)
bash scripts/start_all.sh          # auto-generates seed data & trains models if missing
docker compose down [-v]           # stop (-v also wipes volumes)

# Local dev: dockerized infra + local orchestrator
docker compose up -d zookeeper kafka redis neo4j postgres mlflow
poetry install
poetry run uvicorn orchestrator.main:app --reload --port 8000
cd frontend && npm install && npm run dev   # Vite dev server

# Data & models (one-time, before first run)
python3 data/generators/generate.py --accounts 5000   # → data/seeds/*.parquet
bash scripts/train_all_models.sh                       # → ml/artifacts/*.pt, *.pkl (per cohort)

# Tests
python3 -m pytest tests/ -v
python3 -m pytest tests/agents/ -v                     # fast unit tests
python3 -m pytest tests/scenarios/ -v                  # end-to-end (need full stack)
python3 -m pytest tests/scenarios/sita.py -v           # single scenario

# Load test
locust -f tests/load/locustfile.py --headless -u 500 -r 100 -t 60s --host http://localhost:8000

# Live demo stream
python3 data/generators/replay.py                      # replays transactions through Kafka

# Lint / format (line-length 100; pre-commit configured)
poetry run ruff check . --fix
poetry run black .
```

Scenario test files (`sita.py`, `sim_swap.py`, `cold_start.py`, `mule_ring.py`) are **not** named `test_*` — they're registered as pytest files explicitly in `pyproject.toml [tool.pytest.ini_options].python_files`. Tests rely on the root `conftest.py` putting the repo root on `sys.path`.

Services: Dashboard `:3000`, Orchestrator `:8000` (`/docs`), MLflow `:5050`, Neo4j `:7474` (`neo4j/sentinelpass`), Postgres `:5432`, Redis `:6379`, Kafka `:9092`.

## Architecture

### Request flow
`orchestrator/main.py` is the single entry point (FastAPI). Transactions arrive either via the **Kafka consumer loop** (`sentinel.transactions` topic) or the **`POST /score`** endpoint (used when `KAFKA_ENABLED=false`). Both paths normalize the raw payload through the adapter, then call `process_transaction()`, which:

1. Runs Velocity, Geo, Behavior, and GNN agents **in parallel** via `asyncio.gather` + `asyncio.to_thread` (agents are sync), each with a 1s `AGENT_TIMEOUT`. A timed-out agent returns a neutral score of `0.5`.
2. Fuses scores in `SynthesisAgent.synthesize()`.
3. If verdict is `OTP_INTERLOCK`, fires `OTPInterlock.trigger()` as a background task.
4. Publishes the verdict to Kafka `sentinel.verdicts`, writes a Postgres audit row, broadcasts over the `/ws/verdicts` WebSocket, and appends to in-memory ring buffers backing `GET /stats`.

Audit writes and OTP triggers are fire-and-forget (`asyncio.create_task`) — **failures there must never block or change a verdict**.

### The agents (`agents/<name>/agent.py`)
- **velocity** — Redis sliding-window transaction-rate counters.
- **geo** — heuristic geo-velocity / device-fingerprint, backed by Redis history.
- **behavior** — per-cohort LSTM + Isolation Forest ensemble (the slowest agent, ~68ms).
- **gnn** (`gnn/cypher_agent.py`) — Cypher-based mule-ring detection against Neo4j; degrades gracefully if Neo4j is down.

Every agent exposes a sync `score(tx) -> AgentScore`. Agent identity is `AGENT_NAME` or derived from the class name. To add an agent, register it in `process_transaction`'s `gather` **and** add its weight to every entry of `WEIGHTS_BY_TYPE`.

### Synthesis = the core innovation (`agents/synthesis/agent.py`)
`WEIGHTS_BY_TYPE` maps transaction type → per-agent weight vector. e.g. QR/eSewa weights Geo at 0.40 and GNN at 0.00; SWIFT remittance weights GNN at 0.40 for money-mule detection. Unknown types fall back to `_FALLBACK_WEIGHTS`. Composite = weighted sum, clamped to [0,1]. Thresholds: `< 0.40` → `ALLOW`, `< 0.75` → `OTP_INTERLOCK`, else `BLOCK`. Missing agents are imputed to `0.5`.

### OTP Interlock (`agents/otp/interlock.py`)
Dual-path verification (SMS + Email), both codes stored in Redis with a 300s TTL, the transaction frozen via a `tx_hold:*` key. `confirm()` is a deliberate state machine: **SMS✓+Email✓→RELEASE; SMS✗+Email✓→BLOCK (sim_swap_alert); SMS✓+Email✗→HUMAN_REVIEW; both✗→BLOCK**. The SMS-fails-but-Email-succeeds case is the SIM-swap signal — preserve this asymmetry. Providers live in `agents/otp/providers.py`.

### Cohorts & cold-start (`ml/cohorts/`)
`assign.py` maps an account to one of ~6 cohorts by **first-match rules** (account_type + home_district). Each cohort has its own trained LSTM (`.pt`) and Isolation Forest (`.pkl`) in `ml/artifacts/`. New accounts inherit their cohort's model from day 0 — this is the cold-start strategy. `onboarding.py` handles the staged onboarding; `storage.py` persists assignments.

### Data contract boundary (`data/adapters/real_data_adapter.py`)
`orchestrator/schemas.py` defines `TransactionEvent` / `AgentScore` / `SynthesisVerdict`. **These schemas are provisional** — the real competition data format is unconfirmed. `to_transaction_event()` in the adapter is the *only* place that knows the raw payload shape; everything downstream consumes `TransactionEvent`. When the real format arrives, fill in `_FIELD_MAP` / `_TX_TYPE_MAP` / `_ACCT_TYPE_MAP` in the adapter — **do not** edit `schemas.py` directly. `from_synthetic()` ingests the generated parquet rows without remapping.

### Other directories
- `ml/training/` — model training (`train_lstm.py`, `train_isolation_forest.py`, `build_*_baselines.py`, `register_models.py` → MLflow).
- `ml/monitoring/` — `drift_check.py`, `retrain.py`.
- `graph/` — Neo4j setup (`setup.cypher`), data load (`load_data.py`), `mule_detection.cypher`.
- `data/generators/` — synthetic data: accounts, legitimate txns, and injected fraud patterns.
- `tests/scenarios/__init__.py` — `_SCENARIOS` registry (via `@register`), exposed through `POST /scenarios/run/{name}`.
- `frontend/` — React + Vite + Tailwind + Recharts dashboard; consumes REST + `/ws/verdicts`.

## Conventions

- All env-configurable connections default to localhost in code but are overridden by docker-compose env vars (internal hostnames `kafka:29092`, `redis`, `neo4j`, `postgres`). Toggle `KAFKA_ENABLED` to switch between stream and direct-scoring modes.
- Structured logging via `structlog` (JSON). Bind per-transaction context with `log.bind(tx_id=...)`.
- Agents must stay fast and side-effect-free in `score()`; anything slow or external (DB writes, OTP dispatch) belongs in background tasks off the hot path.
