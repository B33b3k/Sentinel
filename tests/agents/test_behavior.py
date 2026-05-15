"""Unit tests for the Behavior Agent."""
from __future__ import annotations

import json
import pickle
import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from agents.behavior.agent import BehaviorAgent
from orchestrator.schemas import AgentScore, TransactionEvent

_NOW = datetime(2026, 5, 30, 2, 14, 0, tzinfo=timezone.utc)
_DAY = datetime(2026, 5, 30, 11, 0, 0, tzinfo=timezone.utc)


def _tx(
    account_id: str = "ACC_TEST",
    amount: float = 3000.0,
    ts: datetime = _DAY,
    device_id: str = "device_test_0",
    district: str = "Kathmandu",
    age_days: int = 365,
    account_type: str = "SAVINGS",
    tx_type: str = "QR_ESEWA",
) -> TransactionEvent:
    return TransactionEvent(
        transaction_id=uuid.uuid4(),
        account_id=account_id,
        timestamp=ts,
        amount_npr=amount,
        transaction_type=tx_type,
        counterparty_id="MERCHANT_001",
        device_id=device_id,
        ip_address="27.34.1.1",
        geo_lat=27.7172,
        geo_lon=85.3240,
        geo_city=district,
        geo_district=district,
        account_age_days=age_days,
        account_home_district="Kathmandu",
        account_type=account_type,
    )


def _fake_redis(seq: list | None = None):
    """In-memory Redis mock, optionally pre-seeded with a behavior sequence."""
    store: dict = {}
    if seq is not None:
        store["behavior:seq:ACC_TEST"] = json.dumps(seq)
    r = MagicMock()
    r.get.side_effect = lambda k: store.get(k)
    r.set.side_effect = lambda k, v: store.update({k: v})
    r.setex.side_effect = lambda k, ttl, v: store.update({k: v})
    r.exists.side_effect = lambda k: k in store
    return r


def _stub_if_model(score: float = 0.5):
    """Isolation Forest stub that returns a fixed decision_function value.

    Agent computes: score = 1 / (1 + exp(raw * 5))
    Inverting: raw = ln(1/score - 1) / 5  (positive raw → low score, negative raw → high score)
    """
    m = MagicMock()
    import math
    raw = math.log(1 / max(score, 1e-6) - 1) / 5
    m.decision_function.return_value = np.array([raw])
    return m


@pytest.fixture()
def agent_no_models():
    """Agent with no trained models — exercises fallback paths."""
    r = _fake_redis()
    with patch("agents.behavior.agent.redis.Redis.from_url", return_value=r):
        a = BehaviorAgent.__new__(BehaviorAgent)
        a._r = r
        a._if_models = {}
        a._lstm_models = {}
        return a


@pytest.fixture()
def agent_with_if():
    """Agent with a stubbed IF model for 'savings_urban' cohort."""
    r = _fake_redis()
    with patch("agents.behavior.agent.redis.Redis.from_url", return_value=r):
        a = BehaviorAgent.__new__(BehaviorAgent)
        a._r = r
        a._if_models = {"savings_urban": _stub_if_model(0.2), "fallback": _stub_if_model(0.2)}
        a._lstm_models = {}
        return a


class TestBehaviorAgentColdStart:
    def test_day2_strict_rules_abstains(self, agent_no_models):
        """Day 0-3: behavior agent uses NRB rules only, no ML."""
        tx = _tx(age_days=2, amount=5000.0)
        result = agent_no_models.score(tx)
        assert result.agent == "behavior"
        assert "mode:strict_rules" in result.reason_codes
        assert 0.0 <= result.score <= 1.0

    def test_day2_large_amount_blocked_by_rules(self, agent_no_models):
        """Day 1 + NPR 80K exceeds NRB cap → high score."""
        tx = _tx(age_days=1, amount=80000.0)
        result = agent_no_models.score(tx)
        assert result.score >= 0.8
        assert "mode:strict_rules" in result.reason_codes

    def test_new_account_no_history_if_only(self, agent_with_if):
        """< 5 tx history → IF-only mode, no LSTM."""
        tx = _tx(age_days=30)
        result = agent_with_if.score(tx)
        assert "mode:if_only" in result.reason_codes
        assert 0.0 <= result.score <= 1.0

    def test_score_bounded(self, agent_no_models):
        result = agent_no_models.score(_tx())
        assert 0.0 <= result.score <= 1.0

    def test_latency_recorded(self, agent_no_models):
        result = agent_no_models.score(_tx())
        assert result.latency_ms >= 0.0


