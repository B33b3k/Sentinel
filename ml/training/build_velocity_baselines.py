"""Compute per-account velocity baselines from seed data and load into Redis."""
from __future__ import annotations

import pathlib

import pandas as pd
import redis

from data.loader import load_transactions

WINDOWS = {"2m": 120, "10m": 600, "1h": 3600, "24h": 86400}


def build_baselines(redis_url: str = "redis://localhost:6379/0") -> None:
    r = redis.Redis.from_url(redis_url, decode_responses=True)

    txs = load_transactions()
    txs["timestamp"] = pd.to_datetime(txs["timestamp"], utc=True)
    txs = txs.sort_values("timestamp")

    # Per-account average amount
    amt_avg = txs.groupby("account_id")["amount_npr"].mean()
    pipe = r.pipeline(transaction=False)
    for acct, avg in amt_avg.items():
        pipe.set(f"amtavg:{acct}", round(avg, 2))
    pipe.execute()
    print(f"Set amtavg for {len(amt_avg)} accounts")

    # Per-account per-window average daily count
    # Approximate: count tx in each window-sized bucket, average across days
    for label, seconds in WINDOWS.items():
        bucket_size = pd.Timedelta(seconds=seconds)
        counts = (
            txs.groupby(["account_id", pd.Grouper(key="timestamp", freq=bucket_size)])
            .size()
            .groupby(level="account_id")
            .mean()
        )
        pipe = r.pipeline(transaction=False)
        for acct, avg in counts.items():
            pipe.set(f"velavg:{acct}:{label}", round(avg, 4))
        pipe.execute()
        print(f"Set velavg:{label} for {len(counts)} accounts")

    print("Velocity baselines loaded.")


if __name__ == "__main__":
    build_baselines()
