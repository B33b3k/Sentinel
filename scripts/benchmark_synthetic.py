"""Reproducible end-to-end benchmark of the live multi-agent pipeline.

Replays the labelled synthetic seed transactions (data/seeds/*.parquet) through the
*real* Velocity / Geo / Behavior / GNN agents and the context-aware SynthesisAgent —
exactly the code path used online — then reports:

  * detection quality  (AUROC / precision@5%FPR / recall / F1 / FPR) vs the §8.1
    targets and §8.3 rule-engine baseline, via orchestrator.metrics.evaluate;
  * latency            (per-agent and end-to-end p50/p95/p99), measured from the
    agents' own latency_ms instrumentation.

Transactions are replayed in timestamp order so the stateful agents (velocity windows
in Redis, geo history, GNN graph cache) warm up the way they do in production.

Requires Redis (and optionally Neo4j) running:  docker compose up -d redis neo4j
Usage:  python3 scripts/benchmark_synthetic.py [--sample N] [--out benchmarks/eval_report.txt]
"""
from __future__ import annotations

import argparse
import pathlib
import statistics
import time

import pandas as pd

from agents.behavior.agent import BehaviorAgent
from agents.geo.agent import GeoAgent
from agents.gnn.cypher_agent import GNNAgent
from agents.synthesis.agent import SynthesisAgent
from agents.velocity.agent import VelocityAgent
from data.adapters.real_data_adapter import from_synthetic
from orchestrator.metrics import evaluate, format_report

SEEDS = pathlib.Path("data/seeds")


def _pct(xs: list[float], q: float) -> float:
    if not xs:
        return float("nan")
    xs = sorted(xs)
    i = min(len(xs) - 1, int(q * len(xs)))
    return xs[i]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sample", type=int, default=0, help="evaluate on first N (time-ordered) rows; 0 = all")
    ap.add_argument("--out", default="benchmarks/eval_report.txt")
    ap.add_argument("--threshold", type=float, default=0.40, help="ALLOW/escalate boundary (matches synthesis _ALLOW_THRESHOLD)")
    args = ap.parse_args()

    txns = pd.read_parquet(SEEDS / "transactions.parquet")
    labels = pd.read_parquet(SEEDS / "labels.parquet")[["transaction_id", "is_fraud"]]
    txns = txns.sort_values("timestamp").reset_index(drop=True)
    if args.sample:
        txns = txns.head(args.sample)
    print(f"Replaying {len(txns):,} transactions in timestamp order ...")

    velocity, geo, behavior, gnn = VelocityAgent(), GeoAgent(), BehaviorAgent(), GNNAgent()
    synth = SynthesisAgent()
    agents = [velocity, geo, behavior, gnn]

    prob: dict[str, float] = {}
    per_agent: dict[str, list[float]] = {a: [] for a in ("velocity", "geo", "behavior", "gnn")}
    wall_parallel: list[float] = []   # realistic online wall-clock = max(agent) + synth
    wall_serial: list[float] = []     # sum(agent) + synth (upper bound)

    t_start = time.perf_counter()
    for i, row in enumerate(txns.to_dict("records")):
        tx = from_synthetic(row)
        scores = [a.score(tx) for a in agents]
        verdict = synth.synthesize(tx, scores)
        prob[tx.transaction_id] = verdict.composite_score
        lat = {s.agent: s.latency_ms for s in scores}
        for name in per_agent:
            per_agent[name].append(lat.get(name, 0.0))
        synth_overhead = max(0.0, verdict.total_latency_ms - sum(lat.values()))
        wall_parallel.append(max(lat.values()) + synth_overhead)
        wall_serial.append(sum(lat.values()) + synth_overhead)
        if (i + 1) % 10000 == 0:
            print(f"  {i + 1:,} scored ...")
    elapsed = time.perf_counter() - t_start

    merged = txns[["transaction_id"]].merge(labels, on="transaction_id", how="inner")
    y_prob = merged["transaction_id"].map(prob).fillna(0.5).to_numpy()
    y_true = merged["is_fraud"].astype(bool).astype(int).to_numpy()
    m = evaluate(y_true, y_prob, threshold=args.threshold)

    def lat_block(name: str, xs: list[float]) -> str:
        return (f"  {name:<18} p50 {_pct(xs, 0.50):6.2f}ms   "
                f"p95 {_pct(xs, 0.95):6.2f}ms   p99 {_pct(xs, 0.99):6.2f}ms   "
                f"max {max(xs):6.2f}ms")

    report = [
        "SENTINEL — end-to-end benchmark on labelled synthetic seeds",
        f"(replayed through the live Velocity/Geo/Behavior/GNN agents + SynthesisAgent)",
        "",
        "## Detection quality (decision threshold = %.2f)" % args.threshold,
        format_report(m),
        "",
        "## Latency  (n=%d, wall-time %.1fs, %.0f tx/s single-process)" % (
            len(txns), elapsed, len(txns) / elapsed),
        *[lat_block(n, xs) for n, xs in per_agent.items()],
        lat_block("end-to-end (∥)", wall_parallel),
        lat_block("end-to-end (Σ)", wall_serial),
        "",
        "Notes:",
        "  ∥ = realistic online wall-clock: agents run concurrently (asyncio.gather),",
        "      so end-to-end ≈ max(agent latencies) + synthesis overhead.",
        "  Σ = sum of agent latencies (sequential upper bound).",
        "  Detection metrics are on self-generated synthetic data and are indicative;",
        "  eval-day numbers come from scripts/evaluate.py on the official Track-B files.",
    ]
    text = "\n".join(report)
    print("\n" + text)

    out = pathlib.Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text + "\n")
    print(f"\nWrote {out}")


if __name__ == "__main__":
    main()
