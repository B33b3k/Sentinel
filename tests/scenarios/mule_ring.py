"""Scenario 5 — Mule ring: 5 sources → 1 mule → 1 destination."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest

from agents.synthesis.agent import SynthesisAgent
from orchestrator.schemas import AgentScore, TransactionEvent
from tests.scenarios import register

_MULE_TX = TransactionEvent(
    transaction_id=uuid.uuid4(),
    account_id="ACC_MULE_001",
    timestamp=datetime(2026, 5, 30, 15, 30, tzinfo=timezone.utc),
    amount_npr=95000.0,
    transaction_type="SWIFT_REMITTANCE",
    counterparty_id="ACC_DEST_999",
    counterparty_name=None,
    device_id="device_ACC_MULE_001_0",
    ip_address="27.34.1.1",
    geo_lat=27.7172,
    geo_lon=85.3240,
    geo_city="Kathmandu",
    geo_district="Kathmandu",
    account_age_days=30,
    account_home_district="Kathmandu",
    account_type="REMITTANCE",
)


@register("mule_ring")
def run_mule_ring() -> dict:
    synth = SynthesisAgent()
    # GNN detects mule ring → high score
    scores = [
        AgentScore(agent="velocity", score=0.20, reason_codes=[], latency_ms=3),
        AgentScore(agent="geo",      score=0.15, reason_codes=[], latency_ms=5),
        AgentScore(agent="behavior", score=0.30, reason_codes=[], latency_ms=20),
        AgentScore(agent="gnn",      score=0.92, reason_codes=["mule_ring_detected"], latency_ms=8),
    ]
    verdict = synth.synthesize(_MULE_TX, scores)
    return verdict.model_dump()


@pytest.mark.scenario
def test_mule_ring_blocked():
    result = run_mule_ring()
    # SWIFT weights: gnn=0.40 * 0.92 = 0.368 → composite should be high
    assert result["verdict"] in ("OTP_INTERLOCK", "BLOCK")
    assert result["composite_score"] >= 0.40
