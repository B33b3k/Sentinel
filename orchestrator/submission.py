"""Submission helpers — produce the eval-day CSV in the DATA_DESCRIPTION §8.4 format.

The internal verdict vocabulary (ALLOW / OTP_INTERLOCK / BLOCK) differs from the
submission `fraud_decision` enum (ALLOW / OTP_ONLY / BLOCK); this module is the single
place that bridges them and emits the required columns.
"""
from __future__ import annotations

import json
import pathlib
from typing import Any, Iterable

import pandas as pd

from orchestrator.schemas import SynthesisVerdict

# §8.4 — required + optional submission columns, in order.
SUBMISSION_COLUMNS = [
    "txn_id",                # required
    "fraud_probability",     # required — AUROC computed from this
    "fraud_decision",        # required — ALLOW / OTP_ONLY / BLOCK
    "fraud_type_predicted",  # optional — bonus fraud-type scoring
    "agent_scores_json",     # optional — per-agent scores
    "latency_ms",            # required — P95 must be < 800 ms
]

# Internal verdict → submission fraud_decision.
_VERDICT_TO_DECISION = {
    "ALLOW": "ALLOW",
    "OTP_INTERLOCK": "OTP_ONLY",
    "BLOCK": "BLOCK",
}

# Thresholds mirror the SynthesisAgent (ALLOW < 0.40 ≤ OTP_ONLY < 0.75 ≤ BLOCK).
DEFAULT_ALLOW_THRESHOLD = 0.40
DEFAULT_BLOCK_THRESHOLD = 0.75


def to_fraud_decision(verdict: str) -> str:
    """Map an internal SynthesisVerdict.verdict to the §8.4 fraud_decision enum."""
    return _VERDICT_TO_DECISION.get(verdict, "OTP_ONLY")


def decision_from_probability(
    p: float,
    allow_threshold: float = DEFAULT_ALLOW_THRESHOLD,
    block_threshold: float = DEFAULT_BLOCK_THRESHOLD,
) -> str:
    """Derive a fraud_decision from a raw probability (batch scoring path)."""
    if p < allow_threshold:
        return "ALLOW"
    if p < block_threshold:
        return "OTP_ONLY"
    return "BLOCK"


def row_from_verdict(verdict: SynthesisVerdict, fraud_type_predicted: str | None = None) -> dict[str, Any]:
    """Build one submission row from a pipeline verdict."""
    return {
        "txn_id": verdict.transaction_id,
        "fraud_probability": round(verdict.composite_score, 6),
        "fraud_decision": to_fraud_decision(verdict.verdict),
        "fraud_type_predicted": fraud_type_predicted,
        "agent_scores_json": json.dumps({s.agent: round(s.score, 4) for s in verdict.agent_scores}),
        "latency_ms": int(round(verdict.total_latency_ms)),
    }


def build_submission_df(records: Iterable[dict[str, Any]]) -> pd.DataFrame:
    """Normalise records into the exact §8.4 column set/order (missing → None)."""
    df = pd.DataFrame(list(records))
    for col in SUBMISSION_COLUMNS:
        if col not in df.columns:
            df[col] = None
    return df[SUBMISSION_COLUMNS]


def write_submission(
    records: Iterable[dict[str, Any]],
    team_name: str,
    out_dir: pathlib.Path | str = ".",
) -> pathlib.Path:
    """Write submission_[team_name].csv and return its path."""
    df = build_submission_df(records)
    out_dir = pathlib.Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"submission_{team_name}.csv"
    df.to_csv(path, index=False)
    return path
