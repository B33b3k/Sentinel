# LEARNING.md — Tech Stack & Concepts Behind SENTINEL

This explains every technology and concept used in SENTINEL: **what it is**, **why we use it here**, and **where to learn it**. Read it top-to-bottom for a full mental model, or jump to a section. Where useful, it points to the file in this repo that uses the thing.

---

## Part A — Core Concepts (the ideas, independent of tech)

### A1. Real-time fraud detection
Scoring a financial transaction for fraud risk *while it happens* (milliseconds), then deciding allow / verify / block. Unlike batch fraud analysis (run overnight), every decision is on the critical path of a live payment, so latency is a hard requirement.
- **Why it matters here:** SENTINEL's headline constraint is a P99 latency budget; the whole architecture (parallel agents, in-memory stores) exists to meet it.
- **Learn:** [Fraud Detection Handbook](https://fraud-detection-handbook.github.io/) (free, the best practical reference — read Ch. 1–3), Stripe Radar / Adyen engineering blogs.

### A2. Multi-agent scoring + ensemble fusion
Instead of one big model, several **independent specialist scorers** ("agents") each judge the transaction from one angle (speed, location, behavior, network), then a **synthesis** step combines them into one decision. This is a form of **ensembling** — combining weak/narrow signals into a strong one.
- **Why here:** each fraud type leaves a different fingerprint; specialists are easier to build, test, and explain than one monolith.
- **Read:** `orchestrator/main.py` (`process_transaction`), `agents/synthesis/agent.py`.
- **Learn:** "ensemble methods" overview ([scikit-learn ensembles](https://scikit-learn.org/stable/modules/ensemble.html)); the idea of weighted voting / mixture-of-experts.

### A3. Context-aware weighting (our key innovation)
The agents' importance **depends on transaction type**. A QR/eSewa payment weights *location* heavily; a SWIFT remittance weights the *graph/network* agent heavily (mule detection). So the fusion weights are a lookup keyed by transaction type, not fixed.
- **Read:** `WEIGHTS_BY_TYPE` in `agents/synthesis/agent.py`.
- **Concept to study:** "feature/expert weighting", "context-dependent models", "mixture of experts".

### A4. The cold-start problem
A brand-new account has no transaction history, so per-user models can't be trained. SENTINEL solves this with **cohort modeling**: group similar accounts (by type + region), train one model per cohort, and a new account inherits its cohort's model from day 0.
- **Read:** `ml/cohorts/assign.py`, `ml/cohorts/onboarding.py`.
- **Learn:** "cold start problem" (framed in recommender systems but identical idea); "customer segmentation".

### A5. Anomaly detection vs. classification
Fraud data is **highly imbalanced** (fraud is rare). Two complementary approaches:
- **Unsupervised anomaly detection** — learn "normal", flag outliers (no fraud labels needed). We use Isolation Forest.
- **Supervised/sequence models** — learn patterns from history. We use an LSTM over a user's transaction sequence.
- **Learn:** [scikit-learn outlier detection](https://scikit-learn.org/stable/modules/outlier_detection.html); imbalanced-learning basics.

### A6. Evaluation under imbalance
Accuracy is misleading when 99% of transactions are legitimate. The real metrics are **precision, recall, F1, and PR-AUC**, plus the business trade-off between **false positives** (blocking good customers) and **false negatives** (missing fraud).
- **Learn:** [scikit-learn model evaluation](https://scikit-learn.org/stable/modules/model_evaluation.html); precision/recall trade-off.

### A7. Velocity & geo-velocity
- **Velocity:** how many / how much an account transacts within a sliding time window — sudden spikes are suspicious.
- **Geo-velocity ("impossible travel"):** two transactions from locations too far apart to travel between in the elapsed time.
- **Read:** `agents/velocity/agent.py`, `agents/geo/agent.py`.

### A8. Graph / network fraud (money mules)
Fraud rings move money through chains of "mule" accounts. Modeling accounts as a **graph** (nodes = accounts, edges = transfers) lets you detect ring structures that per-account analysis misses.
- **Read:** `agents/gnn/cypher_agent.py`, `graph/mule_detection.cypher`.
- **Learn:** graph databases + community detection; [Stanford CS224W](http://web.stanford.edu/class/cs224w/) for the deep ML version. (Note: our agent is **Cypher-query based**, not a trained GNN.)

### A9. Step-up authentication, OTP interlock & SIM-swap
When risk is medium, don't block — **ask for more proof** (step-up auth) via a one-time password (OTP). SENTINEL uses **two independent channels** (SMS + Email). The clever part: if the SMS code fails but Email succeeds, that asymmetry signals a **SIM-swap attack** (attacker hijacked the phone number but not the email).
- **Read:** `agents/otp/interlock.py` (the `confirm()` state machine).
- **Learn:** OWASP authentication cheat sheet; "SIM swap attack" (GSMA/FTC explainers); MFA concepts.

### A10. Auditability
Every verdict is written to an append-only log so decisions are explainable and reviewable later — essential in regulated finance.
- **Read:** `_write_audit` in `orchestrator/main.py`.

---

## Part B — The Tech Stack (each technology explained)

### Languages & runtime
- **Python 3.11–3.12** — the backend language. Modern features used: `async`/`await`, type hints, dataclasses, `from __future__ import annotations`.
- **TypeScript** — typed JavaScript for the frontend.

### B1. asyncio (Python concurrency)
**What:** Python's built-in framework for concurrent I/O using `async`/`await` — one thread juggling many waiting operations.
**Why here:** the orchestrator runs four agents *at the same time* (`asyncio.gather`), offloads blocking model code with `asyncio.to_thread`, and does audit/OTP work in the background with `asyncio.create_task` so it never blocks a verdict.
**Learn:** [Real Python — Async IO](https://realpython.com/async-io-python/), [official asyncio docs](https://docs.python.org/3/library/asyncio.html).

### B2. FastAPI (web framework)
**What:** a modern Python web framework for building APIs, with automatic validation and OpenAPI docs.
**Why here:** serves the orchestrator's REST endpoints (`/score`, `/stats`, `/otp/*`) and the live `/ws/verdicts` WebSocket; uses a lifespan handler to init agents at startup.
**Learn:** [FastAPI tutorial](https://fastapi.tiangolo.com/tutorial/) (do "Request Body", "WebSockets", "Lifespan Events"). Explore our live API at `http://localhost:8000/docs`.

### B3. Uvicorn (ASGI server)
**What:** the high-performance server that actually runs an async Python web app.
**Why here:** runs `orchestrator.main:app`.
**Learn:** [uvicorn.org](https://www.uvicorn.org/).

### B4. Pydantic v2 (data validation)
**What:** define data shapes as Python classes; it validates and serializes them.
**Why here:** `TransactionEvent`, `AgentScore`, `SynthesisVerdict` are the system's contracts — every payload is validated through them.
**Read:** `orchestrator/schemas.py`. **Learn:** [Pydantic docs](https://docs.pydantic.dev/latest/).

### B5. Apache Kafka (event streaming)
**What:** a distributed log/message bus. Producers publish to **topics**; consumers read at their own pace via **consumer groups** and **offsets**.
**Why here:** the transaction event bus (`sentinel.transactions`) and the verdict stream (`sentinel.verdicts`) — decouples ingestion from scoring and lets the system scale.
**Read:** consumer/producer in `orchestrator/main.py`; `scripts/init_kafka.sh`.
**Learn:** [Kafka 101 (Confluent)](https://developer.confluent.io/courses/apache-kafka/events/). Key terms: topic, partition, consumer group, offset.

### B6. Redis (in-memory data store)
**What:** an ultra-fast key-value store; supports TTL (auto-expiring keys).
**Why here:** velocity sliding-window counters, geo history, and OTP state — all need sub-millisecond reads. OTP codes use `SETEX` with a 5-minute TTL; transactions are "frozen" with `tx_hold:*` keys.
**Read:** `agents/velocity/agent.py`, `agents/otp/interlock.py`.
**Learn:** [Redis docs](https://redis.io/docs/latest/develop/) — strings, TTL/`SETEX`, key naming patterns.

### B7. Neo4j + Cypher (graph database)
**What:** a database that stores data as nodes + relationships; **Cypher** is its query language (think SQL for graphs).
**Why here:** holds the account relationship graph; mule-ring detection is a Cypher query over transfer patterns.
**Read:** `graph/setup.cypher`, `graph/mule_detection.cypher`, `agents/gnn/cypher_agent.py`.
**Learn:** [Neo4j Cypher tutorial](https://neo4j.com/docs/getting-started/cypher/), [GraphAcademy](https://graphacademy.neo4j.com/) (free, interactive).

### B8. PostgreSQL + psycopg 3 (relational database)
**What:** a robust SQL database; `psycopg` is its Python driver (we use the async API).
**Why here:** the append-only `audit_log` table — every verdict archived for compliance/review.
**Read:** `_ensure_audit_table`, `_write_audit` in `orchestrator/main.py`.
**Learn:** [PostgreSQL tutorial](https://www.postgresqltutorial.com/), [psycopg 3 docs](https://www.psycopg.org/psycopg3/docs/).

### B9. PyTorch (deep learning)
**What:** the leading Python deep-learning framework (tensors, autograd, neural nets).
**Why here:** trains the per-cohort **LSTM** models that score behavioral sequences. Models saved as `.pt` files.
**Read:** `ml/training/train_lstm.py`; consumed in `agents/behavior/agent.py`.
**Learn:** [PyTorch 60-min blitz](https://pytorch.org/tutorials/beginner/deep_learning_60min_blitz.html); for LSTMs specifically, Chris Olah's [Understanding LSTMs](https://colah.github.io/posts/2015-08-Understanding-LSTMs/) + [nn.LSTM docs](https://pytorch.org/docs/stable/generated/torch.nn.LSTM.html).

### B10. scikit-learn (classical ML)
**What:** the standard Python library for classical ML.
**Why here:** the **Isolation Forest** anomaly detectors (one per cohort), saved as `.pkl` files.
**Read:** `ml/training/train_isolation_forest.py`.
**Learn:** [IsolationForest docs](https://scikit-learn.org/stable/modules/generated/sklearn.ensemble.IsolationForest.html).

### B11. MLflow (ML lifecycle)
**What:** tracks experiments, stores/versions models in a **model registry**, and supports monitoring.
**Why here:** registers trained cohort models and supports drift checks / retraining. UI at `http://localhost:5050`.
**Read:** `ml/training/register_models.py`, `ml/monitoring/drift_check.py`, `ml/monitoring/retrain.py`.
**Learn:** [MLflow docs](https://mlflow.org/docs/latest/index.html) — Tracking + Model Registry.

### B12. NumPy / pandas / PyArrow (data handling)
**What:** numerical arrays (NumPy), dataframes (pandas), and the columnar **Parquet** format (PyArrow).
**Why here:** synthetic data is generated and stored as `.parquet` in `data/seeds/`; features are built with pandas.
**Read:** `data/generators/`, `ml/training/featurize.py`.
**Learn:** [pandas getting started](https://pandas.pydata.org/docs/getting_started/index.html); "what is Parquet".

### B13. React + Vite + Tailwind + Recharts (frontend)
- **React 18** — component-based UI library. ([react.dev](https://react.dev/learn))
- **Vite** — fast dev server & bundler. ([vitejs.dev](https://vitejs.dev/guide/))
- **Tailwind CSS** — utility-first styling. ([tailwindcss.com](https://tailwindcss.com/docs))
- **Recharts** — React charting for the live latency/TPS/fraud charts. ([recharts.org](https://recharts.org/en-US/examples))
- **WebSocket** — pushes live verdicts to the dashboard. ([MDN WebSocket API](https://developer.mozilla.org/en-US/docs/Web/API/WebSocket))
**Read:** `frontend/src/`, `frontend/package.json`.

### B14. Docker & Docker Compose (infra/orchestration)
**What:** containers package a service + its deps; Compose runs the multi-service stack with one command.
**Why here:** brings up all 8 services (Kafka, Zookeeper, Redis, Neo4j, Postgres, MLflow, orchestrator, frontend) with healthchecks and dependency ordering.
**Read:** `docker-compose.yml`, `Dockerfile`.
**Learn:** [Docker Compose overview](https://docs.docker.com/compose/). Terms: service, image, volume, healthcheck, `depends_on`, internal vs. published ports.

### B15. Dev tooling
- **Poetry** — dependency & packaging manager. ([docs](https://python-poetry.org/docs/))
- **Ruff** — fast linter/formatter (line-length 100). ([docs](https://docs.astral.sh/ruff/))
- **Black** — code formatter. ([docs](https://black.readthedocs.io/))
- **pre-commit** — runs lint/format on every commit. ([pre-commit.com](https://pre-commit.com/))
- **pytest** + **pytest-asyncio** — testing (note scenario files aren't `test_*` named; see `CLAUDE.md`). ([pytest](https://docs.pytest.org/))
- **Locust** — load testing to validate latency/throughput targets. ([docs](https://docs.locust.io/))
- **structlog** — structured JSON logging with bound per-transaction context. ([docs](https://www.structlog.org/))
- **geopy** — geographic distance math for geo-velocity. ([docs](https://geopy.readthedocs.io/))

---

## Part C — Suggested order

1. **Concepts first** (Part A) — understand fraud detection, multi-agent fusion, cohorts, OTP/SIM-swap. This is the "why".
2. **The web + data layer** (B1–B8) — asyncio, FastAPI, then Kafka/Redis/Neo4j/Postgres. Now you can follow a request end-to-end.
3. **The ML** (B9–B12) — Isolation Forest, LSTM, cohorts, MLflow. Now you can retrain and extend models.
4. **Frontend + ops** (B13–B15) — dashboard and the dev/infra tooling.

For the matching code-reading walkthrough and project-specific glossary, see `CLAUDE.md`.
