"""Unit tests for OTP interlock state machine."""
import asyncio
import json
import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock

from agents.otp.interlock import CustomerInfo, OTPInterlock
from agents.otp.providers import MockProvider
from orchestrator.schemas import TransactionEvent


def _fake_redis():
    store: dict = {}
    r = MagicMock()
    r.get.side_effect = lambda k: store.get(k)
    r.set.side_effect = lambda k, v: store.update({k: v})
    r.setex.side_effect = lambda k, ttl, v: store.update({k: v})
    r.delete.side_effect = lambda k: store.pop(k, None)
    r.keys.side_effect = lambda p: [k for k in store if k.startswith(p.replace("*", ""))]
    r.exists.side_effect = lambda k: k in store
    return r, store


def _tx(tx_id=None):
    return TransactionEvent(
        transaction_id=tx_id or uuid.uuid4(),
        account_id="ACC_TEST",
        timestamp=datetime(2026, 5, 30, 2, 0, tzinfo=timezone.utc),
        amount_npr=85000.0,
        transaction_type="QR_ESEWA",
        account_age_days=720,
        account_home_district="Kathmandu",
        account_type="SAVINGS",
    )


def _setup():
    r, store = _fake_redis()
    sms = MockProvider(); sms._r = r
    email = MockProvider(); email._r = r
    il = OTPInterlock(sms_provider=sms, email_provider=email, redis_url="redis://localhost")
    il._r = r
    customer = CustomerInfo(account_id="ACC_TEST", phone="+977-9841234567", email="test@example.com")
    return il, customer, store


def test_both_correct_release():
    il, customer, store = _setup()
    tx = _tx()
    asyncio.run(il.trigger(tx, customer))
    data = json.loads(store[f"otp_pending:{tx.transaction_id}"])
    result = asyncio.run(il.confirm(str(tx.transaction_id), data["sms_otp"], data["email_otp"]))
    assert result["verdict"] == "RELEASE"


def test_wrong_sms_correct_email_sim_swap():
    il, customer, store = _setup()
    tx = _tx()
    asyncio.run(il.trigger(tx, customer))
    data = json.loads(store[f"otp_pending:{tx.transaction_id}"])
    result = asyncio.run(il.confirm(str(tx.transaction_id), "000000", data["email_otp"]))
    assert result["verdict"] == "BLOCK"
    assert result["reason"] == "sim_swap_alert"


def test_correct_sms_wrong_email_human_review():
    il, customer, store = _setup()
    tx = _tx()
    asyncio.run(il.trigger(tx, customer))
    data = json.loads(store[f"otp_pending:{tx.transaction_id}"])
    result = asyncio.run(il.confirm(str(tx.transaction_id), data["sms_otp"], "000000"))
    assert result["verdict"] == "HUMAN_REVIEW"


def test_both_wrong_block():
    il, customer, store = _setup()
    tx = _tx()
    asyncio.run(il.trigger(tx, customer))
    result = asyncio.run(il.confirm(str(tx.transaction_id), "000000", "000000"))
    assert result["verdict"] == "BLOCK"
    assert result["reason"] == "both_failed"


def test_expired_otp_rejected():
    il, customer, store = _setup()
    tx = _tx()
    # Don't trigger — no key in store
    result = asyncio.run(il.confirm(str(tx.transaction_id), "123456", "123456"))
    assert result["verdict"] == "EXPIRED"
