"""Seed geo:hist:{account_id} in Redis from transactions.parquet."""
from __future__ import annotations

import json
import pathlib

import pandas as pd
import redis

SEEDS_DIR = pathlib.Path("data/seeds")


def seed_geo_history(redis_url: str = "redis://localhost:6379/0") -> None:
    r = redis.Redis.from_url(redis_url, decode_responses=True)

    txs = pd.read_parquet(SEEDS_DIR / "transactions.parquet")
    txs["timestamp"] = pd.to_datetime(txs["timestamp"], utc=True)
    txs = txs.sort_values("timestamp")

    # Build per-account history: known devices + last location/timestamp
    grouped = txs.groupby("account_id")
    pipe = r.pipeline(transaction=False)
    count = 0
    for acct, grp in grouped:
        devices = list(grp["device_id"].unique())
        last = grp.iloc[-1]
        hist = {
            "devices": devices[-50:],
            "last_location": {"lat": float(last["geo_lat"]), "lon": float(last["geo_lon"])},
            "last_timestamp": last["timestamp"].timestamp(),
        }
        pipe.set(f"geo:hist:{acct}", json.dumps(hist))
        count += 1
        if count % 500 == 0:
            pipe.execute()
            pipe = r.pipeline(transaction=False)

    pipe.execute()
    print(f"Seeded geo history for {count} accounts")


if __name__ == "__main__":
    seed_geo_history()
