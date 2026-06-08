"""Unit tests for the eval-day submission builder (DATA_DESCRIPTION §8.4)."""
from __future__ import annotations

import json

import pandas as pd

from orchestrator.schemas import AgentScore, SynthesisVerdict
from orchestrator.submission import (
    SUBMISSION_COLUMNS,
    build_submission_df,
    decision_from_probability,
    row_from_verdict,
    to_fraud_decision,
    write_submission,
)


def test_verdict_to_decision_mapping():
    assert to_fraud_decision("ALLOW") == "ALLOW"
    assert to_fraud_decision("OTP_INTERLOCK") == "OTP_ONLY"
    assert to_fraud_decision("BLOCK") == "BLOCK"
    # Unknown verdicts fall back to the cautious OTP_ONLY.
    assert to_fraud_decision("???") == "OTP_ONLY"


def test_decision_from_probability_thresholds():
    assert decision_from_probability(0.0) == "ALLOW"
    assert decision_from_probability(0.39) == "ALLOW"
    assert decision_from_probability(0.40) == "OTP_ONLY"
    assert decision_from_probability(0.74) == "OTP_ONLY"
    assert decision_from_probability(0.75) == "BLOCK"
    assert decision_from_probability(1.0) == "BLOCK"


def _verdict() -> SynthesisVerdict:
    return SynthesisVerdict(
        transaction_id="TXN-20260531-A9F3C1AB",
        composite_score=0.8123456,
        verdict="BLOCK",
        agent_scores=[
            AgentScore(agent="velocity", score=0.71234, reason_codes=[], latency_ms=42),
            AgentScore(agent="gnn", score=0.9, reason_codes=[], latency_ms=224),
        ],
        weights_used={"velocity": 0.2, "geo": 0.15, "behavior": 0.25, "gnn": 0.4},
        transaction_type="ESEWA_P2P",
        total_latency_ms=552.4,
    )


def test_row_from_verdict_shape_and_rounding():
    row = row_from_verdict(_verdict(), fraud_type_predicted="ACCOUNT_TAKEOVER")
    assert row["txn_id"] == "TXN-20260531-A9F3C1AB"
    assert row["fraud_probability"] == 0.812346  # rounded to 6dp
    assert row["fraud_decision"] == "BLOCK"
    assert row["fraud_type_predicted"] == "ACCOUNT_TAKEOVER"
    assert row["latency_ms"] == 552  # int
    scores = json.loads(row["agent_scores_json"])
    assert scores == {"velocity": 0.7123, "gnn": 0.9}


def test_build_submission_df_exact_columns_and_order():
    # Records missing optional columns must still produce the full §8.4 column set.
    df = build_submission_df([
        {"txn_id": "TXN-1", "fraud_probability": 0.1, "fraud_decision": "ALLOW", "latency_ms": 10},
    ])
    assert list(df.columns) == SUBMISSION_COLUMNS
    assert df.loc[0, "fraud_type_predicted"] is None


def test_write_submission_roundtrip(tmp_path):
    path = write_submission([row_from_verdict(_verdict())], team_name="sentinel", out_dir=tmp_path)
    assert path.name == "submission_sentinel.csv"
    back = pd.read_csv(path)
    assert list(back.columns) == SUBMISSION_COLUMNS
    assert back.loc[0, "txn_id"] == "TXN-20260531-A9F3C1AB"
    assert back.loc[0, "fraud_decision"] == "BLOCK"
