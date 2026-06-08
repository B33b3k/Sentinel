"""Tests for §8.2 bonus-evidence artifacts."""
from __future__ import annotations

import json

import pandas as pd

from orchestrator.bonus import (
    OTP_SUBMISSION_COLUMNS,
    SHAP_COLUMNS,
    build_shap_df,
    detect_smurfing_community,
    explain_verdict,
    otp_escalations,
    write_community_detection,
)
from orchestrator.offline_scorer import score_row


# ── community detection ──────────────────────────────────────────────────────

def _edges() -> pd.DataFrame:
    rows = []
    # 8 smurfs → collector; amounts decreasing so ranking is deterministic.
    for i in range(8):
        rows.append({"source": f"ACC-{i:07d}", "target": "ACC-0011204",
                     "txn_id": f"TXN-{i}", "amount_npr": 90000 - i * 1000})
    # noise: an unrelated edge not targeting the collector
    rows.append({"source": "ACC-9999999", "target": "ACC-8888888",
                 "txn_id": "TXN-X", "amount_npr": 5000})
    return pd.DataFrame(rows)


def test_detect_smurfing_community_top7():
    res = detect_smurfing_community(_edges())
    assert res["community_id"] == "COMM-042"
    assert res["collector_account"] == "ACC-0011204"
    assert res["total_members"] == 7
    assert res["member_accounts"][0] == "ACC-0000000"  # highest inflow ranks first
    assert "ACC-9999999" not in res["member_accounts"]  # not feeding the collector


def test_write_community_detection_json(tmp_path):
    path = write_community_detection(_edges(), out_dir=tmp_path)
    data = json.loads(path.read_text())
    assert path.name == "community_detection.json"
    assert len(data["member_accounts"]) == 7


# ── OTP sim-swap escalations ─────────────────────────────────────────────────

def test_otp_escalations_filters_and_labels():
    otp = pd.DataFrame([
        {"otp_event_id": "OTP-1", "txn_id": "TXN-1", "account_id": "ACC-1",
         "channel_1_status": "VERIFIED", "channel_2_status": "VERIFIED",
         "sim_swap_suspected": False, "final_decision": "ALLOWED"},
        {"otp_event_id": "OTP-2", "txn_id": "TXN-2", "account_id": "ACC-2",
         "channel_1_status": "EXPIRED", "channel_2_status": "VERIFIED",
         "sim_swap_suspected": False, "final_decision": "BLOCKED"},
        {"otp_event_id": "OTP-3", "txn_id": "TXN-3", "account_id": "ACC-3",
         "channel_1_status": "FAILED", "channel_2_status": "FAILED",
         "sim_swap_suspected": True, "final_decision": "ESCALATED"},
    ])
    out = otp_escalations(otp)
    assert list(out.columns) == OTP_SUBMISSION_COLUMNS
    assert set(out["otp_event_id"]) == {"OTP-2", "OTP-3"}  # OTP-1 not escalated
    assert (out["action"] == "ESCALATE").all()
    r2 = out[out["otp_event_id"] == "OTP-2"].iloc[0]
    assert r2["escalation_reason"] == "sms_failed_email_verified"
    r3 = out[out["otp_event_id"] == "OTP-3"].iloc[0]
    assert r3["escalation_reason"] == "sim_swap_suspected"


# ── SHAP-style attributions ──────────────────────────────────────────────────

def test_explain_verdict_additive_and_topk():
    row = {
        "txn_id": "TXN-E", "txn_type": "ESEWA_P2P", "counterparty_id": "MERCH-8812",
        "z_score_amount": 6.0, "txn_count_1m": 4, "unique_counterparties_1h": 5,
        "dormancy_break": True, "night_flag": True, "new_counterparty_flag": True,
        "impossible_travel": True, "is_tor": True, "is_datacenter": True,
        "km_from_home_district": 4000.0, "prev_txn_km": 6000.0,
        "within_24h_reciprocal": True, "is_first_transfer_to_target": True,
        "degree_in": 1890, "degree_out": 2,
    }
    v = score_row(row)
    rows = explain_verdict(v, top_k=5)
    assert len(rows) == 5
    assert [r["rank"] for r in rows] == [1, 2, 3, 4, 5]
    # magnitudes are sorted descending
    vals = [abs(r["shap_value"]) for r in rows]
    assert vals == sorted(vals, reverse=True)


def test_build_shap_df_schema():
    v = score_row({"txn_id": "T", "txn_type": "ESEWA_P2P", "counterparty_id": "MERCH-8812"})
    df = build_shap_df([v])
    assert list(df.columns) == SHAP_COLUMNS
    assert (df["txn_id"] == "T").all()
