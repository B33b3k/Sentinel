"""Geo Agent — new-device, geo-velocity, IP-reputation, SIM-recency signals."""
from __future__ import annotations

import json
import time

import redis
from geopy.distance import geodesic

from orchestrator.schemas import AgentScore, TransactionEvent

# Known VPN/proxy CIDR prefixes (first two octets)
_VPN_PREFIXES = {"185.220", "104.244", "198.96", "103.69", "45.142", "23.129"}

# Speed threshold km/h above which geo-velocity is impossible
_IMPOSSIBLE_KMH = 800.0


class GeoAgent:
    def __init__(self, redis_url: str = "redis://localhost:6379/0") -> None:
        self._r = redis.Redis.from_url(redis_url, decode_responses=True)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def score(self, tx: TransactionEvent) -> AgentScore:
        t0 = time.perf_counter()
        acct = tx.account_id
        hist = self._load_history(acct)

        reason_codes: list[str] = []
        signals: list[float] = []

        # 1. New device
        known_devices: set[str] = set(hist.get("devices", []))
        if tx.device_id not in known_devices:
            age = tx.account_age_days
            device_score = 0.50 if age < 30 else 0.65 if age < 180 else 0.80
            signals.append(device_score)
            reason_codes.append("new_device")

        # 2. Geo-velocity impossibility
        last_loc = hist.get("last_location")
        last_ts = hist.get("last_timestamp")
        if last_loc and last_ts:
            dist_km = geodesic(
                (last_loc["lat"], last_loc["lon"]),
                (tx.geo_lat, tx.geo_lon),
            ).km
            elapsed_h = (tx.timestamp.timestamp() - last_ts) / 3600.0
            if elapsed_h > 0:
                speed_kmh = dist_km / elapsed_h
                if speed_kmh > _IMPOSSIBLE_KMH:
                    signals.append(0.95)
                    reason_codes.append(f"geo_velocity_impossible:{speed_kmh:.0f}kmh")

        # 3. IP reputation (VPN/proxy)
        prefix = ".".join(tx.ip_address.split(".")[:2])
        if prefix in _VPN_PREFIXES:
            signals.append(min(1.0, (max(signals) if signals else 0.0) + 0.15))
            reason_codes.append("vpn_or_proxy")

        # 4. SIM recency (mocked via Redis TTL key)
        if self._r.exists(f"sim_changed:{acct}"):
            signals.append(0.92)
            reason_codes.append("sim_changed_recently")

        final_score = max(signals) if signals else 0.05

        # Update history
        self._update_history(acct, tx, known_devices)

        latency_ms = (time.perf_counter() - t0) * 1000
        return AgentScore(
            agent="geo",
            score=round(final_score, 4),
            reason_codes=reason_codes,
            latency_ms=round(latency_ms, 2),
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _load_history(self, acct: str) -> dict:
        raw = self._r.get(f"geo:hist:{acct}")
        return json.loads(raw) if raw else {}

    def _update_history(self, acct: str, tx: TransactionEvent, known_devices: set[str]) -> None:
        known_devices.add(tx.device_id)
        hist = {
            "devices": list(known_devices)[-50:],  # cap at 50
            "last_location": {"lat": tx.geo_lat, "lon": tx.geo_lon},
            "last_timestamp": tx.timestamp.timestamp(),
        }
        self._r.set(f"geo:hist:{acct}", json.dumps(hist))
