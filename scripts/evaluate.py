"""Validate the offline scorer against fraud_labels_train (DATA_DESCRIPTION §8.1).

Scores the labelled training split through the same offline multi-agent pipeline used
for the submission, then reports AUROC / precision@5%FPR / recall / F1 / FPR vs the
§8.1 targets and the §8.3 rule-engine baseline — so you know where you stand before
eval day.

Usage:
  python3 scripts/evaluate.py --data structured [--threshold 0.5] [--sample 100000]
"""
from __future__ import annotations

import argparse
import pathlib

import pandas as pd

from orchestrator.metrics import evaluate, format_report
from orchestrator.offline_scorer import score_records
from scripts.generate_submission import build_scoring_frame


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="structured")
    ap.add_argument("--threshold", type=float, default=0.5)
    ap.add_argument("--sample", type=int, default=0, help="evaluate on a random N-row sample (0 = all)")
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    base = pathlib.Path(args.data)
    labels = pd.read_csv(base / "fraud_labels_train.csv")[["txn_id", "is_fraud"]]

    print(f"Building scoring frame from {base}/ ...")
    frame = build_scoring_frame(base)
    frame = frame.merge(labels, on="txn_id", how="inner")  # labelled rows only
    if args.sample and args.sample < len(frame):
        frame = frame.sample(n=args.sample, random_state=args.seed).reset_index(drop=True)
    print(f"  → evaluating {len(frame):,} labelled transactions")

    verdicts = score_records(frame.drop(columns=["is_fraud"]).to_dict("records"))
    prob = {v.transaction_id: v.composite_score for v in verdicts}
    y_prob = frame["txn_id"].map(prob).fillna(0.5).to_numpy()
    y_true = frame["is_fraud"].astype(bool).astype(int).to_numpy()

    m = evaluate(y_true, y_prob, threshold=args.threshold)
    print("\n" + format_report(m))


if __name__ == "__main__":
    main()
