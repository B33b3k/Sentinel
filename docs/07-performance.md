# 07 — Performance & Evaluation

Every figure here is reproducible. The numbers below come from a single committed run of
`scripts/benchmark_synthetic.py`, captured in
[`benchmarks/eval_report.txt`](../benchmarks/eval_report.txt). Re-run it and you get the same
shape of result.

## Method

```bash
docker compose up -d redis neo4j
python3 graph/load_data.py                 # load the account graph for the GNN agent
python3 scripts/benchmark_synthetic.py     # → benchmarks/eval_report.txt
```

The benchmark replays all **96,938 labelled synthetic transactions** (2.00% fraud) in timestamp
order through the *live* Velocity, Geo, Behavior, and GNN agents and the context-aware
`SynthesisAgent` — the same code path used online. Replaying in time order lets the stateful
agents (Redis velocity windows, geo history, the GNN graph cache) warm up as they would in
production. Latency is taken from each agent's own `latency_ms` instrumentation; detection
metrics from `orchestrator/metrics.py` against the §8.1 targets and the §8.3 rule-engine
baseline.

## Latency

Agents run concurrently (`asyncio.gather`), so the realistic online wall-clock is
`max(agent latencies) + synthesis overhead` (the parallel row), not the sum.

| Stage | p50 | p95 | p99 |
|-------|-----|-----|-----|
| Velocity | 2.28 ms | 4.67 ms | 8.41 ms |
| Geo | 0.71 ms | 1.59 ms | 2.68 ms |
| Behavior | 6.68 ms | 11.04 ms | 18.58 ms |
| GNN | 0.22 ms | 1.45 ms | 3.02 ms |
| **End-to-end (parallel)** | **6.69 ms** | **11.09 ms** | **18.91 ms** |
| End-to-end (sequential Σ) | 10.07 ms | 17.83 ms | 31.10 ms |

**Against the requirement:** Track B allows 800 ms P99. Measured end-to-end P99 is **18.9 ms** —
about **2.4%** of the budget, leaving ample headroom.

A handful of per-agent maxima are large (e.g. a ~1.6 s velocity outlier, ~966 ms behavior). These
are cold-start artifacts — the first model load, the first Neo4j connection, and interpreter
warm-up on the opening transactions — not steady-state behaviour, which is why P99 is the figure
to read.

### Bottleneck
The Behavior agent (per-cohort LSTM + Isolation Forest) dominates at ~6.7 ms median / 18.6 ms
P99 — roughly 3× the next agent. It is the right place to optimize first (e.g. ONNX export,
batching) if the latency budget ever tightened; today it does not need it.

## Detection quality

Measured on the live-agent replay (decision threshold 0.40):

| Metric | Measured | §8.1 target | §8.3 baseline |
|--------|----------|-------------|---------------|
| AUROC | **0.742** | 0.93 | 0.71 |
| Recall | 0.356 | 0.88 | 0.62 |
| Precision @ 5% FPR | 0.114 | 0.75 | — |
| F1 | 0.161 | 0.80 | 0.54 |
| FPR | 0.063 | — | 0.14 |

**Read this honestly.** On the cold live-agent path, ranking quality (AUROC 0.742) clears the
§8.3 rule-engine baseline but falls short of the §8.1 targets, and operating-point recall at the
default threshold is low. The reason — and the genuine path to the eval-day number — is the
signal source, not baseline warmth:

- **Seeding per-account baselines was tried and did *not* help.** Re-running with
  `ml/training/build_velocity_baselines.py` seeded (per-account average amount and velocity)
  slightly *lowered* recall (0.356 → 0.283) and AUROC (0.742 → 0.726). The cause is in-sample
  contamination: a baseline computed over this dataset includes each fraudster's own large
  transactions, which inflates that account's average so the fraud no longer trips the amount
  anomaly. Warm baselines only help when they're built from clean history, as a real bank's are.
- **The live agents recompute signals from raw fields; eval day does not.** The official dataset
  ships the expensive signals precomputed (`velocity_snapshots` §3.5, `geo_events` §3.4, graph
  degrees §3.7), already leakage-free. The **offline scorer** (`orchestrator/offline_scorer.py`)
  reads those directly — a stronger, cleaner signal path than recomputing cold — and covers all
  seven §4 hidden patterns. It is the path measured on eval day by `scripts/evaluate.py`.

This is exactly why the eval-day number is produced by the offline path against the official
data, not asserted here:

```bash
python3 scripts/evaluate.py --data structured   # AUROC / precision@5%FPR / recall / F1 vs §8.1 + §8.3
```

## Throughput

The benchmark's single-process, synchronous replay sustained **~85 tx/s** including every Redis
and Neo4j round-trip on one core. That is a floor, not the production ceiling: the orchestrator
is stateless behind Kafka, scores agents concurrently with `asyncio`, and scales horizontally by
adding consumers. A load-test harness is provided:

```bash
locust -f tests/load/locustfile.py --headless -u 500 -r 100 -t 60s --host http://localhost:8000
```

Production throughput therefore depends on consumer count and hardware; we report the measured
single-process figure rather than an extrapolated cluster number.

## Tests

```bash
python3 -m pytest -q
```

96 tests pass. A further 9 are infrastructure smoke checks (`tests/smoke/`) that require the
dockerized Kafka/Redis/Neo4j/Postgres/MLflow stack to be up; they fail fast when it is not, by
design.

## Summary

- **Latency** — measured P99 18.9 ms end-to-end, ~2.4% of the 800 ms budget. Strong and
  reproducible.
- **Detection** — live cold-path AUROC 0.742, above the rule-engine baseline; the official
  eval-day metrics come from the offline scorer via `scripts/evaluate.py`.
- **Honesty over headline** — the numbers above are whatever the committed benchmark produces on
  your machine; none are hand-set.

---

Next: [08 — Demo Guide](./08-demo.md)
