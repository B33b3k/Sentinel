"""OTP Interlock — dual-path verification with SIM-swap detection."""
from __future__ import annotations

import json
import os
import random
import string
import time
from dataclasses import dataclass

import redis

from agents.otp.providers import OTPProvider, get_email_provider, get_sms_provider
from orchestrator.schemas import TransactionEvent

_OTP_TTL = 300  # 5 minutes


@dataclass
class CustomerInfo:
    account_id: str
    phone: str
    email: str


class OTPInterlock:
    def __init__(
        self,
        sms_provider: OTPProvider | None = None,
        email_provider: OTPProvider | None = None,
        redis_url: str = "redis://localhost:6379/0",
        kafka_producer=None,
    ) -> None:
        self._sms = sms_provider or get_sms_provider()
        self._email = email_provider or get_email_provider()
        self._r = redis.Redis.from_url(redis_url, decode_responses=True)
        self._producer = kafka_producer

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def trigger(self, tx: TransactionEvent, customer: CustomerInfo) -> bool:
        """Freeze tx, generate 2 OTPs, dispatch both. Returns True if dispatched."""
        sms_code = _gen_code()
        email_code = _gen_code()

        payload = {
            "sms_otp": sms_code,
            "email_otp": email_code,
            "customer_phone": customer.phone,
            "customer_email": customer.email,
            "account_id": customer.account_id,
            "tx_id": str(tx.transaction_id),
            "triggered_at": time.time(),
        }
        self._r.setex(f"otp_pending:{tx.transaction_id}", _OTP_TTL, json.dumps(payload))
        self._freeze_transaction(tx)

        sms_ok = self._sms.send(customer.phone, sms_code)
        email_ok = self._email.send(customer.email, email_code)
        return sms_ok and email_ok

    def confirm(self, tx_id: str, sms_attempt: str, email_attempt: str) -> dict:
        """
        State machine:
          SMS✓ + Email✓ → RELEASE
          SMS✗ + Email✓ → BLOCK + sim_swap_alert
          SMS✓ + Email✗ → HUMAN_REVIEW
          SMS✗ + Email✗ → BLOCK + both_failed
        """
        raw = self._r.get(f"otp_pending:{tx_id}")
        if not raw:
            return {"verdict": "EXPIRED", "reason": "otp_expired_or_not_found"}

        data = json.loads(raw)
        sms_ok = sms_attempt == data["sms_otp"]
        email_ok = email_attempt == data["email_otp"]

        if sms_ok and email_ok:
            self._unfreeze_and_release(tx_id)
            self._r.delete(f"otp_pending:{tx_id}")
            return {"verdict": "RELEASE"}

        if not sms_ok and email_ok:
            self._raise_sim_swap_alert(tx_id, data)
            return {"verdict": "BLOCK", "reason": "sim_swap_alert"}

        if sms_ok and not email_ok:
            return {"verdict": "HUMAN_REVIEW", "reason": "email_otp_failed"}

        return {"verdict": "BLOCK", "reason": "both_failed"}

    def get_pending(self) -> list[dict]:
        """Return all active OTP sessions (for demo dashboard / show_pending_otps.py)."""
        keys = self._r.keys("otp_pending:*")
        result = []
        for k in keys:
            raw = self._r.get(k)
            if raw:
                d = json.loads(raw)
                result.append({
                    "tx_id": d["tx_id"],
                    "account_id": d["account_id"],
                    "phone": d["customer_phone"],
                    "email": d["customer_email"],
                    "triggered_at": d["triggered_at"],
                })
        return result

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _freeze_transaction(self, tx: TransactionEvent) -> None:
        self._r.setex(
            f"tx_hold:{tx.transaction_id}", _OTP_TTL + 60,
            json.dumps({"account_id": tx.account_id, "amount": tx.amount_npr}),
        )

    def _unfreeze_and_release(self, tx_id: str) -> None:
        self._r.delete(f"tx_hold:{tx_id}")

    def _raise_sim_swap_alert(self, tx_id: str, data: dict) -> None:
        alert = {
            "event": "sim_swap_alert",
            "tx_id": tx_id,
            "account_id": data["account_id"],
            "timestamp": time.time(),
        }
        if self._producer:
            try:
                self._producer.send("sentinel.otp_events", alert)
            except Exception:
                pass
        print(f"[SIM-SWAP ALERT] tx={tx_id} account={data['account_id']}")


def _gen_code(length: int = 6) -> str:
    return "".join(random.choices(string.digits, k=length))
