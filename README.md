# SENTINEL

> Multi-agent, real-time fraud detection for Nepal's banking sector.
> Global IME AI/ML Hackathon 2026 · Track B — Security & Fraud.

SENTINEL scores every transaction through four specialized agents in parallel, fuses their
scores with **context-aware weights that depend on the transaction type**, and routes the
result to one of three verdicts — `ALLOW`, `OTP_INTERLOCK`, or `BLOCK`. Suspicious transactions
are verified with **dual-path OTP** (SMS + Email) designed to expose SIM-swap attacks rather
than block the customer outright.

## Contents

- [Why this design](#why-this-design)
- [Architecture](#architecture)
- [The agents](#the-agents)
- [Context-aware synthesis](#context-aware-synthesis)
- [Tech stack](#tech-stack)
- [Quick start](#quick-start)
- [Performance & evaluation](#performance--evaluation)
- [Track-B submission (eval day)](#track-b-submission-eval-day)
- [Documentation](#documentation)
- [Repository layout](#repository-layout)
- [Glossary](#glossary)

## Why this design

Track B names four challenges; each maps to a concrete mechanism:

| Challenge | Mechanism |
|-----------|-----------|
| Minimize false positives | A graduated verdict band — `0.40–0.75` routes to OTP verification, not a block |
| Context-aware detection | Per-transaction-type weight vectors in the Synthesis Agent |
| Cold-start protection | Six peer cohorts; a new account inherits its cohort's models from day 0 |
| SIM-swap defense | Independent dual-path OTP; an SMS-pass / Email-fail asymmetry signals SIM-swap |

Detail and the supporting literature are in [docs/01-overview.md](docs/01-overview.md).

## Architecture

```
                    ┌────────────────────────────────────────┐
                    │       Transaction Event (Kafka)        │
                    └──────────────────┬─────────────────────┘
                                       │  normalize via adapter
                ┌──────────────────────┼──────────────────────┐
                ▼          ▼            ▼            ▼          (asyncio.gather,
          ┌──────────┐ ┌──────┐  ┌──────────┐ ┌──────────┐     1s per-agent timeout;
          │ Velocity │ │ Geo  │  │ Behavior │ │   GNN    │     timeout → neutral 0.5)
          │ (Redis)  │ │(heur)│  │(LSTM+IF) │ │ (Neo4j)  │
          └────┬─────┘ └──┬───┘  └────┬─────┘ └────┬─────┘
               └──────────┴─────┬─────┴────────────┘
                                ▼
                     ┌─────────────────────┐
                     │   Synthesis Agent    │  composite = Σ weightᵢ·scoreᵢ
                     │ context-aware weights│  clamped to [0,1]
                     └──────────┬───────────┘
                  ┌─────────────┼─────────────┐
                  ▼             ▼             ▼
           ALLOW (<0.40)  OTP_INTERLOCK   BLOCK (>0.75)
                          (0.40–0.75)
                                │  SMS + Email, 5-min window
                       both ✓ → RELEASE
                       SMS ✗ / Email ✓ → BLOCK (sim-swap)
                       SMS ✓ / Email ✗ → HUMAN_REVIEW
```

The orchestrator (`orchestrator/main.py`) is the single entry point. Audit writes and OTP
dispatch are fire-and-forget — they never block or change a verdict. Full request flow:
[docs/02-architecture.md](docs/02-architecture.md).

## The agents

| Agent | Implementation | Catches |
|-------|----------------|---------|
| **Velocity** | Redis sliding-window counters | Burst attacks, structuring, dormancy breaks |
| **Geo** | Heuristic geo-velocity + device fingerprint | Impossible travel, new device, VPN/Tor, SIM change |
| **Behavior** | Per-cohort LSTM + Isolation Forest ensemble | Anomalous amount / timing / counterparty |
| **GNN** | Neo4j Cypher graph queries | Money-mule rings, layering |

Each agent exposes a sync `score(tx) -> AgentScore` and stays side-effect-free on the hot path.
Algorithms and reason codes: [docs/05-agents.md](docs/05-agents.md).

## Context-aware synthesis

The core innovation. `WEIGHTS_BY_TYPE` maps each transaction type to a per-agent weight vector,
so the signals that actually predict fraud for that type dominate the score:

```python
"KHALTI_QR":     {"velocity": 0.35, "geo": 0.35, "behavior": 0.25, "gnn": 0.05}  # location-driven
"SWIFT_OUTWARD": {"velocity": 0.15, "geo": 0.20, "behavior": 0.20, "gnn": 0.45}  # graph-driven
```

A missing/timed-out agent is imputed to a neutral `0.5`; unknown types fall back to a balanced
vector. This satisfies the §8.2 weight-adaptation bonus. See `agents/synthesis/agent.py`.

## Tech stack

| Layer | Technology | Purpose |
|-------|-----------|---------|
| Streaming | Apache Kafka | Transaction event bus |
| Cache | Redis 7 | Velocity windows, account history, OTP state |
| Graph DB | Neo4j 5 (+ GDS) | Account relationship graph |
| Relational DB | PostgreSQL 16 | Audit log |
| ML | PyTorch + scikit-learn | LSTM + Isolation Forest ensemble |
| Model lifecycle | MLflow | Tracking, registry, drift monitoring |
| API | FastAPI + asyncio | Orchestrator |
| Frontend | React + Vite + Tailwind + Recharts | Dashboard |
| Deployment | Docker Compose | 8-service stack |

Rationale and alternatives considered: [docs/03-tech-stack.md](docs/03-tech-stack.md).

## Quick start

```bash
# Full stack: infra + models + 8 services + frontend (generates data & trains models if missing)
bash scripts/start_all.sh

open http://localhost:3000          # dashboard
python3 data/generators/replay.py   # live transaction stream
```

Full setup, local-dev workflow, and troubleshooting: [SETUP.md](SETUP.md).
Service ports: dashboard `:3000`, orchestrator `:8000` (`/docs`), MLflow `:5050`,
Neo4j `:7474`, Postgres `:5432`, Redis `:6379`, Kafka `:9092`.

## Performance & evaluation

All figures are reproducible, not asserted.

```bash
python3 -m pytest -q                    # test suite
python3 scripts/benchmark_synthetic.py  # end-to-end latency + detection on labelled seeds
```

`benchmark_synthetic.py` replays the labelled synthetic seeds through the live agents and writes
[`benchmarks/eval_report.txt`](benchmarks/eval_report.txt). Current results, per-agent latency,
and the method behind them are in [docs/07-performance.md](docs/07-performance.md). On eval day,
`scripts/evaluate.py` reports against the official §8.1 targets and the §8.3 rule-engine baseline.

## Track-B submission (eval day)

SENTINEL is built against the [`DATA_DESCRIPTION_Track_B.md`](DATA_DESCRIPTION_Track_B.md) data
dictionary. When the real `structured/*.csv` files arrive:

```bash
python3 scripts/evaluate.py --data structured                                  # standing vs §8.1 / §8.3
python3 scripts/generate_submission.py --data structured --team sentinel --out dist
```

| Output | Spec | Producer |
|--------|------|----------|
| `submission_sentinel.csv` | §8.4 | `orchestrator/submission.py` |
| `community_detection.json` | §8.2 (+5%) | `orchestrator/bonus.py` |
| `otp_submission.csv` | §8.2 (+5%) | `orchestrator/bonus.py` |
| `shap_values.csv` | §8.2 (+3%) | `orchestrator/bonus.py` |

Scoring runs the offline multi-agent pipeline (`orchestrator/offline_scorer.py`) over the
dataset's precomputed velocity/geo/graph/device signals — no live infra required. Full guide:
[docs/09-track-b-submission.md](docs/09-track-b-submission.md).

## Documentation

Start with [docs/](docs/README.md). The numbered guides (01–09) go from problem statement to
eval-day submission; [docs/decisions.md](docs/decisions.md) records the architecture decisions
and [docs/schemas.md](docs/schemas.md) the data contracts. [LEARNING.md](LEARNING.md) is a
ground-up walkthrough of the concepts for someone learning the stack.

## Repository layout

```
agents/         the four scoring agents + synthesis + OTP interlock
orchestrator/   FastAPI entry point, schemas, offline scorer, submission + bonus artifacts
ml/             cohorts, training, monitoring, trained artifacts
graph/          Neo4j setup, data load, mule-detection Cypher
data/           synthetic generators + the data-contract adapter
frontend/       React dashboard
scripts/        start/train/seed/benchmark/evaluate/generate_submission
tests/          unit (agents, synthesis, metrics) + scenario + smoke
docs/           technical documentation
```

## Glossary

- **Cohort** — a group of similar accounts that share pretrained models (the cold-start strategy).
- **Composite score** — the fused fraud risk in `[0, 1]` that drives the verdict.
- **OTP interlock** — the dual-path (SMS + Email) verification step for the `0.40–0.75` band.
- **SIM-swap** — an attack that clones a victim's SIM to intercept SMS OTPs; defeated by the
  Email channel the attacker cannot reach.

---

_Built for the Global IME AI/ML Hackathon 2026 · Track B — Security & Fraud._