class TestBehaviorAgentSita:
    def test_sita_normal_daytime_low_score(self, agent_with_if):
        """Sita's normal 11am NPR 1,200 grocery → low IF score."""
        # Stub IF to return low anomaly score
        agent_with_if._if_models["savings_urban"] = _stub_if_model(0.1)
        agent_with_if._if_models["fallback"] = _stub_if_model(0.1)
        tx = _tx(account_id="ACC_SITA_001", amount=1200.0, ts=_DAY, age_days=720)
        result = agent_with_if.score(tx)
        assert result.score < 0.4

    def test_sita_fraud_2am_high_score(self, agent_with_if):
        """Sita's 2am NPR 85K → high IF anomaly score."""
        agent_with_if._if_models["savings_urban"] = _stub_if_model(0.9)
        agent_with_if._if_models["fallback"] = _stub_if_model(0.9)
        tx = _tx(account_id="ACC_SITA_001", amount=85000.0, ts=_NOW, age_days=720)
        result = agent_with_if.score(tx)
        assert result.score >= 0.7

    def test_if_model_unavailable_returns_neutral(self, agent_no_models):
        """No models at all → neutral 0.5 with reason code."""
        tx = _tx(age_days=30)
        result = agent_no_models.score(tx)
        # With no models, IF returns 0.5 neutral
        assert result.score == 0.5 or "if_model_unavailable" in result.reason_codes

    def test_sita_2am_lstm_ensemble_score_above_085(self):
        """Sita 2am NPR 85K with LSTM ensemble (>= 5 tx history) → score > 0.85."""
        from ml.training.featurize import FEATURE_COLS
        n_features = len(FEATURE_COLS)
        # Pre-seed 10 transactions in history so LSTM path is taken
        history = [[0.0] * n_features for _ in range(10)]
        r = _fake_redis(seq=history)

        # Stub IF and LSTM both returning high fraud scores
        if_model = _stub_if_model(0.95)
        lstm_model = MagicMock()
        lstm_model.return_value = MagicMock()
        # Patch _run_lstm to return 0.95 directly
        with patch("agents.behavior.agent.redis.Redis.from_url", return_value=r):
            a = BehaviorAgent.__new__(BehaviorAgent)
            a._r = r
            a._if_models = {"savings_urban": if_model, "fallback": if_model}
            a._lstm_models = {"savings_urban": MagicMock()}

        # Patch _run_lstm to return high score
        with patch.object(a, "_run_lstm", return_value=0.95):
            tx = _tx(account_id="ACC_TEST", amount=85000.0, ts=_NOW, age_days=720)
            result = a.score(tx)

        assert result.score >= 0.85, f"Expected >= 0.85, got {result.score}"
        assert "mode:ensemble_cohort" in " ".join(result.reason_codes)

    def test_sequence_lt5_uses_if_only(self):
        """< 5 tx in history → IF-only mode even when LSTM model exists."""
        from ml.training.featurize import FEATURE_COLS
        n_features = len(FEATURE_COLS)
        # Only 3 transactions in history
        history = [[0.0] * n_features for _ in range(3)]
        r = _fake_redis(seq=history)

        if_model = _stub_if_model(0.5)
        with patch("agents.behavior.agent.redis.Redis.from_url", return_value=r):
            a = BehaviorAgent.__new__(BehaviorAgent)
            a._r = r
            a._if_models = {"savings_urban": if_model, "fallback": if_model}
            a._lstm_models = {"savings_urban": MagicMock()}  # LSTM exists but should not run

        tx = _tx(account_id="ACC_TEST", amount=3000.0, ts=_DAY, age_days=365)
        result = a.score(tx)
        assert "mode:if_only" in result.reason_codes
