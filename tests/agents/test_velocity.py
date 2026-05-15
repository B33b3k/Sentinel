"""Unit tests for the Velocity Agent."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from agents.velocity.agent import VelocityAgent
from orchestrator.schemas import TransactionEvent

_NOW = datetime(2026, 5, 14, 12, 0, 0, tzinfo=timezone.utc)


def _tx(account_id: str = "ACC_TEST", amount: float = 3000.0) -> TransactionEvent:
    return TransactionEvent(
        transaction_id=uuid.uuid4(),
        account_id=account_id,
        timestamp=_NOW,
        amount_npr=amount,
        transaction_type="P2P",
        counterparty_id="MERCHANT_001",
        counterparty_name=None,
        device_id="device_test_0",
        ip_address="27.34.1.1",
        geo_lat=27.7172,
        geo_lon=85.3240,
        geo_city="Kathmandu",
        geo_district="Kathmandu",
        account_age_days=365,
        account_home_district="Kathmandu",
        account_type="SAVINGS",
    )


@pytest.fixture()
def agent(fake_redis):
    with patch("agents.velocity.agent.redis.Redis.from_url", return_value=fake_redis):
        return VelocityAgent()


@pytest.fixture()
def fake_redis():
    """Minimal in-memory Redis mock."""
    store: dict = {}
    zsets: dict = {}

    r = MagicMock()

    def zadd(key, mapping):
        zsets.setdefault(key, {}).update(mapping)

    def zcount(key, mn, mx):
        return sum(1 for v in zsets.get(key, {}).values() if mn <= v <= mx)

    def get(key):
        return store.get(key)

    def set_(key, value, *a, **kw):
        store[key] = str(value)

    def exists(key):
        return key in store

    def expire(key, ttl):
        pass

    r.zadd.side_effect = zadd
    r.zcount.side_effect = zcount
    r.get.side_effect = get
    r.set.side_effect = set_
    r.exists.side_effect = exists
    r.expire.side_effect = expire
    return r


class TestVelocityAgent:
    def test_empty_history_low_score(self, agent):
        result = agent.score(_tx())
        assert result.score < 0.3
        assert result.agent == "velocity"

    def test_high_frequency_burst(self, agent):
        # Simulate 10 prior tx in the 2m window already in the sorted set
        acct = "ACC_BURST"
        ts = _NOW.timestamp()
        agent._r.zadd(f"vel:{acct}", {f"tx_{i}": ts - i for i in range(10)})
        # Set low baseline avg so ratio is high
        agent._r.get = lambda k: "2" if "velavg" in k else None
        result = agent.score(_tx(account_id=acct))
        assert result.score >= 0.5
        assert any("freq_burst" in rc for rc in result.reason_codes)

    def test_amount_spike(self, agent):
        acct = "ACC_SPIKE"
        # avg amount = 100, tx amount = 15000 → 150x spike
        agent._r.get = lambda k: "100" if "amtavg" in k else None
        result = agent.score(_tx(account_id=acct, amount=15000.0))
        assert result.score >= 0.5
        assert any("amount_spike" in rc for rc in result.reason_codes)

    def test_score_bounded(self, agent):
        result = agent.score(_tx())
        assert 0.0 <= result.score <= 1.0

    def test_latency_recorded(self, agent):
        result = agent.score(_tx())
        assert result.latency_ms >= 0.0
