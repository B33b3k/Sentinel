"""Load test — POST /score at target TPS, measure latency."""
from __future__ import annotations

import random
import uuid
from datetime import datetime, timezone

from locust import HttpUser, between, task

_DISTRICTS = ["Kathmandu", "Lalitpur", "Pokhara", "Dharan", "Biratnagar"]
_TX_TYPES = ["P2P", "QR_ESEWA", "SWIFT_REMITTANCE", "ATM_POS"]
_ACCT_TYPES = ["SAVINGS", "CURRENT", "SALARY", "REMITTANCE"]


def _random_tx() -> dict:
    district = random.choice(_DISTRICTS)
    return {
        "transaction_id": str(uuid.uuid4()),
        "account_id": f"ACC_{random.randint(1, 4999):05d}",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "amount_npr": round(random.lognormvariate(8, 1.5), 2),
        "currency": "NPR",
        "transaction_type": random.choice(_TX_TYPES),
        "counterparty_id": f"MERCHANT_{random.randint(1, 200):03d}",
        "counterparty_name": None,
        "device_id": f"device_ACC_{random.randint(1, 4999):05d}_0",
        "ip_address": f"27.{random.randint(0,255)}.{random.randint(0,255)}.1",
        "geo_lat": round(random.uniform(26.0, 29.0), 6),
        "geo_lon": round(random.uniform(80.0, 88.0), 6),
        "geo_city": district,
        "geo_district": district,
        "account_age_days": random.randint(1, 3650),
        "account_home_district": district,
        "account_type": random.choice(_ACCT_TYPES),
    }


class SentinelUser(HttpUser):
    wait_time = between(0.001, 0.01)  # ~100-1000 RPS per user

    @task(10)
    def score_random(self):
        self.client.post("/score", json=_random_tx(), name="/score")

    @task(1)
    def health(self):
        self.client.get("/health", name="/health")

    @task(1)
    def stats(self):
        self.client.get("/stats", name="/stats")
