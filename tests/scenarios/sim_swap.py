"""Scenario 3 — SIM-swap: attacker has email access but SMS went to stolen SIM.

State machine: SMS✗ + Email✓ → BLOCK + sim_swap_alert
The real owner still has email but their SMS OTP was intercepted via SIM swap.
"""
from __future__ import annotations

import asyncio
import json
import uuid
from unittest.mock import MagicMock

import pytest

from agents.otp.interlock import CustomerInfo, OTPInterlock
from agents.otp.providers import MockProvider
from tests.scenarios import register
from tests.scenarios.sita import SITA_FRAUD_TX


@register("sim_swap")
def run_sim_swap() -> dict:
    fake_r = _fake_redis()
    sms = MockProvider(redis_url="redis://localhost:6379/0")
    sms._r = fake_r
    email = MockProvider(redis_url="redis://localhost:6379/0")
    email._r = fake_r

    il = OTPInterlock(sms_provider=sms, email_provider=email, redis_url="redis://localhost:6379/0")
    il._r = fake_r

    customer = CustomerInfo(
        account_id="ACC_SITA_001",
        phone="+977-9841234567",
        email="sita@example.com",
    )
    asyncio.run(il.trigger(SITA_FRAUD_TX, customer))

    # Read the stored OTPs
    raw = fake_r.get(f"otp_pending:{SITA_FRAUD_TX.transaction_id}")
    data = json.loads(raw)
    # Attacker submits wrong SMS (they don't have it) but correct email
    # → SMS✗ + Email✓ → BLOCK + sim_swap_alert
    wrong_sms = "000000"
    correct_email = data["email_otp"]

    result = asyncio.run(il.confirm(str(SITA_FRAUD_TX.transaction_id), wrong_sms, correct_email))
    return result


def _fake_redis():
    store: dict = {}
    r = MagicMock()
    r.get.side_effect = lambda k: store.get(k)
    r.set.side_effect = lambda k, v: store.update({k: v})
    r.setex.side_effect = lambda k, ttl, v: store.update({k: v})
    r.delete.side_effect = lambda k: store.pop(k, None)
    r.keys.side_effect = lambda pat: [k for k in store if k.startswith(pat.replace("*", ""))]
    r.exists.side_effect = lambda k: k in store
    return r


# ---------------------------------------------------------------------------
# pytest test
# ---------------------------------------------------------------------------

@pytest.mark.scenario
def test_sim_swap_blocked():
    result = run_sim_swap()
    assert result["verdict"] == "BLOCK"
    assert result["reason"] == "sim_swap_alert"
