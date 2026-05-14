"""Velocity Agent — sliding-window frequency + amount anomaly via Redis."""
from __future__ import annotations

import time
from dataclasses import dataclass, field

import redis

from orchestrator.schemas import AgentScore, TransactionEvent

WINDOWS: dict[str, int] = {"2m": 120, "10m": 600, "1h": 3600, "24h": 86400}
BURST_MULTIPLIERS: dict[str, float] = {"2m": 5.0, "10m": 4.0, "1h": 3.0, "24h": 2.0}
_DEFAULT_AVG_COUNT = 2.0   # fallback when no baseline exists
_DEFAULT_AVG_AMOUNT = 3000.0


class VelocityAgent:
    def __init__(self, redis_url: str = "redis://localhost:6379/0") -> None:
        self._r = redis.Redis.from_url(redis_url, decode_responses=True)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def score(self, tx: TransactionEvent) -> AgentScore:
        t0 = time.perf_counter()
        now_ts = tx.timestamp.timestamp()
        acct = tx.account_id

        # Record this transaction in the sorted set
        vel_key = f"vel:{acct}"
        self._r.zadd(vel_key, {tx.transaction_id.hex: now_ts})
        self._r.expire(vel_key, WINDOWS["24h"])

        reason_codes: list[str] = []
        signals: list[float] = []

        # --- Frequency anomaly per window ---
        for label, seconds in WINDOWS.items():
            count = self._r.zcount(vel_key, now_ts - seconds, now_ts)
            avg_key = f"velavg:{acct}:{label}"
            raw = self._r.get(avg_key)
            avg = float(raw) if raw else _DEFAULT_AVG_COUNT
            ratio = count / max(avg, 1.0)
            threshold = BURST_MULTIPLIERS[label]
            if ratio >= threshold:
                sig = min(0.95, 0.5 + 0.45 * (ratio - threshold) / threshold)
                signals.append(sig)
                reason_codes.append(f"freq_burst_{label}:count={count}_avg={avg:.1f}")

        # --- Amount anomaly ---
        amt_key = f"amtavg:{acct}"
        raw_amt = self._r.get(amt_key)
        avg_amt = float(raw_amt) if raw_amt else _DEFAULT_AVG_AMOUNT
        amt_ratio = tx.amount_npr / max(avg_amt, 1.0)
        if amt_ratio >= 10.0:
            sig = min(0.95, 0.5 + 0.45 * (amt_ratio - 10) / 90)
            signals.append(sig)
            reason_codes.append(f"amount_spike:{amt_ratio:.0f}x")

        final_score = max(signals) if signals else 0.05
        latency_ms = (time.perf_counter() - t0) * 1000

        return AgentScore(
            agent="velocity",
            score=round(final_score, 4),
            reason_codes=reason_codes,
            latency_ms=round(latency_ms, 2),
        )
