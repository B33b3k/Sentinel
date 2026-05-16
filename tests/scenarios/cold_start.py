"""Scenario 4 — Cold-start: new overseas_worker account, day 5."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest

from agents.synthesis.agent import SynthesisAgent
from orchestrator.schemas import AgentScore, TransactionEvent
from tests.scenarios import register

_NEW_ACCT_LEGIT = TransactionEvent(
    transaction_id=uuid.uuid4(),
    account_id="ACC_NEW_OW_001",
    timestamp=datetime(2026, 5, 30, 14, 0, tzinfo=timezone.utc),
    amount_npr=45000.0,
    transaction_type="SWIFT_REMITTANCE",
    counterparty_id="ACC_NEW_OW_001",
    counterparty_name=None,
    device_id="device_ACC_NEW_OW_001_0",
    ip_address="27.34.1.1",
    geo_lat=27.7172,
    geo_lon=85.3240,
    geo_city="Kathmandu",
    geo_district="Kathmandu",
    account_age_days=5,
    account_home_district="Kathmandu",
    account_type="REMITTANCE",
)

_NEW_ACCT_SUSPICIOUS = TransactionEvent(
    transaction_id=uuid.uuid4(),
    account_id="ACC_NEW_OW_001",
    timestamp=datetime(2026, 5, 30, 23, 0, tzinfo=timezone.utc),
    amount_npr=90000.0,
    transaction_type="SWIFT_REMITTANCE",
    counterparty_id="ACC_UNKNOWN_999",
    counterparty_name=None,
    device_id="device_unknown_new",
    ip_address="185.220.101.1",
    geo_lat=26.8141,
    geo_lon=87.2792,
    geo_city="Dharan",
    geo_district="Dharan",
    account_age_days=5,
    account_home_district="Kathmandu",
    account_type="REMITTANCE",
)


@register("cold_start")
def run_cold_start() -> dict:
    synth = SynthesisAgent()
    # Legit inbound — cohort model passes
    legit_scores = [
        AgentScore(agent="velocity", score=0.10, reason_codes=[], latency_ms=14.2),
        AgentScore(agent="geo",      score=0.10, reason_codes=[], latency_ms=39.42),
        AgentScore(agent="behavior", score=0.15, reason_codes=["mode:if_only"], latency_ms=39.40),
        AgentScore(agent="gnn",      score=0.05, reason_codes=[], latency_ms=39.4),
    ]
    legit_verdict = synth.synthesize(_NEW_ACCT_LEGIT, legit_scores)

    # Suspicious outbound — new device + VPN + high amount
    sus_scores = [
        AgentScore(agent="velocity", score=0.30, reason_codes=[], latency_ms=14.2),
        AgentScore(agent="geo",      score=0.80, reason_codes=["new_device", "vpn_or_proxy"], latency_ms=39.42),
        AgentScore(agent="behavior", score=0.70, reason_codes=["mode:if_only"], latency_ms=39.40),
        AgentScore(agent="gnn",      score=0.05, reason_codes=[], latency_ms=39.4),
    ]
    sus_verdict = synth.synthesize(_NEW_ACCT_SUSPICIOUS, sus_scores)

    return {
        "legit": legit_verdict.model_dump(),
        "suspicious": sus_verdict.model_dump(),
    }


@pytest.mark.scenario
def test_cold_start_legit_allow():
    result = run_cold_start()
    assert result["legit"]["verdict"] == "ALLOW"


@pytest.mark.scenario
def test_cold_start_suspicious_flagged():
    result = run_cold_start()
    assert result["suspicious"]["verdict"] in ("OTP_INTERLOCK", "BLOCK")
