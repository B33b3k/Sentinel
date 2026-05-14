"""Stream transactions.parquet to Kafka at configurable TPS."""
from __future__ import annotations

import argparse
import json
import pathlib
import time

import pandas as pd

SEEDS_DIR = pathlib.Path("data/seeds")
TOPIC = "sentinel.transactions"


def main(tps: int = 1000, loop: bool = False) -> None:
    try:
        from kafka import KafkaProducer
        producer = KafkaProducer(
            bootstrap_servers="localhost:9092",
            value_serializer=lambda v: json.dumps(v).encode(),
        )
        kafka_enabled = True
    except Exception as e:
        print(f"[replay] Kafka unavailable ({e}), dry-run mode")
        kafka_enabled = False

    txs_path = SEEDS_DIR / "transactions.parquet"
    if not txs_path.exists():
        raise FileNotFoundError(f"{txs_path} not found — run generate.py first")

    df = pd.read_parquet(txs_path)
    interval = 1.0 / tps
    total = 0

    while True:
        for _, row in df.iterrows():
            record = row.to_dict()
            # Ensure JSON-serialisable types
            for k, v in record.items():
                if hasattr(v, "isoformat"):
                    record[k] = v.isoformat()
                elif hasattr(v, "item"):  # numpy scalar
                    record[k] = v.item()

            if kafka_enabled:
                producer.send(TOPIC, record)
            total += 1
            time.sleep(interval)

            if total % 1000 == 0:
                print(f"[replay] sent {total} transactions")

        if not loop:
            break

    if kafka_enabled:
        producer.flush()
    print(f"[replay] done — {total} transactions sent")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--tps", type=int, default=1000)
    parser.add_argument("--loop", action="store_true")
    args = parser.parse_args()
    main(tps=args.tps, loop=args.loop)
