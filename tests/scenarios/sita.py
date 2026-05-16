"""Scenario 1 — Sita fraud + Scenario 2 — Legitimate Sita."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest

from orchestrator.schemas import TransactionEvent
from tests.scenarios import register

SITA_FRAUD_TX = TransactionEvent(
    transaction_id=uuid.uuid4(),
    account_id="ACC_SITA_001",
    timestamp=datetime(2026, 5, 30, 2, 14, tzinfo=timezone.utc),
    amount_npr=85000.0,
    transaction_type="QR_ESEWA",
    counterparty_id="MERCHANT_UNKNOWN_42",
    counterparty_name=None,
    device_id="device_unknown_new",
    ip_address="103.69.1.1",
    geo_lat=26.8141,
    geo_lon=87.2792,
    geo_city="Dharan",
    geo_district="Dharan",
    account_age_days=720,
    account_home_district="Kathmandu",
    account_type="SAVINGS",
)

SITA_LEGIT_TX = TransactionEvent(
    transaction_id=uuid.uuid4(),
    account_id="ACC_SITA_001",
    timestamp=datetime(2026, 5, 30, 11, 0, tzinfo=timezone.utc),
    amount_npr=1200.0,
    transaction_type="QR_ESEWA",
    counterparty_id="MERCHANT_001",
    counterparty_name=None,
    device_id="device_ACC_SITA_001_0",
    ip_address="27.34.1.1",
    geo_lat=27.7172,
    geo_lon=85.3240,
    geo_city="Kathmandu",
    geo_district="Kathmandu",
    account_age_days=720,
    account_home_district="Kathmandu",
    account_type="SAVINGS",
)


@register("sita")
def run_sita() -> dict:
    from agents.synthesis.agent import SynthesisAgent
    from agents.geo.agent import GeoAgent
    from agents.velocity.agent import VelocityAgent
    from unittest.mock import MagicMock, patch

    # Use real synthesis with mocked Redis agents for deterministic results
    synth = SynthesisAgent()
    from orchestrator.schemas import AgentScore
    fraud_scores = [
        AgentScore(agent="velocity", score=0.75, reason_codes=["freq_burst_2m"], latency_ms=15.3),
        AgentScore(agent="geo",      score=0.95, reason_codes=["new_device", "geo_velocity_impossible:1200kmh"], latency_ms=24.7),
        AgentScore(agent="behavior", score=0.85, reason_codes=["mode:ensemble_cohort=savings_urban"], latency_ms=68.2),
        AgentScore(agent="gnn",      score=0.05, reason_codes=["no_mule_pattern"], latency_ms=42.1),
    ]
    verdict = synth.synthesize(SITA_FRAUD_TX, fraud_scores)
    return verdict.model_dump()


@register("sita_legit")
def run_sita_legit() -> dict:
    from agents.synthesis.agent import SynthesisAgent
    from orchestrator.schemas import AgentScore
    synth = SynthesisAgent()
    legit_scores = [
        AgentScore(agent="velocity", score=0.05, reason_codes=[], latency_ms=12.8),
        AgentScore(agent="geo",      score=0.05, reason_codes=[], latency_ms=18.3),
        AgentScore(agent="behavior", score=0.08, reason_codes=[], latency_ms=52.1),
        AgentScore(agent="gnn",      score=0.05, reason_codes=[], latency_ms=38.9),
    ]
    verdict = synth.synthesize(SITA_LEGIT_TX, legit_scores)
    return verdict.model_dump()


# ---------------------------------------------------------------------------
# pytest tests
# ---------------------------------------------------------------------------

@pytest.mark.scenario
def test_sita_fraud_otp_or_block():
    result = run_sita()
    assert result["verdict"] in ("OTP_INTERLOCK", "BLOCK")
    assert result["composite_score"] >= 0.75


@pytest.mark.scenario
def test_sita_legit_allow():
    result = run_sita_legit()
    assert result["verdict"] == "ALLOW"
    assert result["composite_score"] < 0.40
