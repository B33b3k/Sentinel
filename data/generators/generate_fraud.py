"""Generate the 6 fraud taxonomy patterns from concept paper Section 2.2."""
from __future__ import annotations

import random
import uuid
from datetime import datetime, timedelta, timezone

import pandas as pd

_NOW = datetime(2026, 5, 14, tzinfo=timezone.utc)

DISTRICT_COORDS: dict[str, tuple[float, float]] = {
    "Kathmandu": (27.7172, 85.3240),
    "Lalitpur":  (27.6644, 85.3188),
    "Bhaktapur": (27.6710, 85.4298),
    "Pokhara":   (28.2096, 83.9856),
    "Dharan":    (26.8141, 87.2792),
    "Biratnagar":(26.4525, 87.2718),
    "Birgunj":   (27.0104, 84.8777),
    "Butwal":    (27.7006, 83.4483),
    "Nepalgunj": (28.0500, 81.6167),
    "Dhangadhi": (28.6833, 80.6000),
}
NEPAL_DISTRICTS = list(DISTRICT_COORDS.keys())
_VPN_IPS = ["185.220.101.1", "104.244.72.1", "198.96.155.1"]


def _tx(account_id: str, ts: datetime, amount: float, tx_type: str,
        device_id: str, ip: str, district: str, home_district: str,
        age_days: int, account_type: str, fraud_type: str,
        counterparty_id: str | None = None) -> dict:
    lat, lon = DISTRICT_COORDS.get(district, (27.7172, 85.3240))
    return {
        "transaction_id": str(uuid.uuid4()),
        "account_id": account_id,
        "timestamp": ts.isoformat(),
        "amount_npr": round(amount, 2),
        "currency": "NPR",
        "transaction_type": tx_type,
        "counterparty_id": counterparty_id or f"MERCHANT_UNKNOWN_{random.randint(1,99)}",
        "counterparty_name": None,
        "device_id": device_id,
        "ip_address": ip,
        "geo_lat": round(lat, 6),
        "geo_lon": round(lon, 6),
        "geo_city": district,
        "geo_district": district,
        "account_age_days": age_days,
        "account_home_district": home_district,
        "account_type": account_type,
        "is_fraud": True,
        "fraud_type": fraud_type,
    }


def _sim_swap_esewa(accounts: pd.DataFrame, rng: random.Random, n: int) -> list[dict]:
    """2am, unknown merchant, new device, distant district, NPR 50K-100K."""
    rows = []
    pool = accounts[accounts["account_age_days"] > 90].sample(n=min(n, len(accounts)), random_state=rng.randint(0, 9999))
    for _, acc in pool.iterrows():
        distant = rng.choice([d for d in NEPAL_DISTRICTS if d != acc["home_district"]])
        ts = _NOW.replace(hour=2, minute=rng.randint(0, 59)) - timedelta(days=rng.randint(0, 30))
        rows.append(_tx(
            acc["account_id"], ts,
            rng.uniform(50000, 100000), "QR_ESEWA",
            f"device_unknown_{uuid.uuid4().hex[:8]}",
            rng.choice(_VPN_IPS), distant, acc["home_district"],
            int(acc["account_age_days"]), acc["account_type"], "sim_swap_esewa",
        ))
    return rows


def _velocity_burst(accounts: pd.DataFrame, rng: random.Random, n: int) -> list[dict]:
    """10+ tx in 90 seconds, small amounts."""
    rows = []
    pool = accounts.sample(n=min(n, len(accounts)), random_state=rng.randint(0, 9999))
    for _, acc in pool.iterrows():
        base_ts = _NOW - timedelta(days=rng.randint(0, 30), hours=rng.randint(0, 23))
        device = f"device_{acc['account_id']}_0"
        ip = f"27.{rng.randint(0,255)}.{rng.randint(0,255)}.1"
        district = acc["home_district"]
        for i in range(rng.randint(10, 15)):
            ts = base_ts + timedelta(seconds=i * rng.randint(3, 8))
            rows.append(_tx(
                acc["account_id"], ts,
                rng.uniform(100, 500), "P2P",
                device, ip, district, district,
                int(acc["account_age_days"]), acc["account_type"], "velocity_burst",
                counterparty_id=f"ACC_{rng.randint(1,4999):05d}",
            ))
    return rows


def _remittance_mule(accounts: pd.DataFrame, rng: random.Random, n: int) -> list[dict]:
    """3+ sources → 1 mule → 1 destination within 2h."""
    rows = []
    mule_pool = accounts[accounts["account_type"] == "REMITTANCE"]
    if len(mule_pool) < 1:
        mule_pool = accounts
    for _ in range(n):
        mule = mule_pool.sample(1, random_state=rng.randint(0, 9999)).iloc[0]
        dest_id = f"ACC_{rng.randint(1,4999):05d}"
        base_ts = _NOW - timedelta(days=rng.randint(0, 30), hours=rng.randint(0, 20))
        n_sources = rng.randint(3, 5)
        for j in range(n_sources):
            src_id = f"ACC_{rng.randint(1,4999):05d}"
            ts = base_ts + timedelta(minutes=j * rng.randint(5, 15))
            rows.append(_tx(
                src_id, ts, rng.uniform(15000, 30000), "SWIFT_REMITTANCE",
                f"device_{src_id}_0", f"27.{rng.randint(0,255)}.1.1",
                mule["home_district"], mule["home_district"],
                int(mule["account_age_days"]), "REMITTANCE", "remittance_mule",
                counterparty_id=mule["account_id"],
            ))
        # Mule forwards out
        rows.append(_tx(
            mule["account_id"], base_ts + timedelta(minutes=90),
            rng.uniform(50000, 90000), "SWIFT_REMITTANCE",
            f"device_{mule['account_id']}_0", f"27.{rng.randint(0,255)}.1.1",
            mule["home_district"], mule["home_district"],
            int(mule["account_age_days"]), "REMITTANCE", "remittance_mule",
            counterparty_id=dest_id,
        ))
    return rows


