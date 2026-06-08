"""Tests for the offline multi-agent batch scorer (DATA_DESCRIPTION columns)."""
from __future__ import annotations

from orchestrator.offline_scorer import (
    score_behavior,
    score_geo,
    score_gnn,
    score_row,
    score_velocity,
)


def _clean_row() -> dict:
    return {
        "txn_id": "TXN-20260101-00000001",
        "account_id": "ACC-0000001",
        "txn_type": "KHALTI_QR",
        "amount_npr": 500.0,
        "counterparty_id": "MERCH-0001",
        "z_score_amount": 0.2, "txn_count_1m": 0, "unique_counterparties_1h": 1,
        "dormancy_break": False, "night_flag": False, "new_counterparty_flag": False,
        "impossible_travel": False, "is_tor": False, "is_datacenter": False, "is_vpn": False,
        "km_from_home_district": 3.0, "prev_txn_km": 2.0,
        "within_24h_reciprocal": False, "is_first_transfer_to_target": False,
        "degree_in": 4, "degree_out": 3,
    }


def _fraud_row() -> dict:
    r = _clean_row()
    r.update({
        "txn_id": "TXN-20260101-DEADBEEF", "txn_type": "ESEWA_P2P",
        "counterparty_id": "MERCH-8812",          # §4 fraud merchant (227×)
        "z_score_amount": 6.0, "txn_count_1m": 4, "unique_counterparties_1h": 5,
        "dormancy_break": True, "night_flag": True, "new_counterparty_flag": True,
        "impossible_travel": True, "is_tor": True, "is_datacenter": True,
        "km_from_home_district": 4000.0, "prev_txn_km": 6000.0,
        "within_24h_reciprocal": True, "is_first_transfer_to_target": True,
        "degree_in": 1890, "degree_out": 2,        # collector shape
    })
    return r


def test_clean_row_allows():
    v = score_row(_clean_row())
    assert v.verdict == "ALLOW"
    assert v.composite_score < 0.40


def test_fraud_row_blocks_with_reasons():
    v = score_row(_fraud_row())
    assert v.verdict == "BLOCK"
    assert v.composite_score >= 0.75
    reasons = {rc for s in v.agent_scores for rc in s.reason_codes}
    assert "impossible_travel" in reasons
    assert "fraud_merchant" in reasons
    assert "z_score_amount_high" in reasons


def test_scorers_return_none_without_inputs():
    # A row with none of an agent's columns → None → synthesis imputes 0.5.
    bare = {"txn_id": "T", "account_id": "A", "txn_type": "RTGS", "amount_npr": 1.0}
    assert score_velocity(bare) is None
    assert score_geo(bare) is None
    assert score_behavior(bare) is None
    assert score_gnn(bare) is None


def test_fraud_merchant_drives_gnn():
    row = {"txn_id": "T", "counterparty_id": "MERCH-9041"}
    s = score_gnn(row)
    assert s is not None and s.score >= 0.8
    assert "fraud_merchant" in s.reason_codes
