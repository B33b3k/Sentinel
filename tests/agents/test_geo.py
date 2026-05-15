"""Unit tests for the Geo Agent."""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

from agents.geo.agent import GeoAgent
from orchestrator.schemas import TransactionEvent

_NOW = datetime(2026, 5, 14, 12, 0, 0, tzinfo=timezone.utc)

# Kathmandu coords
_KTM_LAT, _KTM_LON = 27.7172, 85.3240
# Dharan coords (~300 km east)
_DHARAN_LAT, _DHARAN_LON = 26.8141, 87.2792
# Dhangadhi coords (~800 km west)
_DHANGADHI_LAT, _DHANGADHI_LON = 28.6833, 80.6000


def _tx(
    account_id: str = "ACC_TEST",
    device_id: str = "device_test_0",
    ip: str = "27.34.1.1",
    lat: float = _KTM_LAT,
    lon: float = _KTM_LON,
    district: str = "Kathmandu",
    age_days: int = 365,
    ts: datetime = _NOW,
) -> TransactionEvent:
    return TransactionEvent(
        transaction_id=uuid.uuid4(),
        account_id=account_id,
        timestamp=ts,
        amount_npr=3000.0,
        transaction_type="QR_ESEWA",
        counterparty_id="MERCHANT_001",
        counterparty_name=None,
        device_id=device_id,
        ip_address=ip,
        geo_lat=lat,
        geo_lon=lon,
        geo_city=district,
        geo_district=district,
        account_age_days=age_days,
        account_home_district="Kathmandu",
        account_type="SAVINGS",
    )


@pytest.fixture()
def fake_redis():
    store: dict = {}
    r = MagicMock()
    r.get.side_effect = lambda k: store.get(k)
    r.set.side_effect = lambda k, v: store.update({k: v})
    r.exists.side_effect = lambda k: k in store
    return r, store


@pytest.fixture()
def agent(fake_redis):
    r, _ = fake_redis
    with patch("agents.geo.agent.redis.Redis.from_url", return_value=r):
        return GeoAgent()


class TestGeoAgent:
    def test_same_device_same_city_low_score(self, agent, fake_redis):
        _, store = fake_redis
        acct = "ACC_SAME"
        # Pre-seed history with the same device
        store[f"geo:hist:{acct}"] = json.dumps({
            "devices": ["device_test_0"],
            "last_location": {"lat": _KTM_LAT, "lon": _KTM_LON},
            "last_timestamp": (_NOW - timedelta(hours=2)).timestamp(),
        })
        result = agent.score(_tx(account_id=acct))
        assert result.score < 0.3

    def test_new_device_established_account(self, agent, fake_redis):
        _, store = fake_redis
        acct = "ACC_NEWDEV"
        store[f"geo:hist:{acct}"] = json.dumps({
            "devices": ["device_old_0"],
            "last_location": {"lat": _KTM_LAT, "lon": _KTM_LON},
            "last_timestamp": (_NOW - timedelta(hours=1)).timestamp(),
        })
        result = agent.score(_tx(account_id=acct, device_id="device_brand_new", age_days=365))
        assert result.score >= 0.65
        assert "new_device" in result.reason_codes

    def test_geo_impossible_kathmandu_to_dharan_30min(self, agent, fake_redis):
        """Kathmandu → Dhangadhi (~800 km) in 30 minutes = ~1600 km/h → impossible."""
        _, store = fake_redis
        acct = "ACC_SITA_001"
        store[f"geo:hist:{acct}"] = json.dumps({
            "devices": ["device_sita_0"],
            "last_location": {"lat": _KTM_LAT, "lon": _KTM_LON},
            "last_timestamp": (_NOW - timedelta(minutes=30)).timestamp(),
        })
        result = agent.score(_tx(
            account_id=acct,
            device_id="device_unknown_new",
            lat=_DHANGADHI_LAT, lon=_DHANGADHI_LON,
            district="Dhangadhi",
        ))
        assert result.score >= 0.95
        assert any("geo_velocity_impossible" in rc for rc in result.reason_codes)

    def test_vpn_ip_adds_premium(self, agent, fake_redis):
        _, store = fake_redis
        acct = "ACC_VPN"
        store[f"geo:hist:{acct}"] = json.dumps({
            "devices": ["device_test_0"],
            "last_location": {"lat": _KTM_LAT, "lon": _KTM_LON},
            "last_timestamp": (_NOW - timedelta(hours=1)).timestamp(),
        })
        result = agent.score(_tx(account_id=acct, ip="185.220.101.55"))
        assert "vpn_or_proxy" in result.reason_codes

    def test_score_bounded(self, agent):
        result = agent.score(_tx())
        assert 0.0 <= result.score <= 1.0