def _new_device_takeover(accounts: pd.DataFrame, rng: random.Random, n: int) -> list[dict]:
    """Unknown device, first transaction high-value."""
    rows = []
    pool = accounts[accounts["account_age_days"] > 30].sample(n=min(n, len(accounts)), random_state=rng.randint(0, 9999))
    for _, acc in pool.iterrows():
        ts = _NOW - timedelta(days=rng.randint(0, 30), hours=rng.randint(0, 23))
        rows.append(_tx(
            acc["account_id"], ts,
            rng.uniform(40000, 120000), rng.choice(["P2P", "QR_ESEWA"]),
            f"device_takeover_{uuid.uuid4().hex[:8]}",
            f"103.{rng.randint(0,255)}.{rng.randint(0,255)}.1",
            rng.choice(NEPAL_DISTRICTS), acc["home_district"],
            int(acc["account_age_days"]), acc["account_type"], "new_device_takeover",
        ))
    return rows


def _geo_impossible(accounts: pd.DataFrame, rng: random.Random, n: int) -> list[dict]:
    """Two tx 800+ km apart within 1h (Kathmandu ↔ Dhangadhi ~800km)."""
    far_pairs = [("Kathmandu", "Dhangadhi"), ("Pokhara", "Biratnagar"), ("Kathmandu", "Nepalgunj")]
    rows = []
    pool = accounts[accounts["account_age_days"] > 30].sample(n=min(n, len(accounts)), random_state=rng.randint(0, 9999))
    for _, acc in pool.iterrows():
        d1, d2 = rng.choice(far_pairs)
        base_ts = _NOW - timedelta(days=rng.randint(0, 30), hours=rng.randint(1, 22))
        device = f"device_{acc['account_id']}_0"
        ip = f"27.{rng.randint(0,255)}.1.1"
        rows.append(_tx(
            acc["account_id"], base_ts, rng.uniform(1000, 5000), "ATM_POS",
            device, ip, d1, acc["home_district"],
            int(acc["account_age_days"]), acc["account_type"], "geo_impossible",
        ))
        rows.append(_tx(
            acc["account_id"], base_ts + timedelta(minutes=rng.randint(20, 55)),
            rng.uniform(30000, 80000), "QR_ESEWA",
            f"device_unknown_{uuid.uuid4().hex[:8]}", rng.choice(_VPN_IPS),
            d2, acc["home_district"],
            int(acc["account_age_days"]), acc["account_type"], "geo_impossible",
        ))
    return rows


def _synthetic_identity(accounts: pd.DataFrame, rng: random.Random, n: int) -> list[dict]:
    """New account (<= 3 days old), no prior history, immediate large outbound."""
    rows = []
    pool = accounts[accounts["account_age_days"] <= 3]
    if len(pool) < 1:
        # Create synthetic new accounts not in the main pool
        for i in range(n):
            acc_id = f"ACC_SYNTH_{i:04d}"
            district = rng.choice(NEPAL_DISTRICTS)
            ts = _NOW - timedelta(days=rng.randint(0, 2), hours=rng.randint(0, 23))
            rows.append(_tx(
                acc_id, ts, rng.uniform(50000, 150000), "SWIFT_REMITTANCE",
                f"device_new_{uuid.uuid4().hex[:8]}",
                f"103.{rng.randint(0,255)}.1.1",
                district, district, rng.randint(0, 3), "SAVINGS", "synthetic_identity",
            ))
        return rows
    pool = pool.sample(n=min(n, len(pool)), random_state=rng.randint(0, 9999))
    for _, acc in pool.iterrows():
        ts = _NOW - timedelta(days=rng.randint(0, int(acc["account_age_days"])), hours=rng.randint(0, 23))
        rows.append(_tx(
            acc["account_id"], ts, rng.uniform(50000, 150000), "SWIFT_REMITTANCE",
            f"device_new_{uuid.uuid4().hex[:8]}",
            f"103.{rng.randint(0,255)}.1.1",
            acc["home_district"], acc["home_district"],
            int(acc["account_age_days"]), acc["account_type"], "synthetic_identity",
        ))
    return rows


def generate_fraud(accounts: pd.DataFrame, target_fraud_rate: float = 0.02,
                   total_legit: int = 95000, seed: int = 42) -> pd.DataFrame:
    rng = random.Random(seed)
    target_n = int(total_legit * target_fraud_rate / (1 - target_fraud_rate))
    per_type = max(1, target_n // 6)

    rows: list[dict] = []
    rows += _sim_swap_esewa(accounts, rng, per_type)
    rows += _velocity_burst(accounts, rng, per_type)
    rows += _remittance_mule(accounts, rng, per_type)
    rows += _new_device_takeover(accounts, rng, per_type)
    rows += _geo_impossible(accounts, rng, per_type)
    rows += _synthetic_identity(accounts, rng, per_type)

    return pd.DataFrame(rows)
