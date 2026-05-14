"""Generate 5,000 synthetic accounts. Sita is hardcoded as ACC_SITA_001."""
from __future__ import annotations

import random
import uuid
from datetime import datetime, timedelta, timezone

import pandas as pd

NEPAL_DISTRICTS = [
    "Kathmandu", "Lalitpur", "Bhaktapur", "Pokhara", "Dharan",
    "Biratnagar", "Birgunj", "Butwal", "Nepalgunj", "Dhangadhi",
]
URBAN_DISTRICTS = {"Kathmandu", "Lalitpur", "Bhaktapur", "Pokhara"}
ACCOUNT_TYPES = ["SAVINGS", "CURRENT", "SALARY", "REMITTANCE"]
TYPE_WEIGHTS = [0.55, 0.15, 0.20, 0.10]

_NOW = datetime(2026, 5, 14, tzinfo=timezone.utc)


def _random_account(account_id: str, rng: random.Random) -> dict:
    account_type = rng.choices(ACCOUNT_TYPES, weights=TYPE_WEIGHTS)[0]
    district = rng.choice(NEPAL_DISTRICTS)
    age_days = rng.randint(1, 3650)
    created_at = _NOW - timedelta(days=age_days)
    return {
        "account_id": account_id,
        "account_type": account_type,
        "home_district": district,
        "account_age_days": age_days,
        "created_at": created_at.isoformat(),
        "phone": f"+977-98{rng.randint(10000000, 99999999)}",
        "email": f"{account_id.lower()}@example.com",
    }


def generate_accounts(n: int = 5000, seed: int = 42) -> pd.DataFrame:
    rng = random.Random(seed)
    accounts = []

    # Hardcoded Sita account (concept paper scenario)
    accounts.append({
        "account_id": "ACC_SITA_001",
        "account_type": "SAVINGS",
        "home_district": "Kathmandu",
        "account_age_days": 720,
        "created_at": (_NOW - timedelta(days=720)).isoformat(),
        "phone": "+977-9841234567",
        "email": "sita@example.com",
    })

    for i in range(1, n):
        accounts.append(_random_account(f"ACC_{i:05d}", rng))

    return pd.DataFrame(accounts)


if __name__ == "__main__":
    df = generate_accounts()
    print(df["account_type"].value_counts())
    print(df["home_district"].value_counts())
