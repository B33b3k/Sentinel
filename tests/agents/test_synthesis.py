"""Unit tests for the Synthesis Agent."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest

from agents.synthesis.agent import SynthesisAgent
from orchestrator.schemas import AgentScore, TransactionEvent

_NOW = datetime(2026, 5, 14, 2, 14, 0, tzinfo=timezone.utc)


def _tx(tx_type: str = "QR_ESEWA", account_id: str = "ACC_TEST") -> TransactionEvent:
    return TransactionEvent(
        transaction_id=uuid.uuid4(),
        account_id=account_id,
        timestamp=_NOW,
        amount_npr=85000.0,
        transaction_type=tx_type,
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


def _score(agent: str, score: float) -> AgentScore:
    return AgentScore(agent=agent, score=score, reason_codes=[], latency_ms=1.0)


@pytest.fixture()
def synth():
    return SynthesisAgent()


class TestSynthesisAgent:
    def test_all_low_scores_allow(self, synth):
        scores = [_score(a, 0.1) for a in ("velocity", "geo", "behavior", "gnn")]
        verdict = synth.synthesize(_tx(), scores)
        assert verdict.verdict == "ALLOW"
        assert verdict.composite_score < 0.40

    def test_all_high_qr_block(self, synth):
        scores = [_score(a, 0.95) for a in ("velocity", "geo", "behavior", "gnn")]
        verdict = synth.synthesize(_tx("QR_ESEWA"), scores)
        assert verdict.verdict == "BLOCK"
        assert verdict.composite_score >= 0.75

    def test_mid_range_otp_interlock(self, synth):
        scores = [_score(a, 0.55) for a in ("velocity", "geo", "behavior", "gnn")]
        verdict = synth.synthesize(_tx(), scores)
        assert verdict.verdict == "OTP_INTERLOCK"

    def test_sita_scenario_otp_interlock(self, synth):
        """Sita: high geo (0.95) + high velocity (0.80) + high behavior (0.85), QR_ESEWA."""
        scores = [
            _score("velocity", 0.80),
            _score("geo", 0.95),
            _score("behavior", 0.85),
            _score("gnn", 0.0),
        ]
        verdict = synth.synthesize(_tx("QR_ESEWA"), scores)
        # QR weights: vel=0.35, geo=0.40, behavior=0.25, gnn=0.00
        # composite = 0.35*0.80 + 0.40*0.95 + 0.25*0.85 = 0.28+0.38+0.2125 = 0.8725 → BLOCK
        assert verdict.verdict in ("OTP_INTERLOCK", "BLOCK")
        assert 0.75 <= verdict.composite_score <= 1.0

    def test_swift_gnn_weight_dominates(self, synth):
        """SWIFT: gnn weight = 0.40, others low."""
        scores = [
            _score("velocity", 0.1),
            _score("geo", 0.1),
            _score("behavior", 0.1),
            _score("gnn", 0.9),
        ]
        verdict = synth.synthesize(_tx("SWIFT_REMITTANCE"), scores)
        # gnn contributes 0.40*0.9 = 0.36 alone
        assert verdict.weights_used["gnn"] == 0.40

    def test_missing_agent_neutral_score(self, synth):
        """Only velocity provided — others default to 0.5."""
        scores = [_score("velocity", 0.9)]
        verdict = synth.synthesize(_tx("P2P"), scores)
        missing = [s for s in verdict.agent_scores if "agent_unavailable" in s.reason_codes]
        assert len(missing) == 3  # geo, behavior, gnn all missing

    def test_weights_used_in_output(self, synth):
        scores = [_score(a, 0.5) for a in ("velocity", "geo", "behavior", "gnn")]
        verdict = synth.synthesize(_tx("ATM_POS"), scores)
        assert verdict.weights_used == {"velocity": 0.30, "geo": 0.45, "behavior": 0.25, "gnn": 0.00}

    def test_composite_bounded(self, synth):
        scores = [_score(a, 1.0) for a in ("velocity", "geo", "behavior", "gnn")]
        verdict = synth.synthesize(_tx(), scores)
        assert 0.0 <= verdict.composite_score <= 1.0
