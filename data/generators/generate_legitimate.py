"""Generate normal (legitimate) transaction patterns for each account."""
from __future__ import annotations

import math
import random
import uuid
from datetime import datetime, timedelta, timezone

import pandas as pd

NEPAL_DISTRICTS = [
    "Kathmandu", "Lalitpur", "Bhaktapur", "Pokhara", "Butwal",
    "Biratnagar", "Dharan", "Hetauda", "Chitwan", "Nepalgunj",
]

# (lat, lon) centroids per district — DATA_DESCRIPTION §3.2 (10 districts)
DISTRICT_COORDS: dict[str, tuple[float, float]] = {
    "Kathmandu": (27.7172, 85.3240),
    "Lalitpur":  (27.6644, 85.3188),
    "Bhaktapur": (27.6710, 85.4298),
    "Pokhara":   (28.2096, 83.9856),
    "Butwal":    (27.7006, 83.4483),
    "Biratnagar":(26.4525, 87.2718),
    "Dharan":    (26.8141, 87.2792),
    "Hetauda":   (27.4287, 85.0322),
    "Chitwan":   (27.6766, 84.4333),
    "Nepalgunj": (28.0500, 81.6167),
}

# Real Track-B txn_type enum (DATA_DESCRIPTION §3.1).
TX_TYPES = [
    "ESEWA_P2P", "CARD_POS", "ATM_WITHDRAWAL", "KHALTI_QR",
    "MOBILE_TOPUP", "UTILITY_BILL", "RTGS", "SWIFT_OUTWARD",
]

# Per account-type: (tx_type_weights aligned to TX_TYPES, amount_mean, amount_std,
# daily_tx_rate). Weights echo the overall §3.1 distribution, skewed by account type.
_PROFILE: dict[str, dict] = {
    "SAVINGS":    {"type_w": [0.28, 0.15, 0.15, 0.18, 0.10, 0.10, 0.01, 0.03], "mean": 3000,  "std": 2000,  "rate": 1.5},
    "CURRENT":    {"type_w": [0.22, 0.22, 0.12, 0.10, 0.06, 0.08, 0.10, 0.10], "mean": 15000, "std": 10000, "rate": 3.0},
    "SALARY":     {"type_w": [0.30, 0.18, 0.15, 0.15, 0.08, 0.10, 0.02, 0.02], "mean": 5000,  "std": 3000,  "rate": 1.2},
    "REMITTANCE": {"type_w": [0.18, 0.08, 0.08, 0.06, 0.05, 0.05, 0.10, 0.40], "mean": 25000, "std": 15000, "rate": 0.8},
}

_NOW = datetime(2026, 5, 14, tzinfo=timezone.utc)
_KNOWN_MERCHANTS = [f"MERCHANT_{i:03d}" for i in range(200)]


def _jitter(lat: float, lon: float, rng: random.Random, km: float = 5.0) -> tuple[float, float]:
    """Add small random offset (~km radius)."""
    deg = km / 111.0
    return lat + rng.uniform(-deg, deg), lon + rng.uniform(-deg, deg)


def _hour_weight(h: int) -> float:
    """Gaussian-ish peak around 11am and 5pm."""
    return math.exp(-0.5 * ((h - 11) / 3) ** 2) + 0.5 * math.exp(-0.5 * ((h - 17) / 2) ** 2)


def generate_legitimate(accounts: pd.DataFrame, seed: int = 42) -> pd.DataFrame:
    rng = random.Random(seed)
    rows: list[dict] = []

    for _, acc in accounts.iterrows():
        profile = _PROFILE[acc["account_type"]]
        district = acc["home_district"]
        lat, lon = DISTRICT_COORDS.get(district, (27.7172, 85.3240))
        age_days = int(acc["account_age_days"])
        n_tx = max(1, int(rng.gauss(profile["rate"] * min(age_days, 365), 5)))
        n_tx = min(n_tx, 80)

        # Build a known device set (1-3 devices)
        n_devices = rng.randint(1, 3)
        devices = [f"device_{acc['account_id']}_{d}" for d in range(n_devices)]

        for _ in range(n_tx):
            # Pick a random day within account lifetime
            day_offset = rng.randint(0, min(age_days - 1, 364))
            # Pick hour weighted toward business hours
            hours = list(range(24))
            weights = [_hour_weight(h) for h in hours]
            hour = rng.choices(hours, weights=weights)[0]
            ts = _NOW - timedelta(days=day_offset, hours=rng.randint(0, 23)) + timedelta(hours=hour - 12)

            amount = max(100.0, rng.gauss(profile["mean"], profile["std"]))
            tx_type = rng.choices(TX_TYPES, weights=profile["type_w"])[0]
            jlat, jlon = _jitter(lat, lon, rng)

            rows.append({
                "transaction_id": str(uuid.uuid4()),
                "account_id": acc["account_id"],
                "timestamp": ts.isoformat(),
                "amount_npr": round(amount, 2),
                "currency": "NPR",
                "transaction_type": tx_type,
                "counterparty_id": rng.choice(_KNOWN_MERCHANTS),
                "counterparty_name": None,
                "device_id": rng.choice(devices),
                "ip_address": f"27.{rng.randint(0,255)}.{rng.randint(0,255)}.{rng.randint(1,254)}",
                "geo_lat": round(jlat, 6),
                "geo_lon": round(jlon, 6),
                "geo_city": district,
                "geo_district": district,
                "account_age_days": age_days,
                "account_home_district": district,
                "account_type": acc["account_type"],
                "is_fraud": False,
                "fraud_type": None,
            })

    return pd.DataFrame(rows)
